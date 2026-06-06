"""Model-facing context view types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelView:
    """The exact message view prepared for one model request."""

    messages: list[dict[str, Any]]
    system_message_count: int
    history_message_count: int
    source_message_count: int
    estimated_chars: int
    projection_mode: str = "full_history"
    compact_checkpoint_id: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def message_count(self) -> int:
        return len(self.messages)
