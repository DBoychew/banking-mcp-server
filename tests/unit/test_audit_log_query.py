"""Tests for banking_mcp.audit.logger.log_query - per-query audit records."""

import json
import time

from banking_mcp.audit import logger as audit_logger
from banking_mcp.audit.logger import log_query, start, stop


def _drain_queue(timeout: float = 1.0) -> None:
    """Wait for the writer thread to flush all queued records."""
    deadline = time.time() + timeout
    while time.time() < deadline and not audit_logger._queue.empty():
        time.sleep(0.05)


def _read_log_records(log_path):
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


def test_log_query_writes_success_record(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr(audit_logger.settings, "AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setattr(audit_logger.settings, "AUDIT_ENABLED", True)

    stop()  # ensure no thread carries old state
    start()
    try:
        log_query(
            connection="scards",
            query="SELECT * FROM accounts",
            duration_ms=12.34,
            row_count=5,
            status="success",
            source="test",
        )
        _drain_queue()
    finally:
        stop()

    files = list(tmp_path.glob("audit.*.log"))
    assert len(files) == 1
    records = _read_log_records(files[0])
    assert len(records) == 1
    rec = records[0]
    assert rec["type"] == "query"
    assert rec["connection"] == "scards"
    assert rec["status"] == "success"
    assert rec["row_count"] == 5
    assert rec["duration_ms"] == 12.34
    assert rec["source"] == "test"


def test_log_query_redacts_email_in_query(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr(audit_logger.settings, "AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setattr(audit_logger.settings, "AUDIT_ENABLED", True)

    stop()
    start()
    try:
        log_query(
            connection="scards",
            query="SELECT * FROM users WHERE email = 'jdoe@example.com'",
            duration_ms=1.0,
            status="success",
            source="test",
        )
        _drain_queue()
    finally:
        stop()

    files = list(tmp_path.glob("audit.*.log"))
    rec = _read_log_records(files[0])[0]
    assert "<EMAIL>" in rec["query"]
    assert "jdoe@example.com" not in rec["query"]


def test_log_query_records_error(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr(audit_logger.settings, "AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setattr(audit_logger.settings, "AUDIT_ENABLED", True)

    stop()
    start()
    try:
        log_query(
            connection="scards",
            query="SELECT bad",
            duration_ms=2.5,
            status="error",
            error="ORA-00942: table or view does not exist",
            source="test",
        )
        _drain_queue()
    finally:
        stop()

    files = list(tmp_path.glob("audit.*.log"))
    rec = _read_log_records(files[0])[0]
    assert rec["status"] == "error"
    assert "ORA-00942" in rec["error"]


def test_log_query_skipped_when_audit_disabled(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr(audit_logger.settings, "AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setattr(audit_logger.settings, "AUDIT_ENABLED", False)

    stop()
    log_query(
        connection="scards",
        query="SELECT 1",
        duration_ms=1.0,
        source="test",
    )
    # No thread started, queue empty, no file written
    assert list(tmp_path.glob("audit.*.log")) == []


def test_stop_drains_pending_records(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    monkeypatch.setattr(audit_logger.settings, "AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setattr(audit_logger.settings, "AUDIT_ENABLED", True)

    stop()
    start()
    try:
        for i in range(50):
            log_query(
                connection="scards",
                query=f"SELECT {i}",
                duration_ms=1.0,
                source="test",
            )
    finally:
        stop()

    files = list(tmp_path.glob("audit.*.log"))
    records = _read_log_records(files[0])
    assert len(records) == 50
