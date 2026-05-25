from core.config import Config
from runtime.history import HistoryManager
from runtime.host import CodeAgent
from runtime.prompt_builder import ContextBuilder
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


class _DummyLLM:
    provider = "openai"
    model = "dummy-model"


def test_single_agent_boot_does_not_register_team_tools_by_default(tmp_path):
    config = Config()
    config.enable_agent_teams = False

    agent = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=config,
        enable_mcp=False,
        enable_skills=False,
        enable_tracing=False,
    )

    tools = agent.tool_registry.list_tools()
    assert "Task" not in tools
    assert "TeamCreate" not in tools
    assert agent.team_manager is None


def test_team_tool_modules_do_not_import_experimental_runtime_at_module_load():
    paths = [
        "tools/builtin/task.py",
        "tools/builtin/send_message.py",
        "tools/builtin/team_create.py",
        "tools/builtin/team_delete.py",
        "tools/builtin/team_status.py",
    ]

    for path in paths:
        top_level_experimental_imports = [
            line
            for line in open(path, encoding="utf-8").read().splitlines()
            if line.startswith("from experimental.teams") or line.startswith("import experimental.teams")
        ]
        assert top_level_experimental_imports == []
