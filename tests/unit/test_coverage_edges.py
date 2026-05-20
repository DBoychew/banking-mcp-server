"""Focused tests for defensive and edge paths needed by coverage gates."""

from __future__ import annotations

import asyncio
import datetime
import json
import runpy
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_settings_reject_invalid_transport_and_dirty_mcp_path() -> None:
    from banking_mcp.config import Settings

    with pytest.raises(ValidationError, match="MCP_TRANSPORT"):
        Settings(_env_file=None, MCP_TRANSPORT="ftp")
    with pytest.raises(ValidationError, match="MCP_HTTP_PATH"):
        Settings(_env_file=None, MCP_HTTP_PATH="/mcp?token=x")


def test_stats_ignores_non_positive_row_count() -> None:
    from banking_mcp.classification import stats

    stats.reset()
    stats.record(
        direction="incoming",
        unclassified=True,
        payroll_pattern_hit=True,
        row_count=0,
    )
    assert stats.snapshot()["total"] == 0


def test_keyword_index_skips_invalid_taxonomy_overlay_entries(monkeypatch) -> None:
    from banking_mcp.classification import keyword_index

    categories = {
        "categories": [
            {"full_code": "", "keywords_bg": ["ignored"]},
            {
                "full_code": "001",
                "leaf_name": "Salary",
                "direction": "incoming",
                "keywords_bg": ["", "salary"],
                "main_category": {"name": "Income"},
            },
        ]
    }
    aliases = {
        "aliases": [
            {"code": "missing", "keyword": "x"},
            {"code": "001", "keyword": ""},
            {"code": "001", "keyword": "   "},
            {"code": "001", "keyword": "pay"},
        ],
        "typo_corrections": [
            {"code": "missing", "extra_keywords": ["x"]},
            {"code": "001", "extra_keywords": ["", "wage"]},
        ],
    }
    monkeypatch.setattr(
        keyword_index.categories_loader, "load_categories", lambda: categories
    )
    monkeypatch.setattr(
        keyword_index.categories_loader, "load_merchant_aliases", lambda: aliases
    )
    monkeypatch.setattr(
        keyword_index.categories_loader, "get_payroll_patterns", lambda: []
    )

    index = keyword_index.KeywordIndex()

    result = index.classify("salary wage pay", top_k=5)
    assert result.matches[0].code == "001"
    assert "001" in index.known_codes


def test_payroll_pattern_compile_error_returns_none(monkeypatch) -> None:
    from banking_mcp.classification import keyword_index

    def fail_compile(*_args, **_kwargs):
        raise keyword_index.re.error("bad pattern")

    monkeypatch.setattr(keyword_index.re, "compile", fail_compile)
    assert keyword_index._payroll_pattern_to_regex("PAYROLL_MM_YYYY") is None


def test_schema_fetcher_parse_schema_result_edge_rows() -> None:
    from banking_mcp.db.schema_fetcher import PostgreSQLSchemaFetcher

    rows = [
        {"table_name": "", "column_name": "ignored"},
        {
            "TABLE_NAME": "flags",
            "COLUMN_NAME": "is_active",
            "DATA_TYPE": "BOOLEAN",
            "IS_NULLABLE": False,
        },
        {
            "table_name": "numbers",
            "column_name": "n",
            "data_type": "INTEGER",
            "is_nullable": 1,
        },
    ]

    parsed = PostgreSQLSchemaFetcher().parse_schema_result(rows)

    assert parsed["flags"]["columns"][0]["nullable"] is False
    assert parsed["numbers"]["columns"][0]["nullable"] is True


def test_table_descriptions_loader_cache_reload_and_listing(tmp_path, monkeypatch):
    from banking_mcp.resources import table_descriptions_loader as loader

    monkeypatch.setattr(loader, "_DATA_DIR", tmp_path / "missing")
    loader.reload()
    assert loader.list_described_connections() == []
    assert loader.load_descriptions("missing") == {}

    monkeypatch.setattr(loader, "_DATA_DIR", tmp_path)
    (tmp_path / "scards.json").write_text(
        json.dumps({"CARDS": {"description": "Cards", "columns": {"ID": "Key"}}}),
        encoding="utf-8",
    )
    loader.reload("scards")

    assert loader.list_described_connections() == ["scards"]
    assert loader.load_descriptions("scards")["CARDS"]["columns"]["ID"] == "Key"


