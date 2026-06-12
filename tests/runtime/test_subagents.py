import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from runtime.completion import (
    CompletionCandidate,
    CompletionGateResult,
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
    _SubagentRuntimeHost,
    _summarize_child_messages,
)
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
    for name in ["LS", "Glob", "Grep", "Read", "Write", "Edit", "MultiEdit", "Bash", "Task", "AskUser"]:
        registry.register_tool(_tool(name))
    return registry


def test_runtime_profiles_enforce_readonly_non_recursive_contracts():
    assert EXPLORE_PROFILE.name == "explore"
    assert EXPLORE_PROFILE.tool_allowlist == frozenset({"LS", "Glob", "Grep", "Read"})
    assert VERIFICATION_PROFILE.recursive_subagents is False
    for profile in (EXPLORE_PROFILE, VERIFICATION_PROFILE):
        assert profile.max_steps > 0
        assert profile.context_token_budget > 0
        assert "Task" not in profile.tool_allowlist
        assert not ({"Write", "Edit", "MultiEdit", "Bash", "AskUser"} & profile.tool_allowlist)


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
    assert filtered.get_tool("Write") is None
    assert filtered.get_tool("Task") is None

    decision = RiskClassifier().classify(
        "Write",
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
        "LS",
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
    assert "Write: Create or overwrite" not in tool_contracts


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


def test_formal_task_path_has_no_legacy_runner_or_turn_executor_reference():
    task_source = Path("tools/builtin/task.py").read_text(encoding="utf-8")
    task_prompt = Path("prompts/tools_prompts/task_prompt.py").read_text(encoding="utf-8")
    host_source = Path("runtime/host.py").read_text(encoding="utf-8")
    assert "SubagentRunner" not in task_source
    assert "TurnExecutor" not in task_source
    assert "enable_agent_teams" not in task_source
    assert "TaskTool(" in host_source
    assert "team_name" not in task_prompt
    assert "Supports two modes" not in task_prompt


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
