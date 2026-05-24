"""Compatibility wrapper for runtime input preprocessing."""

from runtime.context import (
    FILE_MENTION_PATTERN,
    MAX_FILE_MENTIONS,
    PreprocessResult,
    SYSTEM_REMINDER_TEMPLATE,
    extract_file_mentions,
    preprocess_input,
)

__all__ = [
    "FILE_MENTION_PATTERN",
    "MAX_FILE_MENTIONS",
    "PreprocessResult",
    "SYSTEM_REMINDER_TEMPLATE",
    "extract_file_mentions",
    "preprocess_input",
]
