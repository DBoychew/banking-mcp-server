"""
Dashboard builder MCP tools — mirrors petru's src/mcp_tools/dashboard_tools.py.
"""

import json
import os

from banking_mcp.dashboard import DashboardManager

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8501")
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


def register_dashboard_tools(mcp, dashboard_manager: DashboardManager) -> None:

    @mcp.tool(description="""Add a visualization widget to the banking analytics dashboard.

Use this AFTER showing the user query results and getting their approval.
The python_code uses the `tools` object (same as execute_code) and renders with Streamlit.

Widget types: line_chart, bar_chart, metric, table, pie_chart, area_chart, scatter

Example — transaction trend chart:
```
df = tools.transactions_df('ACC-001', '2026-01-01', '2026-04-30')
df['date'] = pd.to_datetime(df['date'])
daily = df.groupby('date')['amount'].sum().reset_index()
fig = px.line(daily, x='date', y='amount', title='Daily Transaction Volume')
st.plotly_chart(fig, width="stretch")
```

Example — account balance metrics:
```
accounts = tools.get_accounts()
for acc in accounts[:4]:
    st.metric(label=acc.get('iban', acc['account_id']), value=f"{acc['balance']:,.2f} {acc['currency']}")
```

Note: Filter variables (date_start, date_end, etc.) are available if filters are configured.
""")
    def dashboard_add_widget(
        title: str,
        widget_type: str,
        python_code: str,
        description: str = None,
        filters: list = None,
        position: int = None,
    ) -> str:
        """
        Add a new widget to the banking analytics dashboard.

        Args:
            title: Display title for the widget
            widget_type: One of: line_chart, bar_chart, metric, table, pie_chart, area_chart, scatter
            python_code: Python code using `tools` API and Streamlit for rendering
            description: Optional description of what the widget shows
            filters: Optional list of filter configs
            position: Optional position (0 = first). Defaults to end.
        """
        success, message, widget = dashboard_manager.add_widget(
            title=title,
            widget_type=widget_type,
            python_code=python_code,
            description=description,
            filters=filters,
            position=position,
        )

        if success:
            info = dashboard_manager.view_dashboard()
            response = {
                "status": "success",
                "message": message,
                "widget_id": widget.id,
                "total_widgets": info["widget_count"],
                "dashboard_access": {"url": DASHBOARD_URL},
            }
            if DASHBOARD_USERNAME:
                response["dashboard_access"]["username"] = DASHBOARD_USERNAME
            if DASHBOARD_PASSWORD:
                response["dashboard_access"]["password"] = DASHBOARD_PASSWORD
            return json.dumps(response, indent=2)
        else:
            return json.dumps({"status": "error", "message": message}, indent=2)

    @mcp.tool(description="""Update an existing banking dashboard widget.

Only provide the fields you want to change.
To reorder widgets, use the position parameter (0 = first position).
""")
    def dashboard_update_widget(
        widget_id: str,
        title: str = None,
        widget_type: str = None,
        python_code: str = None,
        description: str = None,
        filters: list = None,
        position: int = None,
    ) -> str:
        success, message, widget = dashboard_manager.update_widget(
            widget_id=widget_id,
            title=title,
            widget_type=widget_type,
            python_code=python_code,
            description=description,
            filters=filters,
            position=position,
        )

        if success:
            return json.dumps({
                "status": "success",
                "message": message,
                "widget": widget.to_dict() if widget else None,
            }, indent=2)
        else:
            return json.dumps({"status": "error", "message": message}, indent=2)

    @mcp.tool(description="Remove a widget from the banking analytics dashboard by its ID.")
    def dashboard_remove_widget(widget_id: str) -> str:
        success, message = dashboard_manager.remove_widget(widget_id)
        return json.dumps({
            "status": "success" if success else "error",
            "message": message,
        }, indent=2)

    @mcp.tool(description="""View the current banking analytics dashboard configuration.

Shows all widgets, their positions, global filters, and the dashboard URL.
Use this to see what's currently on the dashboard before making changes.
""")
    def dashboard_view() -> str:
        info = dashboard_manager.view_dashboard()
        info["how_to_run"] = "Run: streamlit run " + info["app_path"]
        info["dashboard_access"] = {"url": DASHBOARD_URL}
        if DASHBOARD_USERNAME:
            info["dashboard_access"]["username"] = DASHBOARD_USERNAME
        if DASHBOARD_PASSWORD:
            info["dashboard_access"]["password"] = DASHBOARD_PASSWORD
        return json.dumps(info, indent=2)
