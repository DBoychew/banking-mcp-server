"""Tests for banking_mcp.dashboard.generator.StreamlitGenerator.

The generator must produce code that is at least syntactically valid Python
- runtime correctness depends on Streamlit, which we don't import in tests.
"""

from __future__ import annotations

import ast

import pytest

from banking_mcp.dashboard.generator import StreamlitGenerator
from banking_mcp.dashboard.widgets import (
    DashboardState,
    GlobalFilter,
    Widget,
    WidgetFilter,
    WidgetType,
)


@pytest.fixture
def gen() -> StreamlitGenerator:
    return StreamlitGenerator()


def _parse(code: str) -> None:
    ast.parse(code)


def test_empty_dashboard_parses(gen: StreamlitGenerator) -> None:
    state = DashboardState(dashboard_id="default", title="Empty")
    code = gen.generate(state)
    _parse(code)
    assert "No widgets yet" in code


def test_single_widget_parses(gen: StreamlitGenerator) -> None:
    state = DashboardState(
        dashboard_id="default",
        title="Demo",
        widgets=[
            Widget(
                id="rev",
                title="Revenue",
                widget_type=WidgetType.LINE_CHART,
                python_code="df = tools.execute_sql_query('SELECT 1')\nst.line_chart(df)",
            )
        ],
    )
    code = gen.generate(state)
    _parse(code)
    assert "BankingToolsAPI" in code
    assert "get_dashboard_manager" in code
    assert "Revenue" in code


def test_multi_column_layout_parses(gen: StreamlitGenerator) -> None:
    widgets = [
        Widget(
            id=f"w{i}",
            title=f"W {i}",
            widget_type=WidgetType.METRIC,
            python_code=f"st.metric('w{i}', {i})",
            position=i,
        )
        for i in range(3)
    ]
    state = DashboardState(
        dashboard_id="default", title="Multi", widgets=widgets, columns=2
    )
    code = gen.generate(state)
    _parse(code)
    assert "st.columns(2" in code


def test_global_filter_renders_in_sidebar(gen: StreamlitGenerator) -> None:
    state = DashboardState(
        dashboard_id="default",
        title="Filters",
        global_filters=[
            GlobalFilter(
                filter_type="selectbox",
                variable_name="region",
                label="Region",
                options=["EU", "US"],
            )
        ],
    )
    code = gen.generate(state)
    _parse(code)
    assert "st.sidebar.header(" in code
    assert "region = st.sidebar.selectbox(" in code


def test_widget_filter_uses_widget_scoped_container(gen: StreamlitGenerator) -> None:
    widget = Widget(
        id="w",
        title="W",
        widget_type=WidgetType.METRIC,
        python_code="st.metric('x', 1)",
        filters=[
            WidgetFilter(
                filter_type="slider",
                variable_name="threshold",
                label="Threshold",
                min_value=0,
                max_value=100,
                default=50,
            )
        ],
    )
    state = DashboardState(widgets=[widget])
    code = gen.generate(state)
    _parse(code)
    assert "threshold = st.slider(" in code
    assert "🔧 Filters" in code


def test_sanitize_strips_color_overrides(gen: StreamlitGenerator) -> None:
    widget = Widget(
        id="w",
        title="W",
        widget_type=WidgetType.BAR_CHART,
        python_code=(
            "fig = px.bar(df, x='a', y='b', color_discrete_sequence=['#ff0000'], "
            "template='plotly_dark')\nst.plotly_chart(fig)"
        ),
    )
    state = DashboardState(widgets=[widget])
    code = gen.generate(state)
    _parse(code)
    # Theme overrides must not leak through
    assert "color_discrete_sequence" not in code
    assert "plotly_dark" not in code


def test_widget_body_wrapped_in_try_except(gen: StreamlitGenerator) -> None:
    widget = Widget(
        id="w",
        title="W",
        widget_type=WidgetType.METRIC,
        python_code="st.metric('x', 1)",
    )
    state = DashboardState(widgets=[widget])
    code = gen.generate(state)
    _parse(code)
    assert "try:" in code
    assert "except Exception as e" in code
    assert "Error loading widget" in code


def test_titles_with_quotes_do_not_break_parsing(gen: StreamlitGenerator) -> None:
    widget = Widget(
        id="w",
        title='Trend "Q1" / Q2',
        widget_type=WidgetType.METRIC,
        python_code="st.metric('x', 1)",
        description="Описание с 'кавички' и \"двойни\"",
    )
    state = DashboardState(widgets=[widget], title='My "Dashboard"')
    code = gen.generate(state)
    _parse(code)
