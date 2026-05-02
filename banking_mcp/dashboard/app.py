"""
Banking MCP Dashboard — Streamlit application.

Tabs:
  1. 💱 Валутни курсове — BNB FX rates (публичен API)  [TODO: може да се махне]
  2. 📊 Analytics       — dynamic widgets built by Claude via MCP tools

Run directly:
  streamlit run banking_mcp/dashboard/app.py

Or started automatically by the server in HTTP mode.
"""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from banking_mcp.dashboard.utils import fetch_server_config

st.set_page_config(
    page_title="Banking MCP Dashboard",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🏦 Banking MCP")

    cfg = fetch_server_config()
    st.caption(f"Transport: `{cfg.get('transport', '?')}`")
    st.caption(f"Provider: `{cfg.get('provider', '?')}`")
    st.caption(f"Env: `{cfg.get('env', '?')}`")

    st.divider()
    st.caption("MCP endpoint: `http://localhost:8080/mcp/`")
    st.caption("Analytics: ask Claude to add widgets")

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------

tab1, tab2 = st.tabs([
    "💱 Валутни курсове",
    "📊 Analytics",
])

with tab1:
    from banking_mcp.dashboard.pages.fx_rates import render as render_fx
    render_fx()

with tab2:
    # Dynamic analytics dashboard powered by Claude via MCP dashboard tools
    from banking_mcp.dashboard.manager import DashboardManager
    from pathlib import Path

    dm = DashboardManager()
    state = dm.load_state()
    app_file = dm._get_app_file()

    if not state.widgets:
        st.info(
            "📊 No analytics widgets yet.\n\n"
            "Ask Claude to analyze your data and add visualizations:\n\n"
            "_'Show me all bank branches grouped by city'_\n\n"
            "_'Add a chart of branch count per region'_\n\n"
            "_'Query the database and show results as a table'_"
        )
    else:
        info = dm.view_dashboard()
        st.caption(f"**{info['title']}** — {info['widget_count']} widget(s)")

        if app_file.exists():
            try:
                app_code = app_file.read_text(encoding="utf-8")
                lines = app_code.split("\n")
                filtered = []
                skip_next = False
                for line in lines:
                    if "st.set_page_config" in line or "st.write('<style>" in line or 'st.title("' in line:
                        skip_next = True
                    if skip_next and line.strip().endswith(")"):
                        skip_next = False
                        continue
                    if skip_next:
                        continue
                    filtered.append(line)
                exec("\n".join(filtered), {"__name__": "__banking_dashboard__"})
            except Exception as e:
                st.error(f"Dashboard render error: {e}")
                st.code(str(e))
