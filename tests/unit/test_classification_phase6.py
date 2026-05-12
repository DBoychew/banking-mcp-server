"""Phase 6 tests: merchant aliases, audit hooks, stats, codes resource, reload.

Kept in a dedicated file so the original Phase 3 fixture stays focused and we
do not have to thread Phase 6 state through unrelated tests.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from banking_mcp.classification import (
    classify,
    get_index,
    reload_index,
    stats,
)
from banking_mcp.resources import categories_loader
from banking_mcp.resources.banking_resources import register_banking_resources
from banking_mcp.tools.classification_tools import register_classification_tools


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _FakeMCP:
    def __init__(self):
        self.tools: dict = {}
        self.resources: dict = {}

    def tool(self, *_, **__):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri, *_, **__):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator


@pytest.fixture(autouse=True)
def _fresh_caches():
    """Reset taxonomy caches and stats so tests do not leak counters."""
    categories_loader.load_categories.cache_clear()
    categories_loader.load_merchant_aliases.cache_clear()
    get_index.cache_clear()
    stats.reset()
    yield
    categories_loader.load_categories.cache_clear()
    categories_loader.load_merchant_aliases.cache_clear()
    get_index.cache_clear()
    stats.reset()


# ---------------------------------------------------------------------------
# Merchant aliases
# ---------------------------------------------------------------------------


_ALIAS_CASES: list[tuple[str, str]] = [
    ("ЛИДЛ БЪЛГАРИЯ ЕООД", "002001001001"),
    ("KAUFLAND VARNA", "002001001001"),
    ("OMV BG SOFIA", "002001002001"),
    ("SHELL BURGAS", "002001002001"),
    ("LUKOIL PLOVDIV", "002001002001"),
    ("BOLT TRANSPORT", "002001002002"),
    ("WIZZ AIR FLIGHT BG-FR", "002001002004"),
    ("IKEA SOFIA RING", "002001003001"),
    ("PRAKTIKER MLADOST", "002001003003"),
    ("TECHNOPOLIS RING MALL", "002001004001"),
    ("EMAG.BG ORDER 4567", "002001004001"),
    ("GLOVO BG", "002001001006"),
    ("STARBUCKS NDK", "002001001004"),
]


@pytest.mark.parametrize("description,expected_code", _ALIAS_CASES)
def test_merchant_alias_classifies(description, expected_code):
    result = classify(description, top_k=1, audit=False)
    assert not result.unclassified, f"{description!r} should classify"
    assert result.matches[0].code == expected_code


def test_typo_correction_for_unemployment_benefit():
    """Phase 6 overlay adds correctly spelled 'безработица' so well-formed
    descriptions hit 001001006000 despite the source-data typo."""
    result = classify("ОБЕЗЩЕТЕНИЕ ЗА БЕЗРАБОТИЦА НОИ", top_k=1, audit=False)
    assert result.matches[0].code == "001001006000"


# ---------------------------------------------------------------------------
# Stats counter
# ---------------------------------------------------------------------------


def test_stats_increment_on_classify():
    before = stats.snapshot()
    classify("ЛИДЛ БЪЛГАРИЯ", audit=False)
    classify("РАНДОМ БЕЗ МАТЧ ABCDEFG", audit=False)
    after = stats.snapshot()
    assert after["total"] == before["total"] + 2
    assert after["unclassified"] == before["unclassified"] + 1


def test_stats_payroll_hit_counted():
    classify("PAYROLL_03_2026", audit=False)
    snap = stats.snapshot()
    assert snap["payroll_pattern_hits"] >= 1


def test_stats_per_direction_breakdown():
    classify("РЕСТОРАНТ", direction="outgoing", audit=False)
    classify("ЗАПЛАТА", direction="incoming", audit=False)
    classify("ЛИДЛ", direction="auto", audit=False)
    snap = stats.snapshot()
    assert set(snap["by_direction"].keys()) == {"outgoing", "incoming", "auto"}
    for d in ("outgoing", "incoming", "auto"):
        assert snap["by_direction"][d]["total"] == 1


def test_stats_reset_zeros_counters():
    classify("ЛИДЛ", audit=False)
    assert stats.snapshot()["total"] >= 1
    stats.reset()
    assert stats.snapshot()["total"] == 0


# ---------------------------------------------------------------------------
# Audit hook
# ---------------------------------------------------------------------------


def test_audit_hook_fires_for_single_classify(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "banking_mcp.audit.log_classification",
        lambda **kw: calls.append(kw),
    )
    classify("ЗАПЛАТА", source="test", audit=True)
    assert len(calls) == 1
    assert calls[0]["source"] == "test"
    assert calls[0]["top_code"] == "001001001000"
    assert calls[0]["unclassified"] is False


def test_audit_hook_skipped_when_audit_false(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "banking_mcp.audit.log_classification",
        lambda **kw: calls.append(kw),
    )
    classify("ЗАПЛАТА", audit=False)
    assert calls == []


def test_audit_hook_records_unclassified(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "banking_mcp.audit.log_classification",
        lambda **kw: calls.append(kw),
    )
    classify("ZZZZ QQQQ XXX", audit=True)
    assert calls[0]["unclassified"] is True
    assert calls[0]["top_code"] is None


# ---------------------------------------------------------------------------
# Reload mechanism
# ---------------------------------------------------------------------------


def test_reload_index_rebuilds_singleton():
    a = get_index()
    reload_index()
    b = get_index()
    assert a is not b


def test_reload_resets_stats():
    classify("ЛИДЛ", audit=False)
    assert stats.snapshot()["total"] >= 1
    reload_index()
    assert stats.snapshot()["total"] == 0


def test_reload_classification_taxonomy_tool_returns_ok():
    fake = _FakeMCP()
    register_classification_tools(fake)
    out = json.loads(fake.tools["reload_classification_taxonomy"]())
    assert out["status"] == "ok"


# ---------------------------------------------------------------------------
# New MCP resources
# ---------------------------------------------------------------------------


@pytest.fixture
def registered_resources(monkeypatch):
    fake_mcp = _FakeMCP()
    fake_db = MagicMock()
    fake_db.list_connections.return_value = []
    fake_db.get_default_connection.return_value = None
    fake_db.get_schema.return_value = ""
    fake_db.get_domain_queries_info.return_value = []
    monkeypatch.setattr(
        "banking_mcp.resources.banking_resources.get_manager", lambda: fake_db
    )
    register_banking_resources(fake_mcp)
    return fake_mcp


def test_codes_resource_lists_all_categories(registered_resources):
    out = json.loads(
        registered_resources.resources["banking://transaction-categories/codes"]()
    )
    assert out["count"] == 55 + 122
    sample = out["codes"][0]
    assert set(sample.keys()) == {"code", "direction", "leaf_name", "path"}
    # Every code must be a 12-digit string and direction must be incoming/outgoing.
    for entry in out["codes"]:
        assert len(entry["code"]) == 12 and entry["code"].isdigit()
        assert entry["direction"] in {"incoming", "outgoing"}


def test_classification_stats_resource_reflects_state(registered_resources):
    classify("ЛИДЛ", audit=False)
    classify("ZZZZ QQQQ", audit=False)
    out = json.loads(
        registered_resources.resources["banking://classification-stats"]()
    )
    assert out["total"] == 2
    assert out["unclassified"] == 1
    assert out["unclassified_rate"] == pytest.approx(0.5)
