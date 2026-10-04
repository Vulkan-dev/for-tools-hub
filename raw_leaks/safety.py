"""Rate limit and account protection for RAW LEAKS.

Discord rate limits invites per account, per route and per IP, and repeated
pressure shows up as Cloudflare 429s, join blocks and account locks. This
module holds the policy that keeps a run inside those limits:

* jittered pacing between join requests (no fixed-interval bursts)
* a minimum gap between two joins by the same account
* a per-account daily join budget persisted in ``state.json``
* a global cooldown after repeated consecutive failures
* a cap on how long a single request may be blocked before the run stops
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

STATE_FILE = "state.json"


def _number(raw: dict, key: str, default: float, cast=float,
            low: float | None = None, high: float | None = None) -> Any:
    value = raw.get(key, default)
    try:
        value = cast(value)
    except (TypeError, ValueError):
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


@dataclass
class SafetyPolicy:
    """Tunables that decide how aggressive a run is allowed to be."""

    enabled: bool = True
    login_stagger_ms: int = 1000
    min_gap_seconds: float = 60.0
    max_joins_per_account: int = 5
    max_consecutive_failures: int = 3
    cooldown_seconds: float = 120.0
    max_ratelimit_timeout: float = 120.0
    ratelimit_retries: int = 3
    verify_invite: bool = True

    @classmethod
    def from_dict(cls, raw: Any) -> "SafetyPolicy":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            login_stagger_ms=int(_number(data, "login_stagger_ms", 1000, int, 0, 60000)),
            min_gap_seconds=_number(data, "min_gap_seconds", 60.0, float, 0.0, 3600.0),
            max_joins_per_account=int(_number(data, "max_joins_per_account", 5, int, 1, 1000)),
            max_consecutive_failures=int(_number(data, "max_consecutive_failures", 3, int, 1, 100)),
            cooldown_seconds=_number(data, "cooldown_seconds", 120.0, float, 5.0, 7200.0),
            max_ratelimit_timeout=_number(data, "max_ratelimit_timeout", 120.0, float, 10.0, 3600.0),
            ratelimit_retries=int(_number(data, "ratelimit_retries", 3, int, 0, 10)),
            verify_invite=bool(data.get("verify_invite", True)),
        )

    def describe(self) -> str:
        gap = f"{self.min_gap_seconds:.0f}s gap" if self.min_gap_seconds else "no gap"
        return (
            f"login {self.login_stagger_ms}ms · {gap} · "
            f"{self.max_joins_per_account} joins/account/day"
        )


class SafetyGuard:
    """Runtime state backing a :class:`SafetyPolicy`."""

    def __init__(self, policy: SafetyPolicy, state_path: Path) -> None:
        self.policy = policy
        self.state_path = Path(state_path)
        self._today = date.today().isoformat()
        self._joins: dict[str, int] = {}
        self._last_join: dict[str, float] = {}
        self._consecutive_failures = 0
        self._paused_until = 0.0
        self._load()

    # ------------------------------------------------------------------
    # Daily budget
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict) or raw.get("date") != self._today:
            return
        joins = raw.get("joins")
        if isinstance(joins, dict):
            for label, value in joins.items():
                try:
                    self._joins[str(label)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue

    def _save(self) -> None:
        payload = {"date": self._today, "joins": self._joins}
        try:
            self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _rollover(self) -> None:
        today = date.today().isoformat()
        if today != self._today:
            self._today = today
            self._joins = {}
            self._save()

    def joins_today(self, label: str) -> int:
        self._rollover()
        return int(self._joins.get(label, 0))

    def capacity(self, label: str) -> int:
        """Joins this account may still make today (large value when off)."""
        if not self.policy.enabled:
            return 10 ** 9
        return max(0, self.policy.max_joins_per_account - self.joins_today(label))

    # ------------------------------------------------------------------
    # Pacing
    # ------------------------------------------------------------------
    def gap_remaining(self, label: str) -> float:
        """Seconds this account still has to wait before its next join."""
        if not self.policy.enabled:
            return 0.0
        elapsed = time.time() - self._last_join.get(label, 0.0)
        return max(0.0, self.policy.min_gap_seconds - elapsed)

    def cooldown_remaining(self) -> float:
        return max(0.0, self._paused_until - time.time())

    def register_cooldown(self) -> float:
        """Start (or keep) the global cooldown; returns its duration."""
        now = time.time()
        if self._paused_until <= now:
            self._paused_until = now + self.policy.cooldown_seconds
            self._consecutive_failures = 0
        return max(0.0, self._paused_until - now)

    def record_failure(self) -> int:
        self._consecutive_failures += 1
        return self._consecutive_failures

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def should_cooldown(self) -> bool:
        return (
            self.policy.enabled
            and self._consecutive_failures >= self.policy.max_consecutive_failures
        )

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------
    def record_join(self, label: str) -> None:
        self._rollover()
        self._last_join[label] = time.time()
        self._joins[label] = self.joins_today(label) + 1
        self._consecutive_failures = 0
        self._save()

    def record_attempt(self, label: str) -> None:
        """Mark an attempt that did not join (rate limit, already member)."""
        self._last_join[label] = time.time()
