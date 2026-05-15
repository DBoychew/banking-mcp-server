from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # -------- Server --------
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = Field(default=8080, ge=1, le=65535)

    # -------- Audit logging --------
    AUDIT_LOG_PATH: str = "./logs/audit.log"
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=30, ge=1, le=365)
    AUDIT_ENABLED: bool = True

    # -------- MCP transport --------
    # "stdio" for Claude Desktop, "http" for web clients
    MCP_TRANSPORT: str = "stdio"
    MCP_HTTP_PATH: str = "/banking-assistant"
    MCP_STATELESS_HTTP: bool = True

    # -------- Oracle DB  --------
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_DSN: str = ""
    ORACLE_SCHEMA: str = ""

    # -------- Dashboards (Streamlit) --------
    # External URL the LLM hands to the user.
    DASHBOARD_URL: str = "http://localhost:8501"
    DASHBOARD_PORT: int = Field(default=8501, ge=1, le=65535)
    # Only honored when MCP_TRANSPORT in {"http", "sse"}.
    DASHBOARD_AUTOSTART: bool = True
    DASHBOARD_DEFAULT_ID: str = "default"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("MCP_TRANSPORT", mode="before")
    def normalize_mcp_transport(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"stdio", "http", "sse"}:
            raise ValueError("MCP_TRANSPORT must be one of: stdio, http, sse")
        return v

    @field_validator("MCP_HTTP_PATH", mode="before")
    def normalize_mcp_http_path(cls, v: str) -> str:
        path = (v or "/").strip()
        if not path or path == "/":
            return "/"

        if not path.startswith("/"):
            path = f"/{path}"

        path = path.rstrip("/")
        if "?" in path or "#" in path:
            raise ValueError(
                "MCP_HTTP_PATH must be a clean URL path without query or fragment"
            )

        return path


settings = Settings()
