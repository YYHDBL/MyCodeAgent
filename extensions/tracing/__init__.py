"""Tracing extension surface."""

from __future__ import annotations

from extensions.tracing.logger import TraceLogger, create_trace_logger
from extensions.tracing.protocol import CORE_TRACE_EVENTS, SUBAGENT_TRACE_EVENTS, TraceEventSpec
from extensions.tracing.sanitizer import TraceSanitizer


class NullTraceLogger:
    """No-op trace logger used when tracing is disabled at bootstrap time."""

    def __init__(self):
        self.enabled = False
        self.session_id = "disabled"
        self._total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def log_event(self, event, payload, step=0):
        return None

    def log_system_messages(self, messages):
        return None

    def finalize(self):
        return None

    def get_current_run_events(self) -> list[dict]:
        return []

    def clear_current_run_events(self):
        pass


__all__ = [
    "NullTraceLogger",
    "CORE_TRACE_EVENTS",
    "SUBAGENT_TRACE_EVENTS",
    "TraceLogger",
    "TraceEventSpec",
    "TraceSanitizer",
    "create_trace_logger",
]
