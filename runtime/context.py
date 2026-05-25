"""Compatibility facade for runtime context services.

New code should import from runtime.input_preprocess, runtime.summary,
runtime.observation_store, and runtime.context_provider.
"""

from runtime.context_provider import ContextManager
from runtime.input_preprocess import (
    FILE_MENTION_PATTERN,
    MAX_FILE_MENTIONS,
    PreprocessResult,
    extract_file_mentions,
    preprocess_input,
)
from runtime.observation_store import (
    ObservationTruncator,
    _get_max_bytes,
    _get_max_lines,
    compress_tool_result,
    get_truncator,
    truncate_observation,
)
from runtime.summary import (
    _build_summary_prompt,
    _serialize_messages_for_summary,
    create_summary_generator,
)

__all__ = [
    "ContextManager",
    "FILE_MENTION_PATTERN",
    "MAX_FILE_MENTIONS",
    "ObservationTruncator",
    "PreprocessResult",
    "_build_summary_prompt",
    "_get_max_bytes",
    "_get_max_lines",
    "_serialize_messages_for_summary",
    "compress_tool_result",
    "create_summary_generator",
    "extract_file_mentions",
    "get_truncator",
    "preprocess_input",
    "truncate_observation",
]
