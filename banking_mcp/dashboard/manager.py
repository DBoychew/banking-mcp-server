"""
Dashboard Manager — handles state persistence and widget operations.

Mirrors petru's src/dashboard/manager.py exactly.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from filelock import FileLock

from .widgets import (
    DashboardState,
    Widget,
    WidgetType,
    WidgetFilter,
    GlobalFilter,
    generate_widget_id,
)
from .generator import StreamlitGenerator


class DashboardManager:
    """
    Manages dashboard state and coordinates with the Streamlit generator.

    State is persisted to JSON files under DATA_DIR/dashboards/.
    Each dashboard has its own folder with state.json and generated app.py.
    """

    def __init__(self, base_path: str = None):
        if base_path is None:
            data_dir = os.getenv("DATA_DIR", ".")
            base_path = Path(data_dir) / "dashboards"

        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.generator = StreamlitGenerator()

    def _get_dashboard_path(self, dashboard_id: str = "default") -> Path:
        return self.base_path / dashboard_id

    def _get_state_file(self, dashboard_id: str = "default") -> Path:
        return self._get_dashboard_path(dashboard_id) / "state.json"

    def _get_app_file(self, dashboard_id: str = "default") -> Path:
        return self._get_dashboard_path(dashboard_id) / "app.py"

    def _get_lock_file(self, dashboard_id: str = "default") -> Path:
        return self._get_dashboard_path(dashboard_id) / ".state.lock"

    def load_state(self, dashboard_id: str = "default") -> DashboardState:
        dashboard_path = self._get_dashboard_path(dashboard_id)
        dashboard_path.mkdir(parents=True, exist_ok=True)

        state_file = self._get_state_file(dashboard_id)
        lock_file = self._get_lock_file(dashboard_id)

        with FileLock(str(lock_file)):
            if state_file.exists():
                try:
                    content = state_file.read_text(encoding="utf-8")
                    return DashboardState.from_json(content)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: Failed to load dashboard state: {e}")

            return DashboardState(dashboard_id=dashboard_id)

    def save_state(self, state: DashboardState) -> None:
        dashboard_path = self._get_dashboard_path(state.dashboard_id)
        dashboard_path.mkdir(parents=True, exist_ok=True)

        state_file = self._get_state_file(state.dashboard_id)
        app_file = self._get_app_file(state.dashboard_id)
        lock_file = self._get_lock_file(state.dashboard_id)

        state.updated_at = datetime.now().isoformat()

        with FileLock(str(lock_file)):
            state_file.write_text(state.to_json(), encoding="utf-8")
            app_code = self.generator.generate(state)
            app_file.write_text(app_code, encoding="utf-8")

    # -------------------------------------------------------------------------
    # Widget Operations
    # -------------------------------------------------------------------------

    def add_widget(
        self,
        title: str,
        widget_type: str,
        python_code: str,
        description: Optional[str] = None,
        filters: Optional[List[Dict]] = None,
        position: Optional[int] = None,
        dashboard_id: str = "default",
    ) -> Tuple[bool, str, Optional[Widget]]:
        state = self.load_state(dashboard_id)

        try:
            wtype = WidgetType(widget_type)
        except ValueError:
            valid_types = [t.value for t in WidgetType]
            return False, f"Invalid widget type '{widget_type}'. Valid types: {valid_types}", None

        python_code = python_code.replace("\\n", "\n").replace("\\t", "\t")

        import re
        if re.search(r"\breturn\b", python_code):
            return False, "Widget code cannot contain 'return' statements. Use if/else blocks instead.", None

        import ast
        try:
            ast.parse(python_code)
        except SyntaxError as e:
            return (
                False,
                f"Python syntax error at line {e.lineno}: {e.msg}. "
                f"Code snippet: {e.text.strip() if e.text else 'N/A'}",
                None,
            )

        base_id = generate_widget_id(title)
        widget_id = base_id
        counter = 1
        existing_ids = {w.id for w in state.widgets}
        while widget_id in existing_ids:
            widget_id = f"{base_id}_{counter}"
            counter += 1

        widget_filters = []
        if filters:
            for f in filters:
                widget_filters.append(WidgetFilter.from_dict(f))

        if position is None:
            position = len(state.widgets)
        else:
            position = max(0, min(position, len(state.widgets)))

        widget = Widget(
            id=widget_id,
            title=title,
            widget_type=wtype,
            python_code=python_code,
            description=description,
            filters=widget_filters,
            position=position,
        )

        state.widgets.insert(position, widget)
        for i, w in enumerate(state.widgets):
            w.position = i

        self.save_state(state)
        return True, f"Widget '{title}' added to dashboard at position {position}", widget

    def update_widget(
        self,
        widget_id: str,
        title: Optional[str] = None,
        widget_type: Optional[str] = None,
        python_code: Optional[str] = None,
        description: Optional[str] = None,
        filters: Optional[List[Dict]] = None,
        position: Optional[int] = None,
        dashboard_id: str = "default",
    ) -> Tuple[bool, str, Optional[Widget]]:
        state = self.load_state(dashboard_id)

        widget = None
        widget_index = None
        for i, w in enumerate(state.widgets):
            if w.id == widget_id:
                widget = w
                widget_index = i
                break

        if widget is None:
            available = [w.id for w in state.widgets]
            return False, f"Widget '{widget_id}' not found. Available: {available}", None

        if title is not None:
            widget.title = title

        if widget_type is not None:
            try:
                widget.widget_type = WidgetType(widget_type)
            except ValueError:
                valid_types = [t.value for t in WidgetType]
                return False, f"Invalid widget type '{widget_type}'. Valid types: {valid_types}", None

        if python_code is not None:
            python_code = python_code.replace("\\n", "\n").replace("\\t", "\t")
            import re
            if re.search(r"\breturn\b", python_code):
                return False, "Widget code cannot contain 'return' statements.", None
            import ast
            try:
                ast.parse(python_code)
            except SyntaxError as e:
                return False, f"Python syntax error at line {e.lineno}: {e.msg}.", None
            widget.python_code = python_code

        if description is not None:
            widget.description = description

        if filters is not None:
            widget.filters = [WidgetFilter.from_dict(f) for f in filters]

        widget.updated_at = datetime.now().isoformat()

        if position is not None and position != widget_index:
            state.widgets.pop(widget_index)
            position = max(0, min(position, len(state.widgets)))
            state.widgets.insert(position, widget)
            for i, w in enumerate(state.widgets):
                w.position = i

        self.save_state(state)
        return True, f"Widget '{widget_id}' updated successfully", widget

    def remove_widget(self, widget_id: str, dashboard_id: str = "default") -> Tuple[bool, str]:
        state = self.load_state(dashboard_id)

        for i, w in enumerate(state.widgets):
            if w.id == widget_id:
                state.widgets.pop(i)
                for j, w2 in enumerate(state.widgets):
                    w2.position = j
                self.save_state(state)
                return True, f"Widget '{widget_id}' removed from dashboard"

        available = [w.id for w in state.widgets]
        return False, f"Widget '{widget_id}' not found. Available: {available}"

    # -------------------------------------------------------------------------
    # Global Filter Operations
    # -------------------------------------------------------------------------

    def set_global_filter(
        self,
        filter_type: str,
        variable_name: str,
        label: str,
        options: Optional[List[str]] = None,
        default: Optional[any] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        dashboard_id: str = "default",
    ) -> Tuple[bool, str]:
        state = self.load_state(dashboard_id)

        valid_types = ["date_range", "selectbox", "multiselect", "slider"]
        if filter_type not in valid_types:
            return False, f"Invalid filter type '{filter_type}'. Valid types: {valid_types}"

        new_filter = GlobalFilter(
            filter_type=filter_type,
            variable_name=variable_name,
            label=label,
            options=options,
            default=default,
            min_value=min_value,
            max_value=max_value,
        )

        for i, f in enumerate(state.global_filters):
            if f.variable_name == variable_name:
                state.global_filters[i] = new_filter
                self.save_state(state)
                return True, f"Global filter '{variable_name}' updated"

        state.global_filters.append(new_filter)
        self.save_state(state)
        return True, f"Global filter '{variable_name}' added to dashboard"

    def remove_global_filter(self, variable_name: str, dashboard_id: str = "default") -> Tuple[bool, str]:
        state = self.load_state(dashboard_id)
        for i, f in enumerate(state.global_filters):
            if f.variable_name == variable_name:
                state.global_filters.pop(i)
                self.save_state(state)
                return True, f"Global filter '{variable_name}' removed"
        available = [f.variable_name for f in state.global_filters]
        return False, f"Filter '{variable_name}' not found. Available: {available}"

    # -------------------------------------------------------------------------
    # Dashboard Info
    # -------------------------------------------------------------------------

    def view_dashboard(self, dashboard_id: str = "default") -> Dict:
        state = self.load_state(dashboard_id)
        app_file = self._get_app_file(dashboard_id)
        return {
            "dashboard_id": state.dashboard_id,
            "title": state.title,
            "columns": state.columns,
            "widget_count": len(state.widgets),
            "widgets": [
                {
                    "id": w.id,
                    "title": w.title,
                    "type": w.widget_type.value if isinstance(w.widget_type, WidgetType) else w.widget_type,
                    "position": w.position,
                    "description": w.description,
                    "filters": [f.to_dict() for f in w.filters],
                }
                for w in sorted(state.widgets, key=lambda x: x.position)
            ],
            "global_filters": [f.to_dict() for f in state.global_filters],
            "app_path": str(app_file),
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }

    def set_layout(self, columns: int, title: Optional[str] = None, dashboard_id: str = "default") -> Tuple[bool, str]:
        if not 1 <= columns <= 4:
            return False, "Columns must be between 1 and 4"
        state = self.load_state(dashboard_id)
        state.columns = columns
        if title:
            state.title = title
        self.save_state(state)
        return True, f"Dashboard layout set to {columns} column(s)"

    def clear_all_widgets(self, dashboard_id: str = "default") -> Tuple[bool, str]:
        state = self.load_state(dashboard_id)
        widget_count = len(state.widgets)
        filter_count = len(state.global_filters)
        if widget_count == 0 and filter_count == 0:
            return True, "Dashboard is already empty"
        state.widgets = []
        state.global_filters = []
        self.save_state(state)
        return True, f"Dashboard cleared: removed {widget_count} widget(s) and {filter_count} global filter(s)"
