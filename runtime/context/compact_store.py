"""Compact checkpoint storage for read-time context projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class CompactCheckpoint:
    id: str
    summary: str
    source_message_count: int
    retain_start_idx: int
    messages_compacted: int
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CompactStore:
    """Stores the active compact checkpoint without editing history."""

    def __init__(self):
        self._active_checkpoint: CompactCheckpoint | None = None

    @property
    def active_checkpoint(self) -> CompactCheckpoint | None:
        return self._active_checkpoint

    def set_active(self, checkpoint: CompactCheckpoint) -> None:
        self._active_checkpoint = checkpoint

    def clear(self) -> None:
        self._active_checkpoint = None

    def create_checkpoint(
        self,
        *,
        summary: str,
        source_message_count: int,
        retain_start_idx: int,
        messages_compacted: int,
        metadata: dict[str, Any] | None = None,
    ) -> CompactCheckpoint:
        checkpoint = CompactCheckpoint(
            id=f"compact_{uuid.uuid4().hex}",
            summary=summary,
            source_message_count=source_message_count,
            retain_start_idx=retain_start_idx,
            messages_compacted=messages_compacted,
            created_at=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        self.set_active(checkpoint)
        return checkpoint
