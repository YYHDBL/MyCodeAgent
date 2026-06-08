"""Lightweight loop state for the runtime agent harness."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class TransitionReason(str, Enum):
    USER_INPUT = "user_input"
    CONTEXT_COMPACTED = "context_compacted"
    MODEL_EMPTY_RETRY = "model_empty_retry"
    MODEL_EMPTY_FAILED = "model_empty_failed"
    MODEL_RECOVERY_RETRY = "model_recovery_retry"
    MODEL_RECOVERY_FAILED = "model_recovery_failed"
    MODEL_RETURNED_TOOL_CALLS = "model_returned_tool_calls"
    TOOLS_EXECUTED = "tools_executed"
    MODEL_RETURNED_FINAL = "model_returned_final"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    UNRECOVERABLE_ERROR = "unrecoverable_error"


class TerminalReason(str, Enum):
    COMPLETED = "completed"
    COMPLETED_UNVERIFIED = "completed_unverified"
    EMPTY_RESPONSE_FAILED = "empty_response_failed"
    COMPLETION_GATE_BLOCKED = "completion_gate_blocked"
    MAX_STEPS = "max_steps"
    TOOL_ERROR_UNRECOVERABLE = "tool_error_unrecoverable"
    USER_ABORT = "user_abort"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True)
class Transition:
    reason: TransitionReason
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoopState:
    messages: list[dict[str, Any]]
    step: int
    turn_count: int
    tool_choice: str
    transition: Transition | None = None
    compact_attempted: bool = False
    max_output_recovery_count: int = 0
    model_recovery_counts: dict[str, int] = field(default_factory=dict)
    stop_hook_active: bool = False
    completion_block_count: int = 0
    last_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    last_response_meta: dict[str, Any] = field(default_factory=dict)
    last_model_error_kind: str | None = None
    last_model_error_stage: str | None = None
    last_error: str | None = None

    def update(self, **changes: Any) -> "LoopState":
        return replace(self, **changes)

    def next(self, reason: TransitionReason, **changes: Any) -> "LoopState":
        details = changes.pop("details", {})
        return replace(self, transition=Transition(reason=reason, details=details), **changes)
