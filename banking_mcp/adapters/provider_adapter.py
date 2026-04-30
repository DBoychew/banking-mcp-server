from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, runtime_checkable

ProviderOperation = Literal[
    "get_me",
    "list_accounts",
    "list_beneficiaries",
    "get_fx_rates",
    "list_transactions",
    "list_transfers",
    "get_transfer_by_id",
    "get_statement",
]


@dataclass(frozen=True)
class ProviderCapabilities:
    """
    Capability contract for provider adapters.

    The adapter declares which operations are available, so MCP can route
    requests safely without relying on provider-specific assumptions.
    """

    operations: frozenset[ProviderOperation] = field(default_factory=frozenset)

    def supports(self, operation: ProviderOperation) -> bool:
        return operation in self.operations


@runtime_checkable
class ProviderAdapter(Protocol):
    """
    MCP provider interface for bank integrations.

    Implementations adapt provider-specific APIs to a stable MCP operation
    surface. The concrete payload shape can vary for now; canonical mapping
    is handled in later phases.
    """

    def provider_name(self) -> str:
        """Return stable provider identifier."""

    def capabilities(self) -> ProviderCapabilities:
        """Return declared provider capabilities."""

    async def aclose(self) -> None:
        """Release open resources (HTTP clients, sessions, etc.)."""

    async def get_me(self, authorization: Optional[str]) -> Any:
        """Return authenticated user metadata."""

    async def list_accounts(self, authorization: Optional[str]) -> Any:
        """Return provider accounts payload."""

    async def list_beneficiaries(self, authorization: Optional[str]) -> Any:
        """Return provider beneficiaries payload."""

    async def get_fx_rates(self, authorization: Optional[str]) -> Any:
        """Return provider FX rates payload."""

    async def list_transactions(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        """Return provider transactions payload."""

    async def list_transfers(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        """Return provider transfers payload."""

    async def get_transfer_by_id(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        """Return provider transfer details payload."""

    async def get_statement(
        self, args: dict[str, Any], authorization: Optional[str]
    ) -> Any:
        """Return provider statement payload."""
