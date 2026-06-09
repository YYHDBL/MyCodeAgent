import json
from pathlib import Path
from unittest.mock import Mock, patch

from runtime.completion import CompletionCandidate, CompletionRequirements
from runtime.subagents import (
    ExploreResult,
    SubagentCompletionVerifier,
    SubagentLaunchResult,
    SubagentLauncher,
    SubagentRequest,
    SubagentStatus,
    VerificationResult,
    VerificationVerdict,
)
from tools.registry import ToolRegistry


def test_explore_agent_isolates_search_noise(tmp_path):
    parent_history = Mock()
    launcher = SubagentLauncher(
        project_root=tmp_path,
        main_llm=Mock(),
        tool_registry=ToolRegistry(),
        parent_history_manager=parent_history,
    )
    raw = json.dumps(
        {
            "status": "completed",
            "summary": "Only the bounded summary returns.",
            "findings": ["RuntimeRunner is canonical."],
            "evidence": ["runtime/loop.py:1"],
            "unresolved_questions": [],
        }
    )
    with patch("runtime.subagents.RuntimeRunner.run", return_value=raw):
        launched = launcher.launch(SubagentRequest(profile_name="explore", task="inspect runtime"))
    assert isinstance(launched.result, ExploreResult)
    assert launched.result.summary == "Only the bounded summary returns."
    parent_history.get_messages.assert_not_called()


def test_verification_agent_independently_checks_completion_candidate():
    launcher = Mock()
    launcher.launch.return_value = SubagentLaunchResult(
        status=SubagentStatus.COMPLETED,
        profile_name="verification",
        child_session_id="child-session",
        child_run_id="child-run",
        result=VerificationResult(
            verdict=VerificationVerdict.PASS,
            reasons=("evidence matched",),
            child_session_id="child-session",
            child_run_id="child-run",
            terminal_reason="completed",
        ),
    )
    result = SubagentCompletionVerifier(launcher).evaluate(
        CompletionCandidate(final_text="done", step=1, response_meta={}),
        CompletionRequirements(requires_verification=True),
        [],
        [],
    )
    assert result.verdict.value == "pass"
    request = launcher.launch.call_args.args[0]
    assert request.profile_name == "verification"
    assert request.structured_context["candidate"]["final_text"] == "done"
