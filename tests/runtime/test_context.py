from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.prompt_builder import ContextBuilder
from runtime.session import build_session_snapshot


def test_target_runtime_modules_expose_context_services():
    from runtime.context import ContextEngine
    from runtime.host import CodeAgent
    from runtime.input_preprocess import preprocess_input
    from runtime.observation_store import truncate_observation
    from runtime.summary import create_summary_generator

    assert CodeAgent.__name__ == "CodeAgent"
    assert ContextEngine.__name__ == "ContextEngine"
    assert callable(preprocess_input)
    assert callable(create_summary_generator)
    assert callable(truncate_observation)


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


def test_history_prompt_context_and_session_snapshot_remain_integrated(tmp_path):
    history = HistoryManager()
    history.append_user("hello")
    history.append_assistant("hi")

    builder = ContextBuilder(
        tool_registry=_DummyToolRegistry(),
        project_root=str(tmp_path),
        system_prompt_override="base system",
    )
    messages = ContextEngine(builder).build_model_view(history_manager=history).messages
    snapshot = build_session_snapshot(
        system_messages=builder.get_system_messages(),
        history_messages=history.serialize_messages(),
        tool_schema=[],
        project_root=str(tmp_path),
    )

    assert messages[0] == {"role": "system", "content": "base system"}
    assert messages[-1]["role"] == "assistant"
    assert snapshot["history_messages"][0]["content"] == "hello"
    assert snapshot["project_root"] == str(tmp_path)


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


def test_load_session_resets_previous_context_runtime(monkeypatch):
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

    monkeypatch.setattr(
        "runtime.host.load_session_snapshot",
        lambda path: {
            "system_messages": [],
            "history_messages": [{"role": "user", "content": "restored", "metadata": {}}],
            "read_cache": {},
        },
    )
    agent = CodeAgent.__new__(CodeAgent)
    agent.history_manager = history
    agent.context_engine = engine
    agent.tool_registry = _ToolRegistry()
    agent.team_manager = None
    agent._system_messages_override = []

    agent.load_session("session.json")

    assert [message.content for message in history.get_messages()] == ["restored"]
    assert engine.compact_store.active_checkpoint is None
    assert engine.last_usage_tokens == 0
