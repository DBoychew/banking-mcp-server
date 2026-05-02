"""Async audit logger for banking MCP server.

Writes JSON-lines to a rotating daily log file.
All banking PII (IBANs, tokens, long numbers) is redacted before writing.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import threading
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Optional

from banking_mcp.audit.redaction import redact, redact_dict
from banking_mcp.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal background writer thread (non-blocking for async callers)
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

    while not _stop_event.is_set():
        try:
            record = _queue.get(timeout=0.5)
        except Empty:
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
    for p in current_path.parent.glob(f"{current_path.stem.split('.')[0]}.*{current_path.suffix}"):
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
    _stop_event.set()
    if _writer_thread:
        _writer_thread.join(timeout=3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _enqueue(record: dict) -> None:
    if not settings.AUDIT_ENABLED:
        return
    try:
        _queue.put_nowait(record)
    except Exception:
        pass  # Drop if queue full — audit must never block the main path


async def log_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: Optional[str] = None,
) -> None:
    """Log an HTTP REST API request."""
    record = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "type": "http_request",
        "method": method,
        "path": redact(path),
        "status_code": status_code,
        "duration_ms": round(duration_ms, 1),
    }
    if client_ip:
        record["client_ip"] = client_ip
    _enqueue(record)


async def log_error(
    *,
    context: str,
    error: str,
    details: Optional[Any] = None,
) -> None:
    """Log an unexpected error."""
    record = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "type": "error",
        "context": context,
        "error": redact(str(error)),
    }
    if details:
        record["details"] = redact(str(details))
    _enqueue(record)
