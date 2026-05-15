"""Widget definitions and validation for the dashboard builder."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class WidgetType(str, Enum):
    """Supported widget visualization types."""

    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    METRIC = "metric"
    TABLE = "table"
    PIE_CHART = "pie_chart"
    AREA_CHART = "area_chart"
    SCATTER = "scatter"
    HEATMAP = "heatmap"


FilterType = Literal["date_range", "selectbox", "multiselect", "slider"]


@dataclass
class WidgetFilter:
    """Per-widget filter shown inside the widget's expander."""

    filter_type: FilterType
    variable_name: str
    label: str
    options: Optional[List[str]] = None
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "filter_type": self.filter_type,
            "variable_name": self.variable_name,
            "label": self.label,
            "options": self.options,
            "default": self.default,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WidgetFilter":
        return cls(
            filter_type=data["filter_type"],
            variable_name=data["variable_name"],
            label=data["label"],
            options=data.get("options"),
            default=data.get("default"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
        )


@dataclass
class GlobalFilter:
    """Sidebar filter that affects all widgets."""

    filter_type: FilterType
    variable_name: str
    label: str
    options: Optional[List[str]] = None
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "filter_type": self.filter_type,
            "variable_name": self.variable_name,
            "label": self.label,
            "options": self.options,
            "default": self.default,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "GlobalFilter":
        return cls(
            filter_type=data["filter_type"],
            variable_name=data["variable_name"],
            label=data["label"],
            options=data.get("options"),
            default=data.get("default"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
        )


@dataclass
class Widget:
    """A single dashboard visualization.

    ``python_code`` runs in the generated Streamlit app and has access to
    the same ``tools`` object exposed to :class:`banking_mcp.executor.CodeExecutor`.
    """

    id: str
    title: str
    widget_type: WidgetType
    python_code: str
    description: Optional[str] = None
    filters: List[WidgetFilter] = field(default_factory=list)
    position: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "widget_type": (
                self.widget_type.value
                if isinstance(self.widget_type, WidgetType)
                else self.widget_type
            ),
            "python_code": self.python_code,
            "description": self.description,
            "filters": [f.to_dict() for f in self.filters],
            "position": self.position,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Widget":
        widget_type = data["widget_type"]
        if isinstance(widget_type, str):
            widget_type = WidgetType(widget_type)

        filters = [WidgetFilter.from_dict(f) for f in data.get("filters", [])]

        return cls(
            id=data["id"],
            title=data["title"],
            widget_type=widget_type,
            python_code=data["python_code"],
            description=data.get("description"),
            filters=filters,
            position=data.get("position", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at"),
        )


@dataclass
class DashboardState:
    """Full dashboard configuration persisted to ``state.json``."""

    dashboard_id: str = "default"
    title: str = ""
    widgets: List[Widget] = field(default_factory=list)
    global_filters: List[GlobalFilter] = field(default_factory=list)
    columns: int = 2
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "widgets": [w.to_dict() for w in self.widgets],
            "global_filters": [f.to_dict() for f in self.global_filters],
            "columns": self.columns,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DashboardState":
        widgets = [Widget.from_dict(w) for w in data.get("widgets", [])]
        global_filters = [
            GlobalFilter.from_dict(f) for f in data.get("global_filters", [])
        ]

        return cls(
            dashboard_id=data.get("dashboard_id", "default"),
            title=data.get("title", "Dashboard"),
            widgets=widgets,
            global_filters=global_filters,
            columns=data.get("columns", 2),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at"),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "DashboardState":
        return cls.from_dict(json.loads(json_str))


def generate_widget_id(title: str) -> str:
    """Generate a snake_case id from a free-form title."""
    id_str = title.lower()
    id_str = re.sub(r"[^a-z0-9]+", "_", id_str)
    id_str = re.sub(r"_+", "_", id_str)
    id_str = id_str.strip("_")
    return id_str or "widget"
