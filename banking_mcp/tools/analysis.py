"""MCP tool: analyze_spending."""

import json
from typing import Any


def register_analysis_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "Analyse spending for an account over a time period.\n"
            "Returns a breakdown by category (food, dining, transport, etc.), "
            "top merchants, debit/credit totals, and anomaly signals "
            "(unusually large transactions).\n"
            "\n"
            "Arguments:\n"
            "  account_id — account identifier; uses the first account if omitted\n"
            "  from_date  — start date YYYY-MM-DD (defaults to start of current month)\n"
            "  to_date    — end date YYYY-MM-DD (defaults to today)\n"
            "  authorization — leave empty for service credentials"
        )
    )
    async def analyze_spending(
        account_id: str = "",
        from_date: str = "",
        to_date: str = "",
        authorization: str = "",
    ) -> str:
        from banking_mcp.tools._provider import get_provider
        from banking_mcp.analytics.core import analyze_spending as _analyze

        provider = get_provider()
        args: dict[str, Any] = {}
        if account_id:
            args["account_id"] = account_id
        if from_date:
            args["created_from"] = from_date
        if to_date:
            args["created_to"] = to_date

        items = await provider.list_transactions(args, authorization or None)

        currency = ""
        if items:
            currency = str(items[0].get("currency", "")).strip()

        analysis = _analyze(items or [], currency=currency)
        analysis["account_id"] = account_id
        analysis["period"] = {"from": from_date, "to": to_date}

        return json.dumps(analysis, ensure_ascii=False, default=str)
