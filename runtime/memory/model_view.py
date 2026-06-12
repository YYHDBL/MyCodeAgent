"""Render long-term memory snapshots for model-view injection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedLongTermMemory:
    text: str
    chars: int
    target_count: int


def render_long_term_memory_state(state) -> str:
    if not state.entries:
        return ""
    return "\n".join(
        [
            f"## Long-term Memory: {state.target}",
            f"Source: {state.path}",
            f"Usage: {state.usage.chars}/{state.usage.limit} chars across {state.usage.entry_count} entries",
            state.rendered_entries,
        ]
    )


def render_long_term_memory(snapshot) -> RenderedLongTermMemory:
    blocks: list[str] = []
    target_count = 0

    for state in (snapshot.user, snapshot.memory):
        if not state.entries:
            continue
        target_count += 1
        blocks.append(render_long_term_memory_state(state))

    text = "\n\n".join(blocks).strip()
    return RenderedLongTermMemory(
        text=text,
        chars=len(text),
        target_count=target_count,
    )


__all__ = [
    "RenderedLongTermMemory",
    "render_long_term_memory",
    "render_long_term_memory_state",
]
