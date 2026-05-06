"""Tests for multi-DB driver dispatch in banking_mcp.db.manager.

Each driver is exercised by injecting a fake module into ``sys.modules`` so
no real PostgreSQL / MySQL / DuckDB / ClickHouse server is required. The
tests verify:

  1. ``_open_<driver>`` calls the correct entry point with the right args
  2. ``_open_connection`` dispatches by ``db_type``
  3. ``_run_select`` extracts ``(columns, rows)`` correctly per driver
  4. ``_parse_url_dsn`` decodes URL-style DSNs

The full ``query()`` path on top of these is covered by the existing SQLite
suite in test_db_manager.py.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from banking_mcp.db import manager


# ---------------------------------------------------------------------------
# DSN parsing utility
# ---------------------------------------------------------------------------

def test_parse_url_dsn_basic():
    parts = manager._parse_url_dsn("postgresql://alice:secret@db.example.com:5432/analytics")
    assert parts == {
        "user": "alice",
        "password": "secret",
        "host": "db.example.com",
        "port": 5432,
        "database": "analytics",
    }


def test_parse_url_dsn_url_decodes_password():
    parts = manager._parse_url_dsn("mysql://u:p%40ss@host:3306/db")
    assert parts["password"] == "p@ss"


def test_parse_url_dsn_handles_missing_pieces():
    parts = manager._parse_url_dsn("postgresql://host/db")
    assert parts["user"] is None
    assert parts["password"] is None
    assert parts["host"] == "host"
    assert parts["port"] is None
    assert parts["database"] == "db"


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def test_open_postgres_uses_psycopg(monkeypatch):
    captured = {}
    fake_conn = MagicMock(name="pg_conn")

    def fake_connect(dsn):
        captured["dsn"] = dsn
        return fake_conn

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))
    result = manager._open_postgres("postgresql://u:p@h:5432/db")
    assert result is fake_conn
    assert captured["dsn"] == "postgresql://u:p@h:5432/db"


def test_open_postgres_falls_back_to_psycopg2(monkeypatch):
    fake_conn = MagicMock(name="pg2_conn")
    captured = {}

    def fake_connect(dsn):
        captured["dsn"] = dsn
        return fake_conn

    # Force psycopg import to fail
    monkeypatch.setitem(sys.modules, "psycopg", None)
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=fake_connect))
    result = manager._open_postgres("postgresql://u:p@h/db")
    assert result is fake_conn
    assert captured["dsn"] == "postgresql://u:p@h/db"


def test_open_postgres_raises_when_no_driver(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    monkeypatch.setitem(sys.modules, "psycopg2", None)
    with pytest.raises(RuntimeError, match="PostgreSQL driver missing"):
        manager._open_postgres("postgresql://u:p@h/db")


# ---------------------------------------------------------------------------
# MySQL / MariaDB
# ---------------------------------------------------------------------------

def test_open_mysql_parses_url_and_calls_pymysql(monkeypatch):
    captured = {}
    fake_conn = MagicMock(name="mysql_conn")

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return fake_conn

    monkeypatch.setitem(sys.modules, "pymysql", SimpleNamespace(connect=fake_connect))
    result = manager._open_mysql("mysql://root:secret@db.example.com:3307/mydb")
    assert result is fake_conn
    assert captured == {
        "host": "db.example.com",
        "port": 3307,
        "user": "root",
        "password": "secret",
        "database": "mydb",
    }


def test_open_mysql_uses_default_port_when_omitted(monkeypatch):
    captured = {}
    monkeypatch.setitem(
        sys.modules,
        "pymysql",
        SimpleNamespace(connect=lambda **kw: captured.update(kw) or MagicMock()),
    )
    manager._open_mysql("mysql://root@host/mydb")
    assert captured["port"] == 3306


def test_open_mysql_raises_when_driver_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymysql", None)
    with pytest.raises(RuntimeError, match="MySQL driver missing"):
        manager._open_mysql("mysql://u@h/db")


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------

def test_open_duckdb_in_memory(monkeypatch):
    captured = {}
    fake_conn = MagicMock(name="duckdb_conn")

    def fake_connect(path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return fake_conn

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=fake_connect))
    result = manager._open_duckdb("duckdb:///:memory:")
    assert result is fake_conn
    assert captured["path"] == ":memory:"
    # In-memory does not pass read_only=True
    assert "read_only" not in captured["kwargs"]


def test_open_duckdb_file_uses_read_only(monkeypatch):
    captured = {}
    monkeypatch.setitem(
        sys.modules,
        "duckdb",
        SimpleNamespace(connect=lambda p, **kw: captured.update(path=p, kwargs=kw) or MagicMock()),
    )
    manager._open_duckdb("duckdb:///./data/analytics.duckdb")
    assert captured["path"] == "./data/analytics.duckdb"
    assert captured["kwargs"] == {"read_only": True}


def test_open_duckdb_raises_when_driver_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "duckdb", None)
    with pytest.raises(RuntimeError, match="DuckDB driver missing"):
        manager._open_duckdb("duckdb:///./x.db")


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------

def test_open_clickhouse_parses_url_and_calls_get_client(monkeypatch):
    captured = {}
    fake_client = MagicMock(name="ch_client")

    def fake_get_client(**kwargs):
        captured.update(kwargs)
        return fake_client

    monkeypatch.setitem(
        sys.modules, "clickhouse_connect", SimpleNamespace(get_client=fake_get_client)
    )
    result = manager._open_clickhouse("clickhouse://writer:s3cret@ch.example.com:8124/banking")
    assert result is fake_client
    assert captured == {
        "host": "ch.example.com",
        "port": 8124,
        "username": "writer",
        "password": "s3cret",
        "database": "banking",
    }


def test_open_clickhouse_defaults(monkeypatch):
    captured = {}
    monkeypatch.setitem(
        sys.modules,
        "clickhouse_connect",
        SimpleNamespace(get_client=lambda **kw: captured.update(kw) or MagicMock()),
    )
    manager._open_clickhouse("clickhouse://localhost")
    assert captured["host"] == "localhost"
    assert captured["port"] == 8123
    assert captured["username"] == "default"
    assert captured["database"] == "default"


def test_open_clickhouse_raises_when_driver_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "clickhouse_connect", None)
    with pytest.raises(RuntimeError, match="ClickHouse driver missing"):
        manager._open_clickhouse("clickhouse://h")


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "db_type, opener_name",
    [
        ("postgres", "_open_postgres"),
        ("postgresql", "_open_postgres"),
        ("mysql", "_open_mysql"),
        ("mariadb", "_open_mysql"),
        ("duckdb", "_open_duckdb"),
        ("clickhouse", "_open_clickhouse"),
    ],
)
def test_open_connection_dispatches_to_correct_opener(monkeypatch, db_type, opener_name):
    sentinel = MagicMock(name=f"{opener_name}_result")
    monkeypatch.setattr(manager, opener_name, lambda *a, **kw: sentinel)

    out = manager._open_connection({"name": "x", "db_type": db_type, "dsn": "stub"})
    assert out is sentinel


def test_open_connection_rejects_unknown_db_type():
    with pytest.raises(ValueError, match="Unsupported db_type"):
        manager._open_connection({"name": "x", "db_type": "nosuchdb", "dsn": "stub"})


# ---------------------------------------------------------------------------
# _run_select per-driver paths
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, columns, rows):
        self.description = [(c,) for c in columns]
        self._rows = rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self._rows)

    def fetchdf(self):  # for DuckDB style if used
        return self._rows

    def close(self):
        pass


class _FakeDBAPIConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _FakeDuckDBConn:
    """DuckDB returns the cursor directly from ``execute()``."""

    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.last_sql = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        return _FakeCursor(self.columns, self.rows)


class _FakeClickHouseClient:
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = rows
        self.last_sql = None

    def query(self, sql):
        self.last_sql = sql
        return SimpleNamespace(column_names=self._columns, result_rows=self._rows)


def test_run_select_postgres_path():
    cursor = _FakeCursor(["id", "name"], [(1, "A"), (2, "B")])
    conn = _FakeDBAPIConn(cursor)
    cols, rows = manager._run_select(
        {"db_type": "postgres"}, conn, "SELECT id, name FROM t", None
    )
    assert cols == ["id", "name"]
    assert rows == [(1, "A"), (2, "B")]
    assert cursor.executed == [("SELECT id, name FROM t", None)]


def test_run_select_mysql_path_with_params():
    cursor = _FakeCursor(["x"], [(42,)])
    conn = _FakeDBAPIConn(cursor)
    cols, rows = manager._run_select(
        {"db_type": "mysql"}, conn, "SELECT x FROM t WHERE id = :id", {"id": 1}
    )
    assert cols == ["x"]
    assert rows == [(42,)]
    assert cursor.executed == [("SELECT x FROM t WHERE id = :id", {"id": 1})]


def test_run_select_duckdb_path():
    conn = _FakeDuckDBConn(["a"], [("hello",)])
    cols, rows = manager._run_select(
        {"db_type": "duckdb"}, conn, "SELECT 'hello' AS a", None
    )
    assert cols == ["a"]
    assert rows == [("hello",)]
    assert conn.last_sql == "SELECT 'hello' AS a"


def test_run_select_clickhouse_path():
    client = _FakeClickHouseClient(["k", "v"], [("foo", 1), ("bar", 2)])
    cols, rows = manager._run_select(
        {"db_type": "clickhouse"}, client, "SELECT k, v FROM t", None
    )
    assert cols == ["k", "v"]
    assert rows == [("foo", 1), ("bar", 2)]
    assert client.last_sql == "SELECT k, v FROM t"


def test_ping_sql_dialect_selection():
    assert manager._ping_sql("oracle") == "SELECT 1 FROM DUAL"
    assert manager._ping_sql("postgres") == "SELECT 1"
    assert manager._ping_sql("mysql") == "SELECT 1"
    assert manager._ping_sql("clickhouse") == "SELECT 1"
