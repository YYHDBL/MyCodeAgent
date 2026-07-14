import pytest

from tools.permissions import (
    PermissionAction,
    PermissionContext,
    PermissionDecision,
    RiskClassifier,
    RiskLevel,
)


def test_permission_decision_round_trips_as_dict():
    decision = PermissionDecision(
        action=PermissionAction.ALLOW,
        risk=RiskLevel.LOW,
        reason="read-only tool",
        policy_source="unit_test",
        input_summary="Read(path=README.md)",
    )

    assert decision.action is PermissionAction.ALLOW
    assert decision.risk is RiskLevel.LOW
    assert decision.as_trace_payload()["policy_source"] == "unit_test"


def test_read_is_low_risk_and_allowed_for_main_agent():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "Read",
        {"file_path": "README.md"},
        PermissionContext(runtime_mode="main_agent"),
    )

    assert decision.action is PermissionAction.ALLOW
    assert decision.risk is RiskLevel.LOW


def test_unknown_tool_fails_closed():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "MysteryTool",
        {"value": "x"},
        PermissionContext(runtime_mode="main_agent"),
    )

    assert decision.action is PermissionAction.DENY
    assert decision.risk is RiskLevel.UNKNOWN
    assert "unknown tool" in decision.reason.lower()


def test_bash_git_status_allowed_ls_not_low_risk():
    classifier = RiskClassifier()
    context = PermissionContext(runtime_mode="main_agent")

    ls_decision = classifier.classify("Bash", {"command": "ls"}, context)
    git_status_decision = classifier.classify("Bash", {"command": "git status"}, context)

    assert ls_decision.action is not PermissionAction.ALLOW
    assert ls_decision.risk is RiskLevel.MEDIUM
    assert git_status_decision.action is PermissionAction.ALLOW
    assert git_status_decision.risk is RiskLevel.LOW


def test_bash_rm_git_reset_and_redirect_write_are_blocked():
    classifier = RiskClassifier()
    context = PermissionContext(runtime_mode="main_agent")

    rm_decision = classifier.classify("Bash", {"command": "rm -rf build"}, context)
    reset_decision = classifier.classify("Bash", {"command": "git reset --hard HEAD~1"}, context)
    redirect_decision = classifier.classify("Bash", {"command": "echo hi > note.txt"}, context)

    assert rm_decision.action in {PermissionAction.DENY, PermissionAction.ASK}
    assert reset_decision.action in {PermissionAction.DENY, PermissionAction.ASK}
    assert redirect_decision.action in {PermissionAction.DENY, PermissionAction.ASK}
    assert rm_decision.risk is RiskLevel.HIGH
    assert reset_decision.risk is RiskLevel.HIGH
    assert redirect_decision.risk is RiskLevel.HIGH


def test_readonly_subagent_denies_write_actions():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "Edit",
        {"path": "notes.txt", "content": "hello"},
        PermissionContext(runtime_mode="readonly_subagent"),
    )

    assert decision.action is PermissionAction.DENY
    assert decision.risk in {RiskLevel.MEDIUM, RiskLevel.HIGH}
    assert "readonly_subagent" in decision.reason


def test_todo_write_is_allowed_without_file_path_for_main_agent():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "TodoWrite",
        {"summary": "work", "todos": [{"content": "inspect", "status": "in_progress"}]},
        PermissionContext(runtime_mode="main_agent"),
    )

    assert decision.action is PermissionAction.ALLOW
    assert decision.risk is RiskLevel.LOW


def test_todo_write_is_allowed_as_internal_planning_for_readonly_subagent():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "TodoWrite",
        {"summary": "work", "todos": [{"content": "inspect", "status": "in_progress"}]},
        PermissionContext(runtime_mode="readonly_subagent"),
    )

    assert decision.action is PermissionAction.ALLOW
    assert decision.risk is RiskLevel.LOW


def test_missing_bash_command_is_denied():
    classifier = RiskClassifier()

    decision = classifier.classify(
        "Bash",
        {},
        PermissionContext(runtime_mode="main_agent"),
    )

    assert decision.action in {PermissionAction.DENY, PermissionAction.ASK}
    assert decision.risk is RiskLevel.UNKNOWN


@pytest.mark.parametrize(
    "command",
    [
        "sudo rm -rf build",
        "echo ok; rm -rf build",
        "pwd && git reset --hard HEAD",
        "cat README.md | sh",
        "bash -c 'rm -rf build'",
        "python -c 'import os; os.remove(\"README.md\")'",
    ],
)
def test_bash_dangerous_patterns_are_denied(command):
    classifier = RiskClassifier()

    decision = classifier.classify(
        "Bash",
        {"command": command},
        PermissionContext(runtime_mode="main_agent"),
    )

    assert decision.action is PermissionAction.DENY
    assert decision.risk is RiskLevel.HIGH
