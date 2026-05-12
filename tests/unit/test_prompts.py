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


def test_all_prompts_registered(registered):
    fake_mcp, _ = registered
    assert set(fake_mcp.prompts.keys()) == {
        "database_overview",
        "analyze_table",
        "compare_periods",
        "data_quality_check",
        "sql_helper",
        "categorize_transaction",
        "spending_breakdown_by_category",
        "income_pattern_analysis",
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


# ---------------------------------------------------------------------------
# Phase 5 prompts
# ---------------------------------------------------------------------------


def test_categorize_transaction_quotes_description_and_lists_tool(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["categorize_transaction"]("ЛИДЛ БЪЛГАРИЯ", top_k=2)
    assert "'ЛИДЛ БЪЛГАРИЯ'" in out
    assert "classify_description" in out
    assert "unclassified" in out
    # Mentions both the boost and the salary code so the LLM does not
    # need to remember them from elsewhere.
    assert "payroll_pattern_hit" in out
    assert "001001001000" in out


def test_categorize_transaction_defaults_to_auto_direction(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["categorize_transaction"]("anything")
    assert "Direction filter: auto" in out


def test_categorize_transaction_respects_explicit_direction(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["categorize_transaction"]("anything", direction="outgoing")
    assert "Direction filter: outgoing" in out


def test_spending_breakdown_includes_schema_and_tool_call(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["spending_breakdown_by_category"](
        customer_id="12345",
        from_date="2026-01-01",
        to_date="2026-03-31",
    )
    # Customer + date range plumbed through.
    assert "12345" in out
    assert "2026-01-01" in out and "2026-03-31" in out
    # The prompt must direct the LLM to enrich via the Phase 4 method.
    assert "tools.classify_transactions" in out
    # And surface the category columns the method produces.
    assert "category_path" in out
    assert "category_unclassified" in out
    # Error handling note must be present (last_error contract).
    assert "tools.last_error" in out
    # Schema block must be rendered so the LLM does not invent table names.
    assert "accounts:" in out


def test_spending_breakdown_uses_default_connection(registered):
    fake_mcp, db = registered
    fake_mcp.prompts["spending_breakdown_by_category"](
        customer_id="12345",
        from_date="2026-01-01",
        to_date="2026-03-31",
    )
    db.get_context_for_llm.assert_called_with("scards")


def test_income_pattern_analysis_references_salary_code_and_heuristic(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["income_pattern_analysis"](
        customer_id="12345", months=3
    )
    assert "12345" in out
    assert "3 months" in out
    # The taxonomy code must appear so the LLM filters by it instead of
    # inventing a category.
    assert "001001001000" in out
    # The consecutive-months heuristic must be spelled out.
    assert "consecutive months" in out
    # Tool reference + error handling note.
    assert "tools.classify_transactions" in out
    assert "tools.last_error" in out


def test_income_pattern_analysis_default_months_is_six(registered):
    fake_mcp, _ = registered
    out = fake_mcp.prompts["income_pattern_analysis"](customer_id="12345")
    assert "last 6 months" in out


def test_phase5_prompts_render_when_no_connection(registered):
    fake_mcp, db = registered
    db.get_default_connection.return_value = None
    out = fake_mcp.prompts["spending_breakdown_by_category"](
        customer_id="1", from_date="2026-01-01", to_date="2026-01-31"
    )
    assert "no connection configured" in out
