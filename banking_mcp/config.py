from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # -------- Server --------
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = Field(default=8080, ge=1, le=65535)

    # -------- API Key (REST endpoints) --------
    MCP_API_KEY: str = "change-me-in-production"

    # -------- Dashboard --------
    DASHBOARD_PORT: int = Field(default=8501, ge=1, le=65535)
    DASHBOARD_URL: str = "http://localhost:8501"
    DASHBOARD_AUTOSTART: bool = True

    # -------- Audit logging --------
    AUDIT_LOG_PATH: str = "./logs/audit.log"
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=30, ge=1, le=365)
    AUDIT_ENABLED: bool = True

    # -------- MCP transport --------
    # "stdio" for Claude Desktop, "http" for web clients
    MCP_TRANSPORT: str = "stdio"

    # -------- MCP tools --------
    MCP_PROVIDER: str = "db"
    MCP_TOOLS_ALLOW_MUTATIONS: bool = False

    # -------- DB (банкова информация / primary database) --------
    BANK_INFO_DB_PATH: str = "./data/bank_info.db"

    # -------- Oracle DB (когато се получи достъп) --------
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_DSN: str = ""          # e.g. "localhost:1521/XEPDB1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("MCP_TRANSPORT", mode="before")
    def normalize_mcp_transport(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"stdio", "http", "sse"}:
            raise ValueError("MCP_TRANSPORT must be one of: stdio, http, sse")
        return v

    @field_validator("MCP_PROVIDER", mode="before")
    def normalize_mcp_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v:
            raise ValueError("MCP_PROVIDER cannot be empty")
        return v


settings = Settings()
