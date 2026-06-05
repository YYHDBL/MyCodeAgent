import json

from tools.orchestrator import ToolObservation, ToolOrchestrator


def test_tool_orchestrator_exports_v1_types():
    assert ToolOrchestrator.__name__ == "ToolOrchestrator"

    obs = ToolObservation(
        tool_name="Echo",
        tool_call_id="call_1",
        observation='{"status": "success"}',
    )

    assert obs.tool_name == "Echo"
    assert obs.tool_call_id == "call_1"
    assert obs.observation == '{"status": "success"}'


class _TraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))


class _Host:
    def __init__(self):
        self.trace_logger = _TraceLogger()
        self.calls = []
        self.project_root = "."
        self.tool_executor = None

    def _ensure_json_input(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args, None
        try:
            return json.loads(raw_args), None
        except Exception as exc:
            return {}, exc

    def _execute_tool(self, tool_name, tool_input):
        self.calls.append((tool_name, tool_input))
        return json.dumps({"status": "success", "data": {"ok": True}})


def test_run_serial_executes_one_tool_and_returns_observation():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": '{"text": "hi"}'}],
        step=2,
        trace_logger=host.trace_logger,
    )

    assert len(result) == 1
    assert result[0].tool_name == "Echo"
    assert result[0].tool_call_id == "call_1"
    assert json.loads(result[0].observation)["status"] == "success"
    assert host.calls == [("Echo", {"text": "hi"})]
    assert any(event[0] == "tool_call" for event in host.trace_logger.events)
    assert any(event[0] == "tool_result" for event in host.trace_logger.events)


def test_run_serial_returns_invalid_param_observation_on_parse_error():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": "{"}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_PARAM"
    assert host.calls == []
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_call_parse"
        for event in host.trace_logger.events
    )


class _ExplodingHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        raise RuntimeError("boom")


def test_run_serial_returns_execution_error_observation_on_exception():
    host = _ExplodingHost()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Echo", "arguments": '{"text": "hi"}'}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "EXECUTION_ERROR"
    assert payload["error"]["message"] == "boom"
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_execution"
        for event in host.trace_logger.events
    )
