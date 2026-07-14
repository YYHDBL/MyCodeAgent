def test_runtime_loop_delegates_tool_calls_to_the_host_orchestrator():
    from runtime.loop import RuntimeRunner
    from tests.runtime.test_runner import _ToolThenFinalHost

    host = _ToolThenFinalHost()
    calls = []
    original_run = host.tool_orchestrator.run

    def record_run(tool_calls, *, step, trace_logger):
        calls.append((tool_calls, step, trace_logger))
        return original_run(tool_calls, step=step, trace_logger=trace_logger)

    host.tool_orchestrator.run = record_run

    assert RuntimeRunner(host).run("use Echo") == "tool done"
    assert calls[0][0][0]["name"] == "Echo"
    assert calls[0][1] == 1
