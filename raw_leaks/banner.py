"""Startup banner for RAW LEAKS.

Renders the brand frame on terminals that support box drawing characters and
falls back to an ASCII frame on hosts with limited Unicode support.
"""

from __future__ import annotations

from . import console

WIDTH = 46

_UNI = {"tl": "\u2554", "tr": "\u2557", "bl": "\u255a", "br": "\u255d",
        "h": "\u2550", "v": "\u2551"}
_ASCII = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"}

_SPACED_NAME = "              R A W   L E A K S               "
_SUBTITLE = "              AUTOMATION TOOLKIT              "
_EMPTY = " " * WIDTH


def render() -> list[str]:
    """Return the banner as a list of ready-to-print lines."""
    g = _UNI if console.unicode_enabled() else _ASCII
    return [
        g["tl"] + g["h"] * WIDTH + g["tr"],
        g["v"] + _EMPTY + g["v"],
        g["v"] + _SPACED_NAME + g["v"],
        g["v"] + _SUBTITLE + g["v"],
        g["v"] + _EMPTY + g["v"],
        g["bl"] + g["h"] * WIDTH + g["br"],
    ]


def print_banner() -> None:
    """Print the branded startup banner."""
    top, empty, name, subtitle, _, bottom = render()
    print(console.style(top, console.RED), flush=True)
    print(console.style(empty, console.RED), flush=True)
    print(console.style(name, console.WHITE), flush=True)
    print(console.style(subtitle, console.GRAY), flush=True)
    print(console.style(empty, console.RED), flush=True)
    print(console.style(bottom, console.RED), flush=True)
