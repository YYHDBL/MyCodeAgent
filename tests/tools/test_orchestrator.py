import json
import time

from tools.orchestrator import (
    ToolBatch,
    ToolCallPlan,
    ToolObservation,
    ToolOrchestrator,
    ToolResultBudget,
)


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


def test_tool_observation_accepts_budget_metadata():
    obs = ToolObservation(
        tool_name="Read",
        tool_call_id="call_1",
        observation='{"status":"partial"}',
        raw_observation='{"status":"success"}',
        metadata={"budgeted": True, "replaced": True},
    )

    assert obs.raw_observation == '{"status":"success"}'
    assert obs.metadata["budgeted"] is True


def test_tool_result_budget_config_type():
    budget = ToolResultBudget(max_tool_bytes=100, max_message_bytes=300)

    assert budget.max_tool_bytes == 100
    assert budget.max_message_bytes == 300


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


class _EmptyHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        return ""


class _LargeHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        return json.dumps({
            "status": "success",
            "data": {"content": "x" * 2000},
            "text": "large",
        })


class _SizedHost(_Host):
    def _execute_tool(self, tool_name, tool_input):
        size = tool_input["size"]
        return json.dumps({
            "status": "success",
            "data": {"content": "x" * size},
            "text": f"size {size}",
        })


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


def test_run_fills_empty_tool_result_with_placeholder():
    host = _EmptyHost()
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [{"id": "call_1", "name": "Read", "arguments": "{}"}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "success"
    assert "completed with no output" in payload["text"]
    assert result[0].metadata["reason"] == "empty_result"


def test_run_applies_single_tool_result_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_RESULT_BYTES", "200")
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_MESSAGE_BYTES", "10000")

    host = _LargeHost()
    host.project_root = str(tmp_path)
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [{"id": "call_1", "name": "Read", "arguments": "{}"}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["status"] == "partial"
    assert payload["data"]["truncated"] is True
    assert result[0].raw_observation is not None
    assert result[0].metadata["replaced"] is True
    assert result[0].metadata["reason"] == "single_tool_budget"


def test_run_applies_aggregate_message_budget_largest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_RESULT_BYTES", "5000")
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_MESSAGE_BYTES", "1200")

    host = _SizedHost()
    host.project_root = str(tmp_path)
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"size": 300}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"size": 1500}'},
            {"id": "call_3", "name": "Glob", "arguments": '{"size": 400}'},
        ],
        step=2,
        trace_logger=host.trace_logger,
    )

    assert [obs.tool_call_id for obs in result] == ["call_1", "call_2", "call_3"]
    assert result[1].metadata["reason"] == "aggregate_message_budget"
    assert result[1].metadata["replaced"] is True


def test_run_emits_permission_trace_event_when_tool_denied():
    from tools.context import ToolExecutionContext
    from tools.executor import ToolExecutor
    from tools.permissions import PermissionAction, PermissionContext, PermissionDecision, RiskLevel
    from tools.registry import ToolRegistry

    class _NoopTool:
        name = "Write"

        def run(self, parameters):  # pragma: no cover - should never execute
            raise AssertionError("permission denied tool must not run")

    host = _Host()
    registry = ToolRegistry()
    registry.register_tool(_NoopTool())
    host.tool_executor = ToolExecutor(
        registry,
        context=ToolExecutionContext(
            permission_context=PermissionContext(runtime_mode="readonly_subagent"),
            permission_decider=lambda name, params, ctx: PermissionDecision(
                action=PermissionAction.DENY,
                risk=RiskLevel.HIGH,
                reason="readonly_subagent blocks writes",
                policy_source="unit_test",
                input_summary=str(params),
            ),
        ),
    )
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run_serial(
        [{"id": "call_1", "name": "Write", "arguments": '{"path": "a.txt"}'}],
        step=2,
        trace_logger=host.trace_logger,
    )

    payload = json.loads(result[0].observation)

    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert any(
        event[0] == "permission_decision"
        and event[2]["tool_name"] == "Write"
        and event[2]["action"] == "deny"
        for event in host.trace_logger.events
    )


def test_budget_does_not_restore_or_reprocess_replaced_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_RESULT_BYTES", "600")
    monkeypatch.setenv("MYCODEAGENT_MAX_TOOL_MESSAGE_BYTES", "500")

    host = _SizedHost()
    host.project_root = str(tmp_path)
    orchestrator = ToolOrchestrator(host)

    result = orchestrator.run(
        [
            {"id": "call_1", "name": "Read", "arguments": '{"size": 1500}'},
            {"id": "call_2", "name": "Grep", "arguments": '{"size": 300}'},
        ],
        step=2,
        trace_logger=host.trace_logger,
    )

    assert result[0].metadata["reason"] == "single_tool_budget"
    assert result[0].metadata["replaced"] is True
    assert result[0].raw_observation is not None
    assert result[1].metadata["reason"] == "aggregate_message_budget"
