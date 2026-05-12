"""Tests for banking_mcp.classification.keyword_index and classify_description tool.

Golden-fixture format: list of (description, expected_code, expected_direction).
Each description uses keywords or payroll patterns that exist in the loaded
taxonomy. Pure merchant-name descriptions ("ЛИДЛ", "OMV") deliberately fall
under the unclassified bucket - that gap is a data limitation acknowledged in
Phase 3 and is left to be filled by Phase 6 (LLM fallback / merchant aliases).
"""
from __future__ import annotations

import json

import pytest

from banking_mcp.classification import classify, get_index
from banking_mcp.classification.keyword_index import (
    SALARY_CODE,
    KeywordIndex,
    _payroll_pattern_to_regex,
)
from banking_mcp.resources import categories_loader
from banking_mcp.tools.classification_tools import register_classification_tools


GOLDEN_CASES: list[tuple[str, str, str]] = [
    # Incoming - income
    ("ВЪЗНАГРАЖДЕНИЕ ПО ТРУДОВ ДОГОВОР МАРТ 2026", "001001001000", "incoming"),
    ("ИЗПЛАТЕНА ЗАПЛАТА СИРМА СОЛЮШЪНС", "001001001000", "incoming"),
    ("PAYROLL_03_2026 ACME LTD", "001001001000", "incoming"),
    ("ПЕНСИЯ НОИ 03/2026", "001001004000", "incoming"),
    # NOTE: keyword for code 001001006000 has a typo in the source taxonomy
    # ('обезщетеТие безработица'), so a correctly spelled description does
    # not hit it. Tracked as a Phase 6 data-quality follow-up.
    ("ОБЕЗЩЕТЕНИЕ ВРЕМЕННА НЕТРУДОСПОСОБНОСТ БОЛНИЧНИ", "001001007000", "incoming"),
    ("НАЕМ АПАРТАМЕНТ СОФИЯ", "001001010000", "incoming"),
    ("ДИВИДЕНТ ОТ ИНВЕСТИЦИЯ", "001001012000", "incoming"),
    ("МЕСЕЧНА ЛИХВА ПО ДЕПОЗИТ", "001001013000", "incoming"),
    ("СТИПЕНДИЯ СУ КЛИМЕНТ ОХРИДСКИ", "001001014000", "incoming"),
    ("ВЪЗСТАНОВЕН ДАНЪК НАП", "001001015000", "incoming"),
    # Incoming - financing
    ("УСВОЯВАНЕ ИПОТЕЧЕН КРЕДИТ", "001002001000", "incoming"),
    ("ОТПУСКАНЕ ПОТРЕБИТЕЛСКИ КРЕДИТ", "001002002000", "incoming"),
    # Outgoing - food / leisure
    ("РЕСТОРАНТ ХЕМИНГУЕЙ СОФИЯ", "002001001003", "outgoing"),
    ("КАФЕНЕ ОНЛИ ФРЕНДС", "002001001004", "outgoing"),
    ("БАР ПОД ЛИПИТЕ", "002001001005", "outgoing"),
    # Outgoing - misc keywords
    ("ИНТЕРИОР ОБЗАВЕЖДАНЕ МЕБЕЛИ", "002001003001", "outgoing"),
    ("ПИЦАРИЯ ВЕРДИ ВАРНА", "002001001003", "outgoing"),
]


@pytest.fixture(autouse=True)
def _reset_caches():
    categories_loader.load_categories.cache_clear()
    get_index.cache_clear()
    yield
    categories_loader.load_categories.cache_clear()
    get_index.cache_clear()


# ---------------------------------------------------------------------------
# Index invariants
# ---------------------------------------------------------------------------


def test_index_is_cached_singleton():
    assert get_index() is get_index()


def test_index_contains_all_taxonomy_codes():
    idx = get_index()
    expected = {
        c["full_code"]
        for c in categories_loader.load_categories()["categories"]
    }
    assert idx.known_codes == expected


def test_payroll_pattern_compiles_to_digit_regex():
    regex = _payroll_pattern_to_regex("PAYROLL_MM_YYYY")
    assert regex is not None
    assert regex.search("PAYROLL_03_2026")
    assert not regex.search("PAYROLL_ABC_DEFG")


