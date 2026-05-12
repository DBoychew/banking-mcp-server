"""Tests for banking_mcp.tools_api.BankingToolsAPI."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

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


# ---------------------------------------------------------------------------
# classify_transactions (Phase 4)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_txn_df():
    """Mimics what execute_sql_query would return from SCARDS_O.TRANSACTIONS."""
    return pd.DataFrame(
        [
            {"txn_id": 1, "amount": -42.50, "description": "РЕСТОРАНТ ХЕМИНГУЕЙ СОФИЯ"},
            {"txn_id": 2, "amount": 1500.00, "description": "ИЗПЛАТЕНА ЗАПЛАТА СИРМА"},
            {"txn_id": 3, "amount": -120.00, "description": "ЛИДЛ БЪЛГАРИЯ ЕООД"},
            {"txn_id": 4, "amount": -10.00, "description": None},
            {"txn_id": 5, "amount": -55.00, "description": "   "},
            {"txn_id": 6, "amount": -800.00, "description": "НАЕМ АПАРТАМЕНТ"},
        ]
    )


def test_classify_transactions_adds_expected_columns(sample_txn_df):
    api, _ = _api()
    out = api.classify_transactions(sample_txn_df)
    expected = {
        "category_code",
        "category_path",
        "category_score",
        "category_matched_keywords",
        "category_unclassified",
    }
    assert expected.issubset(out.columns)


def test_classify_transactions_assigns_known_categories(sample_txn_df):
    api, _ = _api()
    out = api.classify_transactions(sample_txn_df)
    row = out.set_index("txn_id")
    assert row.loc[1, "category_code"] == "002001001003"  # ресторант
    assert row.loc[2, "category_code"] == "001001001000"  # заплата
    assert row.loc[6, "category_code"] == "001001010000"  # наем


def test_classify_transactions_marks_unclassified(sample_txn_df):
    api, _ = _api()
    out = api.classify_transactions(sample_txn_df)
    row = out.set_index("txn_id")
    # Merchant-only: known Phase 3 gap, expected unclassified.
    assert bool(row.loc[3, "category_unclassified"]) is True
    assert pd.isna(row.loc[3, "category_code"])
    # NaN and whitespace descriptions must be unclassified too.
    assert bool(row.loc[4, "category_unclassified"]) is True
    assert bool(row.loc[5, "category_unclassified"]) is True


def test_classify_transactions_does_not_mutate_input(sample_txn_df):
    api, _ = _api()
    original_cols = list(sample_txn_df.columns)
    api.classify_transactions(sample_txn_df)
    assert list(sample_txn_df.columns) == original_cols


def test_classify_transactions_returns_empty_for_empty_input():
    api, _ = _api()
    out = api.classify_transactions(pd.DataFrame())
    assert out.empty
    assert api.last_error is None


def test_classify_transactions_returns_empty_for_none_input():
    api, _ = _api()
    out = api.classify_transactions(None)  # type: ignore[arg-type]
    assert out.empty
    assert api.last_error is None


def test_classify_transactions_error_on_missing_description_column():
    api, _ = _api()
    df = pd.DataFrame([{"txn_id": 1, "amount": 1.0}])
    out = api.classify_transactions(df, description_column="memo")
    assert out.empty
    assert "memo" in (api.last_error or "")


def test_classify_transactions_error_on_missing_direction_column(sample_txn_df):
    api, _ = _api()
    out = api.classify_transactions(sample_txn_df, direction_column="dir")
    assert out.empty
    assert "dir" in (api.last_error or "")


def test_classify_transactions_respects_direction_column():
    """When direction is supplied per row, classifier filters by it."""
    api, _ = _api()
    df = pd.DataFrame(
        [
            # 'ресторант' only exists in the outgoing taxonomy. Forcing
            # incoming should suppress the match for that row.
            {"txn_id": 1, "description": "РЕСТОРАНТ ХЕМИНГУЕЙ", "dir": "incoming"},
            {"txn_id": 2, "description": "РЕСТОРАНТ ХЕМИНГУЕЙ", "dir": "outgoing"},
        ]
    )
    out = api.classify_transactions(df, direction_column="dir")
    by_id = out.set_index("txn_id")
    assert bool(by_id.loc[1, "category_unclassified"]) is True
    assert by_id.loc[2, "category_code"] == "002001001003"


def test_classify_transactions_unclassified_rate_is_measurable(sample_txn_df):
    """The mean of category_unclassified is the simplest QA signal."""
    api, _ = _api()
    out = api.classify_transactions(sample_txn_df)
    rate = float(out["category_unclassified"].mean())
    # 3 of 6 rows are unclassified (LIDL + NaN + whitespace).
    assert rate == pytest.approx(0.5)


def test_classify_transactions_codes_are_only_from_taxonomy(sample_txn_df):
    """Every non-null category_code must exist in the loaded taxonomy."""
    from banking_mcp.classification import get_index

    api, _ = _api()
    out = api.classify_transactions(sample_txn_df)
    known = get_index().known_codes
    for code in out["category_code"].dropna():
        assert code in known
