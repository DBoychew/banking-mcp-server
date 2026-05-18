"""
Multi-database manager for the banking MCP server.

Supported db_type values:
  - oracle      (primary masked Oracle connection)
  - sqlite
  - postgres / postgresql
  - mysql / mariadb
  - duckdb
  - clickhouse

Drivers are imported lazily per connection - the project only requires
``oracledb`` by default; install the ``[multi-db]`` extras to enable the rest.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse, unquote

import pandas as pd

from banking_mcp.audit import log_query
from banking_mcp.config import settings

from .config import (
    ConnectionInfo,
    DomainQueryDef,
    SchemaFilter,
    add_connection as config_add_connection,
    add_domain_query as config_add_domain_query,
    filter_tables,
    get_connection,
    get_default_connection,
    get_domain_queries,
    list_connections as config_list_connections,
    load_config,
    parse_compact_params,
    remove_connection as config_remove_connection,
    remove_domain_query as config_remove_domain_query,
    resolve_dsn,
    resolve_env_vars,
    set_default_connection as config_set_default_connection,
    update_schema_filter,
)
from .schema_fetcher import (
    OracleSchemaFetcher,
    SchemaFetcher,
    get_schema_fetcher,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
SCHEMA_CACHE_FILE = DATA_DIR / "schema_cache.json"
SCHEMA_CACHE_TTL = timedelta(hours=24)

# SQL keywords forbidden (read-only enforcement)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|REPLACE|UPSERT|CALL|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)
_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")
_SQL_SINGLE_QUOTED = re.compile(r"'(?:''|[^'])*'")
_SQL_DOUBLE_QUOTED = re.compile(r'"(?:""|[^"])*"')
_LEADING_PARENS = re.compile(r"^\(+\s*")

# SQL dialect hints injected into LLM context
SQL_DIALECT_HINTS: dict[str, str] = {
    "oracle": "Oracle: TO_DATE(), TO_CHAR(), || for concat, ROWNUM/FETCH FIRST for limiting",
    "sqlite": "SQLite: strftime() for dates, || for concat, LIKE is case-insensitive",
    "postgres": "PostgreSQL: DATE_TRUNC(), INTERVAL '1 day', || for concat, ILIKE for case-insensitive",
    "postgresql": "PostgreSQL: DATE_TRUNC(), INTERVAL '1 day', || for concat, ILIKE for case-insensitive",
    "mysql": "MySQL: DATE_FORMAT(), DATE_ADD(), CONCAT(), LIKE is case-insensitive",
    "mariadb": "MariaDB: MySQL-compatible, DATE_FORMAT(), DATE_ADD(), CONCAT()",
    "duckdb": "DuckDB: PostgreSQL-like, DATE_TRUNC(), INTERVAL, || for concat",
    "clickhouse": "ClickHouse: toStartOfDay/Week/Month(), formatDateTime(), no INTERVAL syntax",
}


class DomainQueryInfo(TypedDict):
    name: str
    description: str
    parameters: list
    returns: str
    example: str


class LLMContext(TypedDict):
    connection_name: str
    db_type: str
    sql_dialect_hint: str
    schema_compact: str
    domain_queries: list[DomainQueryInfo]
    available_connections: list[str]


# ---------------------------------------------------------------------------
# DSN helpers
# ---------------------------------------------------------------------------

_ORACLE_CONNECT_STRING = re.compile(
    r"(?P<user>[^/\s@]+)/(?P<password>[^@\s]+)@(?P<dsn>.+)"
)


def _resolve_config_value(value: str) -> str:
    try:
        return resolve_env_vars(value)
    except ValueError:
        return value


def _parse_url_dsn(dsn: str) -> dict[str, Any]:
    """Parse a URL-style DSN (postgresql://user:pass@host:port/db) into kwargs."""
    parsed = urlparse(dsn)
    return {
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "host": parsed.hostname,
        "port": parsed.port,
        "database": parsed.path.lstrip("/") or None,
    }


# ---------------------------------------------------------------------------
# Per-driver connection openers
# ---------------------------------------------------------------------------

def _open_sqlite(dsn: str) -> sqlite3.Connection:
    path = dsn.removeprefix("sqlite:///").removeprefix("sqlite://")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _quote_oracle_identifier(identifier: str) -> str:
    ident = identifier.strip()
    if not ident:
        raise ValueError("Oracle schema cannot be empty")
    if '"' in ident or "\x00" in ident:
        raise ValueError("Oracle schema contains unsupported characters")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]*", ident):
        return ident.upper()
    return f'"{ident}"'


