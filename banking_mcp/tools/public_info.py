"""MCP tool: get_bank_public_info — branches, contacts, hours, management."""

import json

from banking_mcp.knowledge.bank_public_info import fetch_bank_public_info_payload


def register_public_info_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "Get public information about the bank.\n"
            "\n"
            "Arguments:\n"
            "  question — freeform question or keyword such as:\n"
            "             'branches', 'offices', 'contact', 'hours', 'management'\n"
            "             or any city/person name for targeted lookup.\n"
            "  language — 'bg' for Bulgarian output, 'en' for English (default 'bg')"
        )
    )
    async def get_bank_public_info(question: str = "contact", language: str = "bg") -> str:
        payload = await fetch_bank_public_info_payload(
            question=question,
            language=language or "bg",
        )
        if not payload:
            return json.dumps({"error": "No information found for the given query."})
        return json.dumps(payload, ensure_ascii=False, default=str)
