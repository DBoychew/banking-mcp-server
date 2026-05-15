"""Dynamic Streamlit dashboards exposed via MCP tools.

Widgets are Python snippets that use the shared ``tools`` object, state is
persisted to ``data/dashboards/<id>/state.json``, and a Streamlit app is
regenerated on every change.
"""

from __future__ import annotations

from typing import Optional

from .generator import StreamlitGenerator
from .manager import DashboardManager
from .widgets import (
    DashboardState,
    GlobalFilter,
    Widget,
    WidgetFilter,
    WidgetType,
    generate_widget_id,
)

__all__ = [
    "DashboardManager",
    "DashboardState",
    "GlobalFilter",
    "StreamlitGenerator",
    "Widget",
    "WidgetFilter",
    "WidgetType",
    "generate_widget_id",
    "get_dashboard_manager",
]


_manager: Optional[DashboardManager] = None


def get_dashboard_manager() -> DashboardManager:
    """Return the process-wide :class:`DashboardManager` singleton."""
    global _manager
    if _manager is None:
        _manager = DashboardManager()
    return _manager
