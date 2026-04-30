from typing import List, Optional, Union, Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class Settings(BaseSettings):
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # -------- BNB FX --------
    BNB_FX_RATES_URL: str = (
        "https://www.bnb.bg/Statistics/StExternalSector/StExchangeRates/"
        "StERForeignCurrencies/index.htm?download=xml&search=&lang=BG"
    )
    BNB_FX_TIMEOUT_S: float = Field(default=15.0, gt=0, le=120.0)

    # -------- eBank provider --------
    EBANK_BASE_URL: str = "http://172.16.51.90:8080/EBank"
    EBANK_LOGIN_PATH: str = "/Login"
    EBANK_HOME_PATH: str = "/Home"
    EBANK_ENQUIRY_PATH: str = "/Enquiry"
    EBANK_USERNAME: str = ""
    EBANK_PASSWORD: str = ""
    EBANK_LANGUAGE: str = "BG"
    EBANK_AUTH_MODE: str = "auto"
    EBANK_TIMEOUT_S: float = Field(default=20.0, gt=0, le=120.0)
    EBANK_SESSION_TTL_S: int = Field(default=4 * 60, ge=30, le=24 * 60 * 60)
    EBANK_ACCLIST_FUNCID: str = ""
    EBANK_STATEMENT_FUNCID: str = "6"

    # -------- JWT --------
    JWT_SECRET_KEY: str = "dev-secret-key-change-me-32-bytes-min"
    JWT_ALGORITHM: str = "HS256"
    MCP_PENDING_ACTION_SECRET: str = ""

    # -------- MCP transport --------
    # "stdio" for Claude Desktop, "sse" for web clients
    MCP_TRANSPORT: str = "stdio"

    # -------- MCP tools --------
    MCP_PROVIDER: str = "ebank_http"
    MCP_REQUIRE_PROVIDER_AUTH: bool = False
    MCP_TOOLS_ALLOW_MUTATIONS: bool = False
    MCP_MUTATION_RATE_LIMIT_PER_MIN: int = Field(default=20, ge=1, le=500)
    MCP_CONFIRM_TOKEN_SINGLE_USE_TTL_S: int = Field(
        default=10 * 60, ge=60, le=24 * 60 * 60
    )
    MCP_TOOL_ARGS_MAX_JSON_BYTES: int = Field(default=16_384, ge=1024, le=500_000)
    MCP_TOOL_ARGS_MAX_DEPTH: int = Field(default=8, ge=1, le=64)
    MCP_TOOL_ARGS_MAX_NODES: int = Field(default=600, ge=10, le=100_000)

    # -------- MCP session / conversation --------
    MCP_SESSION_TTL_S: int = Field(default=30 * 60, ge=60, le=24 * 60 * 60)
    MCP_CONVERSATION_MAX_MESSAGES: int = Field(default=20, ge=1, le=50)
    MCP_CONVERSATION_TTL_S: int = Field(default=30 * 60, ge=60, le=24 * 60 * 60)

    # -------- Circuit breaker --------
    MCP_UPSTREAM_CIRCUIT_BREAKER_ENABLED: bool = True
    MCP_UPSTREAM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=3, ge=1, le=50)
    MCP_UPSTREAM_CIRCUIT_BREAKER_RECOVERY_S: float = Field(
        default=30.0, gt=0.1, le=600.0
    )
    MCP_UPSTREAM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(default=1, ge=1, le=10)

    # -------- Oracle DB (Фаза 2) --------
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_DSN: str = ""          # e.g. "localhost:1521/XEPDB1"
    ORACLE_POOL_MIN: int = Field(default=2, ge=1, le=10)
    ORACLE_POOL_MAX: int = Field(default=10, ge=2, le=100)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -------- validators --------

    @field_validator("JWT_SECRET_KEY", mode="before")
    def validate_jwt_secret_key(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 bytes. Generate a long random secret."
            )
        return v

    @field_validator("JWT_SECRET_KEY")
    def forbid_default_secret_in_prod(cls, v: str, info) -> str:
        env = (info.data.get("ENV") or "").strip().lower()
        if env == "prod" and v == "dev-secret-key-change-me-32-bytes-min":
            raise ValueError(
                "JWT_SECRET_KEY is still set to the default dev value. "
                "Set a strong random secret in production."
            )
        return v

    @field_validator("MCP_PENDING_ACTION_SECRET", mode="before")
    def validate_pending_action_secret(cls, v: Optional[str]) -> str:
        v = (v or "").strip()
        if v and len(v.encode("utf-8")) < 32:
            raise ValueError(
                "MCP_PENDING_ACTION_SECRET must be at least 32 bytes when set."
            )
        return v

    @field_validator("MCP_TRANSPORT", mode="before")
    def normalize_mcp_transport(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"stdio", "sse"}:
            raise ValueError("MCP_TRANSPORT must be one of: stdio, sse")
        return v

    @field_validator("MCP_PROVIDER", mode="before")
    def normalize_mcp_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v:
            raise ValueError("MCP_PROVIDER cannot be empty")
        return v

    @field_validator("EBANK_LOGIN_PATH", "EBANK_HOME_PATH", "EBANK_ENQUIRY_PATH", mode="before")
    def normalize_ebank_paths(cls, v: str) -> str:
        token = str(v or "").strip()
        if not token:
            raise ValueError("eBank endpoint path cannot be empty")
        if not token.startswith("/"):
            token = "/" + token
        return token

    @field_validator("EBANK_LANGUAGE", mode="before")
    def normalize_ebank_language(cls, v: str) -> str:
        return str(v or "").strip().upper() or "BG"

    @field_validator("EBANK_AUTH_MODE", mode="before")
    def normalize_ebank_auth_mode(cls, v: str) -> str:
        token = str(v or "").strip().lower() or "auto"
        if token not in {"auto", "service", "delegated"}:
            raise ValueError("EBANK_AUTH_MODE must be one of: auto, service, delegated")
        return token


settings = Settings()


def pending_action_secret() -> str:
    return settings.MCP_PENDING_ACTION_SECRET or settings.JWT_SECRET_KEY