def _get_oracle_schema(conn_info: ConnectionInfo) -> str | None:
    raw_schema = str(conn_info.get("schema") or settings.ORACLE_SCHEMA or "").strip()
    if not raw_schema:
        return None
    schema = _resolve_config_value(raw_schema).strip()
    if not schema:
        return None
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]*", schema):
        return schema.upper()
    return schema


def _get_oracle_connect_args(conn_info: ConnectionInfo) -> tuple[str, str, str]:
    dsn = _resolve_config_value(str(conn_info.get("dsn", "")).strip())
    user = settings.ORACLE_USER.strip()
    password = settings.ORACLE_PASSWORD

    if (not user or not password) and dsn:
        match = _ORACLE_CONNECT_STRING.fullmatch(dsn)
        if match:
            dsn = match.group("dsn").strip()
            user = user or match.group("user").strip()
            password = password or match.group("password")

    if not dsn:
        raise ValueError("Oracle DSN is not configured")
    if not user or not password:
        raise ValueError(
            "Oracle credentials are not configured. Set ORACLE_USER and ORACLE_PASSWORD."
        )
    return dsn, user, password


def _open_oracle(conn_info: ConnectionInfo) -> Any:
    import oracledb  # lazy

    dsn, user, password = _get_oracle_connect_args(conn_info)
    conn = oracledb.connect(dsn=dsn, user=user, password=password)
    schema = _get_oracle_schema(conn_info)
    if schema:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"ALTER SESSION SET CURRENT_SCHEMA = {_quote_oracle_identifier(schema)}"
            )
        finally:
            cursor.close()
    return conn


def _open_postgres(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except ImportError:
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(dsn)
        except ImportError as e:  # pragma: no cover - depends on install
            raise RuntimeError(
                "PostgreSQL driver missing. Install `psycopg[binary]` or `psycopg2-binary`."
            ) from e


def _open_mysql(dsn: str) -> Any:
    try:
        import pymysql  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("MySQL driver missing. Install `pymysql`.") from e

    parts = _parse_url_dsn(dsn)
    return pymysql.connect(
        host=parts["host"] or "localhost",
        port=parts["port"] or 3306,
        user=parts["user"] or "",
        password=parts["password"] or "",
        database=parts["database"] or "",
    )


def _open_duckdb(dsn: str) -> Any:
    try:
        import duckdb  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("DuckDB driver missing. Install `duckdb`.") from e

    if dsn.startswith("duckdb:///"):
        path = dsn[len("duckdb:///") :]
    elif dsn.startswith("duckdb://"):
        path = dsn[len("duckdb://") :]
    else:
        path = dsn
    if path == ":memory:":
        return duckdb.connect(":memory:")
    return duckdb.connect(path, read_only=True)


def _open_clickhouse(dsn: str) -> Any:
    try:
        import clickhouse_connect  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "ClickHouse driver missing. Install `clickhouse-connect`."
        ) from e

    parts = _parse_url_dsn(dsn)
    return clickhouse_connect.get_client(
        host=parts["host"] or "localhost",
        port=parts["port"] or 8123,
        username=parts["user"] or "default",
        password=parts["password"] or "",
        database=parts["database"] or "default",
    )


def _open_connection(conn_info: ConnectionInfo) -> Any:
    db_type = conn_info.get("db_type", "sqlite").lower()
    raw_dsn = str(conn_info.get("dsn", ""))
    try:
        dsn = resolve_dsn(raw_dsn)
    except ValueError:
        dsn = raw_dsn

    if db_type == "sqlite":
        return _open_sqlite(dsn)
    if db_type == "oracle":
        return _open_oracle(conn_info)
    if db_type in {"postgres", "postgresql"}:
        return _open_postgres(dsn)
    if db_type in {"mysql", "mariadb"}:
        return _open_mysql(dsn)
    if db_type == "duckdb":
        return _open_duckdb(dsn)
    if db_type == "clickhouse":
        return _open_clickhouse(dsn)

    raise ValueError(f"Unsupported db_type: {db_type!r}")


# ---------------------------------------------------------------------------
# Cursor / fetch abstraction
# ---------------------------------------------------------------------------

