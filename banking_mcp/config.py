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

    # -------- Oracle DB  --------
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_DSN: str = ""
    ORACLE_SCHEMA: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("MCP_TRANSPORT", mode="before")
    def normalize_mcp_transport(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"stdio", "http", "sse"}:
            raise ValueError("MCP_TRANSPORT must be one of: stdio, http, sse")
        return v


settings = Settings()
