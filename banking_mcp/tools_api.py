"""
BankingToolsAPI - high-level data access wrapper for the execute_code sandbox.

  - execute_sql_query(sql, connection=None)        -> pd.DataFrame
  - execute_domain_query(name, connection=None,**) -> pd.DataFrame
  - classify_transactions(df, ...)                 -> pd.DataFrame (enriched)
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

    def classify_transactions(
        self,
        df: pd.DataFrame,
        description_column: str = "description",
        direction_column: str | None = None,
    ) -> pd.DataFrame:
        """Enrich a transactions DataFrame with IRIS category codes.

        Adds the following columns to a copy of ``df``:
          - ``category_code``: 12-digit code from the loaded taxonomy, or None.
          - ``category_path``: 'Main > Primary > Sub1 > Sub2' string.
          - ``category_score``: float - match score (higher is more specific).
          - ``category_matched_keywords``: list[str] of keywords that hit.
          - ``category_unclassified``: bool - True when no keyword matched.

        Recommended workflow inside execute_code:
            df = tools.execute_sql_query("SELECT txn_id, description, amount ...")
            enriched = tools.classify_transactions(df)
            unclassified_rate = enriched['category_unclassified'].mean()

        Args:
            df: input DataFrame; must contain ``description_column``.
            description_column: name of the free-text description column.
            direction_column: optional column holding 'incoming'/'outgoing' per
                row. When None, classification runs in 'auto' mode.

        Returns:
            A new DataFrame (original is not mutated) with five extra columns.
            On error (missing column, internal failure) an empty DataFrame is
            returned and ``last_error`` is set, matching the contract of the
            other tools_api methods.
        """
        # Imported lazily so the API module does not pull the taxonomy at
        # import time. The classifier is itself a singleton.
        from banking_mcp.classification import classify

        try:
            self._last_error = None
            if df is None or df.empty:
                return df.copy() if df is not None else pd.DataFrame()
            if description_column not in df.columns:
                raise KeyError(
                    f"description_column {description_column!r} is not in the "
                    f"DataFrame (have: {list(df.columns)})"
                )
            if direction_column is not None and direction_column not in df.columns:
                raise KeyError(
                    f"direction_column {direction_column!r} is not in the "
                    f"DataFrame (have: {list(df.columns)})"
                )

            codes: list[str | None] = []
            paths: list[str | None] = []
            scores: list[float] = []
            matched: list[list[str]] = []
            unclassified: list[bool] = []

            for _, row in df.iterrows():
                description = row[description_column]
                if pd.isna(description) or not str(description).strip():
                    codes.append(None)
                    paths.append(None)
                    scores.append(0.0)
                    matched.append([])
                    unclassified.append(True)
                    continue

                direction = "auto"
                if direction_column is not None:
                    val = row[direction_column]
                    if isinstance(val, str) and val.strip():
                        direction = val.strip().lower()

                # audit=False: emit one batch summary at the end instead.
                result = classify(
                    str(description),
                    direction=direction,
                    top_k=1,
                    audit=False,
                )
                if result.matches:
                    top = result.matches[0]
                    codes.append(top.code)
                    paths.append(top.path)
                    scores.append(top.score)
                    matched.append(list(top.matched_keywords))
                    unclassified.append(False)
                else:
                    codes.append(None)
                    paths.append(None)
                    scores.append(0.0)
                    matched.append([])
                    unclassified.append(True)

            enriched = df.copy()
            enriched["category_code"] = codes
            enriched["category_path"] = paths
            enriched["category_score"] = scores
            enriched["category_matched_keywords"] = matched
            enriched["category_unclassified"] = unclassified

            # Phase 6: one summary audit record per batch.
            from banking_mcp.audit import log_classification

            log_classification(
                description="<batch>",
                direction="auto" if direction_column is None else "per-row",
                top_code=None,
                top_score=0.0,
                unclassified=bool(sum(unclassified)),
                payroll_pattern_hit=False,
                row_count=len(enriched),
                source="tools_api.classify_transactions",
            )
            return enriched
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