def _close_quietly(obj: Any) -> None:
    try:
        if obj is not None:
            obj.close()
    except Exception:
        pass


def _run_select(
    conn_info: ConnectionInfo,
    db_conn: Any,
    sql: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[Any]]:
    """Execute a SELECT and return ``(columns, rows)``.

    Handles driver-specific differences:
      - Oracle uses :name binds and explicit cursor lifecycle.
      - DuckDB uses ``conn.execute(sql).fetchdf()`` style.
      - ClickHouse client returns its own result type.
      - All others use DB-API 2.0.
    """
    db_type = conn_info.get("db_type", "sqlite").lower()

    if db_type == "clickhouse":
        result = db_conn.query(sql)
        columns = list(result.column_names)
        rows = list(result.result_rows)
        return columns, rows

    if db_type == "duckdb":
        cur = db_conn.execute(sql) if params is None else db_conn.execute(sql, params)
        try:
            columns = [d[0] for d in (cur.description or [])]
            rows = cur.fetchall()
            return columns, rows
        finally:
            _close_quietly(cur)

    cursor = db_conn.cursor()
    try:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        columns = [d[0] for d in (cursor.description or [])]
        rows = cursor.fetchall()
        return columns, rows
    finally:
        _close_quietly(cursor)


def _ping_sql(db_type: str) -> str:
    if db_type == "oracle":
        return "SELECT 1 FROM DUAL"
    return "SELECT 1"


