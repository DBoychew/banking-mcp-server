"""
Database analytics MCP tools.

Exposes:
  list_databases()       -> available data sources
  get_database_context() -> schema + domain queries for LLM context
  execute_code()         -> Python sandbox with BankingToolsAPI
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
            "Get database schema and available domain queries for LLM context. "
            "Use this at the start of a conversation to understand available data."
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
            "Execute Python code to analyze data. "
            "The code has access to a `tools` object for SQL queries against the configured database. "
            "Save final output to variable `result`. "
            "IMPORTANT: submit code as a single line using `;` to separate statements. "
            "Literal newlines (\\n) are not supported by the sandbox parser - they cause SyntaxError. "
            "Use UPPERCASE column names from Oracle (e.g. 'DESCRIPTION', not 'description'). "
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
