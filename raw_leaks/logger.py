"""Branded console logging for RAW LEAKS.

Every line carries the ``[RAW LEAKS]`` prefix. Severity labels are padded to a
fixed width so the output stays scannable in a narrow Windows terminal.
"""

from __future__ import annotations

from . import console

PREFIX = "[RAW LEAKS]"

_LABEL_COLORS = {
    "INFO": console.GRAY,
    "OK": console.GRAY,
    "WARN": console.RED,
    "ERROR": console.RED,
}


def line(message: str) -> None:
    """Print a plain branded line, e.g. ``[RAW LEAKS] Initializing...``."""
    print(f"{console.style(PREFIX, console.GRAY)} {message}", flush=True)


def log(level: str, message: str) -> None:
    """Print one branded log entry: ``[RAW LEAKS] <LEVEL> <message>``."""
    label = f"{level:<5}"
    label_out = console.style(label, _LABEL_COLORS.get(level, console.GRAY))
    body_out = console.style(message, console.RED if level == "ERROR" else console.WHITE)
    print(f"{console.style(PREFIX, console.GRAY)} {label_out} {body_out}", flush=True)


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
