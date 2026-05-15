"""Keyword index for IRIS transaction classification (BG-only).

Builds a reverse index `keyword -> [category, ...]` from the bundled
taxonomy and scores free-text transaction descriptions against it.
Payroll patterns from the taxonomy are compiled into regexes and used to
boost the salary code when a description matches a known payroll layout.

Public API:
    get_index() -> KeywordIndex          (singleton)
    classify(text, direction, top_k)     (convenience wrapper)

Hallucination-safe by construction: returned codes are taken verbatim
from the loaded taxonomy and cannot be a value the model invented.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from banking_mcp.resources import categories_loader

SALARY_CODE = "001001001000"
PAYROLL_BOOST = 5.0
SHORT_KEYWORD_LEN = 4  # below this, require word boundaries to avoid false hits
PREFIX_BOOST = 2.0  # added when a keyword is the leading token of the description


@dataclass(frozen=True)
class ClassificationMatch:
    code: str
    leaf_name: str
    path: str
    direction: str
    score: float
    matched_keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.leaf_name,
            "path": self.path,
            "direction": self.direction,
            "score": round(self.score, 4),
            "matched_keywords": list(self.matched_keywords),
        }


@dataclass
class ClassificationResult:
    input: str
    matches: list[ClassificationMatch] = field(default_factory=list)
    payroll_pattern_hit: bool = False

    @property
    def unclassified(self) -> bool:
        return not self.matches

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "matches": [m.to_dict() for m in self.matches],
            "payroll_pattern_hit": self.payroll_pattern_hit,
            "unclassified": self.unclassified,
        }


def _fold(text: str) -> str:
    """Lowercase + NFC normalize. Bulgarian has no accents to strip."""
    return unicodedata.normalize("NFC", text).lower()


def _category_path(cat: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("main_category", "primary_category", "sub_level_1", "sub_level_2"):
        node = cat.get(key)
        if node and node.get("name"):
            parts.append(node["name"])
    return " > ".join(parts) if parts else (cat.get("leaf_name") or "")


def _payroll_pattern_to_regex(pattern_group: str) -> re.Pattern[str] | None:
    """Convert 'PAYROLL_MM_YYYY' style placeholders to a regex.

    MM -> two digits; YYYY -> four digits; everything else literal.
    Whitespace and underscores in the template stay literal.
    """
    text = pattern_group.strip()
    if not text:
        return None
    # Escape, then unescape the placeholders.
    escaped = re.escape(text)
    escaped = escaped.replace("YYYY", r"\d{4}")
    escaped = escaped.replace("MM", r"\d{2}")
    try:
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    except re.error:
        return None


class KeywordIndex:
    """Singleton-style reverse index built once from the taxonomy."""

    def __init__(self) -> None:
        self._by_keyword: list[tuple[str, dict[str, Any]]] = []
        self._all_codes: set[str] = set()
        self._payroll_regexes: list[re.Pattern[str]] = []
        self._build()

    def _build(self) -> None:
        by_code: dict[str, dict[str, Any]] = {}
        for cat in categories_loader.load_categories()["categories"]:
            code = cat.get("full_code")
            if not code:
                continue
            self._all_codes.add(code)
            by_code[code] = cat
            for kw in cat.get("keywords_bg", []) or []:
                folded = _fold(kw).strip()
                if not folded:
                    continue
                self._by_keyword.append((folded, cat))

        # Phase 6: merge merchant aliases and typo corrections.
        overlay = categories_loader.load_merchant_aliases()
        for entry in overlay.get("aliases", []):
            code = entry.get("code")
            keyword = entry.get("keyword")
            cat = by_code.get(code) if code else None
            if not cat or not keyword:
                continue
            folded = _fold(str(keyword)).strip()
            if not folded:
                continue
            self._by_keyword.append((folded, cat))

        for correction in overlay.get("typo_corrections", []):
            code = correction.get("code")
            cat = by_code.get(code) if code else None
            if not cat:
                continue
            for kw in correction.get("extra_keywords", []) or []:
                folded = _fold(str(kw)).strip()
                if not folded:
                    continue
                self._by_keyword.append((folded, cat))

        for pattern in categories_loader.get_payroll_patterns():
            regex = _payroll_pattern_to_regex(pattern.get("pattern_group", ""))
            if regex is not None:
                self._payroll_regexes.append(regex)

    @property
    def known_codes(self) -> set[str]:
        return set(self._all_codes)

    def _matches_keyword(self, folded_text: str, keyword: str) -> bool:
        if len(keyword) >= SHORT_KEYWORD_LEN:
            return keyword in folded_text
        # Short keywords (e.g. 'РЗ' -> 'рз', 'НОИ' -> 'нои') need word boundaries
        # so 'нои' does not match inside 'нощен' etc.
        pattern = rf"(?<![\w]){re.escape(keyword)}(?![\w])"
        return re.search(pattern, folded_text) is not None

    def _is_prefix_match(self, folded_text: str, keyword: str) -> bool:
        # Transaction feeds typically lead with the transaction type
        # ('АТМ ...', 'ПРЕВОД ...'); that prefix is a much stronger signal
        # than the same keyword appearing deeper in the merchant string.
        if not folded_text.startswith(keyword):
            return False
        if len(folded_text) == len(keyword):
            return True
        nxt = folded_text[len(keyword)]
        return not (nxt.isalnum() or nxt == "_")

    def classify(
        self,
        text: str,
        direction: str = "auto",
        top_k: int = 3,
    ) -> ClassificationResult:
        if direction not in {"auto", "incoming", "outgoing"}:
            raise ValueError(
                f"direction must be 'auto', 'incoming' or 'outgoing'; got {direction!r}"
            )
        if not text or not text.strip():
            return ClassificationResult(input=text or "")

        folded = _fold(text)

        # code -> [score, matched_keywords, cat_ref]
        scored: dict[str, dict[str, Any]] = {}
        for keyword, cat in self._by_keyword:
            if direction != "auto" and cat.get("direction") != direction:
                continue
            if not self._matches_keyword(folded, keyword):
                continue
            code = cat["full_code"]
            # Longer keywords are more specific -> higher weight.
            weight = max(1.0, len(keyword) / 5.0)
            if self._is_prefix_match(folded, keyword):
                weight += PREFIX_BOOST
            entry = scored.setdefault(
                code,
                {"score": 0.0, "matched": [], "cat": cat},
            )
            entry["score"] += weight
            if keyword not in entry["matched"]:
                entry["matched"].append(keyword)

        payroll_hit = False
        if direction in {"auto", "incoming"}:
            for regex in self._payroll_regexes:
                if regex.search(text):
                    payroll_hit = True
                    break

        if payroll_hit and SALARY_CODE in self._all_codes:
            # Boost salary code even if no keyword matched.
            salary_cat = next(
                (
                    c
                    for c in categories_loader.load_categories()["categories"]
                    if c.get("full_code") == SALARY_CODE
                ),
                None,
            )
            if salary_cat is not None:
                entry = scored.setdefault(
                    SALARY_CODE,
                    {"score": 0.0, "matched": [], "cat": salary_cat},
                )
                entry["score"] += PAYROLL_BOOST
                if "<payroll-pattern>" not in entry["matched"]:
                    entry["matched"].append("<payroll-pattern>")

        ranked = sorted(
            scored.items(),
            key=lambda kv: (-kv[1]["score"], kv[0]),
        )[:top_k]

        matches = [
            ClassificationMatch(
                code=code,
                leaf_name=data["cat"].get("leaf_name") or "",
                path=_category_path(data["cat"]),
                direction=data["cat"].get("direction", ""),
                score=data["score"],
                matched_keywords=tuple(data["matched"]),
            )
            for code, data in ranked
        ]
        return ClassificationResult(
            input=text,
            matches=matches,
            payroll_pattern_hit=payroll_hit,
        )


@lru_cache(maxsize=1)
def get_index() -> KeywordIndex:
    return KeywordIndex()


def reload_index() -> None:
    """Drop the classifier singleton AND the underlying taxonomy caches.

    Use after editing the source JSON or the merchant-alias overlay so
    the next classify() rebuilds the index. Also resets stats.
    """
    get_index.cache_clear()
    categories_loader.reload_all()
    from . import stats as _stats

    _stats.reset()


def classify(
    text: str,
    direction: str = "auto",
    top_k: int = 3,
    source: str = "api",
    audit: bool = True,
) -> ClassificationResult:
    """Convenience wrapper around the singleton index.

    Phase 6: every call is audit-logged by default and counted in stats.
    Pass audit=False from batch paths (classify_transactions) that emit
    their own summary record to keep audit volume bounded - the per-row
    stats counter still fires either way so unclassified rate is accurate.
    """
    result = get_index().classify(text, direction=direction, top_k=top_k)

    # Stats always tick - cheap, in-memory.
    from . import stats as _stats

    _stats.record(
        direction=direction,
        unclassified=result.unclassified,
        payroll_pattern_hit=result.payroll_pattern_hit,
        row_count=1,
    )

    if audit:
        # Local import: keeps classification importable in environments
        # where the audit module is disabled or partially configured.
        from banking_mcp.audit import log_classification

        top = result.matches[0] if result.matches else None
        log_classification(
            description=text or "",
            direction=direction,
            top_code=top.code if top else None,
            top_score=top.score if top else 0.0,
            unclassified=result.unclassified,
            payroll_pattern_hit=result.payroll_pattern_hit,
            row_count=1,
            source=source,
        )
    return result