def _strip_sql_literals_and_comments(sql: str) -> str:
    stripped = _SQL_BLOCK_COMMENT.sub(" ", sql)
    stripped = _SQL_LINE_COMMENT.sub(" ", stripped)
    stripped = _SQL_DOUBLE_QUOTED.sub('""', stripped)
    stripped = _SQL_SINGLE_QUOTED.sub("''", stripped)
    return stripped


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """Multi-database manager - the core data layer for the banking MCP server."""

    def __init__(self) -> None:
        load_config()
        self.schema_cache = self._load_schema_cache()

    # -------------------------------------------------------------------------
    # Schema cache
    # -------------------------------------------------------------------------

    def _load_schema_cache(self) -> dict:
        if SCHEMA_CACHE_FILE.exists():
            try:
                return json.loads(SCHEMA_CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_schema_cache(self) -> None:
        SCHEMA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_CACHE_FILE.write_text(
            json.dumps(self.schema_cache, indent=2),
            encoding="utf-8",
        )

    # -------------------------------------------------------------------------
    # SQL validation
    # -------------------------------------------------------------------------

    def _validate_sql(self, sql: str) -> None:
        sanitized = _strip_sql_literals_and_comments(sql).strip()
        if not sanitized:
            raise ValueError("SQL query cannot be empty.")
        if ";" in sanitized.rstrip().rstrip(";"):
            raise ValueError("Multiple SQL statements are not allowed.")
        if _FORBIDDEN.search(sanitized):
            raise ValueError("Forbidden SQL keyword detected. Only SELECT queries are allowed.")
        if not re.match(r"^(SELECT|WITH)\b", _LEADING_PARENS.sub("", sanitized), re.IGNORECASE):
            raise ValueError("Only read-only SELECT queries are allowed.")

    # -------------------------------------------------------------------------
    # Core query
    # -------------------------------------------------------------------------

    def query(
        self,
        sql: str,
        connection: str | None = None,
        source: str = "api",
    ) -> pd.DataFrame:
        """Execute a SELECT and return a DataFrame. Audit-logged."""
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        self._validate_sql(sql)

        conn_info = get_connection(conn_name)
        if not conn_info:
            raise ValueError(f"Connection '{conn_name}' not found")

        start = time.perf_counter()
        db_conn = None
        try:
            db_conn = _open_connection(conn_info)
            columns, rows = _run_select(conn_info, db_conn, sql)
            df = pd.DataFrame([dict(zip(columns, row)) for row in rows])
            duration_ms = (time.perf_counter() - start) * 1000
            log_query(
                connection=conn_name,
                query=sql,
                duration_ms=duration_ms,
                row_count=len(df),
                status="success",
                source=source,
            )
            return df
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            log_query(
                connection=conn_name,
                query=sql,
                duration_ms=duration_ms,
                status="error",
                error=str(e),
                source=source,
            )
            raise
        finally:
            _close_quietly(db_conn)

    def execute_sql(
        self,
        sql: str,
        connection: str | None = None,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """Execute a parameterised SELECT (named params) - returns list[dict]."""
        self._validate_sql(sql)
        conn_name = connection or get_default_connection()
        conn_info = get_connection(conn_name or "")
        if not conn_info:
            raise KeyError(f"Connection {conn_name!r} not found")

        db_conn = None
        try:
            db_conn = _open_connection(conn_info)
            columns, rows = _run_select(conn_info, db_conn, sql, params or None)
            return [dict(zip(columns, row)) for row in rows]
        finally:
            _close_quietly(db_conn)

    def test_connection(self, connection: str) -> bool:
        try:
            conn_info = get_connection(connection)
            if not conn_info:
                return False
            db_conn = None
            try:
                db_conn = _open_connection(conn_info)
                _run_select(conn_info, db_conn, _ping_sql(conn_info.get("db_type", "sqlite").lower()))
            finally:
                _close_quietly(db_conn)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Domain queries
    # -------------------------------------------------------------------------

    def execute_domain_query(
        self,
        name: str,
        connection: str | None = None,
        source: str = "domain_query",
        **params: Any,
    ) -> pd.DataFrame:
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        queries = get_domain_queries(conn_name)
        if name not in queries:
            raise ValueError(
                f"Domain query '{name}' not found for connection '{conn_name}'. "
                f"Available: {list(queries)}"
            )

        query_def = queries[name]
        sql = query_def["sql"]

        # Merge config defaults with caller args
        merged: dict[str, Any] = {}
        param_specs = query_def.get("params", query_def.get("parameters", []))
        for spec in parse_compact_params(param_specs):
            if "default" in spec:
                merged[spec["name"]] = spec["default"]
        merged.update(params)

        rows = self.execute_sql(sql, connection=conn_name, **merged)
        return pd.DataFrame(rows)

    # -------------------------------------------------------------------------
    # Schema (cached 24h)
    # -------------------------------------------------------------------------

    def get_schema(self, connection: str | None = None, force_refresh: bool = False) -> str:
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        cached = self.schema_cache.get(conn_name)
        if cached and not force_refresh:
            cached_at = datetime.fromisoformat(cached["cached_at"])
            if datetime.now() - cached_at < SCHEMA_CACHE_TTL:
                return cached["schema"]

        schema = self._fetch_schema(conn_name)
        self.schema_cache[conn_name] = {
            "schema": schema,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_schema_cache()
        return schema

    def _fetch_schema(self, connection: str) -> str:
        conn_info = get_connection(connection)
        if not conn_info:
            raise ValueError(f"Connection '{connection}' not found")

        db_type = conn_info.get("db_type", "sqlite").lower()

        if db_type == "oracle":
            return self._fetch_oracle_schema(conn_info)
        if db_type == "sqlite":
            return self._fetch_sqlite_schema(conn_info)

        # Generic path - schema_fetcher abstraction handles the rest
        return self._fetch_generic_schema(conn_info)

    def _fetch_sqlite_schema(self, conn_info: ConnectionInfo) -> str:
        schema_filter = conn_info.get("schema_filter", {"include": [], "exclude": []})
        db_conn = _open_connection(conn_info)
        try:
            cursor = db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            all_tables = [row[0] for row in cursor.fetchall()]
            tables = filter_tables(all_tables, schema_filter)
            lines = []
            for table in tables:
                cur = db_conn.execute(f"PRAGMA table_info({table})")
                cols = [f"{r[1]}({r[2]})" for r in cur.fetchall()]
                lines.append(f"{table}: {', '.join(cols)}")
            return "\n".join(lines)
        finally:
            _close_quietly(db_conn)

    def _fetch_oracle_schema(self, conn_info: ConnectionInfo) -> str:
        schema_filter = conn_info.get("schema_filter", {"include": [], "exclude": []})
        schema_name = _get_oracle_schema(conn_info)
        db_conn = _open_connection(conn_info)
        try:
            if schema_name:
                sql = """
                    SELECT table_name, column_name, data_type, data_length, data_precision, data_scale
                    FROM all_tab_columns
                    WHERE owner = :owner
                    ORDER BY table_name, column_id
                """
                _, rows = _run_select(conn_info, db_conn, sql, {"owner": schema_name})
            else:
                sql = """
                    SELECT table_name, column_name, data_type, data_length, data_precision, data_scale
                    FROM user_tab_columns
                    ORDER BY table_name, column_id
                """
                _, rows = _run_select(conn_info, db_conn, sql)

            table_map: dict[str, list[str]] = {}
            for table_name, column_name, data_type, data_length, data_precision, data_scale in rows:
                col_type = OracleSchemaFetcher.format_data_type(
                    data_type=data_type,
                    data_length=data_length,
                    data_precision=data_precision,
                    data_scale=data_scale,
                )
                table_map.setdefault(table_name, []).append(f"{column_name}({col_type})")

            tables = filter_tables(sorted(table_map), schema_filter)
            return "\n".join(f"{table}: {', '.join(table_map[table])}" for table in tables)
        finally:
            _close_quietly(db_conn)

    def _fetch_generic_schema(self, conn_info: ConnectionInfo) -> str:
        db_type = conn_info.get("db_type", "").lower()
        fetcher: SchemaFetcher = get_schema_fetcher(db_type)
        schema_filter = conn_info.get("schema_filter", {"include": [], "exclude": []})

        db_conn = _open_connection(conn_info)
        try:
            columns, rows = _run_select(conn_info, db_conn, fetcher.get_schema_query())
        finally:
            _close_quietly(db_conn)

        if not rows:
            return ""

        rows_dicts = [dict(zip(columns, r)) for r in rows]
        tables = fetcher.parse_schema_result(rows_dicts)
        names = filter_tables(list(tables.keys()), schema_filter)
        filtered = {n: tables[n] for n in names if n in tables}
        return fetcher.format_compact_schema(filtered)

    def refresh_schema(self, connection: str | None = None) -> str:
        return self.get_schema(connection, force_refresh=True)

    def get_table_list(self, connection: str | None = None) -> list[str]:
        """Return sorted table names for a connection (uses schema cache)."""
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")
        schema = self.get_schema(conn_name)
        tables = []
        for line in schema.strip().splitlines():
            if ": " in line:
                tables.append(line.split(": ", 1)[0])
        return sorted(tables)

    def get_table_columns(
        self, connection: str | None = None, table_name: str = ""
    ) -> list[dict] | None:
        """Return column dicts for a table, or None if the table is not found."""
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")
        schema = self.get_schema(conn_name)
        needle = table_name.upper()
        for line in schema.strip().splitlines():
            if ": " not in line:
                continue
            name, cols_str = line.split(": ", 1)
            if name.upper() == needle:
                return DatabaseManager._parse_column_list(cols_str)
        return None

    def get_table_comments(
        self, connection: str | None = None, table_name: str = ""
    ) -> dict:
        """Return {'table': str|None, 'columns': {COL: comment}} for Oracle.

        Returns {} for non-Oracle DBs. Comments come from ALL_TAB_COMMENTS /
        ALL_COL_COMMENTS (or the USER_* equivalents when no schema is set).
        """
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")
        conn_info = get_connection(conn_name)
        if not conn_info:
            raise ValueError(f"Connection '{conn_name}' not found")
        if conn_info.get("db_type", "").lower() != "oracle":
            return {}

        schema_name = _get_oracle_schema(conn_info)
        db_conn = _open_connection(conn_info)
        try:
            if schema_name:
                tab_sql = (
                    "SELECT comments FROM all_tab_comments "
                    "WHERE owner = :owner AND table_name = :t"
                )
                col_sql = (
                    "SELECT column_name, comments FROM all_col_comments "
                    "WHERE owner = :owner AND table_name = :t"
                )
                params = {"owner": schema_name, "t": table_name.upper()}
            else:
                tab_sql = "SELECT comments FROM user_tab_comments WHERE table_name = :t"
                col_sql = (
                    "SELECT column_name, comments FROM user_col_comments "
                    "WHERE table_name = :t"
                )
                params = {"t": table_name.upper()}

            _, tab_rows = _run_select(conn_info, db_conn, tab_sql, params)
            _, col_rows = _run_select(conn_info, db_conn, col_sql, params)
            return {
                "table": (tab_rows[0][0] if tab_rows and tab_rows[0][0] else None),
                "columns": {name: comment for name, comment in col_rows if comment},
            }
        finally:
            _close_quietly(db_conn)

    @staticmethod
    def _parse_column_list(cols_str: str) -> list[dict]:
        """Parse 'COL1(type1), COL2(type2(sub))' handling nested parens in types."""
        columns: list[dict] = []
        pos = 0
        col_pat = re.compile(r"([A-Z_#$][A-Z0-9_#$]*)\(", re.IGNORECASE)
        while pos < len(cols_str):
            m = col_pat.match(cols_str, pos)
            if not m:
                break
            col_name = m.group(1)
            type_start = m.end()
            depth = 1
            i = type_start
            while i < len(cols_str) and depth > 0:
                if cols_str[i] == "(":
                    depth += 1
                elif cols_str[i] == ")":
                    depth -= 1
                i += 1
            col_type = cols_str[type_start : i - 1]
            columns.append({"name": col_name, "type": col_type})
            pos = i
            if pos < len(cols_str) and cols_str[pos] == ",":
                pos += 2
        return columns

    # -------------------------------------------------------------------------
    # Connection management
    # -------------------------------------------------------------------------

    def list_connections(self) -> list[str]:
        return [c["name"] for c in config_list_connections()]

    def get_connection_info(self, name: str) -> ConnectionInfo | None:
        return get_connection(name)

    def get_default_connection(self) -> str | None:
        return get_default_connection()

    def add_connection(
        self,
        name: str,
        dsn: str,
        description: str = "",
        db_type: str = "sqlite",
        schema: str = "",
        schema_filter: SchemaFilter | None = None,
    ) -> ConnectionInfo:
        result = config_add_connection(
            name=name,
            dsn=dsn,
            description=description,
            db_type=db_type,
            schema=schema,
            schema_filter=schema_filter,
        )
        return result

    def remove_connection(self, name: str) -> bool:
        result = config_remove_connection(name)
        if result:
            self.schema_cache.pop(name, None)
            self._save_schema_cache()
        return result

    def set_default_connection(self, name: str) -> None:
        config_set_default_connection(name)

    def update_schema_filter(self, connection: str, schema_filter: SchemaFilter) -> None:
        update_schema_filter(connection, schema_filter)
        self.schema_cache.pop(connection, None)
        self._save_schema_cache()

    # -------------------------------------------------------------------------
    # Domain query management
    # -------------------------------------------------------------------------

    def list_domain_queries(self, connection: str | None = None) -> list[str]:
        conn_name = connection or get_default_connection() or ""
        return list(get_domain_queries(conn_name).keys())

    def get_domain_queries_info(self, connection: str | None = None) -> list[DomainQueryInfo]:
        conn_name = connection or get_default_connection() or ""
        queries = get_domain_queries(conn_name)
        result: list[DomainQueryInfo] = []
        for name, q in queries.items():
            params = parse_compact_params(q.get("params", q.get("parameters", [])))
            param_str = ", ".join(p["name"] for p in params)
            example = f"tools.execute_domain_query('{name}'"
            if param_str:
                example += f", {param_str}"
            example += ")"
            result.append(
                DomainQueryInfo(
                    name=name,
                    description=q.get("description", ""),
                    parameters=params,
                    returns=q.get("returns", "DataFrame with query results"),
                    example=example,
                )
            )
        return result

    def add_domain_query(self, connection: str, name: str, query_def: DomainQueryDef) -> None:
        config_add_domain_query(connection, name, query_def)

    def remove_domain_query(self, connection: str, name: str) -> bool:
        result = config_remove_domain_query(connection, name)
        return result

    # -------------------------------------------------------------------------
    # LLM Context
    # -------------------------------------------------------------------------

    def get_context_for_llm(self, connection: str | None = None) -> LLMContext:
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        conn_info = get_connection(conn_name)
        if not conn_info:
            raise ValueError(f"Connection '{conn_name}' not found")

        db_type = str(conn_info.get("db_type", "sqlite")).lower()
        schema_compact = self.get_schema(conn_name)
        domain_queries = self.get_domain_queries_info(conn_name)

        return LLMContext(
            connection_name=conn_name,
            db_type=db_type,
            sql_dialect_hint=SQL_DIALECT_HINTS.get(db_type, "Standard SQL"),
            schema_compact=schema_compact,
            domain_queries=domain_queries,
            available_connections=self.list_connections(),
        )

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def shutdown(self) -> None:
        self._save_schema_cache()

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: DatabaseManager | None = None


def get_manager() -> DatabaseManager:
    global _manager
    if _manager is None:
        _manager = DatabaseManager()
    return _manager
