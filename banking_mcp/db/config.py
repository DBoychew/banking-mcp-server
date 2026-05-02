"""
Connection configuration management — mirrors petru's src/db/config.py.

Manages database connection configs stored in data/db_config.json.
Supports ${VAR} env var substitution in DSN strings, schema filtering,
add/remove connections, and domain query management.
"""

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
CONFIG_FILE = DATA_DIR / "db_config.json"


# ---------------------------------------------------------------------------
# TypedDicts (identical to petru)
# ---------------------------------------------------------------------------

class SchemaFilter(TypedDict, total=False):
    include: list[str]
    exclude: list[str]


class ParameterInfo(TypedDict, total=False):
    name: str
    type: str
    description: str
    required: bool
    default: str | int | float | bool | None


class DomainQueryDef(TypedDict, total=False):
    sql: str
    parameters: str | list[ParameterInfo]
    params: list[dict]           # legacy banking format (list of {name, type, default})
    description: str
    returns: str


class ConnectionInfo(TypedDict, total=False):
    name: str
    dsn: str
    description: str
    db_type: str       # sqlite, oracle
    schema_filter: SchemaFilter
    is_default: bool


class ConfigData(TypedDict, total=False):
    connections: dict[str, ConnectionInfo]
    default_connection: str
    domain_queries: dict[str, dict[str, DomainQueryDef]]


# ---------------------------------------------------------------------------
# Default config (bank_info SQLite)
# ---------------------------------------------------------------------------

