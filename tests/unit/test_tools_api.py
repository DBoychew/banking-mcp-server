"""Tests for banking_mcp.tools_api.BankingToolsAPI."""

from unittest.mock import MagicMock

import pandas as pd

from banking_mcp.tools_api import BankingToolsAPI


def _api(default="scards"):
    db = MagicMock()
    db.get_default_connection.return_value = default
    db.query.return_value = pd.DataFrame([{"x": 1}])
    db.execute_domain_query.return_value = pd.DataFrame([{"y": 2}])
    db.get_context_for_llm.return_value = {"connection_name": default}
    return BankingToolsAPI(db), db


def test_execute_sql_query_returns_dataframe():
    api, db = _api()
    df = api.execute_sql_query("SELECT 1")
    assert len(df) == 1
    db.query.assert_called_once_with("SELECT 1", connection="scards", source="tools_api")


def test_execute_sql_query_with_explicit_connection():
    api, db = _api()
    api.execute_sql_query("SELECT 1", connection="other")
    db.query.assert_called_once_with("SELECT 1", connection="other", source="tools_api")


def test_execute_sql_query_returns_empty_df_on_error():
    api, db = _api()
    db.query.side_effect = ValueError("syntax error")
    df = api.execute_sql_query("BAD SQL")
    assert df.empty
    assert "syntax error" in api.last_error


def test_execute_domain_query_passes_kwargs():
    api, db = _api()
    api.execute_domain_query("get_branches", city="Sofia")
    db.execute_domain_query.assert_called_once_with(
        name="get_branches", connection="scards", source="tools_api", city="Sofia"
    )


def test_execute_domain_query_returns_empty_df_on_error():
    api, db = _api()
    db.execute_domain_query.side_effect = ValueError("not found")
    df = api.execute_domain_query("missing")
    assert df.empty
    assert "not found" in api.last_error


def test_get_context_for_llm_delegates():
    api, db = _api()
    ctx = api.get_context_for_llm()
    assert ctx == {"connection_name": "scards"}
    db.get_context_for_llm.assert_called_once_with("scards")


def test_last_error_resets_on_success():
    api, db = _api()
    db.query.side_effect = [ValueError("boom"), pd.DataFrame([{"x": 1}])]
    api.execute_sql_query("BAD")
    assert api.last_error == "boom"
    api.execute_sql_query("GOOD")
    assert api.last_error is None
