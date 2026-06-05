import json
import time

from tools.orchestrator import ToolBatch, ToolCallPlan, ToolObservation, ToolOrchestrator


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

    plan = ToolCallPlan(
        call={"id": "call_1"},
        tool_name="Read",
        tool_call_id="call_1",
        parsed_input={"path": "a.py"},
        parse_error=None,
        concurrency_safe=True,
    )
    batch = ToolBatch(concurrency_safe=True, calls=[plan])

    assert batch.concurrency_safe is True
    assert batch.calls == [plan]


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


class _TimedHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        self.calls.append((tool_name, tool_input))
        time.sleep(tool_input.get("delay", 0))
        return json.dumps({"status": "success", "data": {"tool": tool_name, "delay": tool_input.get("delay", 0)}})


class _MixedFailureHost(_TimedHost):
    def _execute_tool(self, tool_name, tool_input):
        self.calls.append((tool_name, tool_input))
        time.sleep(tool_input.get("delay", 0))
        if tool_input.get("explode"):
            raise RuntimeError("boom")
        return json.dumps({"status": "success", "data": {"tool": tool_name}})


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


def test_partition_tool_calls_groups_only_contiguous_safe_calls():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    plans = orchestrator.plan_tool_calls(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"path": "a.py"}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"pattern": "x"}'},
            {"id": "call_3", "name": "Edit", "arguments": '{"path": "a.py"}'},
            {"id": "call_4", "name": "Read", "arguments": '{"path": "b.py"}'},
            {"id": "call_5", "name": "Bash", "arguments": '{"command": "pwd"}'},
            {"id": "call_6", "name": "Read", "arguments": '{"path": "c.py"}'},
        ]
    )

    batches = orchestrator.partition_tool_calls(plans)

    assert [batch.concurrency_safe for batch in batches] == [True, False, True, False, True]
    assert [[plan.tool_name for plan in batch.calls] for batch in batches] == [
        ["Read", "Grep"],
        ["Edit"],
        ["Read"],
        ["Bash"],
        ["Read"],
    ]


def test_run_executes_safe_batch_concurrently():
    host = _TimedHost()
    orchestrator = ToolOrchestrator(host)

    start = time.perf_counter()
    result = orchestrator.run(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"delay": 0.2}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"delay": 0.2}'},
        ],
        step=2,
        trace_logger=host.trace_logger,
    )
    elapsed = time.perf_counter() - start

    assert len(result) == 2
    assert elapsed < 0.35
    assert any(event[0] == "tool_orchestration_plan" for event in host.trace_logger.events)
    assert any(event[0] == "tool_batch_start" for event in host.trace_logger.events)
    assert any(event[0] == "tool_batch_end" for event in host.trace_logger.events)


def test_run_preserves_original_tool_call_order_for_parallel_results():
    host = _TimedHost()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"delay": 0.2}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"delay": 0.01}'},
        ],
        step=2,
        trace_logger=host.trace_logger,
    )

    assert [obs.tool_call_id for obs in result] == ["call_1", "call_2"]


def test_plan_tool_calls_marks_parse_error_unsafe_and_run_returns_invalid_param():
    host = _Host()
    orchestrator = ToolOrchestrator(host)

    plans = orchestrator.plan_tool_calls(
        [{"id": "call_1", "name": "Read", "arguments": "{"}]
    )

    assert len(plans) == 1
    assert plans[0].concurrency_safe is False
    assert plans[0].parse_error is not None

    result = orchestrator.run(
        [{"id": "call_1", "name": "Read", "arguments": "{"}],
        step=2,
        trace_logger=host.trace_logger,
    )
    payload = json.loads(result[0].observation)

    assert payload["error"]["code"] == "INVALID_PARAM"


def test_run_keeps_other_safe_tools_running_when_one_fails():
    host = _MixedFailureHost()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"explode": true, "delay": 0.05}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"delay": 0.1}'},
        ],
        step=2,
        trace_logger=host.trace_logger,
    )

    payloads = [json.loads(obs.observation) for obs in result]

    assert payloads[0]["error"]["code"] == "EXECUTION_ERROR"
    assert payloads[1]["status"] == "success"
    assert len(host.calls) == 2
