from __future__ import annotations

from collections.abc import Callable

from banking_mcp.adapters.ebank_http import EBankHTTPTools
from banking_mcp.adapters.provider_adapter import ProviderAdapter

ProviderFactory = Callable[[], ProviderAdapter]


class UnknownProviderError(KeyError):
    """Raised when a provider is requested but not registered."""


class ProviderRegistry:
    """Registry + factory lookup for MCP provider adapters."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    @staticmethod
    def _normalize(name: str) -> str:
        token = str(name or "").strip().lower()
        if not token:
            raise ValueError("Provider name cannot be empty.")
        return token

    def register(
        self, name: str, factory: ProviderFactory, *, overwrite: bool = False
    ) -> None:
        key = self._normalize(name)
        if not callable(factory):
            raise TypeError("Provider factory must be callable.")
        if key in self._factories and not overwrite:
            raise ValueError(f"Provider '{key}' is already registered.")
        self._factories[key] = factory

    def list_providers(self) -> list[str]:
        return sorted(self._factories.keys())

    def create(self, name: str) -> ProviderAdapter:
        key = self._normalize(name)
        factory = self._factories.get(key)
        if factory is None:
            raise UnknownProviderError(key)
        return factory()


def build_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("ebank_http", lambda: EBankHTTPTools())
    return registry
