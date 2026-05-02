"""Pydantic response models for the REST API."""

from typing import Any, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Connection management (petru pattern)
# ---------------------------------------------------------------------------

class SchemaFilterModel(BaseModel):
    include: list[str] = []
    exclude: list[str] = []


class ConnectionCreate(BaseModel):
    name: str
    dsn: str
    description: str = ""
    db_type: str = "sqlite"
    schema_filter: Optional[SchemaFilterModel] = None


class ConnectionResponse(BaseModel):
    name: str
    dsn: str
    description: str = ""
    db_type: str = "sqlite"
    schema_filter: Optional[SchemaFilterModel] = None
    is_default: bool = False


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionResponse]
    default_connection: Optional[str] = None
    count: int


class SetDefaultRequest(BaseModel):
    connection: str


class SchemaFilterUpdate(BaseModel):
    schema_filter: SchemaFilterModel


# ---------------------------------------------------------------------------
# Domain query management (petru pattern)
# ---------------------------------------------------------------------------

class ParameterInfoModel(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Optional[Any] = None


class DomainQueryCreate(BaseModel):
    name: str
    sql: str
    description: str = ""
    returns: str = "DataFrame with query results"
    params: list[ParameterInfoModel] = []


class DomainQueryResponse(BaseModel):
    name: str
    description: str = ""
    parameters: list[ParameterInfoModel] = []
    returns: str = ""
    example: str = ""


class DomainQueryListResponse(BaseModel):
    connection: str
    queries: list[DomainQueryResponse]
    count: int


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str
