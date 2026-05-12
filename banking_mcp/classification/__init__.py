"""Classification helpers for banking transactions.

Phase 3: deterministic keyword-based classification against the IRIS PSD2
taxonomy loaded from banking_mcp.resources.categories_loader.
"""

from .keyword_index import (
    ClassificationMatch,
    ClassificationResult,
    classify,
    get_index,
)

__all__ = [
    "ClassificationMatch",
    "ClassificationResult",
    "classify",
    "get_index",
]
