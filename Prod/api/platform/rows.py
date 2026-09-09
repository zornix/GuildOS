"""Result-shape helpers."""

from __future__ import annotations

from typing import Any


def unwrap_row(result: Any) -> Any:
    """First row of a result that may be a list or a single row."""
    data = result.data
    return data[0] if isinstance(data, list) else data
