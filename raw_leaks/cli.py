"""Command line interface for RAW LEAKS - Automation Toolkit."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from . import FULL_NAME, __version__, banner, captcha, config, console, logger
from .joiner import Joiner
from .safety import SafetyGuard

STARTUP_LINES = [
    "Initializing...",
    "Loading configuration...",
    "System ready.",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="raw-leaks",
        description=f"{FULL_NAME} - join Discord servers from an invite link.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python main.py\n"
            "  python main.py --stagger 250\n"
            "  python main.py --invite https://discord.gg/example --yes\n"
        ),
    )
    parser.add_argument("-i", "--invite",
                        help="invite link (skips the interactive prompt)")
    parser.add_argument("-t", "--tokens", help="path to the token list (default: tokens.txt)")
    parser.add_argument("--stagger", type=int, help="delay between joins in milliseconds")
    parser.add_argument("--timeout", type=int, help="seconds to wait for each account to be ready")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="run once without prompts")
    parser.add_argument("--ascii", action="store_true",
                        help="force the ASCII banner (no Unicode box drawing)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    parser.add_argument("--version", action="version",
                        version=f"{FULL_NAME} {__version__}")
    return parser


def _startup() -> None:
    """Print the brand banner followed by the startup status lines."""
    banner.print_banner()
    logger.line(STARTUP_LINES[0])
    logger.line(STARTUP_LINES[1])


def _ready() -> None:
    logger.line(STARTUP_LINES[2])


def _display_path(path: Path) -> str:
    """Show project files as relative paths, external ones in full."""
    try:
        return str(path.resolve().relative_to(config.ROOT))
    except (ValueError, OSError):
        return str(path)


def _request_invite(prefill: str, interactive: bool) -> Optional[str]:
    """Ask for the invite link. Returns ``None`` when the session should stop."""
    logger.section("Invite")

    if prefill:
        logger.pair("link", prefill)
        return prefill

    if not interactive:
        logger.error("No invite link supplied - pass --invite")
        return None

    logger.note("Paste a Discord invite link")
    logger.blank()
    while True:
        try:
            raw = input(console.style("> ", console.RED))
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        raw = raw.strip()
        if raw:
            return raw
        logger.warn("Invite link is required")


def _ask_again() -> bool:
    try:
        answer = input(console.style("  Join another invite [y/N] ", console.GRAY))
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def _print_result(summary: dict, online: int) -> None:
    failed = int(summary.get("failed", 0))
    logger.section("Result")
    logger.pair("invite", str(summary.get("code", "-")))
    logger.pair("online", str(online), console.WHITE)
    logger.pair("joined", str(summary.get("joined", 0)), console.BRIGHT)
    logger.pair("already", str(summary.get("already", 0)), console.WHITE)
    logger.pair("failed", str(failed), console.RED if failed else console.WHITE)
    logger.pair("skipped", str(summary.get("skipped", 0)), console.GRAY)
    if summary.get("ratelimit"):
        logger.pair("limited", str(summary["ratelimit"]), console.RED)
    if summary.get("restricted"):
        logger.pair("restricted", str(summary["restricted"]), console.RED)
    logger.blank()


async def _run(args: argparse.Namespace) -> int:
    tokens_path = Path(args.tokens) if args.tokens else None
    cfg = config.load()
    accounts = config.load_tokens(tokens_path)
    policy = config.policy()
    guard = SafetyGuard(policy, config.state_path())
    _ready()

    logger.blank()
    logger.info(
        f"Stagger {cfg['stagger_ms']}ms (+{cfg['stagger_jitter_ms']}ms) | "
        f"ready timeout {cfg['ready_timeout_seconds']}s"
    )
    if policy.enabled:
        logger.info(f"Safety: {policy.describe()}")
    else:
        logger.warn("Safety pacing is disabled in config.json")
    if str(cfg.get("nopecha_key") or "").strip():
        try:
            await captcha.log_status()
        except Exception as err:
            logger.warn(f"CAPTCHA status check failed: {err}")
    else:
        logger.warn("No NopeCHA key set - join CAPTCHAs cannot be solved")

    logger.section("Accounts")
    active_tokens = tokens_path or config.tokens_path()
    logger.pair("file", _display_path(active_tokens))
    logger.pair("loaded", str(len(accounts)))
    if not accounts:
        logger.error(f"No accounts found in {_display_path(active_tokens)}")
        logger.info("Add one token per line, then run the toolkit again")
        return 1

    if args.stagger is not None:
        cfg["stagger_ms"] = max(0, min(int(args.stagger), 60000))
    if args.timeout is not None:
        cfg["ready_timeout_seconds"] = max(5, min(int(args.timeout), 300))

    interactive = sys.stdin.isatty() and not args.yes
    prefill = (args.invite or "").strip()
    joiner = Joiner()
    online: list = []
    first_run = True

    try:
        while True:
            invite = _request_invite(prefill, interactive)
            prefill = ""
            if invite is None:
                return 0 if first_run is False or interactive else 1

            if not online:
                logger.blank()
                logger.info(f"Logging in {len(accounts)} account(s) ...")
                online, offline = await joiner.login(
                    accounts,
                    timeout=cfg["ready_timeout_seconds"],
                    policy=policy,
                )
                if not online:
                    logger.error("No accounts came online - nothing to join with")
                    return 1
                logger.info(f"Online: {len(online)} | offline: {len(offline)}")

            try:
                summary = await joiner.join_server(
                    invite,
                    guard,
                    stagger_ms=int(cfg["stagger_ms"]),
                    jitter_ms=int(cfg["stagger_jitter_ms"]),
                    clients=online,
                )
            except ValueError as err:
                logger.error(str(err))
                if not interactive:
                    return 1
                continue
            except RuntimeError as err:
                logger.error(str(err))
                if not interactive:
                    return 1
                continue
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"Join failed: {err}")
                if not interactive:
                    return 1
                continue

            first_run = False
            _print_result(summary, len(online))

            if summary.get("aborted"):
                logger.warn(
                    "Run stopped early to protect the accounts - "
                    "wait before starting it again"
                )
                if not interactive:
                    return 1 if not summary.get("joined") else 0
                continue

            if not interactive:
                return 0
            if not _ask_again():
                return 0
    finally:
        try:
            await joiner.close()
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    console.init()
    args = build_parser().parse_args(argv)
    console.configure(ascii_only=args.ascii, color=False if args.no_color else None)
    console.set_title(FULL_NAME)
    console.install_shutdown_guard()
    _startup()

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        logger.blank()
        logger.info("Shutdown complete")
        return 130
