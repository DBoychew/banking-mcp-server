"""REST API routes for the Banking MCP Server."""

from fastapi import APIRouter, HTTPException

from banking_mcp.config import settings
from banking_mcp.api.schemas import (
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionResponse,
    DomainQueryCreate,
    DomainQueryListResponse,
    DomainQueryResponse,
    MessageResponse,
    ParameterInfoModel,
    SchemaFilterUpdate,
    SetDefaultRequest,
)

api_router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# /api/config  — current server configuration (no secrets)
# ---------------------------------------------------------------------------

@api_router.get("/config")
async def server_config():
    """Return non-sensitive server configuration."""
    return {
        "env": settings.ENV,
        "transport": settings.MCP_TRANSPORT,
        "provider": settings.MCP_PROVIDER,
        "server_port": settings.SERVER_PORT,
        "dashboard_port": settings.DASHBOARD_PORT,
        "dashboard_url": settings.DASHBOARD_URL,
        "audit_enabled": settings.AUDIT_ENABLED,
        "tools_allow_mutations": settings.MCP_TOOLS_ALLOW_MUTATIONS,
    }


# ---------------------------------------------------------------------------
# /api/connections  — connection management (petru pattern)
# ---------------------------------------------------------------------------

def _get_db_manager():
    from banking_mcp.db.manager import get_manager
    return get_manager()


@api_router.get("/connections", response_model=ConnectionListResponse)
async def list_connections():
    """List all configured database connections."""
    mgr = _get_db_manager()
    connections = []
    for conn_info in mgr._config.get("connections", {}).values():
        connections.append(ConnectionResponse(
            name=conn_info.get("name", ""),
            dsn=conn_info.get("dsn", ""),
            description=conn_info.get("description", ""),
            db_type=conn_info.get("db_type", "sqlite"),
            is_default=(conn_info.get("name") == mgr._config.get("default_connection")),
        ))
    return ConnectionListResponse(
        connections=connections,
        default_connection=mgr._config.get("default_connection"),
        count=len(connections),
    )


@api_router.post("/connections", response_model=ConnectionResponse, status_code=201)
async def add_connection(body: ConnectionCreate):
    """Add a new database connection."""
    mgr = _get_db_manager()
    try:
        sf = body.schema_filter.model_dump() if body.schema_filter else None
        conn_info = mgr.add_connection(
            name=body.name,
            dsn=body.dsn,
            description=body.description,
            db_type=body.db_type,
            schema_filter=sf,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ConnectionResponse(
        name=conn_info.get("name", body.name),
        dsn=conn_info.get("dsn", body.dsn),
        description=conn_info.get("description", body.description),
        db_type=conn_info.get("db_type", body.db_type),
        is_default=conn_info.get("is_default", False),
    )


@api_router.delete("/connections/{name}", response_model=MessageResponse)
async def remove_connection(name: str):
    """Remove a database connection."""
    mgr = _get_db_manager()
    removed = mgr.remove_connection(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
    return MessageResponse(message=f"Connection '{name}' removed")


@api_router.post("/connections/{name}/test", response_model=MessageResponse)
async def test_connection(name: str):
    """Test a database connection."""
    mgr = _get_db_manager()
    ok = mgr.test_connection(name)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Connection '{name}' test failed")
    return MessageResponse(message=f"Connection '{name}' is reachable")


@api_router.get("/connections/{name}/schema")
async def get_connection_schema(name: str, force_refresh: bool = False):
    """Get schema for a specific connection."""
    mgr = _get_db_manager()
    try:
        schema = mgr.get_schema(connection=name, force_refresh=force_refresh)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"connection": name, "schema": schema}


@api_router.post("/connections/default", response_model=MessageResponse)
async def set_default_connection(body: SetDefaultRequest):
    """Set the default database connection."""
    mgr = _get_db_manager()
    try:
        mgr.set_default_connection(body.connection)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message=f"Default connection set to '{body.connection}'")


@api_router.put("/connections/{name}/schema-filter", response_model=MessageResponse)
async def update_schema_filter(name: str, body: SchemaFilterUpdate):
    """Update the schema filter for a connection."""
    mgr = _get_db_manager()
    try:
        mgr.update_schema_filter(name, body.schema_filter.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message=f"Schema filter updated for '{name}'")


# ---------------------------------------------------------------------------
# /api/domain-queries  — domain query management (petru pattern)
# ---------------------------------------------------------------------------

@api_router.get("/domain-queries/{connection}", response_model=DomainQueryListResponse)
async def list_domain_queries(connection: str):
    """List all domain queries for a connection."""
    mgr = _get_db_manager()
    queries_info = mgr.get_domain_queries_info(connection=connection)
    queries = [
        DomainQueryResponse(
            name=q["name"],
            description=q["description"],
            parameters=[ParameterInfoModel(**p) for p in q["parameters"]],
            returns=q["returns"],
            example=q["example"],
        )
        for q in queries_info
    ]
    return DomainQueryListResponse(connection=connection, queries=queries, count=len(queries))


@api_router.post("/domain-queries/{connection}", response_model=MessageResponse, status_code=201)
async def add_domain_query(connection: str, body: DomainQueryCreate):
    """Add a domain query to a connection."""
    mgr = _get_db_manager()
    query_def = {
        "sql": body.sql,
        "description": body.description,
        "returns": body.returns,
        "params": [p.model_dump(exclude_none=True) for p in body.params],
    }
    try:
        mgr.add_domain_query(connection=connection, name=body.name, query_def=query_def)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message=f"Domain query '{body.name}' added to '{connection}'")


@api_router.delete("/domain-queries/{connection}/{name}", response_model=MessageResponse)
async def remove_domain_query(connection: str, name: str):
    """Remove a domain query from a connection."""
    mgr = _get_db_manager()
    removed = mgr.remove_domain_query(connection=connection, name=name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Domain query '{name}' not found for '{connection}'")
    return MessageResponse(message=f"Domain query '{name}' removed from '{connection}'")
