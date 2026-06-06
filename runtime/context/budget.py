"""Context budget estimation and compaction decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.config import Config
from runtime.history import Message


@dataclass(frozen=True)
class CompactDecision:
    should_compact: bool
    reason: str
    estimated_tokens: int
    threshold: int
    message_count: int


class ContextBudgetPolicy:
    """Decides when the active model context needs compaction."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()

    def estimate_tokens(self, messages: list[Message], pending_input: str = "") -> int:
        total_chars = len(pending_input or "")
        for msg in messages or []:
            total_chars += len(str(msg.content or ""))
            metadata = msg.metadata or {}
            if msg.role == "assistant" and metadata.get("tool_calls"):
                try:
                    total_chars += len(json.dumps(metadata["tool_calls"], ensure_ascii=False))
                except Exception:
                    total_chars += len(str(metadata["tool_calls"]))
            if msg.role == "tool" and metadata.get("tool_name"):
                total_chars += len(str(metadata["tool_name"]))
        return total_chars // 3

    def should_compact(
        self,
        *,
        messages: list[Message],
        pending_input: str = "",
        last_usage_tokens: int = 0,
    ) -> CompactDecision:
        message_count = len(messages or [])
        threshold = int(self.config.context_window * self.config.compression_threshold)
        estimated_from_messages = self.estimate_tokens(messages, pending_input)
        estimated_from_usage = int(last_usage_tokens or 0) + len(pending_input or "") // 3
        estimated = max(estimated_from_messages, estimated_from_usage)

        if message_count < 3:
            return CompactDecision(False, "messages_not_enough", estimated, threshold, message_count)
        if estimated < threshold:
            return CompactDecision(False, "below_threshold", estimated, threshold, message_count)
        return CompactDecision(True, "threshold_exceeded", estimated, threshold, message_count)
