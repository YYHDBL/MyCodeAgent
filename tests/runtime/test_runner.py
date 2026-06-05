import logging
import json

from runtime.host import CodeAgent


def test_runtime_loop_module_exposes_runner():
    from runtime.loop import RuntimeRunner

    assert RuntimeRunner.__name__ == "RuntimeRunner"


def test_runtime_host_imports_canonical_loop():
    source = open("runtime/host.py", encoding="utf-8").read()

    assert "from runtime.loop import RuntimeRunner" in source
    assert "runtime." + "runner" not in source


def test_runtime_host_initializes_tool_orchestrator():
    source = open("runtime/host.py", encoding="utf-8").read()

    assert "from tools.orchestrator import ToolOrchestrator" in source
    assert "self.tool_orchestrator = ToolOrchestrator(self)" in source


class _FakeTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))

    def log_system_messages(self, messages):
        self.events.append(("system_messages", 0, messages))


class _FakeHistoryManager:
    def __init__(self):
        self.messages = []
        self.last_usage = None

    def append_user(self, content):
        self.messages.append({"role": "user", "content": content})

    def append_assistant(self, content, metadata=None, reasoning_content=None):
        self.messages.append({"role": "assistant", "content": content, "metadata": metadata or {}})

    def append_tool(self, tool_name, raw_result, metadata=None, project_root=None):
        self.messages.append({"role": "tool", "content": raw_result, "metadata": metadata or {}})

    def should_compress(self, pending_input):
        return False

    def to_messages(self):
        return list(self.messages)

    def update_last_usage(self, total_tokens):
        self.last_usage = total_tokens

    def get_message_count(self):
        return len(self.messages)

    def get_rounds_count(self):
        return 1

    def estimate_context_tokens(self, pending_input):
        return 0

    def get_total_usage_tokens(self):
        return 0

    def compact(self, on_event=None, return_info=False):
        info = {"compressed": False}
        return info if return_info else None


class _FakeContextBuilder:
    def __init__(self):
        self.skills_prompt = ""

    def set_skills_prompt(self, prompt):
        self.skills_prompt = prompt

    def build_messages(self, history_messages):
        return [{"role": "system", "content": "system"}] + list(history_messages)


class _FakeHost:
    def __init__(self):
        from tools.orchestrator import ToolOrchestrator

        self.console_progress = False
        self.console_verbose = False
        self.logger = logging.getLogger("test.runtime.loop")
        self._skills_prompt = ""
        self.context_builder = _FakeContextBuilder()
        self.trace_logger = _FakeTraceLogger()
        self.history_manager = _FakeHistoryManager()
        self._run_id = 0
        self.max_steps = 3
        self.enable_agent_teams = False
        self.team_manager = None
        self.config = type("Config", (), {"context_window": 128000, "compression_threshold": 0.8})()
        self.project_root = "."
        self.last_response_raw = None
        self.logged_messages = []
        self.llm_calls = []

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "runner final answer",
                            }
                        }
                    ]
                }

        self.llm = _FakeLLM(self)
        self.tool_orchestrator = ToolOrchestrator(self)

    def _refresh_skills_prompt(self):
        self._skills_prompt = "skills"

    def _log_system_messages_if_needed(self, trace_logger):
        trace_logger.log_system_messages([{"role": "system", "content": "system"}])

    def _log_message_write(self, trace_logger, role, content, metadata, step=0):
        self.logged_messages.append((role, content, metadata, step))

    def _build_messages(self, history_messages):
        return [{"role": "system", "content": "system"}] + list(history_messages)

    def _get_openai_tools_for_current_mode(self):
        return []

    def _extract_content(self, raw_response):
        return raw_response["choices"][0]["message"]["content"]

    def _extract_reasoning_content(self, raw_response):
        return None

    def _extract_usage(self, raw_response):
        return {"total_tokens": 12}

    def _extract_response_meta(self, raw_response):
        return {}

    def _extract_tool_calls(self, raw_response):
        return []

    def _extract_raw_response(self, raw_response):
        return raw_response

    def _ensure_json_input(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args, None
        try:
            return json.loads(raw_args), None
        except Exception as exc:  # pragma: no cover - defensive fake
            return {}, exc

    def _execute_tool(self, tool_name, tool_input):
        raise AssertionError("No tool call expected in this test")

    def _print_context_preview(self, messages):
        raise AssertionError("Compression preview should not be used in this test")

    def _console(self, message):
        self.logged_messages.append(("console", message, {}, 0))


class _EmptyThenFinalHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "after retry"}}]},
        ]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)


