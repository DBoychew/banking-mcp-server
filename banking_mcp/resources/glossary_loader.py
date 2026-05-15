"""Loader for the payment-terminology glossary.

Source: Section 10 of ``docs/specs/AI_CardPayments_Agent_UseCase.docx``
(UC-CARD-AI-001). Maintained as JSON so the LLM can answer terminology
questions deterministically without re-reading the spec.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "payment_glossary.json"


@lru_cache(maxsize=1)
def load_glossary() -> dict[str, Any]:
    """Read the JSON once and return the full payload."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Payment glossary file not found: {DATA_FILE}")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def get_terms() -> list[dict[str, Any]]:
    return load_glossary().get("terms", [])


def find_term(term: str) -> dict[str, Any] | None:
    """Case-insensitive exact-match lookup; None when nothing matches."""
    needle = term.strip().lower()
    for entry in get_terms():
        if entry.get("term", "").lower() == needle:
            return entry
    return None


def reload() -> None:
    load_glossary.cache_clear()


__all__ = ["load_glossary", "get_terms", "find_term", "reload"]
