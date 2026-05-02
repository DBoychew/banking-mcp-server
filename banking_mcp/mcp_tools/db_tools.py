"""
Database & analytics MCP tools — mirrors petru's src/mcp_tools/db_tools.py.

Exposes three tools:
  list_databases()           → available data sources (bank_info + ebank)
  get_database_context()     → schema + domain queries for LLM context
  execute_code()             → Python sandbox with BankingToolsAPI
"""

import json
from typing import Optional

from banking_mcp.db import DatabaseManager, get_manager
from banking_mcp.executor import CodeExecutor


def register_db_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "List all available data sources. "
            "Use this to see what databases and banking APIs are accessible before querying."
        )
    )
    def list_databases() -> str:
        """
        List all configured data sources.

        Returns JSON with connection names, types, and descriptions.
        Includes both the bank_info SQLite database and the eBank HTTP API.
        """
        db = get_manager()
        connections = []

        for name in db.list_connections():
            info = db.get_connection_info(name)
            if info:
                connections.append({
                    "name": name,
                    "db_type": info.get("db_type", "unknown"),
                    "description": info.get("description", ""),
                    "is_default": info.get("is_default", False),
                })

        # Always include the ebank virtual connection
        ebank_names = {c["name"] for c in connections}
        if "ebank" not in ebank_names:
            connections.append({
                "name": "ebank",
                "db_type": "ebank_http",
                "description": "eBank HTTP adapter — accounts, transactions, statements",
                "is_default": False,
            })

        return json.dumps({
            "connections": connections,
            "default": db.get_default_connection(),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get schema and available domain queries for a data source. "
            "Use this at the start of a conversation to understand what data is available. "
            "Pass connection='ebank' for live banking data, or leave empty for bank_info SQLite."
        )
    )
    def get_database_context(connection: str = "") -> str:
        """
        Get schema and domain queries for LLM context.

        Args:
            connection: Connection name — 'bank_info' (SQLite), 'ebank' (HTTP API),
                        or empty for default.

        Returns JSON with schema, domain queries, and usage hints.
        """
        db = get_manager()
        conn = connection or db.get_default_connection()

        if conn == "ebank":
            return json.dumps({
                "connection": "ebank",
                "db_type": "ebank_http",
                "description": "eBank HTTP API — live banking data",
                "schema": (
                    "accounts: account_id(str), iban(str), currency(str), balance(float), status(str)\n"
                    "transactions: id(str), date(str), amount(float), currency(str), "
                    "direction(str:debit|credit), description(str), balance_after(float)\n"
                    "fx_rates: code(str), name(str), rate_per_eur(float), eur_per_unit(float), as_of(str)"
                ),
                "domain_queries": [
                    {
                        "name": "get_accounts",
                        "description": "List all accounts with balances",
                        "example": "accounts = tools.get_accounts()",
                        "returns": "list of account dicts",
                    },
                    {
                        "name": "get_transactions",
                        "description": "List transactions for an account in a date range",
                        "parameters": "account_id, from_date='YYYY-MM-DD', to_date='YYYY-MM-DD', limit=100",
                        "example": "txns = tools.get_transactions('ACC-001', '2026-01-01', '2026-04-30')",
                        "returns": "list of transaction dicts",
                    },
                    {
                        "name": "get_fx_rates",
                        "description": "Get BNB exchange rates (EUR-based)",
                        "parameters": "currencies='USD,GBP,CHF' (comma-separated ISO codes, empty=all)",
                        "example": "fx = tools.get_fx_rates('USD,EUR,GBP')",
                        "returns": "list of rate dicts",
                    },
                    {
                        "name": "accounts_df",
                        "description": "Accounts as a pandas DataFrame",
                        "example": "df = tools.accounts_df()",
                    },
                    {
                        "name": "transactions_df",
                        "description": "Transactions as a pandas DataFrame",
                        "parameters": "account_id, from_date, to_date, limit=100",
                        "example": "df = tools.transactions_df('ACC-001', '2026-01-01', '2026-04-30')",
                    },
                    {
                        "name": "fx_rates_df",
                        "description": "FX rates as a pandas DataFrame",
                        "example": "df = tools.fx_rates_df('USD,EUR')",
                    },
                ],
                "hints": (
                    "Use tools.get_accounts() to list accounts first. "
                    "Use account_id from results to query transactions. "
                    "direction='debit' means money out, 'credit' means money in. "
                    "All dates are ISO 8601 (YYYY-MM-DD)."
                ),
            }, indent=2)

        try:
            context = db.get_context_for_llm(conn)
            return json.dumps(context, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool(
        description=(
            "Execute Python code to analyze banking data. "
            "The code has access to a `tools` object with banking methods and SQL queries. "
            "Save final output to variable `result`.\n\n"
            "Banking data examples:\n"
            "  accounts = tools.get_accounts()\n"
            "  txns = tools.get_transactions('ACC-001', '2026-01-01', '2026-04-30')\n"
            "  df = tools.transactions_df('ACC-001', '2026-01-01', '2026-04-30')\n"
            "  fx = tools.get_fx_rates('USD,EUR,GBP')\n\n"
            "SQL examples (bank_info SQLite):\n"
            "  df = tools.execute_sql_query('SELECT * FROM bank_branches WHERE city = :city', city='Sofia')\n"
            "  df = tools.execute_domain_query('get_branches')\n\n"
            "Available: pd (pandas), np (numpy), json, math."
        )
    )
    def execute_code(code: str) -> str:
        """
        Execute Python code in a sandboxed environment.

        The `tools` object provides:
          tools.get_accounts()                           → list[dict]
          tools.get_transactions(account_id, from, to)   → list[dict]
          tools.get_fx_rates(currencies)                 → list[dict]
          tools.accounts_df()                            → pd.DataFrame
          tools.transactions_df(account_id, from, to)    → pd.DataFrame
          tools.fx_rates_df(currencies)                  → pd.DataFrame
          tools.execute_sql_query(sql)                   → pd.DataFrame
          tools.execute_domain_query(name, **params)     → pd.DataFrame

        Save your final result to the `result` variable.
        """
        db = get_manager()
        executor = CodeExecutor(db)
        execution_data = executor.execute(code)

        if execution_data["success"]:
            return json.dumps(execution_data["result"], indent=2, default=str)
        else:
            return f"Error executing code: {execution_data.get('error')}"
