"""Banking MCP resources.

URIs:
  - banking://databases                    -> list of configured connections
  - banking://schema/{connection}          -> compact schema (text)
  - banking://domain-queries/{connection}  -> list of domain queries (JSON)
  - banking://dialects                     -> SQL dialect hints reference (JSON)
"""

from __future__ import annotations

import json

from banking_mcp.db import SQL_DIALECT_HINTS, get_manager


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
