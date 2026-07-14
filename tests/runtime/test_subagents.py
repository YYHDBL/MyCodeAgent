import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.llm import (
    extract_reasoning_content,
    extract_response_content,
    extract_response_meta,
    extract_tool_calls,
    extract_usage,
    parse_tool_input,
    serialize_response,
)
from runtime.completion import (
    CompletionCandidate,
    CompletionGateVerdict,
    CompletionRequirements,
)
from runtime.subagents import (
    EXPLORE_PROFILE,
    VERIFICATION_PROFILE,
    ExploreResult,
    SubagentLauncher,
    SubagentRequest,
    SubagentStatus,
    VerificationResult,
    VerificationVerdict,
    _RecordingTrace,
    _SubagentRuntimeHost,
    _summarize_child_messages,
)
from runtime.loop import RuntimeRunner
from extensions.tracing import NullTraceLogger
from tools.permissions import PermissionAction, PermissionContext, RiskClassifier
from tools.registry import ToolRegistry


def _tool(name):
    tool = Mock()
    tool.name = name
    tool.description = name
    tool.get_parameters.return_value = []
    tool.run.return_value = json.dumps({"status": "success", "data": {}, "text": "ok"})
    return tool


def _registry():
    registry = ToolRegistry()
    for name in ["Glob", "Grep", "Read", "Edit", "Bash", "Task"]:
        registry.register_tool(_tool(name))
    return registry


class _SDKResponse:
    def __init__(self, payload):
        self._payload = payload
        choice = payload["choices"][0]
        message = choice["message"]
        self.choices = [
            SimpleNamespace(
                finish_reason=choice.get("finish_reason"),
                message=SimpleNamespace(
                    role=message.get("role"),
                    content=message.get("content"),
                    reasoning_content=message.get("reasoning_content"),
                    refusal=message.get("refusal"),
                    function_call=message.get("function_call"),
                    tool_calls=[
                        SimpleNamespace(
                            id=call.get("id"),
                            function=SimpleNamespace(
                                name=(call.get("function") or {}).get("name"),
                                arguments=(call.get("function") or {}).get("arguments"),
                            ),
                        )
                        for call in message.get("tool_calls") or []
                    ],
                ),
            )
        ]
        self.usage = SimpleNamespace(**payload["usage"])

    def model_dump(self):
        return self._payload


def test_subagent_response_normalization_uses_canonical_dict_and_sdk_contracts():
    payload = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "read README",
                    "reasoning_content": "because",
                    "refusal": None,
                    "function_call": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "Read",
                                "arguments": '{"path": "README.md"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }
    responses = (payload, _SDKResponse(payload))

    assert parse_tool_input('{"path": "README.md"}') == ({"path": "README.md"}, None)
    assert [extract_response_content(response) for response in responses] == ["read README"] * 2
    assert [extract_reasoning_content(response) for response in responses] == ["because"] * 2
    assert [extract_tool_calls(response) for response in responses] == [
        [{"id": "call_1", "name": "Read", "arguments": '{"path": "README.md"}'}]
    ] * 2
    assert [extract_usage(response) for response in responses] == [
        {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    ] * 2
    assert [extract_response_meta(response) for response in responses] == [
        {
            "finish_reason": "tool_calls",
            "role": "assistant",
            "content_len": 11,
            "reasoning_len": 7,
            "refusal_present": False,
            "tool_calls_count": 1,
            "function_call_present": False,
        }
    ] * 2
    assert [serialize_response(response) for response in responses] == [payload] * 2


@pytest.mark.parametrize(
    "method_name",
    [
        "_ensure_json_input",
        "_extract_content",
        "_extract_reasoning_content",
        "_extract_tool_calls",
        "_extract_usage",
        "_extract_response_meta",
        "_extract_raw_response",
    ],
)
def test_subagent_runtime_host_has_no_legacy_response_adapters(method_name):
    assert not hasattr(_SubagentRuntimeHost, method_name)


class _OneResponseLLM:
    def __init__(self, response):
        self.response = response

    def invoke_raw(self, _messages, **_kwargs):
        return self.response


def _run_child_response(tmp_path, response):
    trace = _RecordingTrace(NullTraceLogger(), session_id="child-response-normalization")
    host = _SubagentRuntimeHost(
        profile=EXPLORE_PROFILE,
        llm=_OneResponseLLM(response),
        registry=_registry(),
        project_root=tmp_path,
        trace_logger=trace,
    )

    result = RuntimeRunner(host).run("inspect the response contract")
    model_outputs = [payload for name, _step, payload in trace.events if name == "model_output"]

    assert len(model_outputs) == 1
    return result, model_outputs[0]


def test_child_host_runner_normalizes_dict_and_sdk_responses_equivalently(tmp_path):
    content = json.dumps(
        {
            "status": "completed",
            "summary": "response normalization is shared",
            "findings": [],
            "evidence": [],
            "unresolved_questions": [],
        }
    )
    payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": "canonical path",
                    "refusal": None,
                    "function_call": None,
                    "tool_calls": [],
                },
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }

    results = [_run_child_response(tmp_path, response) for response in (payload, _SDKResponse(payload))]

    assert results[0] == results[1]
    assert results[0][0] == content
    assert results[0][1] == {
        "raw": content,
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        "meta": {
            "finish_reason": "stop",
            "role": "assistant",
            "content_len": len(content),
            "reasoning_len": len("canonical path"),
            "refusal_present": False,
            "tool_calls_count": 0,
            "function_call_present": False,
        },
        "raw_response": payload,
        "tool_calls": [],
    }


