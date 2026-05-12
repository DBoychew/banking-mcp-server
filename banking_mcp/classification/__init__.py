"""Classification helpers for banking transactions.

Phase 3: deterministic keyword-based classification against the IRIS PSD2
taxonomy loaded from banking_mcp.resources.categories_loader.
Phase 6: merchant aliases, audit hooks, in-memory stats, reload.
"""

from . import stats
from .keyword_index import (
    ClassificationMatch,
    ClassificationResult,
    classify,
    get_index,
    reload_index,
)

__all__ = [
    "ClassificationMatch",
    "ClassificationResult",
    "classify",
    "get_index",
    "reload_index",
    "stats",
]
