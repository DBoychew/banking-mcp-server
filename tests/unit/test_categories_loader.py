"""Tests for banking_mcp.resources.categories_loader."""

import re

import pytest

from banking_mcp.resources import categories_loader


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the lru_cache between tests so file edits or monkeypatches stick."""
    categories_loader.load_categories.cache_clear()
    categories_loader.load_merchant_aliases.cache_clear()
    yield
    categories_loader.load_categories.cache_clear()
    categories_loader.load_merchant_aliases.cache_clear()


def test_counts_match_phase_1():
    counts = categories_loader.get_counts()
    assert counts == {"incoming": 55, "outgoing": 122, "payroll_patterns": 5}


def test_locale_is_bulgarian():
    payload = categories_loader.load_categories()
    assert payload.get("locale") == "bg_BG"


def test_no_greek_anywhere():
    """Phase 1 promised 0 Greek codepoints. Enforce it at load time too."""
    greek = re.compile(r"[Ͱ-Ͽἀ-῿]")
    payload = categories_loader.load_categories()

    def _walk(value):
        if isinstance(value, str):
            assert not greek.search(value), f"Greek codepoint leaked: {value!r}"
        elif isinstance(value, dict):
            for inner in value.values():
                _walk(inner)
        elif isinstance(value, list):
            for inner in value:
                _walk(inner)

    _walk(payload)


def test_incoming_outgoing_split_is_clean():
    incoming = categories_loader.get_incoming()
    outgoing = categories_loader.get_outgoing()
    assert all(c["direction"] == "incoming" for c in incoming)
    assert all(c["direction"] == "outgoing" for c in outgoing)
    assert len(incoming) + len(outgoing) == len(
        categories_loader.load_categories()["categories"]
    )


def test_payroll_patterns_have_pattern_group_and_example():
    for entry in categories_loader.get_payroll_patterns():
        assert entry["pattern_group"]
        assert entry["example"]
        # NBSP should have been normalized at load time.
        assert "\xa0" not in entry["pattern_group"]
        assert "\xa0" not in entry["example"]


def test_load_is_cached():
    a = categories_loader.load_categories()
    b = categories_loader.load_categories()
    assert a is b


def test_every_category_has_full_code_and_main():
    for cat in categories_loader.load_categories()["categories"]:
        assert cat["full_code"] and len(cat["full_code"]) == 12
        assert cat["main_category"]["code"] in {"001", "002"}
        assert cat["main_category"]["name"]


def test_missing_data_file_raises(monkeypatch, tmp_path):
    categories_loader.load_categories.cache_clear()
    monkeypatch.setattr(categories_loader, "DATA_FILE", tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError):
        categories_loader.load_categories()
