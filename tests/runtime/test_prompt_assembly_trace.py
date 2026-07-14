from runtime.loop import RuntimeRunner

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
