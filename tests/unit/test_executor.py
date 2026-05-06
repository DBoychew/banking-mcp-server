"""Tests for banking_mcp.executor — RestrictedPython sandbox safety + happy path."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from banking_mcp.executor import CodeExecutor


@pytest.fixture
def executor():
    db = MagicMock()
    db.get_default_connection.return_value = "scards"
    db.query.return_value = pd.DataFrame([{"x": 1}, {"x": 2}])
    return CodeExecutor(db)


def test_execute_simple_assignment(executor):
    result = executor.execute("result = 1 + 1")
    assert result["success"] is True
    assert result["result"] == 2


def test_execute_uses_pandas(executor):
    code = """
df = pd.DataFrame([{'a': 1}, {'a': 2}, {'a': 3}])
result = int(df['a'].sum())
"""
    out = executor.execute(code)
    assert out["success"] is True
    assert out["result"] == 6


def test_execute_uses_tools_object(executor):
    code = """
df = tools.execute_sql_query("SELECT 1")
result = df.to_dict("records")
"""
    out = executor.execute(code)
    assert out["success"] is True
    assert out["result"] == [{"x": 1}, {"x": 2}]


def test_execute_blocks_forbidden_imports(executor):
    for forbidden in ["os", "subprocess", "sqlite3", "oracledb", "psycopg"]:
        code = f"import {forbidden}\nresult = 1"
        out = executor.execute(code)
        assert out["success"] is False
        assert forbidden in out["error"]


def test_execute_blocks_forbidden_from_imports(executor):
    out = executor.execute("from os import system\nresult = 1")
    assert out["success"] is False
    assert "os" in out["error"]


def test_execute_blocks_importlib_bypass(executor):
    out = executor.execute(
        "import importlib\nresult = importlib.import_module('subprocess').run"
    )
    assert out["success"] is False
    assert "importlib" in out["error"]


def test_execute_returns_error_when_result_missing(executor):
    out = executor.execute("x = 5")
    assert out["success"] is False
    assert "result" in out["error"].lower()


def test_execute_captures_print_as_result(executor):
    out = executor.execute('print("hello world")')
    assert out["success"] is True
    assert "hello" in str(out["result"])


def test_execute_normalizes_smart_quotes(executor):
    # The smart-quote variants should be normalized to ASCII
    code = "result = “hello”.replace(“hello”, “world”)"
    out = executor.execute(code)
    assert out["success"] is True
    assert out["result"] == "world"


def test_execute_returns_runtime_error_message(executor):
    out = executor.execute("result = 1 / 0")
    assert out["success"] is False
    assert "Runtime Error" in out["error"]


def test_execute_supports_loops_and_unpacking(executor):
    code = """
total = 0
for a, b in [(1, 2), (3, 4), (5, 6)]:
    total += a + b
result = total
"""
    out = executor.execute(code)
    assert out["success"] is True
    assert out["result"] == 21


def test_execute_blocks_syntax_errors(executor):
    out = executor.execute("def x(:")
    assert out["success"] is False
    assert "Syntax" in out["error"] or "syntax" in out["error"]
