from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a protected upstream operation is short-circuited."""

    def __init__(self, *, key: str, retry_after_s: float) -> None:
        self.key = str(key)
        self.retry_after_s = max(0.0, float(retry_after_s))
        retry_after_int = max(0, int(round(self.retry_after_s)))
        super().__init__(
            f"Circuit breaker is open for '{self.key}'. "
            f"Retry in about {retry_after_int}s."
        )


@dataclass
class _CircuitState:
    state: str = "closed"  # closed | open | half_open
    failures: int = 0
    opened_until_monotonic: float = 0.0
    half_open_successes: int = 0


class NamedCircuitBreaker:
    """
    Lightweight per-operation circuit breaker.

    Keys isolate failure domains (for example: `GET /accounts` vs `POST /Login`).
    """

    def __init__(
        self,
        *,
        enabled: bool,
        failure_threshold: int,
        recovery_timeout_s: float,
        half_open_success_threshold: int = 1,
    ) -> None:
        self.enabled = bool(enabled)
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_timeout_s = max(0.1, float(recovery_timeout_s))
        self.half_open_success_threshold = max(1, int(half_open_success_threshold))
        self._lock = threading.RLock()
        self._states: dict[str, _CircuitState] = {}

    def _state_for(self, key: str) -> _CircuitState:
        return self._states.setdefault(str(key), _CircuitState())

    def before_call(self, key: str) -> None:
        """Validate whether call is currently allowed for a protected key."""
        if not self.enabled:
            return

        op = str(key)
        now = time.monotonic()
        with self._lock:
            state = self._state_for(op)
            if state.state != "open":
                return

            if now >= state.opened_until_monotonic:
                state.state = "half_open"
                state.failures = 0
                state.half_open_successes = 0
                return

            raise CircuitBreakerOpenError(
                key=op,
                retry_after_s=(state.opened_until_monotonic - now),
            )

    def record_success(self, key: str) -> None:
        """Mark successful protected call."""
        if not self.enabled:
            return

        with self._lock:
            state = self._state_for(key)
            if state.state == "half_open":
                state.half_open_successes += 1
                if state.half_open_successes >= self.half_open_success_threshold:
                    state.state = "closed"
                    state.failures = 0
                    state.opened_until_monotonic = 0.0
                    state.half_open_successes = 0
                return

            if state.state == "closed":
                state.failures = 0

    def record_failure(self, key: str) -> None:
        """Mark failed protected call and transition to OPEN when threshold is reached."""
        if not self.enabled:
            return

        now = time.monotonic()
        with self._lock:
            state = self._state_for(key)
            if state.state == "half_open":
                state.state = "open"
                state.failures = self.failure_threshold
                state.half_open_successes = 0
                state.opened_until_monotonic = now + self.recovery_timeout_s
                return

            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.state = "open"
                state.half_open_successes = 0
                state.opened_until_monotonic = now + self.recovery_timeout_s

    def snapshot(self) -> dict[str, Any]:
        """Return breaker status for diagnostics/observability."""
        now = time.monotonic()
        with self._lock:
            payload: dict[str, Any] = {}
            for key, state in self._states.items():
                payload[key] = {
                    "state": state.state,
                    "failures": int(state.failures),
                    "half_open_successes": int(state.half_open_successes),
                    "retry_after_s": (
                        max(0.0, state.opened_until_monotonic - now)
                        if state.state == "open"
                        else 0.0
                    ),
                }
            return payload