def test_glossary_loader_find_reload_and_missing_file(tmp_path, monkeypatch):
    from banking_mcp.resources import glossary_loader

    data_file = tmp_path / "glossary.json"
    data_file.write_text(
        json.dumps({"terms": [{"term": "BIN", "definition": "Bank ID"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(glossary_loader, "DATA_FILE", data_file)
    glossary_loader.reload()

    assert glossary_loader.get_terms()[0]["term"] == "BIN"
    assert glossary_loader.find_term(" bin ")["definition"] == "Bank ID"
    assert glossary_loader.find_term("missing") is None

    monkeypatch.setattr(glossary_loader, "DATA_FILE", tmp_path / "missing.json")
    glossary_loader.reload()
    with pytest.raises(FileNotFoundError):
        glossary_loader.load_glossary()


def test_categories_loader_missing_alias_file(tmp_path, monkeypatch):
    from banking_mcp.resources import categories_loader

    original_aliases_file = categories_loader.ALIASES_FILE
    monkeypatch.setattr(categories_loader, "ALIASES_FILE", tmp_path / "aliases.json")
    categories_loader.reload_all()
    assert categories_loader.load_merchant_aliases() == {
        "version": "0",
        "aliases": [],
        "typo_corrections": [],
    }
    monkeypatch.setattr(categories_loader, "ALIASES_FILE", original_aliases_file)
    categories_loader.reload_all()


def test_tools_api_reports_missing_default_connection() -> None:
    import pandas as pd

    from banking_mcp.tools_api import BankingToolsAPI

    db = MagicMock()
    db.get_default_connection.return_value = None
    api = BankingToolsAPI(db)

    assert api.execute_sql_query("SELECT 1").empty
    assert "No connection specified" in api.last_error
    assert api.execute_domain_query("x").empty
    assert "No connection specified" in api.last_error
    assert isinstance(api.classify_transactions(pd.DataFrame()), pd.DataFrame)


def test_dashboard_singleton_uses_configured_manager(monkeypatch):
    import banking_mcp.dashboard as dashboard

    class FakeDashboardManager:
        pass

    monkeypatch.setattr(dashboard, "_manager", None)
    monkeypatch.setattr(dashboard, "DashboardManager", FakeDashboardManager)

    first = dashboard.get_dashboard_manager()
    second = dashboard.get_dashboard_manager()

    assert isinstance(first, FakeDashboardManager)
    assert second is first


def test_dashboard_generator_filter_default_branches() -> None:
    from banking_mcp.dashboard.generator import StreamlitGenerator
    from banking_mcp.dashboard.widgets import GlobalFilter, WidgetFilter

    gen = StreamlitGenerator()

    date_lines = gen._generate_filter_code(
        GlobalFilter("date_range", "period", "Period"), is_global=True
    )
    select_lines = gen._generate_filter_code(
        GlobalFilter("selectbox", "region", "Region", options=["EU", "US"], default="US"),
        is_global=True,
    )
    multi_lines = gen._generate_filter_code(
        WidgetFilter("multiselect", "channels", "Channels", options=["atm", "pos"]),
        widget_id="w1",
    )

    assert any("period_period = st.sidebar.selectbox" in line for line in date_lines)
    assert "index=1," in "\n".join(select_lines)
    assert "default=['atm', 'pos']" in "\n".join(multi_lines)


@pytest.fixture
def dashboard_manager(tmp_path: Path):
    from banking_mcp.dashboard.manager import DashboardManager

    return DashboardManager(base_path=tmp_path)


def test_dashboard_manager_state_and_widget_edge_paths(dashboard_manager) -> None:
    state_file = dashboard_manager._get_state_file("default")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{bad json", encoding="utf-8")
    assert dashboard_manager.load_state().widgets == []

    ok, _, widget = dashboard_manager.add_widget(
        title="A",
        widget_type="metric",
        python_code="st.write(1)",
        filters=[{"filter_type": "slider", "variable_name": "x", "label": "X"}],
        position=99,
    )
    assert ok
    assert widget.position == 0
    assert widget.filters[0].variable_name == "x"

    ok, msg, _ = dashboard_manager.update_widget(widget.id, widget_type="bad")
    assert not ok
    assert "Invalid widget type" in msg

    ok, msg, _ = dashboard_manager.update_widget(widget.id, python_code="return 1")
    assert not ok
    assert "return" in msg

    ok, _, updated = dashboard_manager.update_widget(
        widget.id,
        description="desc",
        filters=[{"filter_type": "selectbox", "variable_name": "r", "label": "R"}],
    )
    assert ok
    assert updated.description == "desc"
    assert updated.filters[0].variable_name == "r"

    dashboard_manager.add_widget("B", "metric", "st.write(2)")
    ok, _, moved = dashboard_manager.update_widget(widget.id, position=1)
    assert ok
    assert moved.position == 1

    ok, msg = dashboard_manager.remove_widget("missing")
    assert not ok
    assert "Available" in msg


def test_dashboard_manager_filter_layout_clear_edges(dashboard_manager) -> None:
    ok, msg = dashboard_manager.set_global_filter("bad", "x", "X")
    assert not ok
    assert "Invalid filter type" in msg

    ok, msg = dashboard_manager.remove_global_filter("missing")
    assert not ok
    assert "Available" in msg

    dashboard_manager.set_global_filter("selectbox", "region", "Region", ["EU"])
    ok, msg = dashboard_manager.remove_global_filter("region")
    assert ok
    assert "removed" in msg

    ok, msg = dashboard_manager.clear_all_widgets()
    assert ok
    assert msg == "Dashboard is already empty"


def test_widget_filter_and_state_from_dict_defaults() -> None:
    from banking_mcp.dashboard.widgets import DashboardState, WidgetFilter

    f = WidgetFilter.from_dict(
        {
            "filter_type": "slider",
            "variable_name": "amount",
            "label": "Amount",
            "min_value": 1,
            "max_value": 10,
        }
    )
    assert f.to_dict()["default"] is None

    state = DashboardState.from_dict({})
    assert state.dashboard_id == "default"
    assert state.title == "Dashboard"


def test_audit_start_enqueue_and_purge_edges(tmp_path, monkeypatch) -> None:
    from banking_mcp.audit import logger as audit

    monkeypatch.setattr(
        audit, "_writer_thread", SimpleNamespace(is_alive=lambda: True)
    )
    audit.start()

    monkeypatch.setattr(audit.settings, "AUDIT_ENABLED", True)
    monkeypatch.setattr(
        audit, "_writer_thread", SimpleNamespace(is_alive=lambda: True)
    )

    class FullQueue:
        def put_nowait(self, _record):
            raise RuntimeError("full")

    monkeypatch.setattr(audit, "_queue", FullQueue())
    asyncio.run(
        audit.log_error(context="/boom", error="card 4111111111111111", details={"x": 1})
    )

    old = tmp_path / (
        "audit."
        + (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        + ".log"
    )
    current = tmp_path / f"audit.{datetime.date.today().isoformat()}.log"
    bad = tmp_path / "audit.not-a-date.log"
    old.write_text("old", encoding="utf-8")
    current.write_text("now", encoding="utf-8")
    bad.write_text("bad", encoding="utf-8")
    monkeypatch.setattr(audit.settings, "AUDIT_LOG_RETENTION_DAYS", 1)

    audit._purge_old_logs(current)

    assert not old.exists()
    assert bad.exists()


def test_audit_writer_loop_rotates_and_logs_errors(tmp_path, monkeypatch) -> None:
    from banking_mcp.audit import logger as audit

    q = Queue()
    q.put({"event": 1})
    q.put({"event": 2})
    paths = [tmp_path / "audit.1.log", tmp_path / "audit.2.log"]
    monkeypatch.setattr(audit, "_queue", q)
    monkeypatch.setattr(audit, "_current_log_path", lambda: paths.pop(0))
    monkeypatch.setattr(audit, "_purge_old_logs", lambda _path: None)
    audit._stop_event.set()

    audit._writer_loop()

    assert (tmp_path / "audit.1.log").exists()
    assert (tmp_path / "audit.2.log").exists()

    q = Queue()
    q.put({"event": "bad"})
    warnings = []
    monkeypatch.setattr(audit, "_queue", q)
    monkeypatch.setattr(
        audit,
        "_current_log_path",
        lambda: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    monkeypatch.setattr(audit.logger, "warning", lambda msg, exc: warnings.append((msg, exc)))
    audit._stop_event.set()

    audit._writer_loop()
    audit._stop_event.clear()

    assert warnings


def test_db_config_error_and_crud_edges(tmp_path, monkeypatch) -> None:
    from banking_mcp.db import config as db_config

    class BadConfigFile:
        def exists(self):
            return True

        def read_text(self, **_kwargs):
            raise OSError("denied")

        def __str__(self):
            return "bad-config.json"

    monkeypatch.setattr(db_config, "CONFIG_FILE", BadConfigFile())
    with pytest.raises(RuntimeError, match="Could not read"):
        db_config.load_config()

    monkeypatch.setattr(db_config, "CONFIG_FILE", tmp_path / "fresh.json")
    conn = db_config.add_connection("one", "sqlite:///one.db", schema="main")
    assert conn["schema"] == "main"
    assert conn["is_default"] is False

    config = db_config.load_config()
    config["default_connection"] = ""
    db_config.save_config(config)
    conn = db_config.add_connection("two", "sqlite:///two.db")
    assert conn["is_default"] is True

    db_config.add_domain_query("two", "q", {"sql": "SELECT 1"})
    assert db_config.remove_connection("two") is True
    assert db_config.get_default_connection() == "scards"
    assert "two" not in db_config.load_config().get("domain_queries", {})

    with pytest.raises(ValueError, match="does not exist"):
        db_config.update_schema_filter("missing", {})
    db_config.update_schema_filter("one", {"include": ["A*"], "exclude": []})
    assert db_config.get_connection("one")["schema_filter"]["include"] == ["A*"]
    with pytest.raises(ValueError, match="does not exist"):
        db_config.add_domain_query("missing", "q", {"sql": "SELECT 1"})
    assert db_config.remove_domain_query("one", "missing") is False


def test_db_config_parse_compact_params_all_value_types() -> None:
    from banking_mcp.db import config as db_config

    parsed = []
    for spec in (
        'choice="A"|"B" (pick)',
        "flag=true",
        "ratio=1.5",
        "bad_float=1.x",
        "count=7",
        "name=abc",
    ):
        parsed.extend(db_config.parse_compact_params(spec))
    by_name = {p["name"]: p for p in parsed}

    assert by_name["choice"]["default"] == "A"
    assert by_name["flag"]["default"] is True
    assert by_name["ratio"]["default"] == 1.5
    assert by_name["bad_float"]["default"] == "1.x"
    assert by_name["count"]["default"] == 7
    assert by_name["name"]["default"] == "abc"
    assert db_config.parse_compact_params("broken") == []

    list_parsed = db_config.parse_compact_params(
        [{"name": "x", "type": "int", "default": 1, "description": "X"}]
    )
    assert list_parsed[0]["description"] == "X"


class _FakeCursor:
    def __init__(self, columns=None, rows=None, fail_close=False):
        self.description = [(c,) for c in (columns or [])]
        self.rows = rows or []
        self.executions = []
        self.fail_close = fail_close

    def execute(self, sql, params=None):
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows

    def close(self):
        if self.fail_close:
            raise RuntimeError("close failed")


class _FakeConn:
    def __init__(self, cursor=None):
        self.cursor_obj = cursor or _FakeCursor(["x"], [(1,)])
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _bare_db(monkeypatch):
    from banking_mcp.db import manager

    db = manager.DatabaseManager.__new__(manager.DatabaseManager)
    db.schema_cache = {}
    return db


def test_db_manager_dsn_oracle_and_validation_edges(monkeypatch) -> None:
    from banking_mcp.db import manager

    assert manager._resolve_config_value("${MISSING_ENV}") == "${MISSING_ENV}"
    assert manager._quote_oracle_identifier("scards") == "SCARDS"
    assert manager._quote_oracle_identifier("mixed schema") == '"mixed schema"'
    with pytest.raises(ValueError, match="empty"):
        manager._quote_oracle_identifier(" ")
    with pytest.raises(ValueError, match="unsupported"):
        manager._quote_oracle_identifier('bad"name')

    monkeypatch.setattr(manager.settings, "ORACLE_SCHEMA", "")
    assert manager._get_oracle_schema({}) is None
    monkeypatch.setenv("EMPTY_SCHEMA", "")
    assert manager._get_oracle_schema({"schema": "${EMPTY_SCHEMA}"}) is None
    assert manager._get_oracle_schema({"schema": "Mixed Schema"}) == "Mixed Schema"

    monkeypatch.setattr(manager.settings, "ORACLE_USER", "")
    monkeypatch.setattr(manager.settings, "ORACLE_PASSWORD", "")
    assert manager._get_oracle_connect_args(
        {"dsn": "user/pass@host:1521/service"}
    ) == ("host:1521/service", "user", "pass")
    with pytest.raises(ValueError, match="DSN"):
        manager._get_oracle_connect_args({"dsn": ""})
    with pytest.raises(ValueError, match="credentials"):
        manager._get_oracle_connect_args({"dsn": "host:1521/service"})

    sentinel = object()
    monkeypatch.setattr(manager, "_open_sqlite", lambda dsn: sentinel)
    assert manager._open_connection(
        {"db_type": "sqlite", "dsn": "${MISSING_DSN}"}
    ) is sentinel

    captured = {}
    monkeypatch.setitem(
        sys.modules,
        "duckdb",
        SimpleNamespace(connect=lambda path, **kw: captured.update(path=path, kwargs=kw) or sentinel),
    )
    assert manager._open_duckdb("duckdb://warehouse.duckdb") is sentinel
    assert captured == {"path": "warehouse.duckdb", "kwargs": {"read_only": True}}
    assert manager._open_duckdb("plain.duckdb") is sentinel
    assert captured == {"path": "plain.duckdb", "kwargs": {"read_only": True}}

    manager._close_quietly(_FakeCursor(fail_close=True))

    db = _bare_db(monkeypatch)
    with pytest.raises(ValueError, match="empty"):
        db._validate_sql("/* comment */ -- line")
    with pytest.raises(ValueError, match="read-only"):
        db._validate_sql("SHOW TABLES")


def test_db_manager_query_and_execute_error_edges(monkeypatch) -> None:
    from banking_mcp.db import manager

    db = _bare_db(monkeypatch)
    monkeypatch.setattr(manager, "get_default_connection", lambda: None)
    with pytest.raises(ValueError, match="No connection"):
        db.query("SELECT 1")
    with pytest.raises(ValueError, match="No connection"):
        db.execute_domain_query("q")
    with pytest.raises(ValueError, match="No connection"):
        db.get_schema()
    with pytest.raises(ValueError, match="No connection"):
        db.get_table_list()
    with pytest.raises(ValueError, match="No connection"):
        db.get_table_columns(table_name="T")
    with pytest.raises(ValueError, match="No connection"):
        db.get_table_comments(table_name="T")
    with pytest.raises(ValueError, match="No connection"):
        db.get_table_keys(table_name="T")
    with pytest.raises(ValueError, match="No connection"):
        db.get_schema_keys()
    with pytest.raises(ValueError, match="No connection"):
        db.get_context_for_llm()

    monkeypatch.setattr(manager, "get_default_connection", lambda: "missing")
    monkeypatch.setattr(manager, "get_connection", lambda _name: None)
    with pytest.raises(ValueError, match="not found"):
        db.query("SELECT 1")
    with pytest.raises(KeyError, match="missing"):
        db.execute_sql("SELECT 1")
    with pytest.raises(ValueError, match="not found"):
        db._fetch_schema("missing")
    with pytest.raises(ValueError, match="not found"):
        db.get_table_comments("missing", "T")
    with pytest.raises(ValueError, match="not found"):
        db.get_table_keys("missing", "T")
    with pytest.raises(ValueError, match="not found"):
        db.get_schema_keys("missing")
    with pytest.raises(ValueError, match="not found"):
        db.get_context_for_llm("missing")

    logs = []
    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda _name: {"name": "x", "db_type": "sqlite", "dsn": "sqlite:///:memory:"},
    )
    monkeypatch.setattr(manager, "_open_connection", lambda _info: _FakeConn())
    monkeypatch.setattr(
        manager,
        "_run_select",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(manager, "log_query", lambda **kwargs: logs.append(kwargs))
    with pytest.raises(RuntimeError, match="db down"):
        db.query("SELECT 1")
    assert logs[-1]["status"] == "error"

    monkeypatch.setattr(
        manager,
        "_open_connection",
        lambda _info: (_ for _ in ()).throw(RuntimeError("connect failed")),
    )
    assert db.test_connection("x") is False


def test_db_manager_schema_fetching_table_and_wrapper_edges(monkeypatch, tmp_path):
    from banking_mcp.db import manager

    db = _bare_db(monkeypatch)
    monkeypatch.setattr(manager, "SCHEMA_CACHE_FILE", tmp_path / "schema_cache.json")
    monkeypatch.setattr(manager, "get_default_connection", lambda: "x")

    db.schema_cache["x"] = {
        "schema": "ignored line\nACCOUNTS: ID(NUMBER(10,0)), NAME(VARCHAR2(20))",
        "cached_at": datetime.datetime.now().isoformat(),
    }
    assert db.get_schema("x") == db.schema_cache["x"]["schema"]
    with monkeypatch.context() as mp:
        mp.setattr(
            manager.DatabaseManager,
            "_fetch_schema",
            lambda self, conn: db.schema_cache[conn]["schema"],
        )
        assert "ACCOUNTS:" in db.refresh_schema("x")
    assert db.get_table_list("x") == ["ACCOUNTS"]
    assert db.get_table_columns("x", "accounts") == [
        {"name": "ID", "type": "NUMBER(10,0)"},
        {"name": "NAME", "type": "VARCHAR2(20)"},
    ]
    assert db.get_table_columns("x", "missing") is None
    assert manager.DatabaseManager._parse_column_list("not a column") == []

    bad_cache = tmp_path / "bad_schema_cache.json"
    bad_cache.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(manager, "SCHEMA_CACHE_FILE", bad_cache)
    assert db._load_schema_cache() == {}

    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "oracle", "dsn": "h/s", "schema": "S"},
    )
    monkeypatch.setattr(manager, "_open_connection", lambda _info: _FakeConn())

    def oracle_rows(_conn_info, _db_conn, sql, params=None):
        assert params == {"owner": "S"}
        return [], [("T", "ID", "NUMBER", None, 10, 0)]

    monkeypatch.setattr(manager, "_run_select", oracle_rows)
    assert db._fetch_schema("x") == "T: ID(NUMBER(10))"

    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "oracle", "dsn": "h/s", "schema": ""},
    )
    monkeypatch.setattr(manager.settings, "ORACLE_SCHEMA", "")
    monkeypatch.setattr(
        manager,
        "_run_select",
        lambda *_args, **_kwargs: ([], [("T", "C", "VARCHAR2", 4, None, None)]),
    )
    assert db._fetch_schema("x") == "T: C(VARCHAR2(4))"

    class FakeFetcher:
        def get_schema_query(self):
            return "SELECT schema"

        def parse_schema_result(self, rows):
            return {
                row["table_name"]: {
                    "name": row["table_name"],
                    "columns": [{"name": row["column_name"], "type": row["data_type"]}],
                    "row_count": None,
                }
                for row in rows
            }

        def format_compact_schema(self, tables):
            return "|".join(sorted(tables))

    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {
            "name": name,
            "db_type": "postgres",
            "dsn": "postgres://h/db",
            "schema_filter": {"include": ["A*"], "exclude": []},
        },
    )
    monkeypatch.setattr(manager, "get_schema_fetcher", lambda _db_type: FakeFetcher())
    monkeypatch.setattr(
        manager,
        "_run_select",
        lambda *_args, **_kwargs: (
            ["table_name", "column_name", "data_type"],
            [("ACCOUNTS", "ID", "INTEGER"), ("CARDS", "ID", "INTEGER")],
        ),
    )
    assert db._fetch_schema("x") == "ACCOUNTS"

    monkeypatch.setattr(manager, "_run_select", lambda *_args, **_kwargs: ([], []))
    assert db._fetch_schema("x") == ""


def test_db_manager_comments_keys_context_and_config_wrappers(monkeypatch, tmp_path):
    from banking_mcp.db import manager

    db = _bare_db(monkeypatch)
    monkeypatch.setattr(manager, "SCHEMA_CACHE_FILE", tmp_path / "schema_cache.json")
    monkeypatch.setattr(manager, "_open_connection", lambda _info: _FakeConn())

    monkeypatch.setattr(
        manager,
        "get_connection",
        lambda name: {"name": name, "db_type": "sqlite", "dsn": "sqlite:///:memory:"},
    )
    assert db.get_table_comments("lite", "T") == {}
    assert db.get_table_keys("lite", "T") == {}
    assert db.get_schema_keys("lite") == {}

    conn_info = {
        "name": "scards",
        "db_type": "oracle",
        "dsn": "h/s",
        "schema": "",
        "schema_filter": {"include": [], "exclude": []},
    }
    monkeypatch.setattr(manager, "get_default_connection", lambda: "scards")
    monkeypatch.setattr(manager, "get_connection", lambda _name: conn_info)
    monkeypatch.setattr(manager.settings, "ORACLE_SCHEMA", "")

    def comments_run_select(_conn_info, _db_conn, sql, params=None):
        if "tab_comments" in sql:
            return [], [("Table comment",)]
        return [], [("ID", "Identifier"), ("EMPTY", None)]

    monkeypatch.setattr(manager, "_run_select", comments_run_select)
    assert db.get_table_comments("scards", "cards") == {
        "table": "Table comment",
        "columns": {"ID": "Identifier"},
    }

    schema_params = []

    def schema_comments_run_select(_conn_info, _db_conn, sql, params=None):
        schema_params.append(params)
        if "tab_comments" in sql:
            return [], [("Schema table comment",)]
        return [], [("ID", "Schema identifier")]

    schema_conn_info = {**conn_info, "schema": "S"}
    monkeypatch.setattr(manager, "get_connection", lambda _name: schema_conn_info)
    monkeypatch.setattr(manager, "_run_select", schema_comments_run_select)
    assert db.get_table_comments("scards", "cards")["table"] == "Schema table comment"
    assert schema_params == [
        {"owner": "S", "t": "CARDS"},
        {"owner": "S", "t": "CARDS"},
    ]

    monkeypatch.setattr(manager, "get_connection", lambda _name: conn_info)

    fake, _calls = _table_key_dispatch_for_edges()
    monkeypatch.setattr(manager, "_run_select", fake)
    keys = db.get_table_keys("scards", "cards")
    assert keys["primary_key"] is None
    assert keys["foreign_keys"][0]["references"]["table"] is None

    def schema_keys_run_select(_conn_info, _db_conn, sql, params=None):
        if "constraint_type = 'P'" in sql:
            return [], [("T", "PK_T", "ID")]
        return [], [("T", "FK_T", "PARENT_ID", None, "PARENT", "ID", None)]

    monkeypatch.setattr(manager, "_run_select", schema_keys_run_select)
    assert db.get_schema_keys("scards")["primary_keys"]["T"]["columns"] == ["ID"]

    monkeypatch.setattr(manager, "config_list_connections", lambda: [{"name": "scards"}])
    assert db.list_connections() == ["scards"]
    monkeypatch.setattr(manager, "get_connection", lambda name: {"name": name})
    assert db.get_connection_info("x") == {"name": "x"}
    monkeypatch.setattr(manager, "get_default_connection", lambda: "scards")
    assert db.get_default_connection() == "scards"

    monkeypatch.setattr(manager, "config_add_connection", lambda **kwargs: kwargs)
    assert db.add_connection("n", "dsn")["name"] == "n"
    monkeypatch.setattr(manager, "config_remove_connection", lambda name: True)
    db.schema_cache["old"] = {"schema": "x"}
    assert db.remove_connection("old") is True
    assert "old" not in db.schema_cache

    called = {}
    monkeypatch.setattr(
        manager, "config_set_default_connection", lambda name: called.setdefault("default", name)
    )
    db.set_default_connection("scards")
    assert called["default"] == "scards"

    monkeypatch.setattr(
        manager, "update_schema_filter", lambda connection, schema_filter: called.update(filter=connection)
    )
    db.schema_cache["scards"] = {"schema": "x"}
    db.update_schema_filter("scards", {"include": ["*"], "exclude": []})
    assert "scards" not in db.schema_cache

    queries = {
        "q": {
            "description": "desc",
            "parameters": "days=7",
            "returns": "rows",
        }
    }
    monkeypatch.setattr(manager, "get_domain_queries", lambda _conn: queries)
    assert db.list_domain_queries("scards") == ["q"]
    assert db.get_domain_queries_info("scards")[0]["example"] == (
        "tools.execute_domain_query('q', days)"
    )

    monkeypatch.setattr(
        manager, "config_add_domain_query", lambda connection, name, query_def: called.update(domain=name)
    )
    db.add_domain_query("scards", "new", {"sql": "SELECT 1"})
    assert called["domain"] == "new"
    monkeypatch.setattr(manager, "config_remove_domain_query", lambda connection, name: False)
    assert db.remove_domain_query("scards", "missing") is False

    monkeypatch.setattr(manager, "get_connection", lambda name: {"name": name, "db_type": "unknown"})
    monkeypatch.setattr(manager.DatabaseManager, "get_schema", lambda self, connection=None, force_refresh=False: "")
    monkeypatch.setattr(manager.DatabaseManager, "list_connections", lambda self: ["scards"])
    ctx = db.get_context_for_llm("scards")
    assert ctx["sql_dialect_hint"] == "Standard SQL"

    monkeypatch.setattr(
        manager.DatabaseManager,
        "shutdown",
        lambda self: (_ for _ in ()).throw(RuntimeError("ignored")),
    )
    db.__del__()


def _table_key_dispatch_for_edges():
    calls = []

    def fake_run_select(_conn_info, _db_conn, sql, params=None):
        calls.append((sql, params))
        if "constraint_name = :cname" in sql:
            return [], []
        if "cons_columns" in sql:
            return [], [("FK_T", "PARENT_ID", 1)]
        return [], [("FK_T", "R", None, "PK_PARENT", None)]

    return fake_run_select, calls


def test_db_manager_execute_domain_query_uses_defaults(monkeypatch) -> None:
    from banking_mcp.db import manager

    db = _bare_db(monkeypatch)
    monkeypatch.setattr(manager, "get_default_connection", lambda: "scards")
    monkeypatch.setattr(
        manager,
        "get_domain_queries",
        lambda _conn: {"q": {"sql": "SELECT :days", "params": "days=30 (lookback)"}},
    )
    captured = {}
    monkeypatch.setattr(
        manager.DatabaseManager,
        "execute_sql",
        lambda self, sql, connection=None, **params: captured.update(sql=sql, connection=connection, params=params)
        or [{"days": params["days"]}],
    )

    out = db.execute_domain_query("q")

    assert out.to_dict("records") == [{"days": 30}]
    assert captured == {
        "sql": "SELECT :days",
        "connection": "scards",
        "params": {"days": 30},
    }


def test_executor_helper_edges(monkeypatch) -> None:
    import numpy as np

    from banking_mcp import executor as executor_mod

    assert executor_mod._inplacevar("+=", 1, 2) == 3
    with pytest.raises(ValueError, match="Unsupported"):
        executor_mod._inplacevar("&=", 1, 2)
    assert executor_mod._write_({"x": 1}) == {"x": 1}
    assert executor_mod._write_(3) == 3
    assert executor_mod._apply_(lambda x: x + 1, 1) == 2
    with pytest.raises(ImportError, match="Imports are not allowed"):
        executor_mod._blocked_import()

    array = np.array([1, 2])
    assert executor_mod.SafeJSON._default_serializer(array) == [1, 2]

    class ItemOnly:
        def item(self):
            return "item-value"

    class StringOnly:
        def __str__(self):
            return "string-value"

    assert executor_mod.SafeJSON._default_serializer(ItemOnly()) == "item-value"
    today = datetime.date(2026, 1, 2)
    assert executor_mod.SafeJSON._default_serializer(today) == "2026-01-02"
    assert executor_mod.SafeJSON._default_serializer(StringOnly()) == "string-value"
    assert executor_mod.SafeJSON.dumps({"x": np.int64(1)}) == '{"x": 1}'
    assert executor_mod.SafeJSON.loads('{"x": 1}') == {"x": 1}

    db = MagicMock()
    db.get_default_connection.return_value = "scards"
    code_executor = executor_mod.CodeExecutor(db)
    fixed = code_executor._fix_multiline_fstrings('result = f"a\\n{1}"')
    assert 'f"""a\\n{1}"""' in fixed
    fixed_single = code_executor._fix_multiline_fstrings("result = f'a\\n{1}'")
    assert "f'''a\\n{1}'''" in fixed_single

    monkeypatch.setattr(
        executor_mod,
        "compile_restricted",
        lambda *_args, **_kwargs: SimpleNamespace(errors=["bad syntax"]),
    )
    assert code_executor.execute("result = 1") == {
        "success": False,
        "error": "Syntax Error: ['bad syntax']",
    }


def test_executor_printed_variable_becomes_result(monkeypatch) -> None:
    from banking_mcp import executor as executor_mod

    db = MagicMock()
    db.get_default_connection.return_value = "scards"
    monkeypatch.setattr(
        executor_mod,
        "compile_restricted",
        lambda *_args, **_kwargs: compile(
            'printed = "manual output"', "<inline code>", "exec"
        ),
    )
    out = executor_mod.CodeExecutor(db).execute("x = 1")
    assert out["success"] is True
    assert out["result"] == "manual output"


class _FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self, *_, **__):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri, *_, **__):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator


def test_db_tool_table_list_and_table_info_edges(monkeypatch) -> None:
    from banking_mcp.tools import db_tools

    fake_mcp = _FakeMCP()
    db = MagicMock()
    db.get_default_connection.return_value = "scards"
    db.get_table_list.return_value = ["ACCOUNTS", "CARDS"]
    db.get_table_columns.return_value = [{"name": "ID", "type": "NUMBER"}]
    db.get_table_comments.return_value = {
        "table": "Accounts",
        "columns": {"ID": "Identifier"},
    }
    monkeypatch.setattr(db_tools, "get_manager", lambda: db)
    db_tools.register_db_tools(fake_mcp)

    out = json.loads(fake_mcp.tools["get_database_table_list"](""))
    assert out["table_count"] == 2
    db.get_table_list.assert_called_with("scards")

    out = json.loads(fake_mcp.tools["get_table_info"]("ACCOUNTS", ""))
    assert out["columns"][0]["description"] == "Identifier"

    db.get_table_columns.return_value = None
    out = json.loads(fake_mcp.tools["get_table_info"]("MISSING", "scards"))
    assert "available_tables" in out

    db.get_default_connection.return_value = None
    assert "error" in json.loads(fake_mcp.tools["get_database_table_list"](""))
    assert "error" in json.loads(fake_mcp.tools["get_table_info"]("T", ""))

    db.get_default_connection.return_value = "scards"
    db.get_table_list.side_effect = RuntimeError("list failed")
    assert json.loads(fake_mcp.tools["get_database_table_list"]("scards"))["error"] == "list failed"
    db.get_table_columns.side_effect = RuntimeError("columns failed")
    assert json.loads(fake_mcp.tools["get_table_info"]("T", "scards"))["error"] == "columns failed"


def test_dashboard_tools_success_and_error_paths(monkeypatch) -> None:
    from banking_mcp.tools import dashboard_tools

    fake_mcp = _FakeMCP()

    class WidgetObj:
        id = "w1"

        def to_dict(self):
            return {"id": self.id}

    manager = MagicMock()
    manager.add_widget.return_value = (True, "added", WidgetObj())
    manager.view_dashboard.return_value = {
        "widget_count": 1,
        "app_path": "app.py",
        "widgets": [],
    }
    manager.update_widget.return_value = (True, "updated", WidgetObj())
    manager.remove_widget.return_value = (False, "missing")
    monkeypatch.setattr(dashboard_tools, "get_dashboard_manager", lambda: manager)
    monkeypatch.setattr(dashboard_tools.settings, "DASHBOARD_URL", "http://dash")
    dashboard_tools.register_dashboard_tools(fake_mcp)

    add_out = json.loads(
        fake_mcp.tools["dashboard_add_widget"]("T", "metric", "st.write(1)")
    )
    assert add_out["status"] == "success"
    assert add_out["dashboard_access"]["url"] == "http://dash"

    manager.add_widget.return_value = (False, "bad", None)
    assert json.loads(
        fake_mcp.tools["dashboard_add_widget"]("T", "bad", "x")
    )["status"] == "error"

    update_out = json.loads(fake_mcp.tools["dashboard_update_widget"]("w1"))
    assert update_out["widget"] == {"id": "w1"}
    manager.update_widget.return_value = (False, "bad update", None)
    assert json.loads(fake_mcp.tools["dashboard_update_widget"]("w1"))["status"] == "error"

    remove_out = json.loads(fake_mcp.tools["dashboard_remove_widget"]("w1"))
    assert remove_out == {"status": "error", "message": "missing"}

    view_out = json.loads(fake_mcp.tools["dashboard_view"]())
    assert view_out["how_to_run"] == "streamlit run app.py"
    assert view_out["dashboard_access"]["url"] == "http://dash"


def test_classification_tool_invalid_top_k_falls_back(monkeypatch) -> None:
    from banking_mcp.tools import classification_tools

    fake_mcp = _FakeMCP()
    captured = {}

    class Result:
        def to_dict(self):
            return {"ok": True}

    def fake_classify(**kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(classification_tools, "classify", fake_classify)
    classification_tools.register_classification_tools(fake_mcp)
    assert json.loads(fake_mcp.tools["classify_description"]("text", top_k="bad")) == {
        "ok": True
    }
    assert captured["top_k"] == 3


def test_banking_resources_table_descriptions(monkeypatch) -> None:
    from banking_mcp.resources import banking_resources

    fake_mcp = _FakeMCP()
    monkeypatch.setattr(
        banking_resources.table_descriptions_loader,
        "load_descriptions",
        lambda connection: {"T": {"description": connection}},
    )
    monkeypatch.setattr(banking_resources, "get_manager", lambda: MagicMock())
    banking_resources.register_banking_resources(fake_mcp)

    out = json.loads(fake_mcp.resources["banking://table-descriptions/{connection}"]("scards"))
    assert out["table_count"] == 1
    assert out["tables"]["T"]["description"] == "scards"


def test_main_entrypoint_paths(monkeypatch) -> None:
    import banking_mcp.config as config
    import banking_mcp.server as server
    import main as main_module

    calls = []
    monkeypatch.setattr(server, "run_stdio", lambda: calls.append("stdio"))
    monkeypatch.setattr(server, "run_http", lambda: calls.append("http"))

    monkeypatch.setattr(sys, "argv", ["main.py", "bad"])
    with pytest.raises(SystemExit):
        main_module.main()

    monkeypatch.setattr(sys, "argv", ["main.py", "http"])
    main_module.main()
    assert calls[-1] == "http"
    assert config.settings.MCP_TRANSPORT == "http"

    monkeypatch.setattr(sys, "argv", ["main.py", "stdio"])
    runpy.run_module("main", run_name="__main__")
    assert calls[-1] == "stdio"


def test_server_streamlit_lifecycle_and_run_edges(monkeypatch, tmp_path):
    import banking_mcp.server as server

    monkeypatch.setattr(server.settings, "DASHBOARD_AUTOSTART", False)
    assert server._start_streamlit_subprocess() is None

    monkeypatch.setattr(server.settings, "DASHBOARD_AUTOSTART", True)
    monkeypatch.setattr(server.settings, "MCP_TRANSPORT", "stdio")
    assert server._start_streamlit_subprocess() is None

    app_file = tmp_path / "dashboards" / "default" / "app.py"

    class FakeDashboardManager:
        def _get_app_file(self, dashboard_id):
            assert dashboard_id == "default"
            return app_file

    import banking_mcp.dashboard as dashboard

    monkeypatch.setattr(
        dashboard, "get_dashboard_manager", lambda: FakeDashboardManager()
    )
    monkeypatch.setattr(server.settings, "MCP_TRANSPORT", "http")
    monkeypatch.setattr(server.settings, "DASHBOARD_DEFAULT_ID", "default")
    monkeypatch.setattr(server.settings, "DASHBOARD_PORT", 8502)

    popen_calls = []

    class FakeProcess:
        pid = 1234

        def __init__(self, cmd):
            popen_calls.append(cmd)
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    monkeypatch.setattr(server.subprocess, "Popen", FakeProcess)
    proc = server._start_streamlit_subprocess()
    assert proc.pid == 1234
    assert app_file.exists()
    assert "streamlit" in popen_calls[0]

    server._stop_streamlit_subprocess()
    assert server._streamlit_process is None
    server._stop_streamlit_subprocess()

    class SlowProcess(FakeProcess):
        def wait(self, timeout=None):
            if timeout is not None:
                raise server.subprocess.TimeoutExpired("streamlit", timeout)
            return 0

    server._streamlit_process = SlowProcess(["streamlit"])
    server._stop_streamlit_subprocess()
    assert server._streamlit_process is None

    monkeypatch.setattr(
        server.subprocess,
        "Popen",
        lambda _cmd: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    assert server._start_streamlit_subprocess() is None


def test_server_app_lifespan_exception_handler_and_sse(monkeypatch):
    import banking_mcp.server as server

    events = []

    class FakeSessionManager:
        @asynccontextmanager
        async def run(self):
            events.append("session-start")
            yield
            events.append("session-stop")

    class FakeMCP:
        def __init__(self):
            self.session_manager = FakeSessionManager()

        def streamable_http_app(self):
            return FastAPI()

        def sse_app(self, mount_path="/mcp"):
            events.append(f"sse:{mount_path}")
            return FastAPI()

        def run(self, transport):
            events.append(f"run:{transport}")

    fake_mcp = FakeMCP()
    monkeypatch.setattr(server, "mcp", fake_mcp)
    monkeypatch.setattr(server, "audit_start", lambda: events.append("audit-start"))
    monkeypatch.setattr(server, "audit_stop", lambda: events.append("audit-stop"))
    monkeypatch.setattr(server, "_start_streamlit_subprocess", lambda: events.append("streamlit-start"))
    monkeypatch.setattr(server, "_stop_streamlit_subprocess", lambda: events.append("streamlit-stop"))

    class FakeManager:
        def shutdown(self):
            events.append("db-shutdown")

    import banking_mcp.db.manager as db_manager

    monkeypatch.setattr(db_manager, "get_manager", lambda: FakeManager())

    errors = []

    async def fake_log_error(**kwargs):
        errors.append(kwargs)

    monkeypatch.setattr(server, "log_error", fake_log_error)
    monkeypatch.setattr(server.settings, "MCP_TRANSPORT", "http")
    monkeypatch.setattr(server.settings, "MCP_HTTP_PATH", "/banking-assistant")
    app = server.create_combined_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/boom").status_code == 500

    assert "session-start" in events
    assert "session-stop" in events
    assert "db-shutdown" in events
    assert errors[0]["context"] == "/boom"
    assert server.health_status() == "ok"

    monkeypatch.setattr(server.settings, "MCP_TRANSPORT", "sse")
    sse_app = server.create_combined_app()
    with TestClient(sse_app):
        pass
    assert "sse:/mcp" in events

    server.run_stdio()
    assert "run:stdio" in events


def test_server_run_http_invokes_uvicorn(monkeypatch):
    import banking_mcp.server as server

    captured = {}
    fake_uvicorn = SimpleNamespace(run=lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(server.settings, "SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(server.settings, "SERVER_PORT", 9000)
    monkeypatch.setattr(server.settings, "ENV", "dev")
    monkeypatch.setattr(server.settings, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(server.settings, "MCP_TRANSPORT", "http")
    monkeypatch.setattr(server.settings, "DASHBOARD_AUTOSTART", True)
    monkeypatch.setattr(server.settings, "DASHBOARD_URL", "http://localhost:8501")
    monkeypatch.setattr(server.settings, "DASHBOARD_PORT", 8501)

    server.run_http()

    assert captured["args"] == ("banking_mcp.server:app",)
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["reload"] is True