def test_runtime_profiles_enforce_readonly_non_recursive_contracts():
    assert EXPLORE_PROFILE.name == "explore"
    assert EXPLORE_PROFILE.tool_allowlist == frozenset({"Glob", "Grep", "Read"})
    assert VERIFICATION_PROFILE.recursive_subagents is False
    for profile in (EXPLORE_PROFILE, VERIFICATION_PROFILE):
        assert profile.max_steps > 0
        assert profile.context_token_budget > 0
        assert "Task" not in profile.tool_allowlist
        assert not ({"Edit", "Bash"} & profile.tool_allowlist)


def test_result_contracts_support_required_verdicts():
    explore = ExploreResult.from_json(
        json.dumps(
            {
                "status": "completed",
                "summary": "found",
                "findings": ["one"],
                "evidence": ["runtime/loop.py:1"],
                "unresolved_questions": [],
            }
        ),
        tool_usage={"Read": 1},
        terminal_reason="completed",
    )
    assert explore.status is SubagentStatus.COMPLETED
    assert explore.tool_usage == {"Read": 1}
    for verdict in VerificationVerdict:
        result = VerificationResult.from_json(
            json.dumps({"verdict": verdict.value, "reasons": [], "findings": [], "evidence": []}),
            child_run_id="child-1",
            terminal_reason="completed",
        )
        assert result.verdict is verdict


def test_filtered_registry_and_permission_core_both_block_mutation():
    launcher = SubagentLauncher(project_root=Path("."), main_llm=Mock(), tool_registry=_registry())
    filtered = launcher.build_registry(EXPLORE_PROFILE)
    assert filtered.get_tool("Read") is not None
    assert filtered.get_tool("Edit") is None
    assert filtered.get_tool("Task") is None

    decision = RiskClassifier().classify(
        "Edit",
        {"path": "x.py", "content": "x"},
        PermissionContext(runtime_mode="readonly_subagent"),
    )
    assert decision.action is PermissionAction.DENY
    recursive = RiskClassifier().classify(
        "Task",
        {"prompt": "nested"},
        PermissionContext(runtime_mode="readonly_subagent"),
    )
    assert recursive.action is PermissionAction.DENY
    readonly = RiskClassifier().classify(
        "Glob",
        {},
        PermissionContext(runtime_mode="readonly_subagent"),
    )
    assert readonly.action is PermissionAction.ALLOW


def test_subagent_prompt_only_describes_allowed_tools():
    trace = Mock(wraps=NullTraceLogger())
    trace.session_id = "child-test"
    host = _SubagentRuntimeHost(
        profile=EXPLORE_PROFILE,
        llm=Mock(),
        registry=_registry(),
        project_root=Path("."),
        trace_logger=trace,
    )

    tool_contracts = "\n".join(
        message["content"]
        for message in host.context_builder.get_system_messages()
        if message["content"].startswith("# Tool Contracts")
    )

    assert "Tool name: Read" in tool_contracts
    assert "Tool name: Bash" not in tool_contracts
    assert "Tool name: Task" not in tool_contracts
    assert "Edit: atomically create" not in tool_contracts


def test_child_compaction_summary_preserves_bounded_facts():
    messages = [
        Mock(role="user", content="Find the runtime ownership boundary.", metadata={}),
        Mock(
            role="tool",
            content="RuntimeRunner is the canonical loop in runtime/loop.py.",
            metadata={"tool_name": "Read"},
        ),
    ]

    summary = _summarize_child_messages(messages)

    assert "Find the runtime ownership boundary." in summary
    assert "RuntimeRunner is the canonical loop" in summary
    assert len(summary) <= 8000


