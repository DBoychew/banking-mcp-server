"""Banking MCP resources.

URIs:
  - banking://databases                          -> list of configured connections
  - banking://schema/{connection}                -> compact schema (text)
  - banking://domain-queries/{connection}        -> list of domain queries (JSON)
  - banking://dialects                           -> SQL dialect hints reference (JSON)
  - banking://transaction-categories             -> IRIS taxonomy (full, BG-only)
  - banking://transaction-categories/incoming    -> incoming categories only
  - banking://transaction-categories/outgoing    -> outgoing categories only
  - banking://transaction-categories/payroll-patterns -> BG payroll patterns
  - banking://payment-glossary                   -> BG payment-terminology glossary (UC-CARD-AI-001 §10)
"""

from __future__ import annotations

import json

from banking_mcp.db import SQL_DIALECT_HINTS, get_manager
from banking_mcp.resources import categories_loader, glossary_loader


def register_banking_resources(mcp) -> None:
    @mcp.resource(
        "banking://databases",
        mime_type="application/json",
        description="List of all configured database connections with type and default flag.",
    )
    def databases_resource() -> str:
        db = get_manager()
        connections = []
        for name in db.list_connections():
            info = db.get_connection_info(name)
            if info:
                connections.append(
                    {
                        "name": name,
                        "db_type": info.get("db_type", "unknown"),
                        "description": info.get("description", ""),
                        "is_default": info.get("is_default", False),
                    }
                )
        return json.dumps(
            {"connections": connections, "default": db.get_default_connection()},
            indent=2,
        )

    @mcp.resource(
        "banking://schema/{connection}",
        mime_type="text/plain",
        description="Compact schema for a specific connection: 'table: col(type), ...'.",
    )
    def schema_resource(connection: str) -> str:
        db = get_manager()
        try:
            return db.get_schema(connection)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.resource(
        "banking://domain-queries/{connection}",
        mime_type="application/json",
        description="Pre-configured domain queries available for the connection.",
    )
    def domain_queries_resource(connection: str) -> str:
        db = get_manager()
        try:
            queries = db.get_domain_queries_info(connection)
            return json.dumps(
                {"connection": connection, "domain_queries": queries},
                indent=2,
                default=str,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    @mcp.resource(
        "banking://dialects",
        mime_type="application/json",
        description="SQL dialect hints for every supported db_type.",
    )
    def dialects_resource() -> str:
        return json.dumps(SQL_DIALECT_HINTS, indent=2, ensure_ascii=False)

    @mcp.resource(
        "banking://transaction-categories",
        mime_type="application/json",
        description=(
            "IRIS PSD2Hub transaction taxonomy (BG-only). Full payload: "
            "categories (incoming + outgoing) and payroll patterns."
        ),
    )
    def transaction_categories_resource() -> str:
        return json.dumps(
            categories_loader.load_categories(), ensure_ascii=False, indent=2
        )

    @mcp.resource(
        "banking://transaction-categories/incoming",
        mime_type="application/json",
        description="Incoming-direction (постъпления) categories only.",
    )
    def transaction_categories_incoming_resource() -> str:
        return json.dumps(
            {
                "direction": "incoming",
                "count": len(categories_loader.get_incoming()),
                "categories": categories_loader.get_incoming(),
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource(
        "banking://transaction-categories/outgoing",
        mime_type="application/json",
        description="Outgoing-direction (плащания / разходи) categories only.",
    )
    def transaction_categories_outgoing_resource() -> str:
        return json.dumps(
            {
                "direction": "outgoing",
                "count": len(categories_loader.get_outgoing()),
                "categories": categories_loader.get_outgoing(),
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource(
        "banking://transaction-categories/payroll-patterns",
        mime_type="application/json",
        description="BG payroll description patterns for income-source detection.",
    )
    def transaction_categories_payroll_patterns_resource() -> str:
        patterns = categories_loader.get_payroll_patterns()
        return json.dumps(
            {"count": len(patterns), "patterns": patterns},
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource(
        "banking://transaction-categories/codes",
        mime_type="application/json",
        description=(
            "Flat list of valid category codes with hierarchical paths. "
            "Use as the enum for client-side LLM structured-output fallback "
            "when classify_description returns unclassified - the LLM picks "
            "from this list and cannot invent a code."
        ),
    )
    def transaction_categories_codes_resource() -> str:
        cats = categories_loader.load_categories()["categories"]
        codes = [
            {
                "code": cat["full_code"],
                "direction": cat.get("direction"),
                "leaf_name": cat.get("leaf_name"),
                "path": " > ".join(
                    node["name"]
                    for key in (
                        "main_category",
                        "primary_category",
                        "sub_level_1",
                        "sub_level_2",
                    )
                    for node in [cat.get(key)]
                    if node and node.get("name")
                ),
            }
            for cat in cats
            if cat.get("full_code")
        ]
        return json.dumps(
            {"count": len(codes), "codes": codes}, ensure_ascii=False, indent=2
        )

    @mcp.resource(
        "banking://payment-glossary",
        mime_type="application/json",
        description=(
            "BG payment-terminology glossary (UC-CARD-AI-001 §10). Use this "
            "to answer terminology questions (BIN, interchange, chargeback, "
            "3DS2, PCI-DSS, etc.) with the canonical definitions from the "
            "card-payments spec."
        ),
    )
    def payment_glossary_resource() -> str:
        return json.dumps(
            glossary_loader.load_glossary(), ensure_ascii=False, indent=2
        )

    @mcp.resource(
        "banking://classification-stats",
        mime_type="application/json",
        description=(
            "In-process classification counters: total calls, unclassified "
            "count, payroll-pattern hits, and a per-direction breakdown. "
            "Resets on process restart - durable history lives in audit log."
        ),
    )
    def classification_stats_resource() -> str:
        # Local import to avoid an import cycle at module load.
        from banking_mcp.classification import stats as _stats

        return json.dumps(_stats.snapshot(), ensure_ascii=False, indent=2)
