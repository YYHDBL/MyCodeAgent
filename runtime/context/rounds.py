"""Conversation round segmentation for context planning."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.history import Message


@dataclass(frozen=True)
class HistoryRound:
    start_idx: int
    end_idx: int


class RoundSegmenter:
    """Identifies rounds that start at user messages."""

    def identify(self, messages: list[Message]) -> list[HistoryRound]:
        rounds: list[HistoryRound] = []
        current_start: int | None = None
        for idx, msg in enumerate(messages or []):
            if msg.role == "user":
                if current_start is not None:
                    rounds.append(HistoryRound(current_start, idx - 1))
                current_start = idx
        if current_start is not None:
            rounds.append(HistoryRound(current_start, len(messages) - 1))
        return rounds
