"""Terminal capability handling for Windows, legacy consoles and colour output.

The toolkit targets Windows terminals first: it switches the console to UTF-8,
enables virtual terminal sequences and degrades to plain ASCII when the host
cannot render box drawing characters.
"""

from __future__ import annotations

import os
import sys

WHITE = "\x1b[37m"
GRAY = "\x1b[90m"
RED = "\x1b[31m"
RESET = "\x1b[0m"

_COLOR = False
_UNICODE = True
_READY = False


def _enable_vt() -> bool:
    """Turn on VT processing so ANSI colour works in legacy conhost."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32(0)
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def set_title(title: str) -> None:
    """Set the console window title (wide API keeps Unicode safe on Windows)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(str(title))
    except Exception:
        pass


def init() -> None:
    """Prepare stdout for branded output. Safe to call more than once."""
    global _UNICODE, _READY
    if _READY:
        return
    _READY = True

    forced_ascii = os.environ.get("RAW_LEAKS_ASCII", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    _UNICODE = not forced_ascii

    if os.name == "nt":
        if _UNICODE:
            # Legacy cmd.exe defaults to a code page that cannot print the
            # banner glyphs; UTF-8 keeps them intact on Windows 10+.
            os.system("chcp 65001 >nul 2>nul")
            os.system("")  # legacy conhost VT opt-in
        _enable_vt()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    configure(color=None)


def configure(ascii_only: bool = False, color: bool | None = None) -> None:
    """Apply command line overrides after :func:`init`."""
    global _COLOR, _UNICODE
    _UNICODE = _UNICODE and not ascii_only
    if color is None:
        _COLOR = bool(sys.stdout.isatty()) and not os.environ.get("NO_COLOR")
    else:
        _COLOR = bool(color)


def color_enabled() -> bool:
    return _COLOR


def unicode_enabled() -> bool:
    return _UNICODE


def style(text: str, color: str | None) -> str:
    """Wrap ``text`` in an ANSI colour when colour output is enabled."""
    if not _COLOR or not color:
        return text
    return f"{color}{text}{RESET}"
