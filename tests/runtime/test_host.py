from runtime.host import CodeAgent
from core.config import Config
from runtime.context import ContextEngine
from runtime.memory import LongTermMemoryStore
from runtime.prompt_builder import ContextBuilder
from tools.registry import ToolRegistry


class _Function:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, function, call_id="call_1"):
        self.function = function
        self.id = call_id


class _Message:
    def __init__(self, tool_calls=None, function_call=None):
        self.tool_calls = tool_calls
        self.function_call = function_call


class _Choice:
    def __init__(self, message):
        self.message = message


class _Response:
    def __init__(self, message):
        self.choices = [_Choice(message)]


def test_extract_tool_calls_from_modern_response():
    response = _Response(
        _Message(
            tool_calls=[
                _ToolCall(
                    _Function(name="Read", arguments='{"path": "a.py"}'),
                    call_id="call_1",
                )
            ]
        )
    )

    assert CodeAgent._extract_tool_calls(response) == [
        {"id": "call_1", "name": "Read", "arguments": '{"path": "a.py"}'}
    ]


def test_extract_tool_calls_from_legacy_function_call():
    response = _Response(
        _Message(function_call=_Function(name="Search", arguments='{"query": "test"}'))
    )

    assert CodeAgent._extract_tool_calls(response) == [
        {"id": None, "name": "Search", "arguments": '{"query": "test"}'}
    ]


class _DummyLLM:
    provider = "openai"
    model = "dummy-model"


def test_codeagent_frozen_long_term_snapshot_stays_stable_until_refresh(tmp_path):
    agent = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(long_term_memory_enabled=True),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )

    assert agent.context_engine.long_term_memory_snapshot is not None
    assert agent.context_engine.long_term_memory_snapshot.memory.entries == ()

    agent.long_term_memory_store.add("memory", "Stable project fact.")

    assert agent.context_engine.long_term_memory_snapshot.memory.entries == ()
    refreshed = agent.refresh_long_term_memory_snapshot()
    assert refreshed is not None
    assert agent.context_engine.long_term_memory_snapshot.memory.entries == ("Stable project fact.",)


def test_new_codeagent_loads_latest_long_term_memory_from_disk(tmp_path):
    first = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(long_term_memory_enabled=True),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )
    first.long_term_memory_store.add("user", "User prefers direct answers.")

    second = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(long_term_memory_enabled=True),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )

    assert second.context_engine.long_term_memory_snapshot is not None
    assert second.context_engine.long_term_memory_snapshot.user.entries == (
        "User prefers direct answers.",
    )


def test_long_term_memory_does_not_change_stable_prompt_fingerprint(tmp_path):
    store = LongTermMemoryStore(project_root=tmp_path)
    store.add("memory", "Stable project fact.")
    snapshot = store.load()
    builder = ContextBuilder(
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        system_prompt_override="base system",
    )
    engine = ContextEngine(builder)
    before = builder.get_prompt_assembly()

    engine.set_long_term_memory_snapshot(snapshot)
    after = builder.get_prompt_assembly()

    assert before.system_fingerprint == after.system_fingerprint
    assert before.runtime_signals_fingerprint == after.runtime_signals_fingerprint


def test_codeagent_traces_long_term_memory_loaded_without_leaking_entries(tmp_path, monkeypatch):
    class _Trace:
        enabled = True
        session_id = "trace-session"

        def __init__(self):
            self.events = []

        def log_event(self, name, payload, step=0):
            self.events.append((name, step, payload))

        def log_system_messages(self, messages):
            return None

        def finalize(self):
            return None

    trace = _Trace()
    monkeypatch.setattr("runtime.host.create_trace_logger", lambda: trace)

    memory_dir = tmp_path / "memory" / "long_term"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "MEMORY.md").write_text("Stable project fact.", encoding="utf-8")

    CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(long_term_memory_enabled=True),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=True,
    )

    loaded = [event for event in trace.events if event[0] == "long_term_memory_loaded"]
    assert loaded
    assert "entries" not in loaded[-1][2]


def test_codeagent_close_shuts_down_skill_evolution(tmp_path):
    agent = CodeAgent(
        name="code",
        llm=_DummyLLM(),
        tool_registry=ToolRegistry(),
        project_root=str(tmp_path),
        config=Config(),
        enable_skills=False,
        enable_mcp=False,
        enable_tracing=False,
    )
    manager = type("Manager", (), {"shutdown_called": False})()

    def shutdown():
        manager.shutdown_called = True

    manager.shutdown = shutdown
    agent._skill_evolution_manager = manager

    agent.close()

    assert manager.shutdown_called is True
