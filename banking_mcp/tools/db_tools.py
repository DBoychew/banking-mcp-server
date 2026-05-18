"""
Database analytics MCP tools.

Exposes:
  list_databases()            -> available data sources
  get_database_context()      -> schema + domain queries for LLM context
  get_database_table_list()   -> table names only (lightweight alternative)
  get_table_info()            -> columns + types for one table
  execute_code()              -> Python sandbox with BankingToolsAPI
"""

import json

from banking_mcp.db import get_manager
from banking_mcp.executor import CodeExecutor


def register_db_tools(mcp) -> None:
    @mcp.tool(
        description=(
            "List all configured database connections. "
            "Use this to see available databases before querying."
        )
    )
    def list_databases() -> str:
        """
        List all configured database connections.

        Returns JSON with connection names, types, and descriptions.
        """
        db = get_manager()
        connections = []

        for name in db.list_connections():
            info = db.get_connection_info(name)
            if info:
                connections.append(
                    {
                        "name": name,
                        "db_type": info.get("db_type", "unknown"),
                        "description": info.get("description", ""),
                        "is_default": info.get("is_default", False),
                    }
                )

        return json.dumps(
            {
                "connections": connections,
                "default": db.get_default_connection(),
            },
            indent=2,
        )

    @mcp.tool(
        description=(
            "Heavy convenience wrapper: returns full schema + domain queries + dialect hint "
            "in one call. WARNING: response can exceed 100k tokens on large schemas — "
            "prefer the lightweight alternatives when possible: "
            "use get_database_table_list to see table names, get_table_info for a specific "
            "table's columns, banking://dialects for SQL dialect hints, and "
            "banking://domain-queries/{connection} for pre-configured queries. "
            "Use this tool only when you need domain queries AND schema together in one shot "
            "and the model context window is large enough to handle it."
        )
    )
    def get_database_context(connection: str = "") -> str:
        """
        Get schema and domain queries for LLM context.

        Args:
            connection: Connection name (uses default if not specified)

        Returns:
            JSON with schema, domain queries, and SQL dialect hints.
        """
        db = get_manager()
        conn = connection or db.get_default_connection()

        if not conn:
            return json.dumps(
                {"error": "No connection specified and no default connection configured"}
            )

        try:
            context = db.get_context_for_llm(conn)
            return json.dumps(context, indent=2, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool(
        description=(
            "List all table names in a database connection. "
            "Much lighter than get_database_context - use this first to discover "
            "which tables exist, then call get_table_info for specific tables. "
            "Also check banking://table-descriptions/{connection} for human-written "
            "table and column descriptions before deciding which table to query."
        )
    )
    def get_database_table_list(connection: str = "") -> str:
        db = get_manager()
        conn = connection or db.get_default_connection()
        if not conn:
            return json.dumps(
                {"error": "No connection specified and no default connection configured"}
            )
        try:
            tables = db.get_table_list(conn)
            return json.dumps(
                {"connection": conn, "table_count": len(tables), "tables": tables},
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool(
        description=(
            "Get column names and data types for a single table. "
            "Use after get_database_table_list to inspect a specific table. "
            "Check banking://table-descriptions/{connection} alongside this to "
            "understand column semantics (e.g. AMOUNT_LOCAL_CCY vs CARD_AMOUNT)."
        )
    )
    def get_table_info(table_name: str, connection: str = "") -> str:
        db = get_manager()
        conn = connection or db.get_default_connection()
        if not conn:
            return json.dumps(
                {"error": "No connection specified and no default connection configured"}
            )
        try:
            columns = db.get_table_columns(conn, table_name)
            if columns is None:
                tables = db.get_table_list(conn)
                return json.dumps(
                    {
                        "error": f"Table '{table_name}' not found in connection '{conn}'",
                        "available_tables": tables,
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "connection": conn,
                    "table": table_name,
                    "column_count": len(columns),
                    "columns": columns,
                },
                indent=2,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool(
        description=(
            "Execute Python code to analyze data. "
            "The code has access to a `tools` object for SQL queries against the configured database. "
            "Save final output to variable `result`. "
            "IMPORTANT: submit code as a single line using `;` to separate statements. "
            "Literal newlines (\\n) are not supported by the sandbox parser - they cause SyntaxError. "
            "Use UPPERCASE column names from Oracle (e.g. 'DESCRIPTION', not 'description'). "
            "When columns look duplicate or ambiguous, profile candidates first: count rows, nulls, zeros, min, max, and sample rows. "
            "For top/largest transaction queries, prefer AMOUNT_LOCAL_CCY when available; do not default to CARD_AMOUNT because valid transactions may have CARD_AMOUNT = 0 while AMOUNT_LOCAL_CCY has the real local-currency amount. "
            "Apply the same caution to date, account, customer, currency, branch, office, device, and settlement columns. "
            "Available preloaded: pd (pandas), np (numpy), json, math, tools. "
            "Examples (each is one complete single-line program): "
            "EX1 -> df = tools.execute_sql_query('SELECT * FROM accounts WHERE ROWNUM <= 10'); result = df.to_dict('records') | "
            "EX2 -> df = tools.execute_sql_query('SELECT * FROM accounts', connection='scards'); result = df.to_dict('records') | "
            "EX3 -> df = tools.execute_sql_query('SELECT description FROM card_transactions WHERE ROWNUM <= 50'); enriched = tools.classify_transactions(df, description_column='DESCRIPTION'); result = enriched.to_dict('records') | "
            "EX4 -> df = tools.execute_sql_query('SELECT 1 FROM no_such_table'); result = {'rows': len(df), 'last_error': tools.last_error}"
        )
    )
    def execute_code(code: str) -> str:
        """
        Execute Python code in a sandboxed environment.

        The `tools` object provides:
          tools.execute_sql_query(sql, connection=None)         -> pd.DataFrame
          tools.execute_domain_query(name, connection=None, **) -> pd.DataFrame
          tools.classify_transactions(df, description_column='description',
                                      direction_column=None)    -> pd.DataFrame
          tools.get_context_for_llm(connection=None)            -> LLMContext

        Save your final result to the `result` variable.
        """
        db = get_manager()
        executor = CodeExecutor(db)
        execution_data = executor.execute(code)

        if execution_data["success"]:
            return json.dumps(execution_data["result"], indent=2, default=str)
        return f"Error executing code: {execution_data.get('error')}"
