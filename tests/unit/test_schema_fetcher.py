"""Tests for banking_mcp.db.schema_fetcher (multi-DB schema abstraction)."""

import pytest

from banking_mcp.db.schema_fetcher import (
    ClickHouseSchemaFetcher,
    DuckDBSchemaFetcher,
    MySQLSchemaFetcher,
    OracleSchemaFetcher,
    PostgreSQLSchemaFetcher,
    SQLiteSchemaFetcher,
    get_schema_fetcher,
    get_supported_db_types,
)


def test_supported_db_types_includes_all_drivers():
    types = set(get_supported_db_types())
    assert {"oracle", "sqlite", "postgres", "postgresql",
            "mysql", "mariadb", "duckdb", "clickhouse"}.issubset(types)


@pytest.mark.parametrize(
    "db_type, expected_cls",
    [
        ("oracle", OracleSchemaFetcher),
        ("sqlite", SQLiteSchemaFetcher),
        ("postgres", PostgreSQLSchemaFetcher),
        ("postgresql", PostgreSQLSchemaFetcher),
        ("mysql", MySQLSchemaFetcher),
        ("mariadb", MySQLSchemaFetcher),
        ("duckdb", DuckDBSchemaFetcher),
        ("clickhouse", ClickHouseSchemaFetcher),
    ],
)
def test_get_schema_fetcher_returns_correct_class(db_type, expected_cls):
    assert isinstance(get_schema_fetcher(db_type), expected_cls)


def test_get_schema_fetcher_is_case_insensitive():
    assert isinstance(get_schema_fetcher("ORACLE"), OracleSchemaFetcher)
    assert isinstance(get_schema_fetcher("PostgreSQL"), PostgreSQLSchemaFetcher)


def test_get_schema_fetcher_raises_for_unknown():
    with pytest.raises(ValueError, match="Unsupported database type"):
        get_schema_fetcher("nosuchdb")


def test_oracle_format_data_type_varchar():
    assert OracleSchemaFetcher.format_data_type("VARCHAR2", 50, None, None) == "VARCHAR2(50)"
    assert OracleSchemaFetcher.format_data_type("CHAR", 10, None, None) == "CHAR(10)"


def test_oracle_format_data_type_number():
    assert OracleSchemaFetcher.format_data_type("NUMBER", None, 10, 0) == "NUMBER(10)"
    assert OracleSchemaFetcher.format_data_type("NUMBER", None, 10, 2) == "NUMBER(10,2)"


def test_oracle_format_data_type_passthrough():
    assert OracleSchemaFetcher.format_data_type("DATE", None, None, None) == "DATE"


def test_parse_schema_result_groups_by_table():
    rows = [
        {"table_name": "accounts", "column_name": "id", "data_type": "INTEGER", "is_nullable": "NO"},
        {"table_name": "accounts", "column_name": "name", "data_type": "TEXT", "is_nullable": "YES"},
        {"table_name": "cards", "column_name": "id", "data_type": "INTEGER", "is_nullable": "NO"},
    ]
    fetcher = PostgreSQLSchemaFetcher()
    tables = fetcher.parse_schema_result(rows)
    assert set(tables.keys()) == {"accounts", "cards"}
    assert len(tables["accounts"]["columns"]) == 2
    assert tables["accounts"]["columns"][0]["nullable"] is False
    assert tables["accounts"]["columns"][1]["nullable"] is True


def test_format_compact_schema_alphabetises_tables():
    fetcher = PostgreSQLSchemaFetcher()
    tables = {
        "z_table": {"name": "z_table", "columns": [{"name": "id", "type": "INTEGER", "nullable": False}], "row_count": None},
        "a_table": {"name": "a_table", "columns": [{"name": "id", "type": "INTEGER", "nullable": False}], "row_count": None},
    }
    out = fetcher.format_compact_schema(tables)
    assert out.index("a_table:") < out.index("z_table:")


def test_get_schema_query_returns_select_for_each():
    for db_type in ("oracle", "sqlite", "postgres", "mysql", "duckdb", "clickhouse"):
        sql = get_schema_fetcher(db_type).get_schema_query().strip().lower()
        assert sql.startswith("select")
