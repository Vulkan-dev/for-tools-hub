"""Runtime configuration for RAW LEAKS - Automation Toolkit.

Settings live in ``config.json`` next to ``main.py``. Environment variables
override the file so CI and scripted runs stay possible:

``NOPECHA_KEY``, ``RAW_LEAKS_INVITE``, ``RAW_LEAKS_STAGGER_MS``,
``RAW_LEAKS_TOKENS_FILE``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
TOKENS_FILE = ROOT / "tokens.txt"
TOKENS_TEMPLATE = ROOT / "tokens.example.txt"

DEFAULTS: dict[str, Any] = {
    # Invite link used when the prompt is left empty.
    "invite": "",
    # Milliseconds between each account's join request.
    "stagger_ms": 10,
    # How long to wait for Discord's READY event after login.
    "ready_timeout_seconds": 60,
    # Token list, one account per line.
    "tokens_file": "tokens.txt",
    # Where Discord serves the CAPTCHA challenge.
    "captcha_url": "https://discord.com/channels/@me",
    # NopeCHA API key - used to solve join CAPTCHAs automatically.
    "nopecha_key": "",
    "nopecha_url": "https://api.nopecha.com",
}

_CONFIG: dict[str, Any] = dict(DEFAULTS)


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def load(path: Path | None = None) -> dict[str, Any]:
    """Load ``config.json`` over the defaults and apply environment overrides."""
    global _CONFIG
    config_path = Path(path) if path else CONFIG_FILE
    merged = dict(DEFAULTS)

    if config_path.is_file():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            from . import logger

            logger.warn(f"Could not read {config_path.name}: {err}")
            raw = {}
        if isinstance(raw, dict):
            for key in DEFAULTS:
                if key in raw and raw[key] not in (None, ""):
                    merged[key] = raw[key]

    env_invite = os.getenv("RAW_LEAKS_INVITE", "").strip()
    if env_invite:
        merged["invite"] = env_invite
    env_stagger = os.getenv("RAW_LEAKS_STAGGER_MS", "").strip()
    if env_stagger:
        merged["stagger_ms"] = _as_int(env_stagger, DEFAULTS["stagger_ms"])
    env_tokens = os.getenv("RAW_LEAKS_TOKENS_FILE", "").strip()
    if env_tokens:
        merged["tokens_file"] = env_tokens
    env_key = os.getenv("NOPECHA_KEY", "").strip()
    if env_key:
        merged["nopecha_key"] = env_key

    merged["stagger_ms"] = max(0, min(_as_int(merged["stagger_ms"], 10), 5000))
    merged["ready_timeout_seconds"] = max(
        5, min(_as_int(merged["ready_timeout_seconds"], 60), 300)
    )

    _CONFIG = merged
    return _CONFIG


def get(key: str, fallback: Any = None) -> Any:
    """Read a loaded setting."""
    return _CONFIG.get(key, DEFAULTS.get(key, fallback))


def snapshot() -> dict[str, Any]:
    """Return a copy of the active configuration."""
    return dict(_CONFIG)


def tokens_path() -> Path:
    configured = str(get("tokens_file", "tokens.txt") or "tokens.txt").strip()
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def ensure_tokens_file(path: Path | None = None) -> Path:
    """Create ``tokens.txt`` from the template on first run."""
    target = Path(path) if path else tokens_path()
    if not target.exists() and TOKENS_TEMPLATE.is_file():
        target.write_text(TOKENS_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def load_tokens(path: Path | None = None) -> list[tuple[str, str]]:
    """Return ``(token, label)`` pairs.

    The file format is one account per line::

        # comment lines are ignored
        mfa.xxxxx                       # main
        long-user-token                 # alt
    """
    target = ensure_tokens_file(path)
    accounts: list[tuple[str, str]] = []
    if not target.is_file():
        return accounts

    text = target.read_text(encoding="utf-8-sig", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        token, sep, label = line.partition("#")
        token = token.strip()
        if not token:
            continue
        label = label.strip() if sep else ""
        accounts.append((token, label))
    return accounts
