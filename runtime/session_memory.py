"""Session memory derived deterministically from transcript events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from runtime.transcript import TranscriptEvent


SESSION_MEMORY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TranscriptEventRange:
    start_event_id: str | None = None
    end_event_id: str | None = None
    start_step: int = 0
    end_step: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_event_id": self.start_event_id,
            "end_event_id": self.end_event_id,
            "start_step": self.start_step,
            "end_step": self.end_step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TranscriptEventRange":
        payload = data or {}
        return cls(
            start_event_id=payload.get("start_event_id"),
            end_event_id=payload.get("end_event_id"),
            start_step=int(payload.get("start_step") or 0),
            end_step=int(payload.get("end_step") or 0),
        )


@dataclass(frozen=True)
class SessionMemoryItem:
    text: str
    source: TranscriptEventRange

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMemoryItem":
        return cls(
            text=str(data.get("text") or ""),
            source=TranscriptEventRange.from_dict(data.get("source")),
        )


@dataclass(frozen=True)
class SessionMemory:
    schema_version: int = SESSION_MEMORY_SCHEMA_VERSION
    current_goal: SessionMemoryItem | None = None
    completed_work: tuple[SessionMemoryItem, ...] = ()
    key_decisions: tuple[SessionMemoryItem, ...] = ()
    failed_attempts: tuple[SessionMemoryItem, ...] = ()
    todo_items: tuple[SessionMemoryItem, ...] = ()
    verification_status: tuple[SessionMemoryItem, ...] = ()
    source: TranscriptEventRange = field(default_factory=TranscriptEventRange)
    version: int = 1
    event_count: int = 0
    last_event_id: str | None = None
    runtime_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "current_goal": self.current_goal.to_dict() if self.current_goal else None,
            "completed_work": [item.to_dict() for item in self.completed_work],
            "key_decisions": [item.to_dict() for item in self.key_decisions],
            "failed_attempts": [item.to_dict() for item in self.failed_attempts],
            "todo_items": [item.to_dict() for item in self.todo_items],
            "verification_status": [item.to_dict() for item in self.verification_status],
            "source": self.source.to_dict(),
            "version": self.version,
            "event_count": self.event_count,
            "last_event_id": self.last_event_id,
            "runtime_state": self.runtime_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMemory":
        return cls(
            schema_version=int(data.get("schema_version") or SESSION_MEMORY_SCHEMA_VERSION),
            current_goal=(
                SessionMemoryItem.from_dict(data["current_goal"])
                if data.get("current_goal")
                else None
            ),
            completed_work=tuple(SessionMemoryItem.from_dict(item) for item in data.get("completed_work") or []),
            key_decisions=tuple(SessionMemoryItem.from_dict(item) for item in data.get("key_decisions") or []),
            failed_attempts=tuple(SessionMemoryItem.from_dict(item) for item in data.get("failed_attempts") or []),
            todo_items=tuple(SessionMemoryItem.from_dict(item) for item in data.get("todo_items") or []),
            verification_status=tuple(
                SessionMemoryItem.from_dict(item) for item in data.get("verification_status") or []
            ),
            source=TranscriptEventRange.from_dict(data.get("source")),
            version=int(data.get("version") or 1),
            event_count=int(data.get("event_count") or 0),
            last_event_id=data.get("last_event_id"),
            runtime_state=dict(data.get("runtime_state") or {}),
        )


class SessionMemoryDeriver:
    """Derive bounded working memory from transcript events."""

    def rebuild(self, events: Iterable["TranscriptEvent"]) -> SessionMemory:
        ordered = list(events)
        if not ordered:
            return SessionMemory()

        current_goal: SessionMemoryItem | None = None
        completed_work: list[SessionMemoryItem] = []
        key_decisions: list[SessionMemoryItem] = []
        failed_attempts: list[SessionMemoryItem] = []
        verification_status: list[SessionMemoryItem] = []
        tool_states: dict[str, dict[str, Any]] = {}

        for event in ordered:
            payload = dict(event.payload or {})
            source = TranscriptEventRange(
                start_event_id=event.event_id,
                end_event_id=event.event_id,
                start_step=event.step,
                end_step=event.step,
            )
            event_type = str(getattr(event.event_type, "value", event.event_type))

            if event_type == "message":
                role = str(payload.get("role") or "")
                metadata = dict(payload.get("metadata") or {})
                if role == "user" and metadata.get("source") != "completion_gate":
                    current_goal = SessionMemoryItem(text=str(payload.get("content") or "").strip(), source=source)
                elif role == "assistant":
                    action_type = str(metadata.get("action_type") or "")
                    content = str(payload.get("content") or "").strip()
                    if action_type in {"final", "final_unverified"} and content:
                        completed_work.append(
                            SessionMemoryItem(
                                text=f"Assistant produced final response: {content}",
                                source=source,
                            )
                        )
            elif event_type == "state_transition":
                reason = str(payload.get("reason") or "")
                details = dict(payload.get("details") or {})
                if reason == "context_compacted":
                    checkpoint_id = details.get("checkpoint_id") or "unknown"
                    key_decisions.append(
                        SessionMemoryItem(text=f"Created compact checkpoint {checkpoint_id}", source=source)
                    )
                elif reason == "stop_hook_blocking":
                    verification_status.append(
                        SessionMemoryItem(
                            text="Completion gate blocked finalization pending verification.",
                            source=source,
                        )
                    )
                elif reason == "model_recovery_failed":
                    failed_attempts.append(
                        SessionMemoryItem(
                            text="Model recovery failed and required terminal fallback.",
                            source=source,
                        )
                    )
            elif event_type == "checkpoint":
                checkpoint_id = str(payload.get("checkpoint_id") or "unknown")
                key_decisions.append(
                    SessionMemoryItem(text=f"Recorded checkpoint {checkpoint_id}", source=source)
                )
            elif event_type == "terminal":
                reason = str(payload.get("reason") or "")
                if reason:
                    verification_status.append(
                        SessionMemoryItem(text=f"Run ended with terminal reason {reason}.", source=source)
                    )
            elif event_type == "tool_lifecycle":
                tool_call_id = str(payload.get("tool_call_id") or "")
                if not tool_call_id:
                    continue
                tool_name = str(payload.get("tool_name") or "unknown")
                status = str(payload.get("status") or "")
                current = tool_states.setdefault(
                    tool_call_id,
                    {
                        "tool_name": tool_name,
                        "requested": None,
                        "started": None,
                        "completed": None,
                        "failed": None,
                    },
                )
                current["tool_name"] = tool_name
                current[status] = {
                    "event_id": event.event_id,
                    "step": event.step,
                }
                if status == "completed":
                    completed_work.append(
                        SessionMemoryItem(text=f"Completed tool {tool_name} ({tool_call_id}).", source=source)
                    )
                elif status == "failed":
                    failed_attempts.append(
                        SessionMemoryItem(text=f"Failed tool {tool_name} ({tool_call_id}).", source=source)
                    )

        todo_items, unresolved_verification = self._build_unresolved_items(tool_states)
        first = ordered[0]
        last = ordered[-1]
        return SessionMemory(
            current_goal=current_goal,
            completed_work=tuple(completed_work),
            key_decisions=tuple(key_decisions),
            failed_attempts=tuple(failed_attempts),
            todo_items=tuple(todo_items),
            verification_status=tuple([*verification_status, *unresolved_verification]),
            source=TranscriptEventRange(
                start_event_id=first.event_id,
                end_event_id=last.event_id,
                start_step=first.step,
                end_step=last.step,
            ),
            version=len(ordered),
            event_count=len(ordered),
            last_event_id=last.event_id,
            runtime_state={"tool_states": tool_states},
        )

    def update(
        self,
        previous: SessionMemory | None,
        events: Iterable["TranscriptEvent"],
        *,
        summary_refiner: Callable[[SessionMemory, SessionMemory | None, list["TranscriptEvent"]], SessionMemory] | None = None,
    ) -> SessionMemory:
        event_list = list(events)
        if not event_list:
            return previous or SessionMemory()

        if previous is None:
            draft = self.rebuild(event_list)
        else:
            draft = self._apply_incremental(previous, event_list)

        draft = SessionMemory(
            schema_version=draft.schema_version,
            current_goal=draft.current_goal,
            completed_work=draft.completed_work,
            key_decisions=draft.key_decisions,
            failed_attempts=draft.failed_attempts,
            todo_items=draft.todo_items,
            verification_status=draft.verification_status,
            source=draft.source,
            version=(previous.version + 1) if previous is not None else draft.version,
            event_count=draft.event_count,
            last_event_id=draft.last_event_id,
            runtime_state=draft.runtime_state,
        )
        if summary_refiner is None:
            return draft
        try:
            return summary_refiner(draft, previous, event_list)
        except Exception:
            return previous if previous is not None else draft

    def _apply_incremental(self, previous: SessionMemory, new_events: list["TranscriptEvent"]) -> SessionMemory:
        current_goal = previous.current_goal
        completed_work = list(previous.completed_work)
        key_decisions = list(previous.key_decisions)
        failed_attempts = list(previous.failed_attempts)
        verification_status = [
            item for item in previous.verification_status if "uncertain tool action" not in item.text.lower()
        ]
        tool_states = dict(previous.runtime_state.get("tool_states") or {})

        for event in new_events:
            payload = dict(event.payload or {})
            source = TranscriptEventRange(
                start_event_id=event.event_id,
                end_event_id=event.event_id,
                start_step=event.step,
                end_step=event.step,
            )
            event_type = str(getattr(event.event_type, "value", event.event_type))

            if event_type == "message":
                role = str(payload.get("role") or "")
                metadata = dict(payload.get("metadata") or {})
                if role == "user" and metadata.get("source") != "completion_gate":
                    current_goal = SessionMemoryItem(text=str(payload.get("content") or "").strip(), source=source)
                elif role == "assistant":
                    action_type = str(metadata.get("action_type") or "")
                    content = str(payload.get("content") or "").strip()
                    if action_type in {"final", "final_unverified"} and content:
                        completed_work.append(
                            SessionMemoryItem(
                                text=f"Assistant produced final response: {content}",
                                source=source,
                            )
                        )
            elif event_type == "state_transition":
                reason = str(payload.get("reason") or "")
                details = dict(payload.get("details") or {})
                if reason == "context_compacted":
                    checkpoint_id = details.get("checkpoint_id") or "unknown"
                    key_decisions.append(
                        SessionMemoryItem(text=f"Created compact checkpoint {checkpoint_id}", source=source)
                    )
                elif reason == "stop_hook_blocking":
                    verification_status.append(
                        SessionMemoryItem(
                            text="Completion gate blocked finalization pending verification.",
                            source=source,
                        )
                    )
                elif reason == "model_recovery_failed":
                    failed_attempts.append(
                        SessionMemoryItem(
                            text="Model recovery failed and required terminal fallback.",
                            source=source,
                        )
                    )
            elif event_type == "checkpoint":
                checkpoint_id = str(payload.get("checkpoint_id") or "unknown")
                key_decisions.append(
                    SessionMemoryItem(text=f"Recorded checkpoint {checkpoint_id}", source=source)
                )
            elif event_type == "terminal":
                reason = str(payload.get("reason") or "")
                if reason:
                    verification_status.append(
                        SessionMemoryItem(text=f"Run ended with terminal reason {reason}.", source=source)
                    )
            elif event_type == "tool_lifecycle":
                tool_call_id = str(payload.get("tool_call_id") or "")
                if not tool_call_id:
                    continue
                tool_name = str(payload.get("tool_name") or "unknown")
                status = str(payload.get("status") or "")
                current = tool_states.setdefault(
                    tool_call_id,
                    {
                        "tool_name": tool_name,
                        "requested": None,
                        "started": None,
                        "completed": None,
                        "failed": None,
                    },
                )
                current["tool_name"] = tool_name
                current[status] = {"event_id": event.event_id, "step": event.step}
                if status == "completed":
                    completed_work.append(
                        SessionMemoryItem(text=f"Completed tool {tool_name} ({tool_call_id}).", source=source)
                    )
                elif status == "failed":
                    failed_attempts.append(
                        SessionMemoryItem(text=f"Failed tool {tool_name} ({tool_call_id}).", source=source)
                    )

        todo_items, unresolved_verification = self._build_unresolved_items(tool_states)
        last = new_events[-1]
        return SessionMemory(
            current_goal=current_goal,
            completed_work=tuple(completed_work),
            key_decisions=tuple(key_decisions),
            failed_attempts=tuple(failed_attempts),
            todo_items=tuple(todo_items),
            verification_status=tuple([*verification_status, *unresolved_verification]),
            source=TranscriptEventRange(
                start_event_id=previous.source.start_event_id or new_events[0].event_id,
                end_event_id=last.event_id,
                start_step=previous.source.start_step if previous.event_count else new_events[0].step,
                end_step=last.step,
            ),
            event_count=previous.event_count + len(new_events),
            last_event_id=last.event_id,
            runtime_state={"tool_states": tool_states},
        )

    def _build_unresolved_items(
        self,
        tool_states: dict[str, dict[str, Any]],
    ) -> tuple[list[SessionMemoryItem], list[SessionMemoryItem]]:
        todo_items: list[SessionMemoryItem] = []
        verification_status: list[SessionMemoryItem] = []
        for tool_call_id, tool_state in sorted(tool_states.items()):
            tool_name = str(tool_state.get("tool_name") or "unknown")
            started = tool_state.get("started")
            completed = tool_state.get("completed")
            failed = tool_state.get("failed")
            requested = tool_state.get("requested")
            if started is not None and completed is None and failed is None:
                source = TranscriptEventRange(
                    start_event_id=(requested or started).get("event_id"),
                    end_event_id=started.get("event_id"),
                    start_step=int((requested or started).get("step") or 0),
                    end_step=int(started.get("step") or 0),
                )
                todo_items.append(
                    SessionMemoryItem(
                        text=f"Resolve uncertain action for {tool_name} ({tool_call_id}) before claiming completion.",
                        source=source,
                    )
                )
                verification_status.append(
                    SessionMemoryItem(
                        text=f"Uncertain tool action detected for {tool_name} ({tool_call_id}).",
                        source=source,
                    )
                )
            elif requested is not None and started is None and completed is None and failed is None:
                source = TranscriptEventRange(
                    start_event_id=requested.get("event_id"),
                    end_event_id=requested.get("event_id"),
                    start_step=int(requested.get("step") or 0),
                    end_step=int(requested.get("step") or 0),
                )
                todo_items.append(
                    SessionMemoryItem(
                        text=f"Replan pending tool call {tool_name} ({tool_call_id}).",
                        source=source,
                    )
                )
        return todo_items, verification_status


def render_session_memory(memory: SessionMemory, *, char_budget: int) -> tuple[str, int]:
    if memory.current_goal is None and not any(
        (
            memory.completed_work,
            memory.key_decisions,
            memory.failed_attempts,
            memory.todo_items,
            memory.verification_status,
        )
    ):
        return "", 0

    sections = [
        "## Session Memory",
        f"Source: transcript events {memory.source.start_event_id or 'unknown'}..{memory.source.end_event_id or 'unknown'}",
    ]
    if memory.current_goal is not None:
        sections.append(f"Current Goal: {memory.current_goal.text}")

    def _append_group(title: str, items: tuple[SessionMemoryItem, ...]) -> None:
        if not items:
            return
        sections.append(f"{title}:")
        for item in items:
            sections.append(f"- {item.text}")

    _append_group("Todo", memory.todo_items)
    _append_group("Verification", memory.verification_status)
    _append_group("Key Decisions", memory.key_decisions)
    _append_group("Failed Attempts", memory.failed_attempts)
    _append_group("Completed Work", memory.completed_work)

    text = "\n".join(sections)
    if len(text) <= char_budget:
        return text, len(text)
    truncated = text[: max(0, char_budget - len("\n[truncated]"))].rstrip() + "\n[truncated]"
    return truncated, len(truncated)


__all__ = [
    "SESSION_MEMORY_SCHEMA_VERSION",
    "SessionMemory",
    "SessionMemoryDeriver",
    "SessionMemoryManager",
    "SessionMemoryItem",
    "TranscriptEventRange",
    "render_session_memory",
]


class SessionMemoryManager:
    """Owns the current session memory and keeps it in sync with transcript events."""

    def __init__(
        self,
        *,
        deriver: SessionMemoryDeriver | None = None,
        summary_refiner: Callable[[SessionMemory, SessionMemory | None, list["TranscriptEvent"]], SessionMemory] | None = None,
        on_update: Callable[[SessionMemory], None] | None = None,
    ):
        self.deriver = deriver or SessionMemoryDeriver()
        self.summary_refiner = summary_refiner
        self.on_update = on_update
        self.memory = SessionMemory()

    def ingest_event(self, event: "TranscriptEvent") -> SessionMemory:
        previous = self.memory if self.memory.event_count > 0 else None
        self.memory = self.deriver.update(
            previous,
            [event],
            summary_refiner=self.summary_refiner,
        )
        if self.on_update is not None:
            self.on_update(self.memory)
        return self.memory

    def rebuild(self, events: Iterable["TranscriptEvent"]) -> SessionMemory:
        self.memory = self.deriver.rebuild(events)
        if self.on_update is not None:
            self.on_update(self.memory)
        return self.memory
