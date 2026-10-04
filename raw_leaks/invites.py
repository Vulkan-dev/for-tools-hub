"""Discord invite parsing.

Extracted unchanged from the control panel's ``bot_manager`` module.
"""

from __future__ import annotations

import re

INVITE_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/(?:invite|join)|discord\.gg)/'
    r'([A-Za-z0-9_-]+)',
    re.IGNORECASE,
)


def extract_invite_code(invite: str) -> str:
    """Accept a full invite URL or a bare invite code."""
    text = str(invite or '').strip()
    if not text:
        raise ValueError('Invite link is empty')
    match = INVITE_RE.search(text)
    if match:
        return match.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{2,100}', text):
        return text
    raise ValueError(f'Not a valid Discord invite: {text}')


def invite_url(code: str) -> str:
    """Canonical invite URL for a code."""
    return f'https://discord.gg/{code}'