def _get_default_config() -> ConfigData:
    return {
        "connections": {
            "bank_info": {
                "name": "bank_info",
                "dsn": "${BANK_INFO_DB_PATH}",
                "description": "Bank public information (branches, contacts, management)",
                "db_type": "sqlite",
                "schema_filter": {"include": [], "exclude": []},
            }
        },
        "default_connection": "bank_info",
        "domain_queries": {
            "bank_info": {
                "get_branches": {
                    "sql": "SELECT * FROM bank_branches ORDER BY city, name",
                    "description": "List all bank branches and offices",
                    "returns": "DataFrame with branch info",
                    "params": [],
                },
                "get_branches_by_city": {
                    "sql": "SELECT * FROM bank_branches WHERE LOWER(city) LIKE LOWER(:city) ORDER BY name",
                    "description": "List branches in a specific city",
                    "returns": "DataFrame with branch info filtered by city",
                    "params": [
                        {"name": "city", "type": "string", "description": "City name to filter by"},
                    ],
                },
                "get_contacts": {
                    "sql": "SELECT * FROM bank_contacts WHERE UPPER(language) = UPPER(:language) ORDER BY type, id",
                    "description": "Get bank contact information (phone, email, website)",
                    "returns": "DataFrame with contact info",
                    "params": [
                        {"name": "language", "type": "string", "default": "BG", "description": "Language code: BG or EN"},
                    ],
                },
                "get_management": {
                    "sql": "SELECT * FROM bank_management ORDER BY id",
                    "description": "Get bank management board members and positions",
                    "returns": "DataFrame with management info",
                    "params": [],
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_config() -> ConfigData:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Normalise: accept legacy "type" key as "db_type"
            for conn in data.get("connections", {}).values():
                if "db_type" not in conn and "type" in conn:
                    conn["db_type"] = conn.pop("type")
            return data
        except (json.JSONDecodeError, IOError):
            pass
    config = _get_default_config()
    save_config(config)
    return config


def save_config(config: ConfigData) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# DSN resolution
# ---------------------------------------------------------------------------

def resolve_dsn(dsn: str) -> str:
    """Substitute ${VAR} placeholders with environment variables."""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        value = os.environ.get(var)
        if value is None:
            raise ValueError(f"Environment variable '{var}' is not set")
        return value
    return re.sub(r"\$\{(\w+)\}", _replace, dsn)


# ---------------------------------------------------------------------------
# Connection CRUD
# ---------------------------------------------------------------------------

def get_connection(name: str) -> ConnectionInfo | None:
    config = load_config()
    conn = config.get("connections", {}).get(name)
    if conn:
        conn = dict(conn)
        conn["is_default"] = (name == config.get("default_connection"))
    return conn


def list_connections() -> list[ConnectionInfo]:
    config = load_config()
    default = config.get("default_connection", "")
    result = []
    for name, conn in config.get("connections", {}).items():
        info = dict(conn)
        info["is_default"] = (name == default)
        result.append(info)
    return result


def get_default_connection() -> str | None:
    return load_config().get("default_connection") or None


def add_connection(
    name: str,
    dsn: str,
    description: str = "",
    db_type: str = "sqlite",
    schema_filter: SchemaFilter | None = None,
) -> ConnectionInfo:
    config = load_config()
    if name in config.get("connections", {}):
        raise ValueError(f"Connection '{name}' already exists")

    conn: ConnectionInfo = {
        "name": name,
        "dsn": dsn,
        "description": description,
        "db_type": db_type,
        "schema_filter": schema_filter or {"include": [], "exclude": []},
    }
    config.setdefault("connections", {})[name] = conn
    if not config.get("default_connection"):
        config["default_connection"] = name
    save_config(config)
    conn["is_default"] = (name == config["default_connection"])
    return conn


def remove_connection(name: str) -> bool:
    config = load_config()
    if name not in config.get("connections", {}):
        return False
    del config["connections"][name]
    if name in config.get("domain_queries", {}):
        del config["domain_queries"][name]
    if config.get("default_connection") == name:
        remaining = list(config.get("connections", {}).keys())
        config["default_connection"] = remaining[0] if remaining else ""
    save_config(config)
    return True


def set_default_connection(name: str) -> None:
    config = load_config()
    if name not in config.get("connections", {}):
        raise ValueError(f"Connection '{name}' does not exist")
    config["default_connection"] = name
    save_config(config)


def update_schema_filter(connection: str, schema_filter: SchemaFilter) -> None:
    config = load_config()
    if connection not in config.get("connections", {}):
        raise ValueError(f"Connection '{connection}' does not exist")
    config["connections"][connection]["schema_filter"] = schema_filter
    save_config(config)


# ---------------------------------------------------------------------------
# Domain queries
# ---------------------------------------------------------------------------

def get_domain_queries(connection: str) -> dict[str, DomainQueryDef]:
    return load_config().get("domain_queries", {}).get(connection, {})


def add_domain_query(connection: str, name: str, query_def: DomainQueryDef) -> None:
    config = load_config()
    if connection not in config.get("connections", {}):
        raise ValueError(f"Connection '{connection}' does not exist")
    config.setdefault("domain_queries", {}).setdefault(connection, {})[name] = query_def
    save_config(config)


def remove_domain_query(connection: str, name: str) -> bool:
    config = load_config()
    queries = config.get("domain_queries", {}).get(connection, {})
    if name not in queries:
        return False
    del queries[name]
    save_config(config)
    return True


# ---------------------------------------------------------------------------
# Schema filtering
# ---------------------------------------------------------------------------

def filter_tables(tables: list[str], schema_filter: SchemaFilter) -> list[str]:
    include = schema_filter.get("include", [])
    exclude = schema_filter.get("exclude", [])
    if include:
        tables = [t for t in tables if any(fnmatch.fnmatch(t, p) for p in include)]
    if exclude:
        tables = [t for t in tables if not any(fnmatch.fnmatch(t, p) for p in exclude)]
    return tables


# ---------------------------------------------------------------------------
# Parameter parsing (petru compact format + banking list format)
# ---------------------------------------------------------------------------

def parse_compact_params(params: str | list) -> list[ParameterInfo]:
    """Parse parameters — supports petru's compact string format and banking's list format."""
    if isinstance(params, list):
        # Banking format: [{name, type, default, description}]
        result = []
        for p in params:
            info: ParameterInfo = {"name": p["name"], "required": False}
            if "default" in p:
                info["default"] = p["default"]
            if "description" in p:
                info["description"] = p["description"]
            if "type" in p:
                info["type"] = p["type"]
            result.append(info)
        return result

    if not params or not str(params).strip():
        return []

    # Petru compact string format: "param=default (desc), ..."
    import re as _re
    result = []
    param_strs = _re.split(r"\),\s*(?=\w+=)", str(params).strip())
    for param_str in param_strs:
        param_str = param_str.strip()
        if not param_str or "=" not in param_str:
            continue
        desc = ""
        match = _re.search(r"\s+\(([^)]+)\)?\s*$", param_str)
        if match:
            desc = match.group(1).strip()
            param_str = param_str[: match.start()].strip()
        name, value = param_str.split("=", 1)
        name = name.strip()
        value = value.strip()
        param: ParameterInfo = {"name": name, "required": False}
        if desc:
            param["description"] = desc
        if "|" in value and '"' in value:
            param["type"] = "str"
            choices = _re.findall(r'"([^"]*)"', value)
            if choices:
                param["default"] = choices[0]
        elif value.lower() in ("true", "false"):
            param["type"] = "bool"
            param["default"] = value.lower() == "true"
        elif "." in value:
            try:
                param["type"] = "float"
                param["default"] = float(value)
            except ValueError:
                param["type"] = "str"
                param["default"] = value
        else:
            try:
                param["type"] = "int"
                param["default"] = int(value)
            except ValueError:
                param["type"] = "str"
                param["default"] = value
        result.append(param)
    return result
