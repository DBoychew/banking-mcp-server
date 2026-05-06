"""Tests for banking_mcp.prompts - MCP prompt registration and rendering."""

from unittest.mock import MagicMock

import pytest

from banking_mcp.prompts.banking_prompts import register_banking_prompts


class FakeMCP:
    """Minimal MCP stub that captures registered prompts by name."""

    def __init__(self):
        self.prompts = {}

    def prompt(self, *_, **__):
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture
def registered(monkeypatch):
    fake_mcp = FakeMCP()
    fake_db = MagicMock()
    fake_db.get_default_connection.return_value = "scards"
    fake_db.get_context_for_llm.return_value = {
        "connection_name": "scards",
        "db_type": "oracle",
        "sql_dialect_hint": "Oracle: TO_DATE() / TO_CHAR() / ROWNUM",
        "schema_compact": "accounts: id(NUMBER), name(VARCHAR2)\ncards: id(NUMBER), status(VARCHAR2)",
        "domain_queries": [],
        "available_connections": ["scards"],
    }
    monkeypatch.setattr("banking_mcp.prompts.banking_prompts.get_manager", lambda: fake_db)
    register_banking_prompts(fake_mcp)
    return fake_mcp, fake_db


def test_five_prompts_registered(registered):
    fake_mcp, _ = registered
    assert set(fake_mcp.prompts.keys()) == {
        "database_overview",
        "analyze_table",
        "compare_periods",
        "data_quality_check",
        "sql_helper",
    }


def test_database_overview_includes_schema_and_dialect(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["database_overview"]()
    assert "accounts:" in out
    assert "Oracle" in out
    assert "5-bullet" in out


def test_database_overview_uses_default_when_no_arg(registered):
    fake_mcp, db = registered
    fake_mcp.prompts["database_overview"]()
    db.get_context_for_llm.assert_called_with("scards")


def test_database_overview_uses_explicit_connection(registered):
    fake_mcp, db = registered
    fake_mcp.prompts["database_overview"]("bank_info")
    db.get_context_for_llm.assert_called_with("bank_info")


def test_analyze_table_includes_table_name(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["analyze_table"]("cards")
    assert "**cards**" in out
    assert "FROM cards" in out


def test_compare_periods_renders_metric_and_dates(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["compare_periods"](
        table_name="transactions",
        date_column="trans_date",
        metric_sql="SUM(amount)",
        period_a_start="2026-01-01",
        period_a_end="2026-01-31",
        period_b_start="2026-02-01",
        period_b_end="2026-02-28",
    )
    assert "transactions" in out
    assert "trans_date" in out
    assert "SUM(amount)" in out
    assert "2026-01-01" in out and "2026-02-28" in out


def test_data_quality_check_targets_table(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["data_quality_check"]("cards")
    assert "**cards**" in out
    assert "NULL" in out


def test_sql_helper_quotes_question(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["sql_helper"]("How many active cards?")
    assert "'How many active cards?'" in out
    assert "SELECT" in out


def test_prompt_handles_missing_connection_gracefully(registered):
    fake_mcp, db = registered
    db.get_default_connection.return_value = None
    out = fake_mcp.prompts["database_overview"]()
    assert "no connection configured" in out


def test_prompt_handles_context_failure(registered):
    fake_mcp, db = registered
    db.get_context_for_llm.side_effect = ValueError("schema fetch failed")
    out = fake_mcp.prompts["analyze_table"]("cards")
    assert "failed to load context" in out
