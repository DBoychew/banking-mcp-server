"""
Streamlit App Generator — creates runnable Streamlit code from dashboard state.

Mirrors petru's src/dashboard/generator.py, adapted for banking_mcp imports.
"""

from textwrap import dedent, indent
from typing import List

from .widgets import DashboardState, Widget, WidgetFilter, GlobalFilter, WidgetType


class StreamlitGenerator:
    """Generates a complete Streamlit application from dashboard state."""

    def generate(self, state: DashboardState) -> str:
        parts = [
            self._generate_imports(),
            self._generate_tools_setup(),
            self._generate_chart_theme(),
            self._generate_page_config(state),
            self._generate_helpers(),
            self._generate_global_filters(state.global_filters),
            self._generate_widgets_section(state),
        ]
        return "\n\n".join(parts)

    def _generate_imports(self) -> str:
        return dedent("""
            import streamlit as st
            import pandas as pd
            import plotly.express as px
            import plotly.graph_objects as go
            import plotly.io as pio
            from plotly.subplots import make_subplots
            from datetime import datetime, timedelta, date
            import json
            import sys
            import os

            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        """).strip()

    def _generate_tools_setup(self) -> str:
        return dedent("""
            from banking_mcp.db import DatabaseManager
            from banking_mcp.dashboard import DashboardManager
            from banking_mcp.tools_api import BankingToolsAPI as ToolsAPI

            tools = ToolsAPI(DatabaseManager())
            dashboard_manager = DashboardManager()
        """).strip()

    def _generate_chart_theme(self) -> str:
        return dedent("""
            # =============================================================================
            # Chart Theme Configuration
            # =============================================================================

            CHART_COLORS = [
                "#2563eb", "#16a34a", "#dc2626", "#ca8a04",
                "#9333ea", "#0891b2", "#c2410c", "#4f46e5",
            ]

            ALTERNATING_PAIRS = [
                "#8fd7d7", "#00b0be", "#ffc8a1", "#f45f74",
                "#bad373", "#98c127", "#ffc8de", "#ffbd15",
            ]

            _chart_template = go.layout.Template()
            _chart_template.layout = go.Layout(
                font=dict(
                    family="ui-sans-serif, -apple-system, system-ui, Segoe UI, Helvetica, Arial, sans-serif",
                    size=13,
                    color="#0d0d0d",
                ),
                title=dict(font=dict(size=18, color="#0d0d0d"), x=0, xanchor="left"),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                colorway=ALTERNATING_PAIRS,
                hovermode="x unified",
                hoverlabel=dict(bgcolor="white", font_size=12),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor="#e5e5e5", linecolor="#e5e5e5",
                           tickfont=dict(size=11, color="#6b7280")),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor="#e5e5e5", linecolor="#e5e5e5",
                           tickfont=dict(size=11, color="#6b7280")),
            )
            pio.templates["banking_dashboard"] = _chart_template
            pio.templates.default = "plotly_white+banking_dashboard"
        """).strip()

    def _generate_page_config(self, state: DashboardState) -> str:
        return dedent(f"""
            # =============================================================================
            # Page Configuration
            # =============================================================================

            st.set_page_config(
                page_title="{state.title}",
                page_icon="🏦",
                layout="wide",
                initial_sidebar_state="collapsed"
            )
            st.write('<style>div.block-container{{padding-top:0;}}</style>', unsafe_allow_html=True)
            st.title("{state.title}")

            with st.sidebar:
                st.divider()
                if st.button("🧹 Clear All Widgets", width="stretch", type="secondary"):
                    success, message = dashboard_manager.clear_all_widgets()
                    if success:
                        st.toast(message, icon="✅")
                        st.rerun()
                    else:
                        st.error(message)
        """).strip()

    def _generate_helpers(self) -> str:
        return dedent("""
            # =============================================================================
            # Helper Functions
            # =============================================================================

            def get_relative_date(days_ago: int) -> date:
                return (datetime.now() - timedelta(days=days_ago)).date()

            def get_date_range(period: str) -> tuple:
                today = datetime.now().date()
                periods = {
                    "last_7_days": (today - timedelta(days=7), today),
                    "last_30_days": (today - timedelta(days=30), today),
                    "last_90_days": (today - timedelta(days=90), today),
                    "last_6_months": (today - timedelta(days=180), today),
                    "last_year": (today - timedelta(days=365), today),
                    "this_month": (today.replace(day=1), today),
                    "this_quarter": (today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1), today),
                    "this_year": (today.replace(month=1, day=1), today),
                }
                return periods.get(period, (today - timedelta(days=30), today))

            def format_currency(value: float, symbol: str = "BGN") -> str:
                return f"{value:,.2f} {symbol}"
        """).strip()

    def _generate_global_filters(self, filters: List[GlobalFilter]) -> str:
        if not filters:
            return "# No global filters configured"

        lines = [
            "# =============================================================================",
            "# Global Filters (Sidebar)",
            "# =============================================================================",
            "",
            'st.sidebar.header("🔍 Filters")',
            "",
        ]
        for f in filters:
            lines.extend(self._generate_filter_code(f, is_global=True))
            lines.append("")
        return "\n".join(lines)

    def _generate_filter_code(
        self, f: GlobalFilter | WidgetFilter, is_global: bool = False, widget_id: str = ""
    ) -> List[str]:
        lines = []
        container = "st.sidebar" if is_global else "st"
        key_prefix = f"global_{f.variable_name}" if is_global else f"{widget_id}_{f.variable_name}"

        if f.filter_type == "date_range":
            lines.extend([
                f"# Date Range Filter: {f.label}",
                f"{f.variable_name}_period = {container}.selectbox(",
                f'    "{f.label}",',
                f'    ["Last 7 days", "Last 30 days", "Last 90 days", "Last 6 months", "Last year", "This month", "This quarter", "This year", "Custom"],',
                f"    index=1,",
                f'    key="{key_prefix}_period"',
                f")",
                f"",
                f'if {f.variable_name}_period == "Custom":',
                f"    {f.variable_name}_col1, {f.variable_name}_col2 = {container}.columns(2)",
                f'    {f.variable_name}_start = {f.variable_name}_col1.date_input("Start", value=get_relative_date(30), key="{key_prefix}_start")',
                f'    {f.variable_name}_end = {f.variable_name}_col2.date_input("End", value=get_relative_date(0), key="{key_prefix}_end")',
                f"else:",
                f"    _period_key = {f.variable_name}_period.lower().replace(' ', '_')",
                f"    {f.variable_name}_start, {f.variable_name}_end = get_date_range(_period_key)",
            ])
        elif f.filter_type == "selectbox":
            options = f.options or []
            default_index = 0
            if f.default and f.default in options:
                default_index = options.index(f.default)
            lines.extend([
                f"# Selectbox Filter: {f.label}",
                f"{f.variable_name} = {container}.selectbox(",
                f'    "{f.label}",',
                f"    {options},",
                f"    index={default_index},",
                f'    key="{key_prefix}"',
                f")",
            ])
        elif f.filter_type == "multiselect":
            options = f.options or []
            default = f.default if f.default else options
            lines.extend([
                f"# Multiselect Filter: {f.label}",
                f"{f.variable_name} = {container}.multiselect(",
                f'    "{f.label}",',
                f"    {options},",
                f"    default={default},",
                f'    key="{key_prefix}"',
                f")",
            ])
        elif f.filter_type == "slider":
            min_val = f.min_value if f.min_value is not None else 0
            max_val = f.max_value if f.max_value is not None else 100
            default = f.default if f.default is not None else min_val
            lines.extend([
                f"# Slider Filter: {f.label}",
                f"{f.variable_name} = {container}.slider(",
                f'    "{f.label}",',
                f"    min_value={min_val},",
                f"    max_value={max_val},",
                f"    value={default},",
                f'    key="{key_prefix}"',
                f")",
            ])
        return lines

    def _generate_widgets_section(self, state: DashboardState) -> str:
        if not state.widgets:
            return dedent("""
                # =============================================================================
                # Widgets
                # =============================================================================

                st.info("📊 No widgets yet. Ask the AI assistant to add banking analytics visualizations!")
            """).strip()

        lines = [
            "# =============================================================================",
            "# Widgets",
            "# =============================================================================",
            "",
        ]

        sorted_widgets = sorted(state.widgets, key=lambda w: w.position)
        columns = state.columns

        for i in range(0, len(sorted_widgets), columns):
            row_widgets = sorted_widgets[i : i + columns]

            if columns > 1 and len(row_widgets) > 1:
                col_names = [f"col_{i}_{j}" for j in range(len(row_widgets))]
                lines.append(f"{', '.join(col_names)} = st.columns({len(row_widgets)}, gap='medium')")
                lines.append("")
                for j, widget in enumerate(row_widgets):
                    lines.append(f"with {col_names[j]}:")
                    widget_code = self._generate_widget_code(widget)
                    lines.append(indent(widget_code, "    "))
                    lines.append("")
            else:
                for widget in row_widgets:
                    lines.append(self._generate_widget_code(widget))
                    lines.append("")

            lines.append("")

        return "\n".join(lines)

    def _sanitize_chart_code(self, code: str) -> str:
        import re
        patterns = [
            r",\s*color_discrete_sequence\s*=\s*(?:px\.colors\.[^\),]+|\[[^\]]*\])",
            r"color_discrete_sequence\s*=\s*(?:px\.colors\.[^\),]+|\[[^\]]*\]),\s*",
            r",\s*color_continuous_scale\s*=\s*(?:px\.colors\.[^\),]+|[\"'][^\"']+[\"'])",
            r"color_continuous_scale\s*=\s*(?:px\.colors\.[^\),]+|[\"'][^\"']+[\"'])\s*,\s*",
            r",\s*(?<![a-zA-Z_])template\s*=\s*[\"'][^\"']+[\"']",
            r"(?<![a-zA-Z_])template\s*=\s*[\"'][^\"']+[\"']\s*,\s*",
        ]
        for pattern in patterns:
            code = re.sub(pattern, "", code)
        return code

    def _generate_widget_code(self, widget: Widget) -> str:
        lines = [
            f"# Widget: {widget.title}",
            f"with st.container(border=True):",
        ]

        escaped_title = widget.title.replace('"', '\\"')
        lines.append(f'    st.subheader("{escaped_title}")')

        if widget.description:
            escaped_desc = widget.description.replace("'", "\\'")
            lines.append(f"    st.caption('{escaped_desc}')")

        if widget.filters:
            lines.append('    with st.expander("🔧 Filters", expanded=False):')
            for f in widget.filters:
                filter_lines = self._generate_filter_code(f, is_global=False, widget_id=widget.id)
                for line in filter_lines:
                    lines.append(f"        {line}")
            lines.append("")

        lines.append("    try:")
        sanitized_code = self._sanitize_chart_code(widget.python_code.strip())
        for code_line in sanitized_code.split("\n"):
            lines.append(f"        {code_line}")
        lines.append("    except Exception as e:")
        lines.append('        st.error(f"Error loading widget: {e}")')

        return "\n".join(lines)
