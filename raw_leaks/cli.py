"""Command line interface for RAW LEAKS - Automation Toolkit."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from . import FULL_NAME, __version__, banner, captcha, config, console, logger
from .joiner import Joiner

BANNER_LINES = [
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
            "  python main.py --invite https://discord.gg/example\n"
            "  python main.py --stagger 250 --yes --invite example\n"
        ),
    )
    parser.add_argument("-i", "--invite", help="invite link or bare invite code")
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
    logger.line(BANNER_LINES[0])
    logger.line(BANNER_LINES[1])


def _ready() -> None:
    logger.line(BANNER_LINES[2])


def _prompt_invite(default: str) -> Optional[str]:
    hint = f" [{default}]" if default else ""
    try:
        return input(console.style(f"Invite link{hint}: ", console.GRAY))
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _prompt_again() -> bool:
    try:
        answer = input(console.style("Join another invite? [y/N]: ", console.GRAY))
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


async def _run(args: argparse.Namespace) -> int:
    tokens_path = Path(args.tokens) if args.tokens else None
    cfg = config.load()
    accounts = config.load_tokens(tokens_path)
    _ready()

    logger.info(FULL_NAME)
    logger.info(f"Version {__version__}")
    logger.info(f"Stagger {cfg['stagger_ms']}ms | ready timeout {cfg['ready_timeout_seconds']}s")

    if not accounts:
        logger.error(f"No accounts found in {config.tokens_path().name}")
        logger.info("Add one token per line, then run the toolkit again")
        return 1
    logger.info(f"Accounts loaded: {len(accounts)}")

    if str(cfg.get("nopecha_key") or "").strip():
        try:
            await captcha.log_status()
        except Exception as err:
            logger.warn(f"CAPTCHA status check failed: {err}")
    else:
        logger.warn("No NopeCHA key set - join CAPTCHAs cannot be solved")

    if args.stagger is not None:
        cfg["stagger_ms"] = max(0, min(int(args.stagger), 5000))
    if args.timeout is not None:
        cfg["ready_timeout_seconds"] = max(5, min(int(args.timeout), 300))

    joiner = Joiner()
    try:
        logger.info(f"Logging in {len(accounts)} account(s) ...")
        online, failed = await joiner.login(accounts, timeout=cfg["ready_timeout_seconds"])
        if not online:
            logger.error("No accounts came online - nothing to join with")
            return 1
        logger.info(f"Online: {len(online)} | offline: {len(failed)}")

        first = (args.invite or str(cfg.get("invite") or "")).strip()
        interactive = sys.stdin.isatty() and not args.yes

        while True:
            invite = first if first else (_prompt_invite(str(cfg.get("invite") or "")) or "")
            invite = invite.strip()
            if not invite:
                logger.warn("No invite supplied")
            else:
                try:
                    await joiner.join_server(invite, stagger_ms=int(cfg["stagger_ms"]))
                except ValueError as err:
                    logger.error(str(err))
                except RuntimeError as err:
                    logger.error(str(err))
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    logger.error(f"Join failed: {err}")

            first = ""
            if not interactive:
                break
            if not _prompt_again():
                break
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
    _startup()

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        logger.line("")
        logger.info("Shutdown complete")
        return 130
