"""Non-destructive context compaction."""

from __future__ import annotations

from typing import Any, Callable

from core.config import Config
from runtime.context.compact_store import CompactStore
from runtime.context.rounds import RoundSegmenter
from runtime.history import Message


class ContextCompactor:
    """Creates compact checkpoints while preserving full history."""

    def __init__(
        self,
        *,
        config: Config | None = None,
        compact_store: CompactStore | None = None,
        summary_generator: Callable[[list[Message]], str | None] | None = None,
        round_segmenter: RoundSegmenter | None = None,
    ):
        self.config = config or Config.from_env()
        self.compact_store = compact_store or CompactStore()
        self.summary_generator = summary_generator
        self.round_segmenter = round_segmenter or RoundSegmenter()

    def compact(self, messages: list[Message]) -> dict[str, Any]:
        source_messages = list(messages or [])
        rounds = self.round_segmenter.identify(source_messages)
        min_rounds = self.config.min_retain_rounds
        if len(rounds) <= min_rounds:
            return {
                "compacted": False,
                "reason": "rounds_not_enough",
                "rounds_count": len(rounds),
                "min_retain_rounds": min_rounds,
            }

        retain_start_round = len(rounds) - min_rounds
        retain_start_idx = rounds[retain_start_round].start_idx
        messages_to_compact = source_messages[:retain_start_idx]
        if not messages_to_compact:
            return {"compacted": False, "reason": "no_messages_to_compact"}

        if not self.summary_generator:
            return {"compacted": False, "reason": "summary_unavailable"}

        try:
            summary = self.summary_generator(messages_to_compact)
        except Exception:
            summary = None

        if summary is None:
            return {"compacted": False, "reason": "summary_unavailable"}

        checkpoint = self.compact_store.create_checkpoint(
            summary=summary,
            source_message_count=len(source_messages),
            retain_start_idx=retain_start_idx,
            messages_compacted=len(messages_to_compact),
            metadata={
                "rounds_count": len(rounds),
                "min_retain_rounds": min_rounds,
                "retain_start_round": retain_start_round,
            },
        )
        return {
            "compacted": True,
            "checkpoint_id": checkpoint.id,
            "messages_before": len(source_messages),
            "messages_compacted": len(messages_to_compact),
            "retain_start_idx": retain_start_idx,
            "summary_generated": True,
            "summary_len": len(summary),
        }
