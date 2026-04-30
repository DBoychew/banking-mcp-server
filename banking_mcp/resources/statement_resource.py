"""MCP resource: statement://{account_id}/{year}/{month}."""

import json


def register_statement_resources(mcp) -> None:

    @mcp.resource("statement://{account_id}/{year}/{month}")
    async def monthly_statement(account_id: str, year: str, month: str) -> str:
        """Full statement for a given month (YYYY/MM)."""
        from banking_mcp.tools._provider import get_provider

        provider = get_provider()
        month_padded = month.zfill(2)
        from_date = f"{year}-{month_padded}-01"

        import calendar
        try:
            last_day = calendar.monthrange(int(year), int(month))[1]
        except (ValueError, TypeError):
            last_day = 31
        to_date = f"{year}-{month_padded}-{last_day:02d}"

        args = {
            "account_id": account_id,
            "from_date": from_date,
            "created_from": from_date,
            "to_date": to_date,
            "created_to": to_date,
        }

        stmt = await provider.get_statement(args, None)

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
            "period": {"from": from_date, "to": to_date},
            "opening_balance": stmt.get("opening_balance"),
            "closing_balance": stmt.get("closing_balance"),
            "summary": stmt.get("summary", {}),
            "transactions": rows,
        }
        return json.dumps(result, ensure_ascii=False, default=str)
