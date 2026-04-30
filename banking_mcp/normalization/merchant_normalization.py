from __future__ import annotations

import re
from typing import Iterable


_CYR_TO_LAT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sht",
        "ъ": "a",
        "ь": "y",
        "ю": "yu",
        "я": "ya",
    }
)

_MERCHANT_ALIASES: dict[str, set[str]] = {
    "omv": {"omv", "омв"},
    "eko": {"eko", "еко", "eko petrol", "eko petrol balgariya", "gas stations eko"},
    "rompetrol": {"rompetrol", "ромпетрол", "rom petrol"},
    "shell": {"shell", "шел"},
    "kaufland": {"kaufland", "кауфланд", "kaufland bulgaria"},
    "lidl": {"lidl", "лидл", "lidl balgariya"},
    "billa": {"billa", "била"},
    "fantastico": {"fantastico", "фантастико"},
    "easypay": {"easypay", "изипей"},
    "jumbo": {"jumbo", "джъмбо"},
    "sinsay": {"sinsay"},
}

_DISPLAY_LABELS: dict[str, str] = {
    "omv": "OMV",
    "eko": "EKO",
    "rompetrol": "ROMPETROL",
    "shell": "SHELL",
    "kaufland": "KAUFLAND",
    "lidl": "LIDL",
    "billa": "BILLA",
    "fantastico": "FANTASTICO",
    "easypay": "EASYPAY",
    "jumbo": "JUMBO",
    "sinsay": "SINSAY",
}


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    if abs(len(left) - len(right)) > 1:
        return False

    if len(left) > len(right):
        left, right = right, left

    i = 0
    j = 0
    edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) == len(right):
            i += 1
            j += 1
        else:
            j += 1
    if j < len(right) or i < len(left):
        edits += 1
    return edits <= 1


def _token_matches(query_token: str, candidate_token: str) -> bool:
    if not query_token or not candidate_token:
        return False
    if query_token == candidate_token:
        return True
    if len(query_token) >= 4 and len(candidate_token) >= 4:
        if query_token in candidate_token or candidate_token in query_token:
            return True
    if len(query_token) >= 5 and len(candidate_token) >= 5:
        if query_token[:5] == candidate_token[:5]:
            return True
    if min(len(query_token), len(candidate_token)) >= 4 and _edit_distance_at_most_one(
        query_token, candidate_token
    ):
        return True
    return False


def normalize_merchant_text(value: object) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    if not normalized:
        return ""
    normalized = normalized.translate(_CYR_TO_LAT)
    normalized = re.sub(r"pan\*?\d{2,}", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def canonical_merchant_name(value: object) -> str:
    normalized = normalize_merchant_text(value)
    if not normalized:
        return ""
    for canonical, aliases in _MERCHANT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    normalized = re.sub(r"\b\d{2,}\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def merchant_matches_query(query: object, candidate: object) -> bool:
    query_normalized = normalize_merchant_text(query)
    candidate_normalized = normalize_merchant_text(candidate)
    if not query_normalized or not candidate_normalized:
        return False

    canonical_query = canonical_merchant_name(query_normalized)
    canonical_candidate = canonical_merchant_name(candidate_normalized)
    if canonical_query and canonical_query == canonical_candidate:
        return True

    if len(query_normalized) >= 4 and query_normalized in candidate_normalized:
        return True

    query_tokens = query_normalized.split()
    candidate_tokens = candidate_normalized.split()
    if len(query_tokens) == 1 and len(query_tokens[0]) <= 4:
        return any(_token_matches(query_tokens[0], token) for token in candidate_tokens)
    return bool(query_tokens) and all(
        any(_token_matches(token, part) for part in candidate_tokens)
        for token in query_tokens
    )


def display_merchant_name(value: object) -> str:
    canonical = canonical_merchant_name(value)
    if canonical in _DISPLAY_LABELS:
        return _DISPLAY_LABELS[canonical]
    return " ".join(part.upper() for part in canonical.split()) if canonical else ""


def iter_aliases(canonical_name: str) -> Iterable[str]:
    return tuple(_MERCHANT_ALIASES.get(canonical_name, set()))
