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

SUBAGENT_TRACE_EVENTS: dict[str, TraceEventSpec] = {
    "subagent_requested": TraceEventSpec(
        (
            "parent_session_id",
            "parent_run_id",
            "child_session_id",
            "child_run_id",
            "profile",
            "model",
            "max_steps",
            "context_token_budget",
            "total_token_budget",
        )
    ),
    "subagent_started": TraceEventSpec(
        ("parent_session_id", "parent_run_id", "child_session_id", "child_run_id", "profile")
    ),
    "subagent_completed": TraceEventSpec(
        (
            "parent_session_id",
            "parent_run_id",
            "child_session_id",
            "child_run_id",
            "profile",
            "terminal_reason",
            "tool_usage",
            "token_usage",
            "verdict",
            "elapsed_ms",
        )
    ),
    "subagent_failed": TraceEventSpec(
        (
            "parent_session_id",
            "parent_run_id",
            "child_session_id",
            "child_run_id",
            "profile",
            "terminal_reason",
            "elapsed_ms",
        )
    ),
}


__all__ = ["CORE_TRACE_EVENTS", "SUBAGENT_TRACE_EVENTS", "TraceEventSpec"]
