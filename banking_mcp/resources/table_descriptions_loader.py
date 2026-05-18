"""Loader for per-connection table and column descriptions.

Files live in  data/table_descriptions/{connection}.json
Format:
{
  "TABLE_NAME": {
    "description": "What this table contains.",
    "columns": {
      "COLUMN_NAME": "What this column means / when to use it."
    }
  }
}

The loader caches results in memory; call reload() to invalidate the cache
after editing a descriptions file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DATA_DIR = Path(os.getenv("DATA_DIR", ".")) / "table_descriptions"

_cache: dict[str, dict[str, Any]] = {}


def load_descriptions(connection: str) -> dict[str, Any]:
    """Return descriptions dict for *connection*; {} when no file exists."""
    if connection not in _cache:
        file_path = _DATA_DIR / f"{connection}.json"
        if file_path.exists():
            _cache[connection] = json.loads(file_path.read_text(encoding="utf-8"))
        else:
            _cache[connection] = {}
    return _cache[connection]


def reload(connection: str | None = None) -> None:
    """Invalidate cache for one connection (or all if connection is None)."""
    if connection:
        _cache.pop(connection, None)
    else:
        _cache.clear()


def list_described_connections() -> list[str]:
    """Return connection names that have a descriptions file."""
    if not _DATA_DIR.exists():
        return []
    return [p.stem for p in sorted(_DATA_DIR.glob("*.json"))]


__all__ = ["load_descriptions", "reload", "list_described_connections"]
