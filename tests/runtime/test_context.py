from runtime.context_provider import ContextManager
from runtime.history import HistoryManager
from runtime.prompt import ContextBuilder
from runtime.session import build_session_snapshot


def test_target_runtime_modules_expose_context_services():
    from runtime.host import CodeAgent
    from runtime.input_preprocess import preprocess_input
    from runtime.observation_store import truncate_observation
    from runtime.summary import create_summary_generator

    assert CodeAgent.__name__ == "CodeAgent"
    assert callable(preprocess_input)
    assert callable(create_summary_generator)
    assert callable(truncate_observation)


class _DummyToolRegistry:
    def get_disabled_tools(self):
        return []


def test_context_manager_builds_messages_from_preprocessed_history(tmp_path):
    prompts_dir = tmp_path / "prompts" / "agents_prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "L1_system_prompt.py").write_text('system_prompt = "base system"', encoding="utf-8")

    history = HistoryManager()
    builder = ContextBuilder(tool_registry=_DummyToolRegistry(), project_root=str(tmp_path))
    manager = ContextManager(history_manager=history, prompt_builder=builder)

    processed = manager.preprocess_input("check @src/main.py")
    history.append_user(processed.processed_input)

    messages = manager.build_messages()

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
    messages = builder.build_messages(history.to_messages())
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
