"""Phase 0 frozen trace protocol for the harness core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TraceEventSpec:
    required_payload_fields: tuple[str, ...]


CORE_TRACE_EVENTS: dict[str, TraceEventSpec] = {
    "run_start": TraceEventSpec(("run_id", "input", "processed")),
    "context_build": TraceEventSpec(
        ("message_count", "history_count", "source_message_count", "projection_mode")
    ),
    "model_output": TraceEventSpec(("raw", "usage", "meta", "raw_response", "tool_calls")),
    "state_transition": TraceEventSpec(
        ("step", "turn_count", "reason", "message_count", "details")
    ),
    "tool_call": TraceEventSpec(("tool", "args", "tool_call_id")),
    "tool_result": TraceEventSpec(("tool", "result")),
    "terminal": TraceEventSpec(("reason", "details")),
    "run_end": TraceEventSpec(("run_id", "final")),
}


__all__ = ["CORE_TRACE_EVENTS", "TraceEventSpec"]
