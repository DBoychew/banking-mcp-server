from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_currency(value: str) -> str:
    token = str(value or "").strip().upper()
    if len(token) != 3:
        raise ValueError("Currency must be a 3-letter ISO code.")
    return token


class CanonicalAccount(BaseModel):
    """Canonical account model used by MCP runtime."""

    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(min_length=1, max_length=128)
    iban: Optional[str] = Field(default=None, max_length=64)
    currency: str = Field(min_length=3, max_length=3)
    balance: Decimal = Field(default=Decimal("0"))
    status: Optional[str] = Field(default=None, max_length=64)
    provider_account_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)


class CanonicalTransaction(BaseModel):
    """Canonical transaction model used by MCP runtime."""

    model_config = ConfigDict(extra="ignore")

    transaction_id: Optional[str] = Field(default=None, max_length=128)
    account_id: Optional[str] = Field(default=None, max_length=128)
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    direction: Literal["credit", "debit", "unknown"] = "unknown"
    status: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)
    created_at: Optional[datetime] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)


class CanonicalTransfer(BaseModel):
    """Canonical transfer model used by MCP runtime."""

    model_config = ConfigDict(extra="ignore")

    transfer_id: Optional[str] = Field(default=None, max_length=128)
    from_account_id: str = Field(min_length=1, max_length=128)
    to_account_id: Optional[str] = Field(default=None, max_length=128)
    to_iban: Optional[str] = Field(default=None, max_length=64)
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    status: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)
    created_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)

    @model_validator(mode="after")
    def validate_destination(self):
        if bool(self.to_account_id) == bool(self.to_iban):
            raise ValueError(
                "Provide exactly one destination: to_account_id or to_iban."
            )
        return self


class CanonicalStatement(BaseModel):
    """Canonical statement model used by MCP runtime."""

    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(min_length=1, max_length=128)
    currency: str = Field(min_length=3, max_length=3)
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_credit: Optional[Decimal] = None
    total_debit: Optional[Decimal] = None
    total_count: Optional[int] = Field(default=None, ge=0)
    items: list[CanonicalTransaction] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _normalize_currency(value)
