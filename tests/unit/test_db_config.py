"""Tests for banking_mcp.db.config — env var substitution, CRUD, schema filter."""

import json

import pytest

from banking_mcp.db import config as db_config


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point CONFIG_FILE to a temp dir for each test."""
    cfg = tmp_path / "db_config.json"
    monkeypatch.setattr(db_config, "CONFIG_FILE", cfg)
    return cfg


def test_default_config_is_banking_schemaracle(isolated_config):
    cfg = db_config._get_default_config()
    assert cfg["default_connection"] == "scards"
    scards = cfg["connections"]["scards"]
    assert scards["db_type"] == "oracle"
    assert scards["dsn"] == "${ORACLE_DSN}"
    assert scards["schema"] == "${ORACLE_SCHEMA}"


def test_default_config_has_only_scards(isolated_config):
    cfg = db_config._get_default_config()
    assert list(cfg["connections"].keys()) == ["scards"]
    assert cfg["domain_queries"] == {"scards": {}}


def test_load_config_creates_default_when_missing(isolated_config):
    assert not isolated_config.exists()
    cfg = db_config.load_config()
    assert cfg["default_connection"] == "scards"
    assert isolated_config.exists()


def test_load_config_invalid_json_raises_and_preserves_file(isolated_config):
    isolated_config.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid database config JSON"):
        db_config.load_config()
    assert isolated_config.read_text(encoding="utf-8") == "{bad json"


def test_resolve_env_vars_substitutes(monkeypatch):
    monkeypatch.setenv("FOO_DSN", "host:1521/SVC")
    assert db_config.resolve_env_vars("${FOO_DSN}") == "host:1521/SVC"
    assert db_config.resolve_env_vars("oracle://${FOO_DSN}") == "oracle://host:1521/SVC"


def test_resolve_env_vars_raises_on_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="MISSING_VAR"):
        db_config.resolve_env_vars("${MISSING_VAR}")


def test_add_remove_connection(isolated_config):
    db_config.add_connection(
        name="extra", dsn="sqlite:///x.db", db_type="sqlite", description="x"
    )
    assert db_config.get_connection("extra")["dsn"] == "sqlite:///x.db"

    assert db_config.remove_connection("extra") is True
    assert db_config.get_connection("extra") is None
    assert db_config.remove_connection("extra") is False  # idempotent


def test_add_connection_rejects_duplicate(isolated_config):
    db_config.load_config()  # bootstrap default scards
    with pytest.raises(ValueError, match="already exists"):
        db_config.add_connection(name="scards", dsn="x", db_type="oracle")


def test_set_default_connection(isolated_config):
    db_config.add_connection(name="other", dsn="sqlite:///o.db", db_type="sqlite")
    db_config.set_default_connection("other")
    assert db_config.get_default_connection() == "other"


def test_set_default_connection_unknown_raises(isolated_config):
    with pytest.raises(ValueError):
        db_config.set_default_connection("nonexistent")


def test_filter_tables_include():
    tables = ["accounts", "cards", "audit_log"]
    out = db_config.filter_tables(tables, {"include": ["acc*", "card*"], "exclude": []})
    assert sorted(out) == ["accounts", "cards"]


def test_filter_tables_exclude():
    tables = ["accounts", "cards", "audit_log"]
    out = db_config.filter_tables(tables, {"include": [], "exclude": ["audit*"]})
    assert sorted(out) == ["accounts", "cards"]


def test_domain_query_crud(isolated_config):
    db_config.load_config()  # bootstrap scards
    db_config.add_domain_query(
        "scards", "active_cards",
        {"sql": "SELECT * FROM cards WHERE status='A'", "description": "active", "params": []},
    )
    queries = db_config.get_domain_queries("scards")
    assert "active_cards" in queries
    assert queries["active_cards"]["sql"] == "SELECT * FROM cards WHERE status='A'"

    assert db_config.remove_domain_query("scards", "active_cards") is True
    assert "active_cards" not in db_config.get_domain_queries("scards")


def test_legacy_type_key_normalized(isolated_config):
    raw = {
        "connections": {"old": {"name": "old", "dsn": "x", "type": "sqlite"}},
        "default_connection": "old",
        "domain_queries": {},
    }
    isolated_config.write_text(json.dumps(raw), encoding="utf-8")
    cfg = db_config.load_config()
    assert cfg["connections"]["old"]["db_type"] == "sqlite"
    assert "type" not in cfg["connections"]["old"]


def test_parse_compact_params_list_format():
    params = [{"name": "city", "type": "string", "default": "Sofia"}]
    parsed = db_config.parse_compact_params(params)
    assert parsed[0]["name"] == "city"
    assert parsed[0]["default"] == "Sofia"


def test_parse_compact_params_string_format():
    parsed = db_config.parse_compact_params("days=30 (lookback)")
    assert parsed[0]["name"] == "days"
    assert parsed[0]["default"] == 30
    assert parsed[0]["type"] == "int"
    assert parsed[0]["description"] == "lookback"


def test_parse_compact_params_empty():
    assert db_config.parse_compact_params("") == []
    assert db_config.parse_compact_params([]) == []