class _ToolThenFinalHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{\"text\": \"hi\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "tool done"}}]},
        ]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)

    def _extract_tool_calls(self, raw_response):
        message = raw_response["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        normalized = []
        for call in calls:
            fn = call.get("function", {})
            normalized.append(
                {
                    "id": call.get("id"),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments"),
                }
            )
        return normalized

    def _execute_tool(self, tool_name, tool_input):
        return "{\"status\": \"success\", \"data\": {\"echo\": \"hi\"}}"


class _AlwaysToolHost(_ToolThenFinalHost):
    def __init__(self):
        super().__init__()
        self.max_steps = 1
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{\"text\": \"hi\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]


class _AlwaysEmptyHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": ""}}]},
        ]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)


class _CompressingHistoryManager(_FakeHistoryManager):
    def __init__(self):
        super().__init__()
        self.compacted = False

    def should_compress(self, pending_input):
        return not self.compacted

    def estimate_context_tokens(self, pending_input):
        return 200

    def get_total_usage_tokens(self):
        return 100

    def compact(self, on_event=None, return_info=False):
        self.compacted = True
        info = {"compressed": True, "summary_generated": True}
        return info if return_info else None


class _CompressingHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.history_manager = _CompressingHistoryManager()


class _InvalidArgsToolHost(_ToolThenFinalHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "tool done"}}]},
        ]


class _ExplodingToolHost(_ToolThenFinalHost):
    def _execute_tool(self, tool_name, tool_input):
        raise RuntimeError("boom")


class _RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def run(self, tool_calls, *, step, trace_logger):
        self.calls.append(("run", tool_calls, step))
        return [
            type(
                "Obs",
                (),
                {
                    "tool_name": "Echo",
                    "tool_call_id": "call_1",
                    "observation": "{\"status\": \"success\", \"data\": {\"echo\": \"hi\"}}",
                },
            )()
        ]

    def run_serial(self, tool_calls, *, step, trace_logger):
        raise AssertionError("runtime should use run(), not run_serial()")


class _BudgetedOrchestrator:
    def run(self, tool_calls, *, step, trace_logger):
        from tools.orchestrator import ToolObservation

        return [
            ToolObservation(
                tool_name="Read",
                tool_call_id="call_1",
                observation='{"status":"partial"}',
                raw_observation='{"status":"success"}',
                metadata={"budgeted": True, "reason": "single_tool_budget"},
            )
        ]


def test_runtime_runner_executes_turn_loop_and_returns_final_answer():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "runner final answer"
    assert host.history_manager.messages[0]["role"] == "user"
    assert host.history_manager.messages[-1]["role"] == "assistant"
    assert host.history_manager.last_usage == 12
    assert host.llm_calls
    assert any(event[0] == "finish" for event in host.trace_logger.events)
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_returned_final" for event in transitions)
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "completed"
        for event in host.trace_logger.events
    )


def test_runtime_runner_preprocesses_file_mentions_before_history_append():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("inspect @src/main.py", show_raw=False)

    user_content = host.history_manager.messages[0]["content"]
    assert "@src/main.py" in user_content
    assert "<system-reminder>" in user_content


def test_codeagent_run_delegates_to_runtime_runner():
    class _DummyRunner:
        def __init__(self):
            self.calls = []

        def run(self, input_text, **kwargs):
            self.calls.append((input_text, kwargs))
            return "delegated"

    agent = CodeAgent.__new__(CodeAgent)
    agent.runner = _DummyRunner()

    result = CodeAgent.run(agent, "delegate this", show_raw=True)

    assert result == "delegated"
    assert agent.runner.calls == [("delegate this", {"show_raw": True})]


def test_runtime_state_types_are_importable():
    from runtime.state import LoopState, TerminalReason, Transition, TransitionReason

    transition = Transition(reason=TransitionReason.USER_INPUT, details={"input": "hello"})
    state = LoopState(messages=[], step=1, turn_count=1, tool_choice="auto", transition=transition)

    assert state.transition.reason is TransitionReason.USER_INPUT
    assert state.transition.details == {"input": "hello"}
    assert TerminalReason.COMPLETED.value == "completed"