def test_launcher_uses_runtime_runner_and_does_not_touch_parent_state(tmp_path):
    parent_history = Mock()
    parent_context = Mock()
    llm = Mock()
    launcher = SubagentLauncher(
        project_root=tmp_path,
        main_llm=llm,
        tool_registry=_registry(),
        parent_history_manager=parent_history,
        parent_context_engine=parent_context,
    )
    raw = json.dumps(
        {
            "status": "completed",
            "summary": "isolated",
            "findings": [],
            "evidence": [],
            "unresolved_questions": [],
        }
    )
    with patch("runtime.subagents.RuntimeRunner.run", autospec=True, return_value=raw) as run:
        result = launcher.launch(SubagentRequest(profile_name="explore", task="inspect"))

    assert run.call_count == 1
    child_host = run.call_args.args[0].host
    assert child_host.history_manager is not parent_history
    assert child_host.context_engine is not parent_context
    assert result.result.summary == "isolated"
    parent_history.get_messages.assert_not_called()
    parent_context.build_model_view.assert_not_called()


def test_launcher_invalid_or_failed_child_maps_to_failed_result(tmp_path):
    launcher = SubagentLauncher(project_root=tmp_path, main_llm=Mock(), tool_registry=_registry())
    with patch("runtime.subagents.RuntimeRunner.run", side_effect=RuntimeError("boom")):
        result = launcher.launch(SubagentRequest(profile_name="explore", task="inspect"))
    assert result.status is SubagentStatus.FAILED
    assert result.terminal_reason == "runtime_error"


def test_disabled_parent_tracing_stays_disabled_with_unique_child_sessions(tmp_path):
    launcher = SubagentLauncher(
        project_root=tmp_path,
        main_llm=Mock(),
        tool_registry=_registry(),
        parent_trace_logger=NullTraceLogger(),
    )
    raw = json.dumps(
        {
            "status": "completed",
            "summary": "isolated",
            "findings": [],
            "evidence": [],
            "unresolved_questions": [],
        }
    )

    with (
        patch("runtime.subagents.RuntimeRunner.run", return_value=raw),
        patch("runtime.subagents.create_trace_logger") as create_trace,
    ):
        first = launcher.launch(SubagentRequest(profile_name="explore", task="first"))
        second = launcher.launch(SubagentRequest(profile_name="explore", task="second"))

    create_trace.assert_not_called()
    assert first.child_session_id != second.child_session_id
    assert first.child_session_id != "disabled"
    assert second.child_session_id != "disabled"


def test_verification_completion_adapter_maps_verdicts():
    candidate = CompletionCandidate(final_text="done", step=1, response_meta={})
    requirements = CompletionRequirements(requires_verification=True)
    launcher = Mock()
    launcher.launch.return_value.result = VerificationResult(
        verdict=VerificationVerdict.PASS,
        child_run_id="child-1",
        terminal_reason="completed",
    )
    from runtime.subagents import SubagentCompletionVerifier

    result = SubagentCompletionVerifier(launcher).evaluate(candidate, requirements, [], [])
    assert result.verdict is CompletionGateVerdict.PASS


def test_deterministic_failure_never_launches_verification_agent():
    candidate = CompletionCandidate(final_text="done", step=1, response_meta={})
    requirements = CompletionRequirements(
        requires_verification=False,
        has_incomplete_todos=True,
        incomplete_todos=("finish tests",),
    )
    launcher = Mock()
    from runtime.subagents import SubagentCompletionVerifier

    result = SubagentCompletionVerifier(launcher).evaluate(candidate, requirements, [], [])
    assert result.verdict is CompletionGateVerdict.FAIL
    launcher.launch.assert_not_called()


def test_verifier_failure_or_invalid_result_maps_to_unverified():
    candidate = CompletionCandidate(final_text="done", step=1, response_meta={})
    requirements = CompletionRequirements(requires_verification=True)
    launcher = Mock()
    launcher.launch.side_effect = RuntimeError("boom")
    from runtime.subagents import SubagentCompletionVerifier

    result = SubagentCompletionVerifier(launcher).evaluate(candidate, requirements, [], [])
    assert result.verdict is CompletionGateVerdict.UNVERIFIED


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (VerificationVerdict.PASS, CompletionGateVerdict.PASS),
        (VerificationVerdict.FAIL, CompletionGateVerdict.FAIL),
        (VerificationVerdict.PARTIAL, CompletionGateVerdict.FAIL),
        (VerificationVerdict.UNVERIFIED, CompletionGateVerdict.UNVERIFIED),
    ],
)
def test_verification_agent_four_verdicts_map_to_completion_gate(verdict, expected):
    candidate = CompletionCandidate(final_text="done", step=1, response_meta={})
    requirements = CompletionRequirements(requires_verification=True)
    launcher = Mock()
    launcher.launch.return_value.result = VerificationResult(
        verdict=verdict,
        child_run_id="child-1",
        terminal_reason="completed",
    )
    from runtime.subagents import SubagentCompletionVerifier

    result = SubagentCompletionVerifier(launcher).evaluate(candidate, requirements, [], [])
    assert result.verdict is expected
