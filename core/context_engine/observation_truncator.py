"""Compatibility wrapper for runtime observation truncation."""

from runtime.context import (
    ObservationTruncator,
    _get_max_bytes,
    _get_max_lines,
    compress_tool_result,
    get_truncator,
    truncate_observation,
)

__all__ = [
    "ObservationTruncator",
    "_get_max_bytes",
    "_get_max_lines",
    "compress_tool_result",
    "get_truncator",
    "truncate_observation",
]
