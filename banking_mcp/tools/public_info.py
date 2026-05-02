"""MCP tool: get_bank_public_info — reads from configured DB via domain queries."""

import json


_TOPIC_MAP: dict[str, list[str]] = {
    "get_branches": [
        "клон", "офис", "адрес", "филиал", "branch", "office", "address",
        "location", "работно", "hours", "schedule", "working",
    ],
    "get_contacts": [
        "телефон", "имейл", "email", "mail", "контакт", "contact",
        "phone", "връзка", "call",
    ],
    "get_management": [
        "управление", "директор", "ръководство", "борд", "board",
        "management", "director", "executive", "ceo",
    ],
}


def _infer_query(question: str) -> str:
    q = question.lower()
    scores = {name: sum(1 for kw in kws if kw in q) for name, kws in _TOPIC_MAP.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "get_branches"


def register_public_info_tools(mcp) -> None:

    @mcp.tool(
        description=(
            "Get public bank information from the database: branches, contacts, or management.\n"
            "\n"
            "Arguments:\n"
            "  question — natural language question, e.g. 'branch offices in Sofia',\n"
            "             'phone numbers', 'who is the CEO'.\n"
            "  language — 'BG' (default) or 'EN' for contacts."
        )
    )
    async def get_bank_public_info(question: str = "branches", language: str = "BG") -> str:
        from banking_mcp.db.manager import get_manager

        mgr = get_manager()
        query_name = _infer_query(question)

        try:
            # get_branches_by_city: extract city if present
            if query_name == "get_branches":
                city = _extract_city(question)
                if city:
                    df = mgr.execute_domain_query("get_branches_by_city", city=city)
                else:
                    df = mgr.execute_domain_query("get_branches")
            elif query_name == "get_contacts":
                df = mgr.execute_domain_query("get_contacts", language=language.upper())
            else:
                df = mgr.execute_domain_query(query_name)

            rows = df.to_dict("records")
            return json.dumps(
                {"query": query_name, "language": language, "rows": rows, "count": len(rows)},
                ensure_ascii=False,
            )

        except Exception as exc:
            return json.dumps({"error": str(exc), "query": query_name})


def _extract_city(question: str) -> str | None:
    """Very simple city extraction — looks for known Bulgarian city names."""
    cities = ["София", "Варна", "Пловдив", "Бургас", "Русе", "Стара Загора",
              "sofia", "varna", "plovdiv", "burgas", "ruse"]
    q = question.lower()
    for city in cities:
        if city.lower() in q:
            return city
    return None