def test_runtime_runner_transition_logs_state_event():
    from runtime.loop import RuntimeRunner
    from runtime.state import LoopState, TransitionReason

    host = _FakeHost()
    runner = RuntimeRunner(host)
    state = LoopState(messages=[], step=1, turn_count=1, tool_choice="auto")

    next_state = runner._transition(
        state,
        TransitionReason.MODEL_RETURNED_FINAL,
        host.trace_logger,
        step=1,
        final_length=12,
    )

    assert next_state.transition.reason is TransitionReason.MODEL_RETURNED_FINAL
    assert next_state.transition.details == {"final_length": 12}
    assert (
        "state_transition",
        1,
        {
            "step": 1,
            "turn_count": 1,
            "reason": "model_returned_final",
            "message_count": 0,
            "details": {"final_length": 12},
        },
    ) in host.trace_logger.events


def test_runtime_runner_emits_user_input_transition():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "user_input" for event in transitions)


def test_runtime_runner_emits_empty_response_retry_transition():
    from runtime.loop import RuntimeRunner

    host = _EmptyThenFinalHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "after retry"
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_empty_retry" for event in transitions)


def test_runtime_runner_emits_tools_executed_transition():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "tools_executed" for event in transitions)


def test_runtime_runner_delegates_tool_execution_to_orchestrator():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    host.tool_orchestrator = _RecordingOrchestrator()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    assert host.tool_orchestrator.calls
    assert host.tool_orchestrator.calls[0][0] == "run"
    assert host.history_manager.messages[-2]["role"] == "tool"


def test_runtime_runner_preserves_invalid_param_tool_observation():
    from runtime.loop import RuntimeRunner

    host = _InvalidArgsToolHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    tool_message = host.history_manager.messages[-2]
    payload = json.loads(tool_message["content"])
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_PARAM"
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_call_parse"
        for event in host.trace_logger.events
    )


def test_runtime_runner_preserves_execution_error_tool_observation():
    from runtime.loop import RuntimeRunner

    host = _ExplodingToolHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    tool_message = host.history_manager.messages[-2]
    payload = json.loads(tool_message["content"])
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "EXECUTION_ERROR"
    assert payload["error"]["message"] == "boom"
    assert any(
        event[0] == "error" and event[2]["stage"] == "tool_execution"
        for event in host.trace_logger.events
    )


def test_runtime_runner_passes_budget_metadata_to_history():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    host.tool_orchestrator = _BudgetedOrchestrator()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    tool_message = host.history_manager.messages[-2]
    assert tool_message["metadata"]["budgeted"] is True
    assert tool_message["metadata"]["reason"] == "single_tool_budget"


def test_runtime_runner_emits_max_steps_terminal():
    from runtime.loop import RuntimeRunner

    host = _AlwaysToolHost()
    runner = RuntimeRunner(host)

    result = runner.run("loop", show_raw=False)

    assert "限定步数" in result
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "max_steps"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "state_transition" and event[2]["reason"] == "max_steps_exceeded"
        for event in host.trace_logger.events
    )


def test_runtime_runner_emits_empty_response_failed_terminal():
    from runtime.loop import RuntimeRunner

    host = _AlwaysEmptyHost()
    runner = RuntimeRunner(host)

    result = runner.run("loop", show_raw=False)

    assert "限定步数" in result
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "empty_response_failed"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] == "terminal" and event[2]["reason"] == "max_steps"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] == "state_transition" and event[2]["reason"] == "max_steps_exceeded"
        for event in host.trace_logger.events
    )


def test_runtime_runner_state_tracks_current_model_view_messages():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    final_transitions = [
        event
        for event in host.trace_logger.events
        if event[0] == "state_transition" and event[2]["reason"] == "model_returned_final"
    ]
    assert final_transitions
    assert final_transitions[-1][2]["message_count"] > 0


def test_runtime_runner_emits_context_compacted_transition():
    from runtime.loop import RuntimeRunner

    host = _CompressingHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "runner final answer"
    assert any(
        event[0] == "state_transition" and event[2]["reason"] == "context_compacted"
        for event in host.trace_logger.events
    )
