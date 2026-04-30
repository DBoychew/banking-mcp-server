"""MCP resource: account://{account_id}/summary."""

import json


def register_account_resources(mcp) -> None:

    @mcp.resource("account://{account_id}/summary")
    async def account_summary(account_id: str) -> str:
        """Current balance and status for a bank account."""
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        accounts = await provider.list_accounts(None)

        for acc in accounts:
            if acc.get("account_id") == account_id:
                return json.dumps(
                    {
                        "account_id": account_id,
                        "iban": acc.get("iban", ""),
                        "currency": acc.get("currency", ""),
                        "balance": acc.get("balance", "0"),
                        "status": acc.get("status", ""),
                    },
                    ensure_ascii=False,
                )

        return json.dumps({"error": f"Account '{account_id}' not found."})
