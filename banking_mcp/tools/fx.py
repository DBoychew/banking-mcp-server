"""MCP tool: get_fx_rates — Bulgarian National Bank exchange rates."""

import json

import httpx

from banking_mcp.adapters.bnb_fx import fetch_bnb_fx_rates
from banking_mcp.config import settings


def register_fx_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "Get current foreign exchange rates from the Bulgarian National Bank (BNB).\n"
            "Rates are EUR-based (how many BGN per 1 EUR, and per 1 unit of each currency).\n"
            "\n"
            "Arguments:\n"
            "  currencies — comma-separated ISO-4217 codes to filter, e.g. 'USD,GBP,CHF'.\n"
            "               Leave empty to return all available rates."
        )
    )
    async def get_fx_rates(currencies: str = "") -> str:
        async with httpx.AsyncClient() as client:
            payload = await fetch_bnb_fx_rates(
                client=client,
                url=settings.BNB_FX_RATES_URL,
                timeout_s=settings.BNB_FX_TIMEOUT_S,
            )

        rates = payload.get("rates", [])
        if currencies:
            wanted = {c.strip().upper() for c in currencies.split(",") if c.strip()}
            rates = [r for r in rates if r.get("code", "") in wanted]

        result = {
            "provider": payload.get("provider", "bnb"),
            "base_currency": payload.get("base_currency", "EUR"),
            "as_of": payload.get("as_of"),
            "rates": rates,
            "count": len(rates),
        }
        return json.dumps(result, ensure_ascii=False)
