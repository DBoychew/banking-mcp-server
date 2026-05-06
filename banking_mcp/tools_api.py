"""
BankingToolsAPI - high-level data access wrapper for the execute_code sandbox.

  - execute_sql_query(sql, connection=None)        -> pd.DataFrame
  - execute_domain_query(name, connection=None,**) -> pd.DataFrame
  - get_context_for_llm(connection=None)           -> LLMContext
  - last_error                                     -> str | None

The sandbox passes this object as ``tools`` so user code can run multi-DB
analytics without ever touching a driver directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from banking_mcp.db.manager import DatabaseManager, LLMContext


class BankingToolsAPI:
    """Unified data access API for the code sandbox."""

    def __init__(
        self,
        db_manager: "DatabaseManager",
        default_connection: str | None = None,
    ) -> None:
        self._db = db_manager
        self._default_conn = default_connection or db_manager.get_default_connection()
        self._last_error: str | None = None

    def _resolve_connection(self, connection: str | None) -> str:
        conn = connection or self._default_conn
        if not conn:
            raise ValueError(
                "No connection specified and no default connection configured"
            )
        return conn

    def execute_sql_query(self, sql: str, connection: str | None = None) -> pd.DataFrame:
        """Execute a SELECT query and return a DataFrame (empty on error)."""
        try:
            conn = self._resolve_connection(connection)
            self._last_error = None
            return self._db.query(sql, connection=conn, source="tools_api")
        except Exception as e:
            self._last_error = str(e)
            return pd.DataFrame()

    def execute_domain_query(
        self,
        name: str,
        connection: str | None = None,
        **params: Any,
    ) -> pd.DataFrame:
        """Execute a pre-configured domain query and return a DataFrame."""
        try:
            conn = self._resolve_connection(connection)
            self._last_error = None
            return self._db.execute_domain_query(
                name=name,
                connection=conn,
                source="tools_api",
                **params,
            )
        except Exception as e:
            self._last_error = str(e)
            return pd.DataFrame()

    def get_context_for_llm(self, connection: str | None = None) -> "LLMContext":
        """Return schema + domain queries + dialect hint for the LLM prompt."""
        conn = self._resolve_connection(connection)
        return self._db.get_context_for_llm(conn)

    @property
    def last_error(self) -> str | None:
        return self._last_error
