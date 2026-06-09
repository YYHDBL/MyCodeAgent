"""Append-only transcript facts and resume reconstruction."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from runtime.context.compact_store import CompactCheckpoint
from runtime.state import LoopState, Transition, TransitionReason


SCHEMA_VERSION = 1
UNSAFE_UNCERTAIN_REPLAY_TOOLS = {"Write", "Edit", "MultiEdit", "Bash", "Task"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_transcript_session_id(trace_session_id: str | None) -> str:
    normalized = str(trace_session_id or "").strip()
    if normalized and normalized != "disabled":
        return normalized
    return f"session-{uuid.uuid4().hex}"


class TranscriptEventType(str, Enum):
    MESSAGE = "message"
    STATE_TRANSITION = "state_transition"
    TOOL_LIFECYCLE = "tool_lifecycle"
    CHECKPOINT = "checkpoint"
    TERMINAL = "terminal"


class ToolLifecycleStatus(str, Enum):
    REQUESTED = "requested"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class TranscriptEvent:
    event_id: str
    timestamp: str
    session_id: str
    run_id: str
    step: int
    event_type: TranscriptEventType
    payload: dict[str, Any]
    reference_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "step": self.step,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "schema_version": self.schema_version,
        }
        if self.reference_id:
            data["reference_id"] = self.reference_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptEvent":
        return cls(
            event_id=str(data["event_id"]),
            timestamp=str(data["timestamp"]),
            session_id=str(data["session_id"]),
            run_id=str(data["run_id"]),
            step=int(data["step"]),
            event_type=TranscriptEventType(str(data["event_type"])),
            payload=dict(data.get("payload") or {}),
            reference_id=data.get("reference_id"),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class UncertainAction:
    tool_name: str
    tool_call_id: str
    step: int
    payload: dict[str, Any] = field(default_factory=dict)
    replay_allowed: bool = False


@dataclass(frozen=True)
class ResumeState:
    session_id: str
    run_id: str
    history_messages: list[dict[str, Any]]
    loop_state: LoopState
    checkpoint: dict[str, Any] | None
    terminal: dict[str, Any] | None
    pending_tool_calls: list[dict[str, Any]]
    uncertain_actions: list[UncertainAction]
    completed_tool_results: dict[str, dict[str, Any]]
    failed_tool_results: dict[str, dict[str, Any]]
    runtime_state: dict[str, Any] = field(default_factory=dict)

    def apply_to_host(self, host: Any) -> None:
        if hasattr(host, "context_engine"):
            host.context_engine.reset()
        if hasattr(host, "history_manager"):
            host.history_manager.load_messages(self.history_messages)
        checkpoint = self.checkpoint
        compact_store = getattr(getattr(host, "context_engine", None), "compact_store", None)
        if checkpoint and compact_store is not None:
            compact_store.set_active(
                CompactCheckpoint(
                    id=str(checkpoint["checkpoint_id"]),
                    summary=str(checkpoint.get("summary", "")),
                    source_message_count=int(checkpoint.get("source_message_count", len(self.history_messages))),
                    retain_start_idx=int(checkpoint.get("retain_start_idx", 0)),
                    messages_compacted=int(checkpoint.get("messages_compacted", 0)),
                    created_at=str(checkpoint.get("created_at") or _utc_now_iso()),
                    metadata=dict(checkpoint.get("metadata") or {}),
                )
            )
        tool_registry = getattr(host, "tool_registry", None)
        read_cache = self.runtime_state.get("read_cache")
        if tool_registry is not None and isinstance(read_cache, dict) and hasattr(tool_registry, "import_read_cache"):
            tool_registry.import_read_cache(read_cache)


class TranscriptStore:
    """Append-only JSONL transcript store."""

    def __init__(self, path: str | Path, *, session_id: str):
        self.path = Path(path)
        self.session_id = str(session_id)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def infer_session_id(path: str | Path) -> str | None:
        transcript_path = Path(path)
        if not transcript_path.exists():
            return None
        with transcript_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = payload.get("session_id")
                if session_id:
                    return str(session_id)
        return None

    def append_event(self, event: TranscriptEvent) -> TranscriptEvent:
        line = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock:
            self._repair_trailing_record()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()
        return event

    def _repair_trailing_record(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        data = self.path.read_bytes()
        if data.endswith(b"\n"):
            return

        last_newline = data.rfind(b"\n")
        tail_start = last_newline + 1
        tail = data[tail_start:]
        try:
            json.loads(tail.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            with self.path.open("r+b") as handle:
                handle.truncate(tail_start)
            return

        with self.path.open("ab") as handle:
            handle.write(b"\n")
            handle.flush()

    def append_message(
        self,
        *,
        run_id: str,
        step: int,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self._append(
            run_id=run_id,
            step=step,
            event_type=TranscriptEventType.MESSAGE,
            payload={
                "role": role,
                "content": content,
                "metadata": dict(metadata or {}),
            },
            reference_id=reference_id,
        )

    def append_state_transition(
        self,
        *,
        run_id: str,
        step: int,
        from_state: str | None,
        to_state: str,
        reason: str,
        details: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self._append(
            run_id=run_id,
            step=step,
            event_type=TranscriptEventType.STATE_TRANSITION,
            payload={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "details": dict(details or {}),
            },
            reference_id=reference_id,
        )

    def append_tool_lifecycle(
        self,
        *,
        run_id: str,
        step: int,
        tool_name: str,
        tool_call_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self._append(
            run_id=run_id,
            step=step,
            event_type=TranscriptEventType.TOOL_LIFECYCLE,
            payload={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "status": status,
                **dict(payload or {}),
            },
            reference_id=reference_id,
        )

    def append_checkpoint(
        self,
        *,
        run_id: str,
        step: int,
        checkpoint_id: str,
        payload: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        body = dict(payload or {})
        body["checkpoint_id"] = checkpoint_id
        body.setdefault("created_at", _utc_now_iso())
        return self._append(
            run_id=run_id,
            step=step,
            event_type=TranscriptEventType.CHECKPOINT,
            payload=body,
            reference_id=reference_id,
        )

    def append_terminal(
        self,
        *,
        run_id: str,
        step: int,
        reason: str,
        details: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self._append(
            run_id=run_id,
            step=step,
            event_type=TranscriptEventType.TERMINAL,
            payload={
                "reason": reason,
                "details": dict(details or {}),
            },
            reference_id=reference_id,
        )

    def read_events(self, *, run_id: str | None = None) -> list[TranscriptEvent]:
        if not self.path.exists():
            return []
        events: list[TranscriptEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        for index, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                if index == len(lines) - 1:
                    break
                raise
            if parsed.get("session_id") != self.session_id:
                continue
            event = TranscriptEvent.from_dict(parsed)
            if run_id is not None and event.run_id != str(run_id):
                continue
            events.append(event)
        return events

    def _append(
        self,
        *,
        run_id: str,
        step: int,
        event_type: TranscriptEventType,
        payload: dict[str, Any],
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        event = TranscriptEvent(
            event_id=f"evt-{uuid.uuid4().hex}",
            timestamp=_utc_now_iso(),
            session_id=self.session_id,
            run_id=str(run_id),
            step=int(step),
            event_type=event_type,
            payload=payload,
            reference_id=reference_id,
        )
        return self.append_event(event)


class TranscriptRecorder:
    """Runtime-facing recorder that hides raw store writes."""

    def __init__(self, store: TranscriptStore):
        self.store = store

    def record_message(
        self,
        *,
        run_id: str,
        step: int,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self.store.append_message(
            run_id=run_id,
            step=step,
            role=role,
            content=content,
            metadata=metadata,
            reference_id=reference_id,
        )

    def record_state_transition(
        self,
        *,
        run_id: str,
        step: int,
        from_state: str | None,
        to_state: str,
        reason: str,
        details: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self.store.append_state_transition(
            run_id=run_id,
            step=step,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            details=details,
            reference_id=reference_id,
        )

    def record_tool_lifecycle(
        self,
        *,
        run_id: str,
        step: int,
        tool_name: str,
        tool_call_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self.store.append_tool_lifecycle(
            run_id=run_id,
            step=step,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            status=status,
            payload=payload,
            reference_id=reference_id,
        )

    def record_checkpoint(
        self,
        *,
        run_id: str,
        step: int,
        checkpoint_id: str,
        payload: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self.store.append_checkpoint(
            run_id=run_id,
            step=step,
            checkpoint_id=checkpoint_id,
            payload=payload,
            reference_id=reference_id,
        )

    def record_terminal(
        self,
        *,
        run_id: str,
        step: int,
        reason: str,
        details: dict[str, Any] | None = None,
        reference_id: str | None = None,
    ) -> TranscriptEvent:
        return self.store.append_terminal(
            run_id=run_id,
            step=step,
            reason=reason,
            details=details,
            reference_id=reference_id,
        )


class ResumeLoader:
    """Reconstruct runtime facts from transcript events."""

    def __init__(self, store: TranscriptStore):
        self.store = store

    def load(self, *, run_id: str) -> ResumeState:
        events = self.store.read_events(run_id=run_id)
        history_messages: list[dict[str, Any]] = []
        checkpoint: dict[str, Any] | None = None
        terminal: dict[str, Any] | None = None
        latest_transition: Transition | None = None
        latest_step = 0
        tool_events: dict[str, dict[str, Any]] = {}

        for event in events:
            latest_step = max(latest_step, event.step)
            payload = event.payload
            if event.event_type is TranscriptEventType.MESSAGE:
                history_messages.append(
                    {
                        "role": payload.get("role", "assistant"),
                        "content": payload.get("content", ""),
                        "metadata": dict(payload.get("metadata") or {}),
                    }
                )
            elif event.event_type is TranscriptEventType.STATE_TRANSITION:
                reason_value = str(payload.get("reason") or TransitionReason.USER_INPUT.value)
                try:
                    reason = TransitionReason(reason_value)
                except ValueError:
                    reason = TransitionReason.UNRECOVERABLE_ERROR
                latest_transition = Transition(
                    reason=reason,
                    details=dict(payload.get("details") or {}),
                )
            elif event.event_type is TranscriptEventType.CHECKPOINT:
                checkpoint = dict(payload)
            elif event.event_type is TranscriptEventType.TERMINAL:
                terminal = dict(payload)
            elif event.event_type is TranscriptEventType.TOOL_LIFECYCLE:
                tool_call_id = str(payload.get("tool_call_id") or "")
                if not tool_call_id:
                    continue
                current = tool_events.setdefault(tool_call_id, {})
                current.update(
                    {
                        "tool_call_id": tool_call_id,
                        "tool_name": str(payload.get("tool_name") or current.get("tool_name") or ""),
                        "step": event.step,
                        "payload": dict(payload),
                    }
                )
                statuses = current.setdefault("statuses", [])
                statuses.append(str(payload.get("status") or ""))

        completed_tool_results: dict[str, dict[str, Any]] = {}
        failed_tool_results: dict[str, dict[str, Any]] = {}
        pending_tool_calls: list[dict[str, Any]] = []
        uncertain_actions: list[UncertainAction] = []

        for tool_call_id, tool_state in tool_events.items():
            statuses = tool_state.get("statuses", [])
            payload = dict(tool_state.get("payload") or {})
            tool_name = str(tool_state.get("tool_name") or "")
            if ToolLifecycleStatus.COMPLETED.value in statuses:
                completed_tool_results[tool_call_id] = payload
                continue
            if ToolLifecycleStatus.FAILED.value in statuses:
                failed_tool_results[tool_call_id] = payload
                continue
            if (
                ToolLifecycleStatus.REQUESTED.value in statuses
                and ToolLifecycleStatus.STARTED.value not in statuses
            ):
                pending_tool_calls.append(
                    {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "step": int(tool_state.get("step") or 0),
                        "payload": payload,
                    }
                )
                continue
            if ToolLifecycleStatus.STARTED.value in statuses:
                uncertain_actions.append(
                    UncertainAction(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        step=int(tool_state.get("step") or 0),
                        payload=payload,
                        replay_allowed=tool_name not in UNSAFE_UNCERTAIN_REPLAY_TOOLS,
                    )
                )

        loop_state = LoopState(
            messages=[
                {"role": message["role"], "content": message["content"]}
                for message in history_messages
            ],
            step=latest_step,
            turn_count=sum(1 for message in history_messages if message["role"] == "user"),
            tool_choice="auto",
            transition=latest_transition,
        )

        return ResumeState(
            session_id=self.store.session_id,
            run_id=str(run_id),
            history_messages=history_messages,
            loop_state=loop_state,
            checkpoint=checkpoint,
            terminal=terminal,
            pending_tool_calls=pending_tool_calls,
            uncertain_actions=uncertain_actions,
            completed_tool_results=completed_tool_results,
            failed_tool_results=failed_tool_results,
            runtime_state={},
        )


__all__ = [
    "ResumeLoader",
    "ResumeState",
    "SCHEMA_VERSION",
    "ToolLifecycleStatus",
    "TranscriptEvent",
    "TranscriptEventType",
    "TranscriptRecorder",
    "TranscriptStore",
    "UNSAFE_UNCERTAIN_REPLAY_TOOLS",
    "UncertainAction",
    "resolve_transcript_session_id",
]
