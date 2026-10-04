"""Terminal capability handling for Windows, legacy consoles and colour output.

The toolkit targets Windows terminals first: it switches the console to UTF-8,
enables virtual terminal sequences and degrades to plain ASCII when the host
cannot render box drawing characters.

Palette (near-black background assumed, e.g. Windows Terminal default):

* ``WHITE`` / ``BRIGHT`` - primary text
* ``GRAY``  - secondary text, labels and rules
* ``RED``   - single restrained accent
"""

from __future__ import annotations

import errno
import os
import sys
import threading
import traceback

WHITE = "\x1b[37m"
BRIGHT = "\x1b[97m"
GRAY = "\x1b[90m"
RED = "\x1b[31m"
RESET = "\x1b[0m"

# Full width of the brand frame - rules and dividers align to it.
RULE_WIDTH = 48

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


def rule_character() -> str:
    """Horizontal rule glyph, ASCII on limited terminals."""
    return "\u2500" if _UNICODE else "-"


def style(text: str, color: str | None) -> str:
    """Wrap ``text`` in an ANSI colour when colour output is enabled."""
    if not _COLOR or not color:
        return text
    return f"{color}{text}{RESET}"


def install_shutdown_guard() -> None:
    """Silence a harmless teardown race in the HTTP stack.

    The HTTP layer (curl_cffi) polls sockets from a worker thread vendored out
    of Tornado. When the session closes, that thread can still be inside
    ``select`` with an already-closed handle; on Windows the call then fails
    with ``WSAENOTSOCK`` and prints a traceback on the way out of the
    interpreter. Only that exact case is dropped - every other thread
    exception keeps its default reporting.
    """
    previous = threading.excepthook

    def _hook(args: "threading.ExceptHookArgs") -> None:
        exc = args.exc_value
        thread = getattr(args, "thread", None)
        if (
            thread is not None
            and thread.name == "Tornado selector"
            and isinstance(exc, OSError)
            and exc.errno == getattr(errno, "WSAENOTSOCK", None)
        ):
            return
        if previous is not None:
            previous(args)
            return
        name = getattr(thread, "name", "MainThread")
        sys.stderr.write(f"Exception in thread {name}:\n")
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _hook
