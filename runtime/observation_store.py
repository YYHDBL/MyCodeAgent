"""Compatibility exports for the tool observation store.

The implementation lives in ``tools`` so tool orchestration does not depend on
the higher-level runtime package.
"""

from tools.observation_store import (
    ObservationTruncator,
    _get_max_bytes,
    _get_max_lines,
    compress_tool_result,
    force_truncate_observation,
    get_truncator,
    truncate_observation,
)

__all__ = [
    "ObservationTruncator",
    "_get_max_bytes",
    "_get_max_lines",
    "compress_tool_result",
    "force_truncate_observation",
    "get_truncator",
    "truncate_observation",
]
