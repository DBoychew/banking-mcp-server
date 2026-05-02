"""
DatabaseManager — mirrors petru's src/db/manager.py pattern.

Key additions over the original:
  - query()              → pd.DataFrame   (petru's primary method)
  - schema caching       → 24h TTL + disk persistence
  - add/remove/test connection
  - add/remove domain queries
  - get_domain_queries_info()
  - SQL dialect hints
  - shutdown()
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd

from .config import (
    CONFIG_FILE,
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
    set_default_connection as config_set_default_connection,
    update_schema_filter,
)

logger = logging.getLogger(__name__)

import os
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
SCHEMA_CACHE_FILE = DATA_DIR / "schema_cache.json"
SCHEMA_CACHE_TTL = timedelta(hours=24)

# SQL keywords forbidden (read-only enforcement)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

# SQL dialect hints (mirrors petru)
SQL_DIALECT_HINTS: dict[str, str] = {
    "sqlite": "SQLite: Use strftime() for dates, || for concat, LIKE is case-insensitive by default",
    "oracle": "Oracle: Use TO_DATE(), TO_CHAR(), || for concat, ROWNUM for row limiting",
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
# Low-level connection factory
# ---------------------------------------------------------------------------

def _open_sqlite(path: str) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _open_connection(conn_info: ConnectionInfo) -> Any:
    db_type = conn_info.get("db_type", "sqlite").lower()
    raw_dsn = conn_info.get("dsn", "")
    try:
        dsn = resolve_dsn(raw_dsn)
    except ValueError:
        dsn = raw_dsn  # fallback: use raw DSN without substitution

    if db_type == "sqlite":
        path = dsn.removeprefix("sqlite:///").removeprefix("sqlite://")
        return _open_sqlite(path)

    if db_type == "oracle":
        import oracledb
        return oracledb.connect(dsn=dsn)

    raise ValueError(f"Unsupported db_type: {db_type!r}")


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """
    Multi-connection database manager for the banking MCP server.

    Supports SQLite (bank_info) and Oracle.
    Mirrors petru's DatabaseManager interface:
      - query()                → pd.DataFrame
      - execute_domain_query() → pd.DataFrame
      - get_schema()           → str (compact, cached 24h)
      - get_context_for_llm()  → LLMContext dict
      - add/remove/test connection
      - add/remove domain queries
    """

    def __init__(self) -> None:
        self._config = load_config()
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
        if _FORBIDDEN.search(sql):
            raise ValueError("Forbidden SQL keyword detected. Only SELECT queries are allowed.")

    # -------------------------------------------------------------------------
    # Core query — returns pd.DataFrame  (petru pattern)
    # -------------------------------------------------------------------------

    def query(
        self,
        sql: str,
        connection: str | None = None,
        source: str = "api",
    ) -> pd.DataFrame:
        """
        Execute a SELECT query and return a pd.DataFrame.

        This is the primary method — mirrors petru's DatabaseManager.query().
        """
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        self._validate_sql(sql)

        conn_info = get_connection(conn_name)
        if not conn_info:
            raise ValueError(f"Connection '{conn_name}' not found")

        start = time.perf_counter()
        db_conn = _open_connection(conn_info)
        try:
            cursor = db_conn.execute(sql)
            columns = [d[0] for d in (cursor.description or [])]
            rows = cursor.fetchall()
            df = pd.DataFrame([dict(zip(columns, row)) for row in rows])
            logger.debug("query ok [%s] %.1fms %d rows", conn_name, (time.perf_counter() - start) * 1000, len(df))
            return df
        finally:
            db_conn.close()

    def execute_sql(
        self,
        sql: str,
        connection: str | None = None,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """
        Execute a raw SELECT with SQLite named params (:name).

        Returns list[dict] for backward compatibility with banking tools.
        """
        self._validate_sql(sql)
        conn_name = connection or get_default_connection()
        conn_info = get_connection(conn_name or "")
        if not conn_info:
            raise KeyError(f"Connection {conn_name!r} not found")

        db_conn = _open_connection(conn_info)
        try:
            cursor = db_conn.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            db_conn.close()

    def test_connection(self, connection: str) -> bool:
        """Return True if the connection can execute a simple query."""
        try:
            conn_info = get_connection(connection)
            if not conn_info:
                return False
            db_conn = _open_connection(conn_info)
            db_conn.execute("SELECT 1")
            db_conn.close()
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Domain queries — returns pd.DataFrame  (petru pattern)
    # -------------------------------------------------------------------------

    def execute_domain_query(
        self,
        name: str,
        connection: str | None = None,
        source: str = "domain_query",
        **params: Any,
    ) -> pd.DataFrame:
        """Execute a pre-configured domain query, return pd.DataFrame."""
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        queries = get_domain_queries(conn_name)
        if name not in queries:
            raise ValueError(f"Domain query '{name}' not found for connection '{conn_name}'. Available: {list(queries)}")

        query_def = queries[name]
        sql = query_def["sql"]

        # Merge config defaults with caller params
        merged: dict[str, Any] = {}
        for p in query_def.get("params", []):
            if "default" in p:
                merged[p["name"]] = p["default"]
        merged.update(params)

        # Use execute_sql with SQLite named params (:name)
        rows = self.execute_sql(sql, connection=conn_name, **merged)
        return pd.DataFrame(rows)

    # -------------------------------------------------------------------------
    # Schema — cached 24h (petru pattern)
    # -------------------------------------------------------------------------

    def get_schema(self, connection: str | None = None, force_refresh: bool = False) -> str:
        """
        Return compact schema: 'table: col(type), ...'

        Cached for 24h. Pass force_refresh=True to bypass cache.
        """
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        cache_key = conn_name
        cached = self.schema_cache.get(cache_key)

        if cached and not force_refresh:
            cached_at = datetime.fromisoformat(cached["cached_at"])
            if datetime.now() - cached_at < SCHEMA_CACHE_TTL:
                return cached["schema"]

        schema = self._fetch_schema(conn_name)
        self.schema_cache[cache_key] = {
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

        if db_type == "sqlite":
            return self._fetch_sqlite_schema(conn_info)

        return f"Schema introspection not supported for db_type={db_type!r}"

    def _fetch_sqlite_schema(self, conn_info: ConnectionInfo) -> str:
        schema_filter = conn_info.get("schema_filter", {"include": [], "exclude": []})
        db_conn = _open_connection(conn_info)
        try:
            cursor = db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
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
            db_conn.close()

    def refresh_schema(self, connection: str | None = None) -> str:
        return self.get_schema(connection, force_refresh=True)

    # -------------------------------------------------------------------------
    # Connection management (petru pattern)
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
        schema_filter: SchemaFilter | None = None,
    ) -> ConnectionInfo:
        result = config_add_connection(name=name, dsn=dsn, description=description, db_type=db_type, schema_filter=schema_filter)
        self._config = load_config()
        return result

    def remove_connection(self, name: str) -> bool:
        result = config_remove_connection(name)
        if result:
            self.schema_cache.pop(name, None)
            self._save_schema_cache()
            self._config = load_config()
        return result

    def set_default_connection(self, name: str) -> None:
        config_set_default_connection(name)
        self._config = load_config()

    def update_schema_filter(self, connection: str, schema_filter: SchemaFilter) -> None:
        update_schema_filter(connection, schema_filter)
        self.schema_cache.pop(connection, None)
        self._save_schema_cache()
        self._config = load_config()

    # -------------------------------------------------------------------------
    # Domain query management (petru pattern)
    # -------------------------------------------------------------------------

    def list_domain_queries(self, connection: str | None = None) -> list[str]:
        conn_name = connection or get_default_connection() or ""
        return list(get_domain_queries(conn_name).keys())

    def get_domain_queries_info(self, connection: str | None = None) -> list[DomainQueryInfo]:
        conn_name = connection or get_default_connection() or ""
        queries = get_domain_queries(conn_name)
        result = []
        for name, q in queries.items():
            params = parse_compact_params(q.get("params", []))
            param_str = ", ".join(p["name"] for p in params)
            example = f"tools.execute_domain_query('{name}'"
            if param_str:
                example += f", {param_str}"
            example += ")"
            result.append(DomainQueryInfo(
                name=name,
                description=q.get("description", ""),
                parameters=params,
                returns=q.get("returns", "DataFrame with query results"),
                example=example,
            ))
        return result

    def add_domain_query(self, connection: str, name: str, query_def: DomainQueryDef) -> None:
        config_add_domain_query(connection, name, query_def)
        self._config = load_config()

    def remove_domain_query(self, connection: str, name: str) -> bool:
        result = config_remove_domain_query(connection, name)
        if result:
            self._config = load_config()
        return result

    # -------------------------------------------------------------------------
    # LLM Context (petru pattern)
    # -------------------------------------------------------------------------

    def get_context_for_llm(self, connection: str | None = None) -> LLMContext:
        """Return structured context dict for LLM system prompts — mirrors petru."""
        conn_name = connection or get_default_connection()
        if not conn_name:
            raise ValueError("No connection specified and no default connection configured")

        conn_info = get_connection(conn_name)
        if not conn_info:
            raise ValueError(f"Connection '{conn_name}' not found")

        db_type = conn_info.get("db_type", "sqlite")
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
