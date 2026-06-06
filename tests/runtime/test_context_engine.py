import json

from runtime.context import ModelView


def test_model_view_tracks_counts_and_estimated_chars():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
    ]

    view = ModelView(
        messages=messages,
        system_message_count=1,
        history_message_count=1,
        source_message_count=1,
        estimated_chars=11,
        projection_mode="full_history",
    )

    assert view.messages == messages
    assert view.message_count == 2
    assert view.system_message_count == 1
    assert view.history_message_count == 1
    assert view.source_message_count == 1
    assert view.estimated_chars == 11
    assert view.projection_mode == "full_history"
    assert view.warnings == ()


from runtime.context import ProjectionBuilder
from runtime.history import HistoryManager


def test_projection_returns_copy_without_mutating_history():
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")

    before = history.get_messages()
    projected = ProjectionBuilder().project(before)

    assert projected.messages == before
    assert projected.messages is not before
    assert history.get_message_count() == 2
    assert projected.source_message_count == 2
    assert projected.projection_mode == "full_history"


def test_projection_warnings_default_to_empty_tuple():
    projected = ProjectionBuilder().project([])

    assert projected.messages == []
    assert projected.warnings == ()


from runtime.context import MessageNormalizer
from runtime.history import Message


def test_normalizer_serializes_tool_call_assistant_message():
    normalizer = MessageNormalizer()
    msg = Message(
        content="",
        role="assistant",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [
                {"id": "call_1", "name": "Read", "arguments": {"file_path": "a.py"}}
            ],
        },
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "arguments": json.dumps({"file_path": "a.py"}, ensure_ascii=False),
                    },
                }
            ],
        }
    ]


def test_normalizer_serializes_tool_result_with_call_id():
    normalizer = MessageNormalizer()
    msg = Message(
        content='{"status":"success"}',
        role="tool",
        metadata={"tool_name": "Read", "tool_call_id": "call_1"},
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"status":"success"}',
        }
    ]


def test_normalizer_falls_back_tool_without_call_id_to_user_observation():
    normalizer = MessageNormalizer()
    msg = Message(
        content='{"status":"success"}',
        role="tool",
        metadata={"tool_name": "Read"},
    )

    messages = normalizer.normalize([msg])

    assert messages == [
        {
            "role": "user",
            "content": 'Observation (Read): {"status":"success"}',
        }
    ]


def test_normalizer_converts_summary_to_system_message():
    normalizer = MessageNormalizer()
    msg = Message(content="old facts", role="summary")

    messages = normalizer.normalize([msg])

    assert messages == [{"role": "system", "content": "## Archived History Summary\nold facts"}]


from runtime.context import ContextEngine


class _FakeContextBuilder:
    def get_system_messages(self):
        return [{"role": "system", "content": "system prompt"}]


class _FakeTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))


def test_context_engine_builds_model_view_with_system_and_history():
    history = HistoryManager()
    history.append_user("hello")
    engine = ContextEngine(context_builder=_FakeContextBuilder())

    view = engine.build_model_view(history_manager=history, pending_input="hello", step=3)

    assert view.messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
    ]
    assert view.system_message_count == 1
    assert view.history_message_count == 1
    assert view.source_message_count == 1
    assert view.estimated_chars > 0


def test_context_engine_emits_model_view_build_trace():
    history = HistoryManager()
    history.append_user("hello")
    trace = _FakeTraceLogger()
    engine = ContextEngine(context_builder=_FakeContextBuilder())

    engine.build_model_view(
        history_manager=history,
        pending_input="hello",
        step=5,
        trace_logger=trace,
    )

    assert trace.events
    name, step, payload = trace.events[-1]
    assert name == "model_view_build"
    assert step == 5
    assert payload["system_message_count"] == 1
    assert payload["history_message_count"] == 1
    assert payload["source_message_count"] == 1
    assert payload["projection_mode"] == "full_history"


from core.config import Config


def test_context_engine_records_usage_and_decides_compaction():
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")
    history.append_user("q2")
    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.8),
    )

    engine.record_usage(810)

    assert engine.should_compact(history_manager=history, pending_input="more") is True
    assert engine.total_usage_tokens == 810


def test_context_engine_compact_if_needed_creates_checkpoint_and_preserves_history():
    history = HistoryManager()
    for idx in range(5):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    before = history.get_messages()
    trace = _FakeTraceLogger()
    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=2),
        summary_generator=lambda messages: f"summary({len(messages)})",
    )
    engine.record_usage(900)

    info = engine.compact_if_needed(
        history_manager=history,
        pending_input="more",
        step=7,
        trace_logger=trace,
    )
    view = engine.build_model_view(history_manager=history)

    assert info["compacted"] is True
    assert history.get_messages() == before
    assert view.projection_mode == "compact_checkpoint"
    assert view.messages[1]["role"] == "system"
    assert "Archived History Summary" in view.messages[1]["content"]
    assert any(event[0] == "context_compaction_completed" for event in trace.events)


def test_context_engine_does_not_repeat_compaction_for_unchanged_history():
    history = HistoryManager()
    for idx in range(5):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    summary_calls = []

    def generate_summary(messages):
        summary_calls.append(len(messages))
        return f"summary({len(messages)})"

    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=2),
        summary_generator=generate_summary,
    )
    engine.record_usage(900)

    first = engine.compact_if_needed(history_manager=history, pending_input="more")
    second = engine.compact_if_needed(history_manager=history, pending_input="more")

    assert first["compacted"] is True
    assert second == {
        "compacted": False,
        "reason": "checkpoint_current",
        "checkpoint_id": first["checkpoint_id"],
    }
    assert summary_calls == [6]


def test_context_engine_reset_clears_checkpoint_and_usage():
    history = HistoryManager()
    for idx in range(3):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    engine = ContextEngine(
        context_builder=_FakeContextBuilder(),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=1),
        summary_generator=lambda messages: "summary",
    )
    engine.record_usage(900)
    engine.compact_if_needed(history_manager=history, pending_input="more")

    engine.reset()

    assert engine.compact_store.active_checkpoint is None
    assert engine.last_usage_tokens == 0
    assert engine.total_usage_tokens == 0
