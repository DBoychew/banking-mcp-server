"""In-memory classification stats (Phase 6 observability).

A tiny thread-safe counter that tracks how the classifier is performing in
the running process. Surfaced via the ``banking://classification-stats``
MCP resource so operators can spot a regression (e.g. unclassified rate
spiking) without parsing audit logs.

Resets to zero on every process restart; this is intentional - durable
history lives in the audit log, not here.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Counters:
    total: int = 0
    unclassified: int = 0
    payroll_hits: int = 0
    by_direction: dict[str, int] = field(default_factory=dict)
    by_direction_unclassified: dict[str, int] = field(default_factory=dict)


_lock = threading.Lock()
_counters = _Counters()


def record(
    *,
    direction: str,
    unclassified: bool,
    payroll_pattern_hit: bool,
    row_count: int = 1,
) -> None:
    """Bump counters for one classify() call (or one batch summary)."""
    if row_count <= 0:
        return
    with _lock:
        _counters.total += row_count
        if unclassified:
            _counters.unclassified += row_count
        if payroll_pattern_hit:
            _counters.payroll_hits += row_count
        _counters.by_direction[direction] = (
            _counters.by_direction.get(direction, 0) + row_count
        )
        if unclassified:
            _counters.by_direction_unclassified[direction] = (
                _counters.by_direction_unclassified.get(direction, 0) + row_count
            )


def snapshot() -> dict[str, Any]:
    """Read-only snapshot of the current counters."""
    with _lock:
        total = _counters.total
        unclassified = _counters.unclassified
        payroll = _counters.payroll_hits
        by_direction = dict(_counters.by_direction)
        by_direction_unclassified = dict(_counters.by_direction_unclassified)

    rate = (unclassified / total) if total else 0.0
    per_direction = {
        d: {
            "total": by_direction[d],
            "unclassified": by_direction_unclassified.get(d, 0),
            "unclassified_rate": (
                by_direction_unclassified.get(d, 0) / by_direction[d]
                if by_direction[d]
                else 0.0
            ),
        }
        for d in by_direction
    }
    return {
        "total": total,
        "unclassified": unclassified,
        "unclassified_rate": round(rate, 4),
        "payroll_pattern_hits": payroll,
        "by_direction": per_direction,
    }


def reset() -> None:
    """Reset all counters. Mostly for tests; callable from admin reload."""
    global _counters
    with _lock:
        _counters = _Counters()
