from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.prompt_builder import ContextBuilder
import json


def test_target_runtime_modules_expose_context_services():
    from runtime.context import ContextEngine
    from runtime.host import CodeAgent
    from runtime.input_preprocess import preprocess_input
    from tools.observation_store import truncate_result
    from runtime.summary import create_summary_generator

    assert CodeAgent.__name__ == "CodeAgent"
    assert ContextEngine.__name__ == "ContextEngine"
    assert callable(preprocess_input)
    assert callable(create_summary_generator)
    assert callable(truncate_result)


class _DummyToolRegistry:
    def get_disabled_tools(self):
        return []


def test_context_engine_builds_messages_from_preprocessed_history(tmp_path):
    prompts_dir = tmp_path / "prompts" / "agents_prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "L1_system_prompt.py").write_text('system_prompt = "base system"', encoding="utf-8")

    from runtime.input_preprocess import preprocess_input

    history = HistoryManager()
    builder = ContextBuilder(tool_registry=_DummyToolRegistry(), project_root=str(tmp_path))
    engine = ContextEngine(builder)

    processed = preprocess_input("check @src/main.py")
    history.append_user(processed.processed_input)

    view = engine.build_model_view(history_manager=history)
    messages = view.messages

    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "@src/main.py" in messages[-1]["content"]


def test_history_prompt_context_remains_transcript_compatible(tmp_path):
    history = HistoryManager()
    history.append_user("hello")
    history.append_assistant("hi")

    builder = ContextBuilder(
        tool_registry=_DummyToolRegistry(),
        project_root=str(tmp_path),
        system_prompt_override="base system",
    )
    messages = ContextEngine(builder).build_model_view(history_manager=history).messages

    assert messages[0] == {"role": "system", "content": "base system"}
    assert messages[-1]["role"] == "assistant"


def test_system_messages_are_always_derived_from_context_builder():
    from runtime.host import CodeAgent

    agent = CodeAgent.__new__(CodeAgent)
    agent.context_builder = type(
        "Builder", (), {"get_system_messages": lambda self: [{"role": "system", "content": "canonical"}]}
    )()

    assert CodeAgent._get_system_messages_for_run(agent) == [
        {"role": "system", "content": "canonical"}
    ]


def test_clear_history_resets_context_runtime():
    from core.config import Config
    from runtime.host import CodeAgent

    history = HistoryManager()
    for idx in range(3):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    engine = ContextEngine(
        ContextBuilder(
            tool_registry=_DummyToolRegistry(),
            project_root=".",
            system_prompt_override="system",
        ),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=1),
        summary_generator=lambda messages: "summary",
    )
    engine.record_usage(900)
    engine.compact_if_needed(history_manager=history, pending_input="more")

    agent = CodeAgent.__new__(CodeAgent)
    agent.history_manager = history
    agent.context_engine = engine

    agent.clear_history()

    assert history.get_messages() == []
    assert engine.compact_store.active_checkpoint is None
    assert engine.last_usage_tokens == 0


def test_load_transcript_resets_previous_context_runtime(tmp_path):
    from core.config import Config
    from runtime.host import CodeAgent

    class _ToolRegistry:
        def import_read_cache(self, cache):
            self.cache = cache

    history = HistoryManager()
    for idx in range(3):
        history.append_user(f"q{idx}")
        history.append_assistant(f"a{idx}")
    engine = ContextEngine(
        ContextBuilder(
            tool_registry=_DummyToolRegistry(),
            project_root=".",
            system_prompt_override="system",
        ),
        config=Config(context_window=1000, compression_threshold=0.1, min_retain_rounds=1),
        summary_generator=lambda messages: "summary",
    )
    engine.record_usage(900)
    engine.compact_if_needed(history_manager=history, pending_input="more")

    from runtime.transcript import TranscriptStore

    transcript = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    transcript.append_message(run_id="run-1", step=0, role="user", content="restored")
    agent = CodeAgent.__new__(CodeAgent)
    agent.history_manager = history
    agent.context_engine = engine
    agent.tool_registry = _ToolRegistry()
    agent.transcript_store = transcript
    agent.session_memory_manager = type("Memory", (), {"memory": None, "ingest_event": lambda self, event: None})()
    agent._run_id = 0

    agent.load_transcript(str(transcript.path))

    assert [message.content for message in history.get_messages()] == ["restored"]
    assert engine.compact_store.active_checkpoint is None
    assert engine.last_usage_tokens == 0


def test_legacy_snapshot_import_does_not_create_a_compact_model_summary(tmp_path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    snapshot = tmp_path / "session-latest.json"
    snapshot.write_text(
        json.dumps(
            {"history_messages": [{"role": "user", "content": "restore me", "metadata": {}}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = TranscriptStore(tmp_path / "transcript.jsonl", session_id="session-1")
    assert store.import_legacy_snapshot(snapshot)
    history = HistoryManager()
    engine = ContextEngine(
        ContextBuilder(
            tool_registry=_DummyToolRegistry(),
            project_root=str(tmp_path),
            system_prompt_override="system",
        )
    )
    host = type("Host", (), {"history_manager": history, "context_engine": engine, "tool_registry": None})()

    ResumeLoader(store).load_session().apply_to_host(host)
    view = engine.build_model_view(history_manager=history)

    assert engine.compact_store.active_checkpoint is None
    assert all(message["role"] != "summary" for message in view.messages)
    assert view.messages[-1] == {"role": "user", "content": "restore me"}
