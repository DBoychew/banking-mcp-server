"""MCP tool: get_statement."""

import json
from typing import Any


def register_statement_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "Get a full account statement for a time period.\n"
            "Returns opening/closing balances, credit/debit totals, and all transactions.\n"
            "\n"
            "Arguments:\n"
            "  account_id — account identifier; uses the first account if omitted\n"
            "  from_date  — start date YYYY-MM-DD (defaults to start of current month)\n"
            "  to_date    — end date YYYY-MM-DD (defaults to today)\n"
            "  authorization — leave empty for service credentials"
        )
    )
    async def get_statement(
        account_id: str = "",
        from_date: str = "",
        to_date: str = "",
        authorization: str = "",
    ) -> str:
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        args: dict[str, Any] = {}
        if account_id:
            args["account_id"] = account_id
        if from_date:
            args["from_date"] = from_date
            args["created_from"] = from_date
        if to_date:
            args["to_date"] = to_date
            args["created_to"] = to_date

        stmt = await provider.get_statement(args, authorization or None)

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
            for tx in (stmt.get("items") or [])
        ]

        result = {
            "account_id": stmt.get("account_id", account_id),
            "currency": stmt.get("currency", ""),
            "period": {
                "from": stmt.get("created_from", from_date),
                "to": stmt.get("created_to", to_date),
            },
            "opening_balance": stmt.get("opening_balance"),
            "closing_balance": stmt.get("closing_balance"),
            "summary": stmt.get("summary", {}),
            "transactions": rows,
        }
        return json.dumps(result, ensure_ascii=False, default=str)
