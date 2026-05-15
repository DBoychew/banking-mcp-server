"""Tests for banking_mcp.dashboard.manager.DashboardManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from banking_mcp.dashboard.manager import DashboardManager
from banking_mcp.dashboard.widgets import WidgetType


@pytest.fixture
def manager(tmp_path: Path) -> DashboardManager:
    return DashboardManager(base_path=tmp_path)


def test_add_widget_persists_state_and_app(manager: DashboardManager) -> None:
    ok, msg, widget = manager.add_widget(
        title="Revenue Trend",
        widget_type="line_chart",
        python_code="df = tools.execute_sql_query('SELECT 1 FROM dual')\nst.line_chart(df)",
    )

    assert ok, msg
    assert widget is not None
    assert widget.id == "revenue_trend"
    assert widget.position == 0

    state_file = manager._get_state_file("default")
    app_file = manager._get_app_file("default")
    assert state_file.exists()
    assert app_file.exists()

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["widgets"][0]["id"] == "revenue_trend"
    assert payload["widgets"][0]["widget_type"] == "line_chart"


def test_add_widget_rejects_return_statement(manager: DashboardManager) -> None:
    ok, msg, widget = manager.add_widget(
        title="bad",
        widget_type="metric",
        python_code="def f():\n    return 1",
    )
    assert not ok
    assert "return" in msg.lower()
    assert widget is None


def test_add_widget_rejects_invalid_syntax(manager: DashboardManager) -> None:
    ok, msg, _ = manager.add_widget(
        title="bad",
        widget_type="metric",
        python_code="df = ",
    )
    assert not ok
    assert "syntax error" in msg.lower()


def test_add_widget_rejects_unknown_type(manager: DashboardManager) -> None:
    ok, msg, _ = manager.add_widget(
        title="x",
        widget_type="treemap",
        python_code="st.write(1)",
    )
    assert not ok
    assert "treemap" in msg


def test_add_widget_normalizes_escaped_newlines(manager: DashboardManager) -> None:
    ok, _, widget = manager.add_widget(
        title="escaped",
        widget_type="metric",
        python_code="x = 1\\ny = 2\\nst.metric('x', x + y)",
    )
    assert ok
    assert widget is not None
    assert "\n" in widget.python_code
    assert "\\n" not in widget.python_code


def test_add_widget_assigns_unique_ids_on_collision(
    manager: DashboardManager,
) -> None:
    manager.add_widget(title="Same", widget_type="metric", python_code="st.write(1)")
    _, _, w2 = manager.add_widget(
        title="Same", widget_type="metric", python_code="st.write(2)"
    )
    _, _, w3 = manager.add_widget(
        title="Same", widget_type="metric", python_code="st.write(3)"
    )

    assert w2.id == "same_1"
    assert w3.id == "same_2"


def test_add_widget_transliterates_cyrillic_titles(
    manager: DashboardManager,
) -> None:
    # Bulgarian titles used to collapse to the literal "widget" fallback
    # (only ASCII a-z0-9 survived the slug regex), so two cyrillic titles
    # in the same dashboard collided. Transliteration produces stable ids.
    _, _, w1 = manager.add_widget(
        title="Най-голяма транзакция",
        widget_type="metric",
        python_code="st.write(1)",
    )
    _, _, w2 = manager.add_widget(
        title="Сума на топ 10",
        widget_type="metric",
        python_code="st.write(2)",
    )
    assert w1.id == "nay_golyama_tranzaktsiya"
    assert w2.id == "suma_na_top_10"
    assert w1.id != w2.id


def test_update_widget_changes_fields(manager: DashboardManager) -> None:
    _, _, widget = manager.add_widget(
        title="x", widget_type="metric", python_code="st.write(1)"
    )
    ok, _, updated = manager.update_widget(
        widget.id, title="New Title", python_code="st.write(2)"
    )
    assert ok
    assert updated.title == "New Title"
    assert "2" in updated.python_code
    assert updated.updated_at is not None


def test_update_widget_missing_id_returns_error(manager: DashboardManager) -> None:
    ok, msg, _ = manager.update_widget("does_not_exist", title="x")
    assert not ok
    assert "not found" in msg


def test_remove_widget(manager: DashboardManager) -> None:
    _, _, widget = manager.add_widget(
        title="bye", widget_type="metric", python_code="st.write(1)"
    )
    ok, _ = manager.remove_widget(widget.id)
    assert ok

    state = manager.load_state()
    assert state.widgets == []


def test_remove_widget_reindexes_positions(manager: DashboardManager) -> None:
    _, _, w1 = manager.add_widget(
        title="a", widget_type="metric", python_code="st.write(1)"
    )
    _, _, w2 = manager.add_widget(
        title="b", widget_type="metric", python_code="st.write(2)"
    )
    _, _, w3 = manager.add_widget(
        title="c", widget_type="metric", python_code="st.write(3)"
    )

    manager.remove_widget(w2.id)
    state = manager.load_state()
    by_id = {w.id: w.position for w in state.widgets}
    assert by_id[w1.id] == 0
    assert by_id[w3.id] == 1


def test_clear_all_widgets(manager: DashboardManager) -> None:
    manager.add_widget(title="x", widget_type="metric", python_code="st.write(1)")
    manager.set_global_filter(
        filter_type="selectbox",
        variable_name="region",
        label="Region",
        options=["EU", "US"],
    )

    ok, msg = manager.clear_all_widgets()
    assert ok
    assert "1 widget" in msg

    state = manager.load_state()
    assert state.widgets == []
    assert state.global_filters == []


def test_set_global_filter_updates_existing(manager: DashboardManager) -> None:
    manager.set_global_filter(
        filter_type="selectbox",
        variable_name="region",
        label="Region",
        options=["EU"],
    )
    manager.set_global_filter(
        filter_type="selectbox",
        variable_name="region",
        label="Region (new)",
        options=["EU", "US"],
    )

    state = manager.load_state()
    assert len(state.global_filters) == 1
    assert state.global_filters[0].label == "Region (new)"
    assert state.global_filters[0].options == ["EU", "US"]


def test_set_layout_validates_columns(manager: DashboardManager) -> None:
    assert manager.set_layout(columns=2, title="hi")[0] is True
    assert manager.load_state().columns == 2

    ok, msg = manager.set_layout(columns=5)
    assert not ok
    assert "between 1 and 4" in msg


def test_list_dashboards(manager: DashboardManager) -> None:
    manager.add_widget(title="x", widget_type="metric", python_code="st.write(1)")
    manager.add_widget(
        title="y",
        widget_type="metric",
        python_code="st.write(2)",
        dashboard_id="other",
    )

    dashboards = set(manager.list_dashboards())
    assert dashboards == {"default", "other"}


def test_view_dashboard_returns_summary(manager: DashboardManager) -> None:
    manager.add_widget(
        title="Trend",
        widget_type="line_chart",
        python_code="st.line_chart([1, 2, 3])",
        description="Monthly trend",
    )

    info = manager.view_dashboard()
    assert info["widget_count"] == 1
    assert info["widgets"][0]["type"] == "line_chart"
    assert info["widgets"][0]["description"] == "Monthly trend"
    assert info["app_path"].endswith("app.py")


def test_widget_type_enum_round_trips() -> None:
    assert WidgetType("metric") is WidgetType.METRIC
    with pytest.raises(ValueError):
        WidgetType("nope")
