"""MCP tool: list_transactions."""

import json
from typing import Any


def register_transaction_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "List account transactions with optional date and pagination filters.\n"
            "\n"
            "Arguments:\n"
            "  account_id  — account identifier; uses the first account if omitted\n"
            "  from_date   — start date as YYYY-MM-DD (defaults to start of current month)\n"
            "  to_date     — end date as YYYY-MM-DD (defaults to today)\n"
            "  limit       — maximum number of results to return (default 50)\n"
            "  offset      — skip first N results for pagination (default 0)\n"
            "  authorization — leave empty for service credentials"
        )
    )
    async def list_transactions(
        account_id: str = "",
        from_date: str = "",
        to_date: str = "",
        limit: int = 50,
        offset: int = 0,
        authorization: str = "",
    ) -> str:
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        args: dict[str, Any] = {"limit": limit, "offset": max(0, offset)}
        if account_id:
            args["account_id"] = account_id
        if from_date:
            args["created_from"] = from_date
        if to_date:
            args["created_to"] = to_date

        items = await provider.list_transactions(args, authorization or None)

        rows = [
            {
                "id": tx.get("transaction_id") or tx.get("id", ""),
                "date": tx.get("created_at") or tx.get("date", ""),
                "amount": tx.get("amount", "0"),
                "currency": tx.get("currency", ""),
                "direction": tx.get("direction", "unknown"),
                "description": tx.get("description", ""),
                "balance_after": tx.get("balance_after", ""),
            }
            for tx in (items or [])
        ]

        return json.dumps(
            {"transactions": rows, "count": len(rows)},
            ensure_ascii=False,
            default=str,
        )
