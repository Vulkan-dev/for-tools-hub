"""Invite join engine for RAW LEAKS - Automation Toolkit.

The login, gateway and join flow is extracted from the control panel's
``bot_manager`` module: accounts are logged in with ``discord.py-self``,
CAPTCHAs are routed through the NopeCHA hook and every join is fired
``stagger_ms`` apart.
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable, Optional

import discord

from . import logger
from .captcha import discord_captcha_handler
from .invites import extract_invite_code, invite_url

log = logger.Logger("joiner")


class JoinerClient(discord.Client):
    """One Discord user account used for joining."""

    def __init__(self, label: str, **options: Any) -> None:
        super().__init__(**options)
        self.label = label
        self.ready_event = asyncio.Event()

    async def on_ready(self) -> None:
        self.ready_event.set()


class Joiner:
    """Logs accounts in and joins a single invite with all of them."""

    def __init__(self) -> None:
        self.clients: list[JoinerClient] = []

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    async def login(
        self,
        accounts: Iterable[tuple[str, str]],
        timeout: float = 60.0,
    ) -> tuple[list[JoinerClient], list[tuple[str, str]]]:
        """Log every account in and wait for READY.

        Returns ``(online, failed)`` where ``failed`` holds ``(label, reason)``.
        """
        started: list[tuple[JoinerClient, asyncio.Task]] = []
        failed: list[tuple[str, str]] = []

        for index, (token, name) in enumerate(accounts, start=1):
            label = name or f"#{index}"
            client = JoinerClient(
                label,
                captcha_handler=discord_captcha_handler,
                chunk_guilds_at_startup=False,
            )
            try:
                await client.login(token)
            except Exception as err:
                log.error("%s login failed: %s", label, err)
                failed.append((label, str(err)))
                continue

            task = asyncio.create_task(
                client.connect(reconnect=True), name=f"discord-connect-{label}"
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
    # Joining
    # ------------------------------------------------------------------
    async def join_server(
        self,
        invite: str,
        stagger_ms: int = 10,
        clients: Optional[list[JoinerClient]] = None,
    ) -> dict[str, Any]:
        """Join a single invite with every online account.

        Each join is launched ``stagger_ms`` apart; the captcha solve time
        dominates the actual delay per account.
        """
        code = extract_invite_code(invite)
        targets = list(self.clients if clients is None else clients)
        if not targets:
            raise RuntimeError("No accounts online - check tokens.txt and config.json")

        log.info("Joining invite %s with %d account(s) (%dms apart)",
                 code, len(targets), stagger_ms)

        pending: list[tuple[JoinerClient, "asyncio.Task[dict[str, Any]]"]] = []
        for client in targets:
            pending.append((
                client,
                asyncio.create_task(self._join_invite(client, code),
                                    name=f"join-{client.label}"),
            ))
            if stagger_ms:
                await asyncio.sleep(max(0, stagger_ms) / 1000)

        results: list[dict[str, Any]] = []
        for client, task in pending:
            try:
                results.append(await task)
            except Exception as err:
                results.append({
                    "label": client.label,
                    "ok": False,
                    "error": str(err),
                })

        joined = sum(1 for item in results if item.get("ok"))
        log.info("Join finished: %d joined, %d failed",
                 joined, len(results) - joined)
        return {
            "code": code,
            "total": len(results),
            "joined": joined,
            "failed": len(results) - joined,
            "results": results,
        }

    async def _join_invite(self, client: JoinerClient, code: str) -> dict[str, Any]:
        url = invite_url(code)
        try:
            # Captchas raised here are solved through ``captcha_handler``.
            invite = await client.accept_invite(url)
        except discord.HTTPException as err:
            detail = getattr(err, "text", None) or str(err)
            log.error("%s failed to join %s: %s", client.label, code, detail)
            return {"label": client.label, "ok": False, "error": detail}
        except Exception as err:
            log.error("%s failed to join %s: %s", client.label, code, err)
            return {"label": client.label, "ok": False, "error": str(err)}

        guild = getattr(invite, "guild", None)
        guild_name = getattr(guild, "name", None)
        log.ok("%s joined %s", client.label, guild_name or code)
        return {"label": client.label, "ok": True, "guild": guild_name}

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
