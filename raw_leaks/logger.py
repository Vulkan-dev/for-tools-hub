"""Branded console output for RAW LEAKS.

Two layers:

* ``log`` / ``info`` / ``ok`` / ``warn`` / ``error`` - operational logs that
  always carry the ``[RAW LEAKS]`` prefix and a fixed-width severity label.
* ``section`` / ``pair`` / ``rule`` - layout helpers used for the branded
  blocks (accounts, invite, result) so the session reads like a designed tool
  instead of a raw stream.
"""

from __future__ import annotations

from . import console

PREFIX = "[RAW LEAKS]"

_LABEL_COLORS = {
    "INFO": console.GRAY,
    "OK": console.BRIGHT,
    "WARN": console.RED,
    "ERROR": console.RED,
}

_MESSAGE_COLORS = {
    "INFO": console.WHITE,
    "OK": console.BRIGHT,
    "WARN": console.WHITE,
    "ERROR": console.RED,
}


def line(message: str) -> None:
    """Print a plain branded line, e.g. ``[RAW LEAKS] Initializing...``."""
    print(f"{console.style(PREFIX, console.WHITE)} {message}", flush=True)


def log(level: str, message: str) -> None:
    """Print one branded log entry: ``[RAW LEAKS] <LEVEL> <message>``."""
    label = f"{level:<5}"
    label_out = console.style(label, _LABEL_COLORS.get(level, console.GRAY))
    body_out = console.style(message, _MESSAGE_COLORS.get(level, console.WHITE))
    print(f"{console.style(PREFIX, console.WHITE)} {label_out} {body_out}", flush=True)


def info(message: str) -> None:
    log("INFO", message)


def ok(message: str) -> None:
    log("OK", message)


def warn(message: str) -> None:
    log("WARN", message)


def warning(message: str) -> None:
    log("WARN", message)


def error(message: str) -> None:
    log("ERROR", message)


def debug(message: str) -> None:
    """Debug output is intentionally silent in the branded console."""


def blank() -> None:
    """Print an empty line."""
    print("", flush=True)


def rule() -> None:
    """Print the brand-width hairline used under every section header."""
    print(console.style(console.rule_character() * console.RULE_WIDTH, console.GRAY),
          flush=True)


def section(title: str) -> None:
    """Print a divider with an uppercase section label."""
    blank()
    print(console.style(str(title).upper(), console.GRAY), flush=True)
    rule()


def pair(label: str, value: str, color: str | None = console.WHITE) -> None:
    """Print an indented ``label   value`` row inside a section."""
    pad = f"{label:<9}"
    print(f"  {console.style(pad, console.GRAY)}{console.style(str(value), color)}",
          flush=True)


def note(message: str) -> None:
    """Secondary explanatory line inside a section."""
    print(f"  {console.style(message, console.GRAY)}", flush=True)


class Logger:
    """``logging``-style shim so extracted modules keep their original calls."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name

    @staticmethod
    def _format(message: object, args: tuple) -> str:
        text = str(message)
        if not args:
            return text
        try:
            return text % args
        except (TypeError, ValueError):
            return f"{text} {' '.join(str(a) for a in args)}"

    def info(self, message: object, *args: object) -> None:
        log("INFO", self._format(message, args))

    def ok(self, message: object, *args: object) -> None:
        log("OK", self._format(message, args))

    def warning(self, message: object, *args: object) -> None:
        log("WARN", self._format(message, args))

    def warn(self, message: object, *args: object) -> None:
        log("WARN", self._format(message, args))

    def error(self, message: object, *args: object) -> None:
        log("ERROR", self._format(message, args))

    def debug(self, message: object, *args: object) -> None:
        return None

    def exception(self, message: object, *args: object) -> None:
        log("ERROR", self._format(message, args))
