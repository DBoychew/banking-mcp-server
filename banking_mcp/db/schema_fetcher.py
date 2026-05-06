"""
Database-specific schema fetching strategies.

Each database type implements `SchemaFetcher` and returns:
  - get_schema_query() -> SQL that yields rows {table_name, column_name, data_type, is_nullable}

Oracle has a custom path (`OracleSchemaFetcher.fetch_via_cursor`) because it
needs explicit `:owner` binding and special data-type formatting for
VARCHAR2/NUMBER. SQLite has a custom path because it doesn't expose
INFORMATION_SCHEMA - we use sqlite_master + PRAGMA.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class ColumnInfo(TypedDict):
    name: str
    type: str
    nullable: bool


class TableInfo(TypedDict):
    name: str
    columns: list[ColumnInfo]
    row_count: int | None


class SchemaFetcher(ABC):
    """Abstract base class for schema fetchers."""

    @abstractmethod
    def get_schema_query(self) -> str:
        """Return SQL that yields {table_name, column_name, data_type, is_nullable} rows."""

    def parse_schema_result(self, rows: list[dict]) -> dict[str, TableInfo]:
        tables: dict[str, TableInfo] = {}
        for row in rows:
            table_name = row.get("table_name") or row.get("TABLE_NAME") or ""
            if not table_name:
                continue
            tables.setdefault(
                table_name,
                {"name": table_name, "columns": [], "row_count": None},
            )
            nullable_val = row.get("is_nullable", row.get("IS_NULLABLE", "YES"))
            if isinstance(nullable_val, bool):
                is_nullable = nullable_val
            elif isinstance(nullable_val, int):
                is_nullable = nullable_val == 1
            else:
                is_nullable = str(nullable_val).upper() in {"YES", "Y", "TRUE", "1"}

            tables[table_name]["columns"].append(
                {
                    "name": row.get("column_name", row.get("COLUMN_NAME", "")),
                    "type": row.get("data_type", row.get("DATA_TYPE", "unknown")),
                    "nullable": is_nullable,
                }
            )
        return tables

    def format_compact_schema(self, tables: dict[str, TableInfo]) -> str:
        lines = []
        for name in sorted(tables):
            cols = ", ".join(
                f"{c['name']}({str(c['type']).lower()})" for c in tables[name]["columns"]
            )
            lines.append(f"{name}: {cols}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Concrete fetchers
# ---------------------------------------------------------------------------


class OracleSchemaFetcher(SchemaFetcher):
    """Schema fetcher for Oracle. Uses all_tab_columns / user_tab_columns."""

    def get_schema_query(self) -> str:
        return """
            SELECT table_name, column_name, data_type, nullable AS is_nullable,
                   data_length, data_precision, data_scale
            FROM user_tab_columns
            ORDER BY table_name, column_id
        """

    @staticmethod
    def format_data_type(
        data_type: str,
        data_length: int | None,
        data_precision: int | None,
        data_scale: int | None,
    ) -> str:
        if data_type in {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"} and data_length:
            return f"{data_type}({data_length})"
        if data_type == "NUMBER" and data_precision is not None:
            if data_scale not in (None, 0):
                return f"{data_type}({data_precision},{data_scale})"
            return f"{data_type}({data_precision})"
        return data_type


class SQLiteSchemaFetcher(SchemaFetcher):
    """SQLite has no INFORMATION_SCHEMA - manager uses sqlite_master + PRAGMA directly."""

    def get_schema_query(self) -> str:
        return (
            "SELECT m.name AS table_name, p.name AS column_name, p.type AS data_type, "
            "CASE WHEN p.[notnull]=0 THEN 'YES' ELSE 'NO' END AS is_nullable "
            "FROM sqlite_master m JOIN pragma_table_info(m.name) p "
            "WHERE m.type='table' AND m.name NOT LIKE 'sqlite_%' "
            "ORDER BY m.name, p.cid"
        )


class PostgreSQLSchemaFetcher(SchemaFetcher):
    def get_schema_query(self) -> str:
        return """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_name, ordinal_position
        """


class MySQLSchemaFetcher(SchemaFetcher):
    def get_schema_query(self) -> str:
        return """
            SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
                   DATA_TYPE AS data_type, IS_NULLABLE AS is_nullable
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """


class DuckDBSchemaFetcher(SchemaFetcher):
    def get_schema_query(self) -> str:
        return """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """


class ClickHouseSchemaFetcher(SchemaFetcher):
    def get_schema_query(self) -> str:
        return """
            SELECT table AS table_name, name AS column_name,
                   type AS data_type, 'YES' AS is_nullable
            FROM system.columns
            WHERE database = currentDatabase()
            ORDER BY table, position
        """


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_FETCHERS: dict[str, type[SchemaFetcher]] = {
    "oracle": OracleSchemaFetcher,
    "sqlite": SQLiteSchemaFetcher,
    "postgres": PostgreSQLSchemaFetcher,
    "postgresql": PostgreSQLSchemaFetcher,
    "mysql": MySQLSchemaFetcher,
    "mariadb": MySQLSchemaFetcher,
    "duckdb": DuckDBSchemaFetcher,
    "clickhouse": ClickHouseSchemaFetcher,
}


def get_schema_fetcher(db_type: str) -> SchemaFetcher:
    cls = _FETCHERS.get(db_type.lower())
    if cls is None:
        supported = ", ".join(sorted(set(_FETCHERS.keys())))
        raise ValueError(
            f"Unsupported database type: {db_type!r}. Supported: {supported}"
        )
    return cls()


def get_supported_db_types() -> list[str]:
    return sorted(set(_FETCHERS.keys()))
