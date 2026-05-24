from runtime.context import ContextManager
from runtime.messages import HistoryManager
from runtime.prompt import ContextBuilder


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

