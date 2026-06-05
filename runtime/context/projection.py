"""Read-time history projection."""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime.history import Message


@dataclass(frozen=True)
class ProjectionResult:
    messages: list[Message]
    source_message_count: int
    projection_mode: str = "full_history"
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ProjectionBuilder:
    """Builds the active history view without mutating the runtime log."""

    def project(self, source_messages: list[Message]) -> ProjectionResult:
        copied = list(source_messages or [])
        return ProjectionResult(
            messages=copied,
            source_message_count=len(source_messages or []),
            projection_mode="full_history",
            warnings=(),
        )
