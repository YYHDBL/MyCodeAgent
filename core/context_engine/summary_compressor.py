"""Compatibility wrapper for runtime summary generation."""

import runtime.context as _runtime_context

concurrent = _runtime_context.concurrent
create_summary_generator = _runtime_context.create_summary_generator
_serialize_messages_for_summary = _runtime_context._serialize_messages_for_summary
_build_summary_prompt = _runtime_context._build_summary_prompt

__all__ = [
    "concurrent",
    "create_summary_generator",
    "_serialize_messages_for_summary",
    "_build_summary_prompt",
]
