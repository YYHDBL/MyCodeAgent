"""Small synchronous event boundary for runtime facts."""

from __future__ import annotations

import logging
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from runtime.state import LoopState, TransitionReason


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeEvent:
    """One name-stable fact emitted by the runtime."""

    run_id: str
    step: int
    type: str
    payload: dict[str, Any]


class RuntimeEventSink(Protocol):
    """Consumes synchronous runtime facts."""

    def emit(self, event: RuntimeEvent) -> None: ...


class NoopRuntimeEventSink:
    """Accept runtime facts when persistence is intentionally disabled."""

    def emit(self, event: RuntimeEvent) -> None:
        return None


class CompositeRuntimeEventSink:
    """Deliver an event to independent sinks in construction order."""

    def __init__(
        self,
        sinks: tuple[RuntimeEventSink, ...] | list[RuntimeEventSink],
        *,
        on_sink_failure: Callable[[RuntimeEvent, RuntimeEventSink, Exception], None] | None = None,
    ) -> None:
        self.sinks = tuple(sinks)
        self.on_sink_failure = on_sink_failure

    def emit(self, event: RuntimeEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception as error:  # Persistence diagnostics must not alter loop state.
                logger.warning("Runtime event sink failed for %s: %s", event.type, error)
                if self.on_sink_failure is not None:
                    try:
                        self.on_sink_failure(event, sink, error)
                    except Exception as callback_error:
                        logger.warning("Runtime event sink failure callback failed: %s", callback_error)


class TraceRuntimeEventSink:
    """Project runtime facts into the established diagnostic trace protocol."""

    _TRACE_EVENT_NAMES = {"message": "message_written"}

    def __init__(self, trace_logger: Any) -> None:
        self.trace_logger = trace_logger

    def emit(self, event: RuntimeEvent) -> None:
        if event.type == "tool_lifecycle":
            self._emit_tool_lifecycle(event)
            return
        payload = event.payload
        if event.type == "state_transition":
            payload = {
                field: event.payload[field]
                for field in ("step", "turn_count", "reason", "message_count", "details")
            }
        self.trace_logger.log_event(
            self._TRACE_EVENT_NAMES.get(event.type, event.type),
            payload,
            step=event.step,
        )

    def _emit_tool_lifecycle(self, event: RuntimeEvent) -> None:
        payload = event.payload
        lifecycle_payload = payload.get("payload") or {}
        status = payload.get("status")
        if status == "requested":
            self.trace_logger.log_event(
                "tool_call",
                {
                    "tool": payload.get("tool_name"),
                    "args": lifecycle_payload.get("args") or {},
                    "tool_call_id": payload.get("tool_call_id"),
                },
                step=event.step,
            )
        elif status in {"completed", "failed"} and (
            "result" in lifecycle_payload or "result_text" in lifecycle_payload
        ):
            self.trace_logger.log_event(
                "tool_result",
                {
                    "tool": payload.get("tool_name"),
                    "result": lifecycle_payload.get("result", {"text": lifecycle_payload.get("result_text", "")}),
                },
                step=event.step,
            )
        self.trace_logger.log_event("tool_lifecycle", payload, step=event.step)


class TranscriptRuntimeEventSink:
    """Project durable facts into the append-only transcript schema."""

    def __init__(self, recorder: Any | None) -> None:
        self.recorder = recorder

    def emit(self, event: RuntimeEvent) -> None:
        if self.recorder is None:
            return
        payload = event.payload
        if event.type == "message":
            self._require(payload, "message", "role", "content")
            self.recorder.record_message(
                run_id=event.run_id,
                step=event.step,
                role=payload["role"],
                content=payload["content"],
                metadata=payload.get("metadata") or {},
            )
        elif event.type == "state_transition":
            self._require(payload, "state_transition", "to_state", "reason")
            self.recorder.record_state_transition(
                run_id=event.run_id,
                step=event.step,
                from_state=payload.get("from_state"),
                to_state=payload["to_state"],
                reason=payload["reason"],
                details=payload.get("details") or {},
            )
        elif event.type == "checkpoint":
            self._require(payload, "checkpoint", "checkpoint_id")
            self.recorder.record_checkpoint(
                run_id=event.run_id,
                step=event.step,
                checkpoint_id=payload["checkpoint_id"],
                payload=payload.get("payload") or {},
            )
        elif event.type == "terminal":
            self._require(payload, "terminal", "reason")
            self.recorder.record_terminal(
                run_id=event.run_id,
                step=event.step,
                reason=payload["reason"],
                details=payload.get("details") or {},
            )
        elif event.type == "tool_lifecycle":
            self._require(payload, "tool_lifecycle", "tool_name", "tool_call_id", "status")
            self.recorder.record_tool_lifecycle(
                run_id=event.run_id,
                step=event.step,
                tool_name=payload["tool_name"],
                tool_call_id=payload["tool_call_id"],
                status=payload["status"],
                payload=payload.get("payload") or {},
            )

    @staticmethod
    def _require(payload: dict[str, Any], event_type: str, *fields: str) -> None:
        missing = [field for field in fields if field not in payload]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{event_type} event requires {joined}")


def create_runtime_event_sink(trace_logger: Any, recorder: Any | None) -> CompositeRuntimeEventSink:
    """Build the standard trace-plus-transcript sink for one runtime host."""

    return CompositeRuntimeEventSink(
        (TraceRuntimeEventSink(trace_logger), TranscriptRuntimeEventSink(recorder))
    )


def transition_state(
    state: LoopState,
    reason: TransitionReason,
    *,
    emit: Callable[[str, dict[str, Any], int], None],
    step: int | None = None,
    details: dict[str, Any] | None = None,
    **changes: Any,
) -> LoopState:
    """Advance one loop state and persist its public transition fact."""

    next_step = state.step if step is None else step
    fields = LoopState.__dataclass_fields__
    state_changes = {key: value for key, value in changes.items() if key in fields}
    payload_details = details if details is not None else {
        key: value for key, value in changes.items() if key not in fields
    }
    next_state = state.next(reason, step=next_step, details=payload_details, **state_changes)
    emit(
        "state_transition",
        {
            "from_state": state.transition.reason.value if state.transition else None,
            "to_state": reason.value,
            "step": next_state.step,
            "turn_count": next_state.turn_count,
            "reason": reason.value,
            "message_count": len(next_state.messages),
            "details": payload_details,
        },
        next_state.step if step is None else step,
    )
    return next_state


def record_active_checkpoint(host: Any, *, emit: Callable[[str, dict[str, Any], int], None], step: int) -> None:
    checkpoint = host.context_engine.compact_store.active_checkpoint
    if checkpoint is None:
        return
    emit(
        "checkpoint",
        {
            "checkpoint_id": checkpoint.id,
            "payload": {
                "summary": checkpoint.summary,
                "source_message_count": checkpoint.source_message_count,
                "retain_start_idx": checkpoint.retain_start_idx,
                "messages_compacted": checkpoint.messages_compacted,
                "created_at": checkpoint.created_at,
                "metadata": dict(checkpoint.metadata),
            },
        },
        step,
    )


def trace_model_request_state(
    host: Any,
    *,
    emit: Callable[[str, dict[str, Any], int], None],
    tools_schema: list[dict[str, Any]],
    step: int,
) -> None:
    """Record the stable prompt and tool-schema facts for one model call."""

    prompt_assembly = host.context_builder.get_prompt_assembly()
    previous = getattr(host, "_last_prompt_fingerprints", {})
    current = {
        "constitution": prompt_assembly.constitution_fingerprint,
        "tool_contracts": prompt_assembly.tool_contracts_fingerprint,
        "project_rules": prompt_assembly.project_rules_fingerprint,
        "runtime_signals": prompt_assembly.runtime_signals_fingerprint,
    }
    emit(
        "prompt_assembly",
        {
            "constitution_fingerprint": prompt_assembly.constitution_fingerprint,
            "tool_contracts_fingerprint": prompt_assembly.tool_contracts_fingerprint,
            "project_rules_fingerprint": prompt_assembly.project_rules_fingerprint,
            "runtime_signals_fingerprint": prompt_assembly.runtime_signals_fingerprint,
            "system_fingerprint": prompt_assembly.system_fingerprint,
            "stable_message_count": len(prompt_assembly.stable_messages),
            "runtime_signal_count": len(prompt_assembly.runtime_signal_messages),
            "changed_layers": [key for key, value in current.items() if previous.get(key) not in (None, value)],
        },
        step,
    )
    host._last_prompt_fingerprints = current
    fingerprint = hashlib.sha256(
        json.dumps(tools_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    previous_fingerprint = getattr(host, "_last_tool_schema_fingerprint", None)
    emit(
        "tool_schema",
        {
            "fingerprint": fingerprint,
            "tool_count": len(tools_schema),
            "changed": previous_fingerprint not in (None, fingerprint),
        },
        step,
    )
    host._last_tool_schema_fingerprint = fingerprint


__all__ = [
    "CompositeRuntimeEventSink",
    "NoopRuntimeEventSink",
    "RuntimeEvent",
    "RuntimeEventSink",
    "TraceRuntimeEventSink",
    "TranscriptRuntimeEventSink",
    "create_runtime_event_sink",
]
