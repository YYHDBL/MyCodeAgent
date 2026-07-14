import json

from core.config import Config
from runtime.context import CompactStore, ContextCompactor, ProjectionBuilder, RoundSegmenter
from runtime.history import HistoryManager, Message



def test_round_segmenter_identifies_user_started_rounds():
    messages = [
        Message("old summary", "summary"),
        Message("q1", "user"),
        Message("a1", "assistant"),
        Message("q2", "user"),
        Message("a2", "assistant"),
    ]

    rounds = RoundSegmenter().identify(messages)

    assert [(r.start_idx, r.end_idx) for r in rounds] == [(1, 2), (3, 4)]


def test_round_segmenter_handles_consecutive_users():
    messages = [
        Message("q1", "user"),
        Message("q2", "user"),
        Message("a2", "assistant"),
    ]

    rounds = RoundSegmenter().identify(messages)

    assert [(r.start_idx, r.end_idx) for r in rounds] == [(0, 0), (1, 2)]


def _append_round(history: HistoryManager, idx: int):
    history.append_user(f"q{idx}")
    history.append_assistant(f"a{idx}")


def test_context_compactor_creates_checkpoint_without_mutating_history():
    history = HistoryManager(config=Config(min_retain_rounds=2))
    for idx in range(5):
        _append_round(history, idx)
    before = history.get_messages()

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=2),
        compact_store=store,
        summary_generator=lambda messages: f"summary({len(messages)})",
    )

    info = compactor.compact(history.get_messages())

    assert info["compacted"] is True
    assert history.get_messages() == before
    checkpoint = store.active_checkpoint
    assert checkpoint is not None
    assert checkpoint.summary == "summary(6)"
    assert checkpoint.retain_start_idx == 6


def test_context_compactor_skips_when_rounds_not_enough():
    history = HistoryManager(config=Config(min_retain_rounds=3))
    for idx in range(2):
        _append_round(history, idx)

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=3),
        compact_store=store,
        summary_generator=lambda messages: "summary",
    )

    info = compactor.compact(history.get_messages())

    assert info == {
        "compacted": False,
        "reason": "rounds_not_enough",
        "rounds_count": 2,
        "min_retain_rounds": 3,
    }
    assert store.active_checkpoint is None


def test_context_compactor_skips_when_summary_unavailable():
    history = HistoryManager(config=Config(min_retain_rounds=1))
    for idx in range(3):
        _append_round(history, idx)

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=1),
        compact_store=store,
        summary_generator=lambda messages: None,
    )

    info = compactor.compact(history.get_messages())

    assert info["compacted"] is False
    assert info["reason"] == "summary_unavailable"
    assert store.active_checkpoint is None


def test_projection_uses_active_compact_checkpoint_without_mutating_source():
    history = HistoryManager()
    for idx in range(4):
        _append_round(history, idx)
    source = history.get_messages()

    store = CompactStore()
    checkpoint = store.create_checkpoint(
        summary="summary text",
        source_message_count=len(source),
        retain_start_idx=4,
        messages_compacted=4,
    )

    projected = ProjectionBuilder(compact_store=store).project(source)

    assert history.get_messages() == source
    assert projected.projection_mode == "compact_checkpoint"
    assert projected.compact_checkpoint_id == checkpoint.id
    assert projected.messages[0].role == "summary"
    assert projected.messages[0].content == "summary text"
    assert projected.messages[1:] == source[4:]


def test_compact_projection_preserves_recent_tool_pairs():
    history = HistoryManager()
    for idx in range(6):
        history.append_user(f"Question {idx}")
        history.append_assistant(
            "",
            metadata={
                "action_type": "tool_call",
                "tool_calls": [
                    {"id": f"call_{idx}", "name": "Read", "arguments": {"path": "a.py"}}
                ],
            },
        )
        history.append_tool(
            "Read",
            json.dumps({"status": "success", "data": {"round": idx}}),
            metadata={"tool_call_id": f"call_{idx}"},
        )
        history.append_assistant(f"Answer {idx}")

    store = CompactStore()
    compactor = ContextCompactor(
        config=Config(min_retain_rounds=2),
        compact_store=store,
        summary_generator=lambda messages: f"summary({len(messages)})",
    )

    info = compactor.compact(history.get_messages())
    projected = ProjectionBuilder(store).project(history.get_messages())

    assert info["compacted"] is True
    assert history.get_rounds_count() == 6
    assert projected.messages[0].role == "summary"
    recent_tools = [message for message in projected.messages if message.role == "tool"]
    assert len(recent_tools) == 2
    assert [message.metadata["tool_call_id"] for message in recent_tools] == [
        "call_4",
        "call_5",
    ]
