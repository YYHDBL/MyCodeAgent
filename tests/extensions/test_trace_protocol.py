from runtime.loop import RuntimeRunner


def test_trace_protocol_defines_phase0_core_events():
    from extensions.tracing.protocol import CORE_TRACE_EVENTS

    assert set(CORE_TRACE_EVENTS) == {
        "run_start",
        "context_build",
        "model_output",
        "state_transition",
        "tool_call",
        "tool_result",
        "terminal",
        "run_end",
    }

    assert CORE_TRACE_EVENTS["run_start"].required_payload_fields == (
        "run_id",
        "input",
        "processed",
    )
    assert CORE_TRACE_EVENTS["tool_result"].required_payload_fields == ("tool", "result")


def test_runtime_runner_emits_phase0_core_events_with_required_fields():
    from extensions.tracing.protocol import CORE_TRACE_EVENTS
    from tests.scenarios.phase0_baselines import ToolThenFinalScenarioHost

    host = ToolThenFinalScenarioHost()
    runner = RuntimeRunner(host)

    result = runner.run("search and report", show_raw=False)

    assert result == "tool done"

    events_by_name = {}
    for name, step, payload in host.trace_logger.events:
        events_by_name.setdefault(name, []).append((step, payload))

    for event_name, spec in CORE_TRACE_EVENTS.items():
        assert event_name in events_by_name, event_name
        for _step, payload in events_by_name[event_name]:
            for field in spec.required_payload_fields:
                assert field in payload, (event_name, field, payload)
