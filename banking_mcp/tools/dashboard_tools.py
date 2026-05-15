"""Dashboard builder MCP tools.

Mirrors ``petru/src/mcp_tools/dashboard_tools.py``: the LLM adds widgets
whose Python code uses the same ``tools`` object as ``execute_code``.
Streamlit re-renders them on the next file watcher tick.

NOTE: do not add ``from __future__ import annotations`` here.
FastMCP introspects parameter types via ``issubclass()``, which only works
when annotations are real classes (not PEP 563 strings).
"""

import json

from banking_mcp.config import settings
from banking_mcp.dashboard import get_dashboard_manager


def _dashboard_access() -> dict:
    return {"url": settings.DASHBOARD_URL}


def register_dashboard_tools(mcp) -> None:
    @mcp.tool(
        description=(
            "Add a visualization widget to the dashboard.\n\n"
            "Use this AFTER showing the user query results and getting their "
            "approval. The python_code should use the `tools` object (same "
            "API as execute_code) and render output using Streamlit "
            "(st.line_chart, st.bar_chart, st.metric, etc.).\n\n"
            "Widget types: line_chart, bar_chart, metric, table, pie_chart, "
            "area_chart, scatter, heatmap.\n\n"
            "Example python_code for a line chart:\n"
            "```\n"
            "df = tools.execute_sql_query('''\n"
            "    SELECT TO_CHAR(txn_date, 'YYYY-MM-DD') as day,\n"
            "           SUM(amount) as revenue\n"
            "    FROM transactions\n"
            "    GROUP BY TO_CHAR(txn_date, 'YYYY-MM-DD')\n"
            "    ORDER BY 1\n"
            "''')\n"
            "st.line_chart(df.set_index('day'))\n"
            "```\n\n"
            "Filter variables (e.g. date_start, date_end) are available "
            "when filters are configured."
        )
    )
    def dashboard_add_widget(
        title: str,
        widget_type: str,
        python_code: str,
        description: str = None,
        filters: list = None,
        position: int = None,
    ) -> str:
        manager = get_dashboard_manager()
        success, message, widget = manager.add_widget(
            title=title,
            widget_type=widget_type,
            python_code=python_code,
            description=description,
            filters=filters,
            position=position,
        )

        if not success:
            return json.dumps(
                {"status": "error", "message": message}, ensure_ascii=False, indent=2
            )

        info = manager.view_dashboard()
        response = {
            "status": "success",
            "message": message,
            "widget_id": widget.id if widget else None,
            "total_widgets": info["widget_count"],
            "dashboard_access": _dashboard_access(),
        }
        return json.dumps(response, ensure_ascii=False, indent=2)

    @mcp.tool(
        description=(
            "Update an existing dashboard widget. Only provided fields are "
            "changed. Use position to reorder widgets (0 = first)."
        )
    )
    def dashboard_update_widget(
        widget_id: str,
        title: str = None,
        widget_type: str = None,
        python_code: str = None,
        description: str = None,
        filters: list = None,
        position: int = None,
    ) -> str:
        success, message, widget = get_dashboard_manager().update_widget(
            widget_id=widget_id,
            title=title,
            widget_type=widget_type,
            python_code=python_code,
            description=description,
            filters=filters,
            position=position,
        )

        if not success:
            return json.dumps(
                {"status": "error", "message": message}, ensure_ascii=False, indent=2
            )

        return json.dumps(
            {
                "status": "success",
                "message": message,
                "widget": widget.to_dict() if widget else None,
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool(description="Remove a widget from the dashboard by its ID.")
    def dashboard_remove_widget(widget_id: str) -> str:
        success, message = get_dashboard_manager().remove_widget(widget_id)
        return json.dumps(
            {"status": "success" if success else "error", "message": message},
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool(
        description=(
            "View the current dashboard configuration. Returns all widgets, "
            "their positions, global filters, the path of the generated "
            "Streamlit app and the URL where it is served."
        )
    )
    def dashboard_view() -> str:
        info = get_dashboard_manager().view_dashboard()
        info["how_to_run"] = f"streamlit run {info['app_path']}"
        info["dashboard_access"] = _dashboard_access()
        return json.dumps(info, ensure_ascii=False, indent=2)

    # NOTE: dashboard_set_global_filter is intentionally not exposed yet
    # (same as petru). The DashboardManager already supports it - flip on
    # when we agree on the LLM-facing description.
