"""Shared provider singleton — one EBankHTTPTools instance per process."""

from __future__ import annotations

from typing import Optional

from banking_mcp.adapters.ebank_http import EBankHTTPTools

_provider: Optional[EBankHTTPTools] = None


def get_provider() -> EBankHTTPTools:
    global _provider
    if _provider is None:
        _provider = EBankHTTPTools()
    return _provider
