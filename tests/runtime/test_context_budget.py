from core.config import Config
from runtime.context import ContextBudgetPolicy
from runtime.history import HistoryManager


def test_context_budget_policy_requires_minimum_messages():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.1))
    history = HistoryManager()
    history.append_user("q")
    history.append_assistant("a")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="input",
        last_usage_tokens=900,
    )

    assert decision.should_compact is False
    assert decision.reason == "messages_not_enough"


def test_context_budget_policy_triggers_from_usage_estimate():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.8))
    history = HistoryManager()
    history.append_user("q1")
    history.append_assistant("a1")
    history.append_user("q2")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="more",
        last_usage_tokens=810,
    )

    assert decision.should_compact is True
    assert decision.reason == "threshold_exceeded"
    assert decision.threshold == 800


def test_context_budget_policy_estimates_message_content_and_tool_calls():
    policy = ContextBudgetPolicy(Config(context_window=1000, compression_threshold=0.8))
    history = HistoryManager()
    history.append_user("q" * 900)
    history.append_assistant(
        "",
        metadata={
            "action_type": "tool_call",
            "tool_calls": [{"id": "call_1", "name": "Read", "arguments": {"path": "a.py"}}],
        },
    )
    history.append_user("next")

    decision = policy.should_compact(
        messages=history.get_messages(),
        pending_input="more",
        last_usage_tokens=0,
    )

    assert decision.estimated_tokens > 0
