"""Tests for banking_mcp.audit.redaction."""

from banking_mcp.audit.redaction import redact


def test_redact_returns_empty_for_empty_input():
    assert redact("") == ""
    assert redact(None) is None  # type: ignore[arg-type]


def test_redact_email_in_quotes():
    sql = "SELECT * FROM users WHERE email = 'john@example.com'"
    assert redact(sql) == "SELECT * FROM users WHERE email = '<EMAIL>'"


def test_redact_phone_in_quotes():
    sql = "INSERT INTO contacts VALUES ('+359888123456')"
    out = redact(sql)
    assert "<PHONE>" in out or "<REDACTED>" in out


def test_redact_long_string_literal():
    sql = "WHERE notes = 'this is a very long sensitive note here'"
    assert "'<REDACTED>'" in redact(sql)


def test_redact_does_not_touch_short_literals():
    sql = "WHERE status = 'A' AND code = 'OK'"
    assert redact(sql) == sql


def test_redact_does_not_touch_numeric_ids():
    sql = "WHERE account_id = 123456789012 AND ts = 1714999200000"
    assert redact(sql) == sql


def test_redact_handles_multiple_patterns():
    sql = (
        "INSERT INTO log VALUES "
        "('user@x.com', '+359888777666', 'a quite long literal note value')"
    )
    out = redact(sql)
    assert "<EMAIL>" in out
    assert "<PHONE>" in out or "<REDACTED>" in out


def test_redact_is_case_insensitive_for_email():
    assert "<EMAIL>" in redact("WHERE e='User@Domain.COM'")
