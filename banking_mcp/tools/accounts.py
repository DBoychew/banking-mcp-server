"""MCP tools: list_accounts, get_balance."""

import json


def register_account_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "List all bank accounts with balances, IBANs, and status. "
            "Returns a JSON object with an 'accounts' array. "
            "Pass 'authorization' only for delegated auth (eBank session or Basic creds). "
            "Leave empty to use service credentials from environment."
        )
    )
    async def list_accounts(authorization: str = "") -> str:
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        accounts = await provider.list_accounts(authorization or None)

        if not accounts:
            return json.dumps({"accounts": [], "count": 0})

        rows = [
            {
                "account_id": acc.get("account_id", ""),
                "iban": acc.get("iban", ""),
                "currency": acc.get("currency", ""),
                "balance": acc.get("balance", "0"),
                "status": acc.get("status", "active"),
            }
            for acc in accounts
        ]
        return json.dumps({"accounts": rows, "count": len(rows)}, ensure_ascii=False)

    @mcp.tool(
        description=(
            "Get the current balance for a specific account by account_id. "
            "Use list_accounts first to discover valid account IDs. "
            "Returns a JSON object with account_id, balance, currency, and IBAN."
        )
    )
    async def get_balance(account_id: str, authorization: str = "") -> str:
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        accounts = await provider.list_accounts(authorization or None)

        for acc in accounts:
            if acc.get("account_id") == account_id:
                return json.dumps(
                    {
                        "account_id": account_id,
                        "balance": acc.get("balance", "0"),
                        "currency": acc.get("currency", ""),
                        "iban": acc.get("iban", ""),
                        "status": acc.get("status", ""),
                    },
                    ensure_ascii=False,
                )

        return json.dumps({"error": f"Account '{account_id}' not found."})
