from runtime.loop import RuntimeRunner
from runtime.context import ContextEngine
from runtime.prompt_builder import ContextBuilder

from tests.scenarios.phase0_baselines import FinalOnlyScenarioHost


def test_runtime_runner_emits_prompt_and_tool_schema_fingerprints():
    host = FinalOnlyScenarioHost()
    runner = RuntimeRunner(host)

    runner.run("hello", show_raw=False)

    prompt_events = [event for event in host.trace_logger.events if event[0] == "prompt_assembly"]
    tool_events = [event for event in host.trace_logger.events if event[0] == "tool_schema"]

    assert prompt_events
    assert tool_events
    assert "system_fingerprint" in prompt_events[0][2]
    assert "runtime_signals_fingerprint" in prompt_events[0][2]
    assert "changed_layers" in prompt_events[0][2]
    assert "fingerprint" in tool_events[0][2]
    assert "changed" in tool_events[0][2]


def test_prompt_trace_matches_runtime_signals_sent_to_model(tmp_path):
    agents_dir = tmp_path / "prompts" / "agents_prompts"
    agents_dir.mkdir(parents=True)
    (agents_dir / "L1_system_prompt.py").write_text(
        'system_prompt = "base"',
        encoding="utf-8",
    )

    class _Registry:
        def get_disabled_tools(self):
            return []

    class _TeamManager:
        def drain_events(self):
            return [{"team": "demo", "type": "completed", "payload": {}}]

        def export_state(self):
            return {"work_items": {"demo": {"succeeded": 1}}}

    host = FinalOnlyScenarioHost()
    host.context_builder = ContextBuilder(
        tool_registry=_Registry(),
        project_root=str(tmp_path),
    )
    host.context_engine = ContextEngine(
        host.context_builder,
        config=host.config,
        summary_generator=lambda messages: "",
    )
    host.enable_agent_teams = True
    host.team_manager = _TeamManager()
    host._format_runtime_system_blocks = (
        lambda events, runtime_state=None: ["[Team Runtime]\n- demo completed"]
    )

    RuntimeRunner(host).run("hello", show_raw=False)

    prompt_events = [event for event in host.trace_logger.events if event[0] == "prompt_assembly"]
    sent_messages = host.llm_calls[0]["messages"]

    assert any("[Team Runtime]" in message["content"] for message in sent_messages)
    assert prompt_events[-1][2]["runtime_signal_count"] == 1
    assert prompt_events[-1][2]["runtime_signals_fingerprint"] == (
        host.context_builder.get_prompt_assembly().runtime_signals_fingerprint
    )
