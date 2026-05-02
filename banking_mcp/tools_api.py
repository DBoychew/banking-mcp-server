"""
BankingToolsAPI — high-level data access wrapper for the execute_code sandbox
and generated dashboards.

Mirrors petru's ToolsAPI pattern:
  - execute_sql_query()    → SELECT queries against any configured DB
  - execute_domain_query() → pre-configured SQL templates
  - get_context_for_llm()  → schema + domain queries for current connection
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from banking_mcp.db.manager import DatabaseManager


class BankingToolsAPI:
    """
    Unified data access API for the code sandbox and generated dashboards.

    SQL access:
        df = tools.execute_sql_query("SELECT * FROM bank_branches")
        df = tools.execute_domain_query("get_branches")
        df = tools.execute_domain_query("get_branches_by_city", city="Sofia")
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",
        default_connection: str | None = None,
    ) -> None:
        self._db = db_manager
        self._default_conn = default_connection or db_manager.get_default_connection()
        self._last_error: str | None = None

    def execute_sql_query(self, sql: str, connection: str | None = None) -> pd.DataFrame:
        """Execute a SELECT query against the configured database, return DataFrame."""
        try:
            df = self._db.query(sql, connection=connection or self._default_conn)
            self._last_error = None
            return df
        except Exception as e:
            self._last_error = str(e)
            return pd.DataFrame()

    def execute_domain_query(self, name: str, connection: str | None = None, **params: Any) -> pd.DataFrame:
        """Execute a pre-configured domain query, return DataFrame."""
        try:
            df = self._db.execute_domain_query(name, connection=connection or self._default_conn, **params)
            self._last_error = None
            return df
        except Exception as e:
            self._last_error = str(e)
            return pd.DataFrame()

    def get_context_for_llm(self, connection: str | None = None) -> str:
        """Return schema + domain queries context for LLM prompts."""
        return self._db.get_context_for_llm(connection or self._default_conn)

    @property
    def last_error(self) -> str | None:
        return self._last_error