def test_payroll_pattern_handles_empty_input():
    assert _payroll_pattern_to_regex("") is None


# ---------------------------------------------------------------------------
# Classification correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("description,expected_code,direction", GOLDEN_CASES)
def test_top3_contains_expected(description, expected_code, direction):
    """Top-3 must contain the expected code on every golden case."""
    result = classify(description, top_k=3)
    codes = [m.code for m in result.matches]
    assert expected_code in codes, (
        f"Expected {expected_code} in top-3, got {codes} for {description!r}"
    )


def test_top1_precision_meets_threshold():
    """Top-1 precision over the golden fixture must be >= 80%."""
    hits = 0
    for description, expected_code, _direction in GOLDEN_CASES:
        result = classify(description, top_k=1)
        if result.matches and result.matches[0].code == expected_code:
            hits += 1
    precision = hits / len(GOLDEN_CASES)
    assert precision >= 0.8, (
        f"top-1 precision was {precision:.0%}, want >= 80% over "
        f"{len(GOLDEN_CASES)} cases"
    )


def test_classifier_never_invents_a_code():
    """Every code returned must exist in the loaded taxonomy (no hallucinations)."""
    known = get_index().known_codes
    samples = [d for d, _, _ in GOLDEN_CASES] + [
        "RANDOM STRING WITH NO KEYWORDS",
        "ЛИДЛ БЪЛГАРИЯ ЕООД",  # merchant-only, expected unclassified
        "",
        "   ",
    ]
    for sample in samples:
        result = classify(sample, top_k=5)
        for match in result.matches:
            assert match.code in known, (
                f"Classifier returned unknown code {match.code} for {sample!r}"
            )


def test_unclassified_for_empty_input():
    result = classify("")
    assert result.unclassified
    assert result.matches == []


def test_unclassified_for_merchant_only_description():
    """Documents the known data gap: bare merchant names are unclassified.

    The taxonomy does not enumerate retailer brand names. This test pins the
    current behavior so a future Phase 6 (LLM fallback / merchant aliases)
    deliberately changes it.
    """
    result = classify("ЛИДЛ БЪЛГАРИЯ ЕООД ПЛОВДИВ")
    assert result.unclassified


def test_direction_filter_excludes_other_side():
    """Asking for incoming-only must not return outgoing categories."""
    result = classify("РЕСТОРАНТ ХЕМИНГУЕЙ", direction="incoming")
    assert all(m.direction == "incoming" for m in result.matches)


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        classify("anything", direction="sideways")


def test_payroll_pattern_boosts_salary_even_without_keyword():
    """A bare payroll layout with no BG income keyword should still hit salary."""
    result = classify("PAYROLL_03_2026 ACME LTD")
    assert result.payroll_pattern_hit
    assert result.matches[0].code == SALARY_CODE


def test_longer_keyword_outranks_shorter_overlap():
    """'ипотечен кредит' must outrank just 'ипотечен' for a description containing both."""
    result = classify("УСВОЯВАНЕ ИПОТЕЧЕН КРЕДИТ", top_k=1)
    assert result.matches[0].code == "001002001000"
    assert "ипотечен кредит" in result.matches[0].matched_keywords


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *_, **__):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def test_classify_description_tool_returns_valid_json():
    fake = _FakeMCP()
    register_classification_tools(fake)
    payload = json.loads(
        fake.tools["classify_description"]("РЕСТОРАНТ ХЕМИНГУЕЙ СОФИЯ")
    )
    assert payload["input"] == "РЕСТОРАНТ ХЕМИНГУЕЙ СОФИЯ"
    assert payload["unclassified"] is False
    assert payload["matches"][0]["code"] == "002001001003"


def test_classify_description_tool_clamps_top_k():
    fake = _FakeMCP()
    register_classification_tools(fake)
    payload = json.loads(
        fake.tools["classify_description"]("ЗАПЛАТА", top_k=999)
    )
    assert len(payload["matches"]) <= 10


def test_classify_description_tool_returns_error_for_bad_direction():
    fake = _FakeMCP()
    register_classification_tools(fake)
    payload = json.loads(
        fake.tools["classify_description"]("ЗАПЛАТА", direction="weird")
    )
    assert "error" in payload
