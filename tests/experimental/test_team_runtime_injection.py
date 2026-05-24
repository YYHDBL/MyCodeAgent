from core.config import Config
from core.context_engine.context_builder import ContextBuilder
from core.context_engine.history_manager import HistoryManager
from tools.registry import ToolRegistry


def test_runtime_notifications_injected_as_system_blocks(tmp_path):
    builder = ContextBuilder(tool_registry=ToolRegistry(), project_root=str(tmp_path), system_prompt_override="base")
    builder.set_runtime_system_blocks(["[Team Runtime]\n- msg-1"])
    messages = builder.build_messages([{"role": "user", "content": "hello"}])

    system_blocks = [m for m in messages if m.get("role") == "system"]
    assert any("[Team Runtime]" in m.get("content", "") for m in system_blocks)
    assert messages[-1]["role"] == "user"


def test_runtime_notifications_do_not_create_user_rounds():
    hm = HistoryManager(config=Config())
    hm.append_user("u1")
    hm.append_assistant("a1")
    before = hm.get_rounds_count()

    builder = ContextBuilder(tool_registry=ToolRegistry(), project_root=".", system_prompt_override="base")
    builder.set_runtime_system_blocks(["[Team Runtime]\n- ack"])
    _ = builder.build_messages(hm.to_messages())

    after = hm.get_rounds_count()
    assert before == after
