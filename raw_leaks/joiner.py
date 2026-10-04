"""Invite join engine for RAW LEAKS - Automation Toolkit.

The login, gateway and join flow is extracted from the control panel's
``bot_manager`` module, then paced by :mod:`raw_leaks.safety`:

* accounts log in with ``discord.py-self`` and a jittered stagger
* joins run **sequentially** - never as a burst of parallel requests
* Discord's own bucket limiter absorbs normal 429s; long or Cloudflare blocks
  stop the run instead of hammering the endpoint
* per-account daily budget, per-account gap and a global cooldown keep the
  whole session inside conservative limits
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Iterable, Optional

import discord

from . import logger
from .captcha import discord_captcha_handler
from .config import Account
from .invites import extract_invite_code, invite_url
from .safety import SafetyGuard, SafetyPolicy

log = logger.Logger("joiner")

ALREADY_MEMBER = "already"
RESTRICTED = "restricted"

_RESTRICTED_MARKERS = (
    "verify your account",
    "verify your email",
    "must verify",
    "your account has been",
    "phone number",
    "locked",
    "disabled",
    "checkpoint",
    "unusual",
    "self-bot",
    "selfbot",
    "violat",
)


class JoinerClient(discord.Client):
    """One Discord user account used for joining."""

    def __init__(self, label: str, proxy: str = "", **options: Any) -> None:
        if proxy:
            options["proxy"] = proxy
        super().__init__(**options)
        self.label = label
        self.proxy = proxy
        self.ready_event = asyncio.Event()
        self.quarantined = False

    async def on_ready(self) -> None:
        self.ready_event.set()


def _retry_after(err: discord.HTTPException) -> float:
    """Seconds Discord asked us to wait, when it is exposed on the response."""
    response = getattr(err, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0.0
    try:
        return float(headers.get("Retry-After") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_already_member(text: str) -> bool:
    lowered = (text or "").lower()
    return "already a guild member" in lowered or "already a member" in lowered


def _is_restricted(text: str, status: int) -> bool:
    """Account-level blocks: never retry these, they only add pressure."""
    if status in (401, 403):
        lowered = (text or "").lower()
        if not lowered:
            return True
        return any(marker in lowered for marker in _RESTRICTED_MARKERS)
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _RESTRICTED_MARKERS)


class Joiner:
    """Logs accounts in and joins a single invite with all of them."""

    def __init__(self) -> None:
        self.clients: list[JoinerClient] = []

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    async def login(
        self,
        accounts: Iterable[Account],
        timeout: float = 60.0,
        policy: Optional[SafetyPolicy] = None,
    ) -> tuple[list[JoinerClient], list[tuple[str, str]]]:
        """Log every account in and wait for READY.

        Logins themselves are staggered - a burst of fresh sessions from one
        IP is exactly what Discord's anomaly checks look for.

        Returns ``(online, failed)`` where ``failed`` holds ``(label, reason)``.
        """
        policy = policy or SafetyPolicy()
        started: list[tuple[JoinerClient, asyncio.Task]] = []
        failed: list[tuple[str, str]] = []
        accounts = list(accounts)

        for index, account in enumerate(accounts):
            if index and policy.enabled and policy.login_stagger_ms:
                spread = policy.login_stagger_ms // 2
                await asyncio.sleep(
                    (policy.login_stagger_ms + random.randint(0, max(0, spread))) / 1000
                )

            client = JoinerClient(
                account.label,
                proxy=account.proxy,
                captcha_handler=discord_captcha_handler,
                chunk_guilds_at_startup=False,
                max_ratelimit_timeout=(
                    policy.max_ratelimit_timeout if policy.enabled else None
                ),
            )
            try:
                await client.login(account.token)
            except Exception as err:
                log.error("%s login failed: %s", account.label, err)
                failed.append((account.label, str(err)))
                continue

            task = asyncio.create_task(
                client.connect(reconnect=True),
                name=f"discord-connect-{account.label}",
            )
            started.append((client, task))
            self.clients.append(client)

        if started:
            waits = [client.ready_event.wait() for client, _ in started]
            try:
                await asyncio.wait_for(asyncio.gather(*waits), timeout=timeout)
            except asyncio.TimeoutError:
                pass

        online: list[JoinerClient] = []
        for client, task in started:
            if client.ready_event.is_set():
                user = getattr(client, "user", None)
                log.ok("%s online as %s", client.label, user)
                online.append(client)
            else:
                log.error("%s timed out waiting for the READY event", client.label)
                failed.append((client.label, "READY timeout"))
                await self._close_client(client, task)
                if client in self.clients:
                    self.clients.remove(client)

        if failed:
            log.warn("%d account(s) could not connect", len(failed))
        return online, failed

    # ------------------------------------------------------------------
    # Invite verification
    # ------------------------------------------------------------------
    @staticmethod
    async def _verify_invite(client: JoinerClient, code: str) -> tuple[str, str]:
        """Resolve the invite first so a dead link costs one request, not N."""
        try:
            data = await client.http.get_invite(
                code, with_counts=False, with_permissions=False
            )
        except discord.NotFound:
            return "invalid", "not found or expired"
        except discord.Forbidden:
            return "invalid", "blocked"
        except discord.HTTPException as err:
            return "unknown", getattr(err, "text", None) or str(err)
        except Exception as err:  # network hiccup - do not block the run
            return "unknown", str(err)

        if not isinstance(data, dict) or not data.get("code"):
            return "invalid", "not found or expired"
        guild = data.get("guild") or {}
        channel = data.get("channel") or {}
        name = guild.get("name") or channel.get("name") or code
        return "ok", str(name)

    # ------------------------------------------------------------------
    # Joining
    # ------------------------------------------------------------------
    async def join_server(
        self,
        invite: str,
        guard: SafetyGuard,
        stagger_ms: int = 1500,
        jitter_ms: int = 1000,
        clients: Optional[list[JoinerClient]] = None,
    ) -> dict[str, Any]:
        """Join a single invite with every online, usable account.

        Joins are issued one at a time with a randomised delay so the interval
        never becomes a recognisable fixed-rate pattern.
        """
        code = extract_invite_code(invite)
        policy = guard.policy
        targets = [
            client
            for client in (self.clients if clients is None else clients)
            if not client.quarantined
        ]
        if not targets:
            raise RuntimeError("No usable accounts online - check tokens.txt")

        counts: dict[str, Any] = {
            "joined": 0,
            "already": 0,
            "failed": 0,
            "skipped": 0,
            "ratelimit": 0,
            "restricted": 0,
            "aborted": False,
        }
        results: list[tuple[str, str]] = []

        if policy.verify_invite:
            status, detail = await self._verify_invite(targets[0], code)
            if status == "invalid":
                log.error("Invite %s is not usable: %s", code, detail)
                counts["code"] = code
                counts["aborted"] = True
                counts["total"] = len(targets)
                counts["results"] = results
                return counts
            if status == "ok":
                log.ok("Invite verified: %s", detail)
            else:
                log.warn("Could not verify the invite (%s) - continuing", detail)

        order = list(targets)
        random.shuffle(order)
        log.info(
            "Joining invite %s with %d account(s), stagger %dms (+%dms jitter)",
            code, len(order), stagger_ms, max(0, jitter_ms),
        )

        for position, client in enumerate(order):
            pause = guard.cooldown_remaining()
            if pause > 0:
                log.warn("Rate limit cooldown - holding every account for %.0fs", pause)
                await asyncio.sleep(pause)

            if guard.should_cooldown():
                seconds = guard.register_cooldown()
                log.warn("Repeated failures - pausing the whole run for %.0fs", seconds)
                await asyncio.sleep(seconds)

            if guard.capacity(client.label) <= 0:
                log.warn("%s skipped - daily join limit of %d reached",
                         client.label, policy.max_joins_per_account)
                counts["skipped"] += 1
                results.append((client.label, "skipped"))
                continue

            gap = guard.gap_remaining(client.label)
            if gap > 0:
                log.info("%s waiting %.0fs before its next join", client.label, gap)
                await asyncio.sleep(gap)

            if position:
                delay = stagger_ms + random.randint(0, max(0, jitter_ms))
                if delay:
                    await asyncio.sleep(delay / 1000)

            outcome = await self._join_one(client, code, guard)
            results.append((client.label, outcome))
            if outcome == "abort":
                counts["aborted"] = True
                break
            counts[outcome] = counts.get(outcome, 0) + 1

        counts["code"] = code
        counts["total"] = len(order)
        counts["results"] = results
        log.info(
            "Join finished: %d joined, %d already, %d failed, %d skipped",
            counts["joined"], counts["already"], counts["failed"], counts["skipped"],
        )
        return counts

    async def _join_one(self, client: JoinerClient, code: str, guard: SafetyGuard) -> str:
        policy = guard.policy
        attempts = max(1, policy.ratelimit_retries + 1)

        for attempt in range(attempts):
            try:
                # Captchas raised here are solved through ``captcha_handler``.
                invite = await client.accept_invite(invite_url(code))
            except discord.RateLimited as err:
                guard.record_attempt(client.label)
                guard.record_failure()
                if getattr(err, "cloudflare", False):
                    log.error(
                        "%s hit a Cloudflare rate limit (%.0fs) - stopping the run "
                        "instead of pushing the accounts further",
                        client.label, float(err.retry_after or 0),
                    )
                    return "abort"
                wait = min(float(err.retry_after or 60.0), 300.0)
                log.warn("%s rate limited - backing off %.0fs (%d/%d)",
                         client.label, wait, attempt + 1, attempts)
                await asyncio.sleep(wait)
                continue
            except discord.HTTPException as err:
                status = getattr(err, "status", 0)
                text = getattr(err, "text", "") or ""

                if status == 429:
                    guard.record_attempt(client.label)
                    guard.record_failure()
                    wait = _retry_after(err) or min(60 * (attempt + 1), 300.0)
                    log.warn("%s rate limited - backing off %.0fs (%d/%d)",
                             client.label, wait, attempt + 1, attempts)
                    await asyncio.sleep(wait)
                    continue

                if _is_already_member(text):
                    guard.record_attempt(client.label)
                    guard.record_success()
                    log.info("%s is already in this server", client.label)
                    return ALREADY_MEMBER

                if _is_restricted(text, status):
                    client.quarantined = True
                    guard.record_failure()
                    log.warn(
                        "%s is restricted (%s) - removed from this session, "
                        "do not push it further",
                        client.label, text or f"HTTP {status}",
                    )
                    return RESTRICTED

                if status == 404:
                    guard.record_failure()
                    log.error("Invite %s disappeared during the run", code)
                    return "abort"

                guard.record_failure()
                log.error("%s failed to join %s: %s", client.label, code,
                          text or f"HTTP {status}")
                return "failed"
            except asyncio.CancelledError:
                raise
            except Exception as err:
                guard.record_failure()
                log.error("%s failed to join %s: %s", client.label, code, err)
                return "failed"

            guard.record_join(client.label)
            guild = getattr(invite, "guild", None)
            guild_name = getattr(guild, "name", None)
            left = guard.capacity(client.label)
            budget = left if left < 10 ** 9 else -1
            log.ok("%s joined %s%s", client.label, guild_name or code,
                   "" if budget < 0 else f" ({budget} joins left today)")
            return "joined"

        guard.record_attempt(client.label)
        log.warn("%s gave up after %d rate limit retries", client.label, attempts)
        return "ratelimit"

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    @staticmethod
    async def _close_client(client: discord.Client, task: Optional[asyncio.Task]) -> None:
        try:
            await client.close()
        except Exception:
            pass
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def close(self) -> None:
        """Disconnect every account."""
        clients, self.clients = self.clients, []
        for client in clients:
            try:
                await client.close()
            except Exception:
                pass
        await asyncio.sleep(0.1)
