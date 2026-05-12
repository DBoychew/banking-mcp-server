"""Async audit logger.

Writes JSON-lines records to a daily-rotated log file. Provides two public
entry points:

  - ``log_query(...)``  - records a single SQL execution (sync wrapper)
  - ``log_error(...)``  - records an unexpected error (async)

Sensitive fields are PII-redacted before being written to disk.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Optional

from banking_mcp.audit.redaction import redact
from banking_mcp.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal background writer thread
# ---------------------------------------------------------------------------

_queue: Queue = Queue(maxsize=10_000)
_writer_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _current_log_path() -> Path:
    base = Path(settings.AUDIT_LOG_PATH)
    base.parent.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    return base.parent / f"{base.stem}.{date_str}{base.suffix}"


def _writer_loop() -> None:
    current_path: Optional[Path] = None
    fh = None

    while True:
        try:
            record = _queue.get(timeout=0.5)
        except Empty:
            if _stop_event.is_set():
                break
            continue

        try:
            path = _current_log_path()
            if path != current_path:
                if fh:
                    fh.close()
                fh = open(path, "a", encoding="utf-8")
                current_path = path
                _purge_old_logs(path)

            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
        except Exception as exc:
            logger.warning("Audit write error: %s", exc)
        finally:
            _queue.task_done()

    if fh:
        fh.close()


def _purge_old_logs(current_path: Path) -> None:
    """Remove log files older than AUDIT_LOG_RETENTION_DAYS."""
    cutoff = datetime.date.today() - datetime.timedelta(
        days=settings.AUDIT_LOG_RETENTION_DAYS
    )
    stem_root = current_path.stem.split(".")[0]
    for p in current_path.parent.glob(f"{stem_root}.*{current_path.suffix}"):
        try:
            date_part = p.stem.split(".")[-1]
            file_date = datetime.date.fromisoformat(date_part)
            if file_date < cutoff:
                p.unlink(missing_ok=True)
        except (ValueError, IndexError):
            pass


def start() -> None:
    """Start the background writer thread (idempotent)."""
    global _writer_thread
    if _writer_thread and _writer_thread.is_alive():
        return
    _stop_event.clear()
    _writer_thread = threading.Thread(target=_writer_loop, daemon=True, name="audit-writer")
    _writer_thread.start()


def stop() -> None:
    if _writer_thread and _writer_thread.is_alive():
        _queue.join()
        _stop_event.set()
        _writer_thread.join(timeout=3)
    else:
        _stop_event.set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _enqueue(record: dict) -> None:
    if not settings.AUDIT_ENABLED:
        return
    if _writer_thread is None or not _writer_thread.is_alive():
        # Lazy-start so callers outside of the FastAPI lifespan still record events
        start()
    try:
        _queue.put_nowait(record)
    except Exception:
        pass  # Drop if queue full - audit must never block the main path


def _utc_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def log_query(
    *,
    connection: str,
    query: str,
    duration_ms: float,
    row_count: Optional[int] = None,
    status: str = "success",
    error: Optional[str] = None,
    source: str = "unknown",
) -> None:
    """Record a single SQL query execution.

    The query and error fields are PII-redacted before persistence. This is a
    sync function (writes are still async via the background thread) so it can
    be called from any code path, including the sandbox.
    """
    record = {
        "ts": _utc_iso(),
        "type": "query",
        "connection": connection,
        "query": redact(query[:2000]),
        "duration_ms": round(duration_ms, 2),
        "row_count": row_count,
        "status": status,
        "error": redact(error) if error else None,
        "source": source,
    }
    _enqueue(record)


async def log_error(
    *,
    context: str,
    error: str,
    details: Optional[Any] = None,
) -> None:
    """Record an unexpected error from request handling."""
    record = {
        "ts": _utc_iso(),
        "type": "error",
        "context": context,
        "error": redact(str(error)),
    }
    if details:
        record["details"] = redact(str(details))
    _enqueue(record)


def log_classification(
    *,
    description: str,
    direction: str,
    top_code: Optional[str],
    top_score: float,
    unclassified: bool,
    payroll_pattern_hit: bool = False,
    row_count: int = 1,
    source: str = "unknown",
) -> None:
    """Record one classification call (single description or batch).

    The description is PII-redacted; the code is a verbatim taxonomy value
    and is safe to log. For batch calls (classify_transactions) callers
    typically log once per row, but a summary call with row_count > 1 and
    a None top_code is also acceptable for compact bulk audit.
    """
    record = {
        "ts": _utc_iso(),
        "type": "classification",
        "description": redact(description[:500]) if description else None,
        "direction": direction,
        "top_code": top_code,
        "top_score": round(float(top_score), 4),
        "unclassified": bool(unclassified),
        "payroll_pattern_hit": bool(payroll_pattern_hit),
        "row_count": int(row_count),
        "source": source,
    }
    _enqueue(record)
