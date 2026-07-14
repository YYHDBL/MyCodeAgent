import json

from runtime.completion import (
    CompletionCandidate,
    CompletionGateVerdict,
    CompletionRequirements,
    DeterministicCompletionVerifier,
    collect_verification_evidence,
    infer_completion_requirements,
)
from runtime.history import Message


def test_infer_completion_requirements_detects_explicit_test_request():
    requirements = infer_completion_requirements(
        user_input="make the fix and run tests",
        history_messages=[],
    )

    assert requirements.requires_verification is True
    assert requirements.verification_kinds == ("tests",)
    assert requirements.allow_unverified is False


def test_infer_completion_requirements_detects_chinese_test_request():
    requirements = infer_completion_requirements(
        user_input="修复这个问题，然后运行测试",
        history_messages=[],
    )

    assert requirements.requires_verification is True
    assert requirements.verification_kinds == ("tests",)


def test_infer_completion_requirements_allows_unverified_when_user_marks_optional():
    requirements = infer_completion_requirements(
        user_input="make the fix and run tests if possible",
        history_messages=[],
    )

    assert requirements.requires_verification is True
    assert requirements.allow_unverified is True


def test_collect_verification_evidence_ignores_non_test_commands_with_test_text():
    history_messages = [
        Message(
            role="tool",
            content=json.dumps(
                {
                    "status": "success",
                    "data": {"exit_code": 0},
                    "context": {"params_input": {"command": "grep test README.md"}},
                }
            ),
            metadata={"tool_name": "Bash", "step": 1},
        ),
    ]

    evidence = collect_verification_evidence(history_messages)

    assert evidence == []


def test_collect_verification_evidence_invalidates_after_later_mutation():
    history_messages = [
        Message(
            role="tool",
            content=json.dumps(
                {
                    "status": "success",
                    "data": {"exit_code": 0},
                    "context": {"params_input": {"command": ".venv/bin/python -m pytest -q"}},
                }
            ),
            metadata={"tool_name": "Bash", "step": 1},
        ),
        Message(
            role="tool",
            content=json.dumps(
                {
                    "status": "success",
                    "data": {"path": "a.txt"},
                    "context": {"params_input": {"path": "a.txt", "content": "x"}},
                }
            ),
                metadata={"tool_name": "Edit", "step": 2},
        ),
    ]

    evidence = collect_verification_evidence(history_messages)

    assert len(evidence) == 1
    assert evidence[0].requirement_id == "verification:tests"
    assert evidence[0].valid is False
    assert evidence[0].invalid_reason == "modified_after_verification:2"


def test_deterministic_verifier_returns_unverified_when_optional_evidence_missing():
    verifier = DeterministicCompletionVerifier()
    candidate = CompletionCandidate(final_text="done", step=1, response_meta={})
    requirements = CompletionRequirements(
        requires_verification=True,
        verification_kinds=("tests",),
        allow_unverified=True,
    )

    result = verifier.evaluate(candidate, requirements, evidence=[], history_messages=[])

    assert result.verdict is CompletionGateVerdict.UNVERIFIED
