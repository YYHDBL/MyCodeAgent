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


def test_runtime_runner_enforces_total_token_budget():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    host.max_total_tokens = 5

    result = RuntimeRunner(host).run("budgeted task")

    assert "限定预算" in result
    terminal = [payload for name, _step, payload in host.trace_logger.events if name == "terminal"]
    assert terminal[-1]["reason"] == "token_budget"


class _FakeTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))

    def log_system_messages(self, messages):
        self.events.append(("system_messages", 0, messages))


class _FakeTranscriptRecorder:
    def __init__(self):
        self.messages = []
        self.transitions = []
        self.tool_lifecycle = []
        self.checkpoints = []
        self.terminals = []

    def record_message(self, **payload):
        self.messages.append(payload)

    def record_state_transition(self, **payload):
        self.transitions.append(payload)

    def record_tool_lifecycle(self, **payload):
        self.tool_lifecycle.append(payload)

    def record_checkpoint(self, **payload):
        self.checkpoints.append(payload)

    def record_terminal(self, **payload):
        self.terminals.append(payload)


class _FakeHistoryManager:
    def __init__(self):
        self.messages = []

    def append_user(self, content, metadata=None):
        self.messages.append({"role": "user", "content": content, "metadata": metadata or {}})

    def append_assistant(self, content, metadata=None, reasoning_content=None):
        self.messages.append({"role": "assistant", "content": content, "metadata": metadata or {}})

    def append_tool(self, tool_name, raw_result, metadata=None, project_root=None):
        self.messages.append(
            {
                "role": "tool",
                "content": raw_result,
                "metadata": {"tool_name": tool_name, **(metadata or {})},
            }
        )

    def get_messages(self):
        from runtime.history import Message

        return [
            Message(
                content=message["content"],
                role=message["role"],
                metadata=message.get("metadata", {}),
            )
            for message in self.messages
        ]

    def get_message_count(self):
        return len(self.messages)

    def get_rounds_count(self):
        return 1

    def load_messages(self, items):
        self.messages = []
        for item in items:
            self.messages.append(
                {
                    "role": item.get("role"),
                    "content": item.get("content"),
                    "metadata": item.get("metadata", {}),
                }
            )


class _FakeContextBuilder:
    def __init__(self):
        self.skills_prompt = ""

    def set_skills_prompt(self, prompt):
        self.skills_prompt = prompt

    def get_system_messages(self):
        return [{"role": "system", "content": "system"}]

    def get_prompt_assembly(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class _Assembly:
            constitution_fingerprint: str = "constitution"
            tool_contracts_fingerprint: str = "tool-contracts"
            project_rules_fingerprint: str = "project-rules"
            runtime_signals_fingerprint: str = "runtime-signals"
            system_fingerprint: str = "system"
            stable_messages: list = None
            runtime_signal_messages: list = None
            all_system_messages: list = None

        messages = self.get_system_messages()
        return _Assembly(
            stable_messages=list(messages),
            runtime_signal_messages=[],
            all_system_messages=list(messages),
        )

    def build_messages(self, history_messages):
        return [{"role": "system", "content": "system"}] + list(history_messages)


class _FakeHost:
    def __init__(self):
        from runtime.context import ContextEngine
        from tools.orchestrator import ToolOrchestrator

        self.console_progress = False
        self.console_verbose = False
        self.logger = logging.getLogger("test.runtime.loop")
        self._skills_prompt = ""
        self.config = type(
            "Config",
            (),
            {"context_window": 128000, "compression_threshold": 0.8, "min_retain_rounds": 2},
        )()
        self.context_builder = _FakeContextBuilder()
        self.context_engine = ContextEngine(
            self.context_builder,
            config=self.config,
            summary_generator=lambda messages: f"summary({len(messages)})",
        )
        self.trace_logger = _FakeTraceLogger()
        self.history_manager = _FakeHistoryManager()
        self._run_id = 0
        self.max_steps = 3
        self.enable_agent_teams = False
        self.team_manager = None
        self.project_root = "."
        self.last_response_raw = None
        self.logged_messages = []
        self.llm_calls = []
        self.transcript_recorder = None
        self.responses = None

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                if self.outer.responses:
                    return self.outer.responses.pop(0)
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

    def _get_openai_tools_fingerprint_for_current_mode(self):
        return "tools"

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


class _DeniedToolThenFinalHost(_ToolThenFinalHost):
    def _execute_tool(self, tool_name, tool_input):
        return json.dumps(
            {
                "status": "error",
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "blocked by permission core",
                    "details": {
                        "permission": {
                            "tool_name": tool_name,
                            "risk": "high",
                            "action": "deny",
                            "reason": "readonly_subagent blocks writes",
                            "policy_source": "permission_core",
                            "input_summary": json.dumps(tool_input, ensure_ascii=False, sort_keys=True),
                        }
                    },
                },
                "data": {},
            }
        )


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


class _ApiErrorHost(_FakeHost):
    def __init__(self):
        super().__init__()

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                raise RuntimeError("rate limit exceeded")

        self.llm = _FakeLLM(self)


class _MaxOutputWithToolCallsHost(_ToolThenFinalHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {
                "choices": [
                    {
                        "message": {
                            "content": "partial",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "Echo",
                                        "arguments": "{\"text\": \"should-not-run\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]

        class _FailIfToolRuns:
            def run(self, tool_calls, *, step, trace_logger):
                raise AssertionError("truncated model output must not execute tool calls")

        self.tool_orchestrator = _FailIfToolRuns()

    def _extract_response_meta(self, raw_response):
        return {"finish_reason": "length"}


class _ReactiveCompactContextEngine:
    def __init__(self):
        self.compact_calls = []
        self.build_calls = []
        self.last_usage_tokens = 0
        self.total_usage_tokens = 0

    def compact_if_needed(self, **kwargs):
        return {"compacted": False, "reason": "budget_ok"}

    def build_model_view(self, *, history_manager, pending_input="", step=0, trace_logger=None):
        self.build_calls.append(step)
        if trace_logger:
            trace_logger.log_event(
                "model_view_build",
                {
                    "message_count": 2,
                    "system_message_count": 1,
                    "history_message_count": 1,
                    "source_message_count": 1,
                    "estimated_chars": len(pending_input or ""),
                    "projection_mode": "full",
                    "compact_checkpoint_id": None,
                    "warnings": [],
                },
                step=step,
            )
        return type(
            "ModelView",
            (),
            {
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": pending_input},
                ],
                "history_message_count": 1,
                "source_message_count": 1,
                "projection_mode": "full",
            },
        )()

    def record_usage(self, total_tokens):
        if total_tokens is None:
            return
        self.last_usage_tokens = int(total_tokens)
        self.total_usage_tokens += int(total_tokens)

    def reactive_compact(self, *, history_manager, pending_input, step=0, trace_logger=None):
        self.compact_calls.append({"pending_input": pending_input, "step": step})
        info = {
            "compacted": len(self.compact_calls) == 1,
            "reason": "reactive_prompt_too_long",
            "checkpoint_id": f"ckpt-{len(self.compact_calls)}",
            "messages_compacted": 1,
            "retain_start_idx": 0,
        }
        if trace_logger:
            trace_logger.log_event("context_compaction_completed", info, step=step)
        return info


class _PromptTooLongHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.context_engine = _ReactiveCompactContextEngine()

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                raise RuntimeError("prompt too long for model context window")

        self.llm = _FakeLLM(self)


class _CompressingHistoryManager(_FakeHistoryManager):
    def __init__(self):
        super().__init__()


class _CompressingHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.config = type(
            "Config",
            (),
            {
                "context_window": 1000,
                "compression_threshold": 0.1,
                "min_retain_rounds": 1,
            },
        )()
        from runtime.context import ContextEngine

        self.history_manager = _CompressingHistoryManager()
        self.context_engine = ContextEngine(
            self.context_builder,
            config=self.config,
            summary_generator=lambda messages: f"summary({len(messages)})",
        )
        self.context_engine.record_usage(900)
        self.history_manager.append_user("old q")
        self.history_manager.append_assistant("old a")
        self.history_manager.append_user("older q")
        self.history_manager.append_assistant("older a")

    def _extract_tool_calls(self, raw_response):
        return _ToolThenFinalHost._extract_tool_calls(self, raw_response)

    def _execute_tool(self, tool_name, tool_input):
        return "{\"status\": \"success\", \"data\": {\"echo\": \"hi\"}}"


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


class _SimpleQuestionHost(_FakeHost):
    pass


class _FinalWithoutEvidenceHost(_FakeHost):
    def __init__(self):
        super().__init__()
        self.responses = [{"choices": [{"message": {"content": "tests passed, task complete"}}]}]

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses[0]

        self.llm = _FakeLLM(self)


class _BashVerificationHost(_FakeHost):
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
                                        "name": "Bash",
                                        "arguments": "{\"command\": \".venv/bin/python -m pytest -q\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "tests passed, task complete"}}]},
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
        return _ToolThenFinalHost._extract_tool_calls(self, raw_response)

    def _execute_tool(self, tool_name, tool_input):
        return json.dumps(
            {
                "status": "success",
                "data": {"exit_code": 0},
                "text": "Command succeeded: .venv/bin/python -m pytest -q",
                "context": {"params_input": tool_input},
            }
        )


class _VerificationInvalidatedByWriteHost(_BashVerificationHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            self.responses[0],
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "function": {
                                        "name": "Write",
                                        "arguments": "{\"path\": \"a.txt\", \"content\": \"x\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "tests passed earlier, task complete"}}]},
        ]

    def _execute_tool(self, tool_name, tool_input):
        if tool_name == "Bash":
            return super()._execute_tool(tool_name, tool_input)
        return json.dumps(
            {
                "status": "success",
                "data": {"path": tool_input.get("path")},
                "text": "file written",
                "context": {"params_input": tool_input},
            }
        )


class _TodoBlockingHost(_FakeHost):
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
                                        "name": "TodoWrite",
                                        "arguments": "{\"summary\": \"work\", \"todos\": [{\"content\": \"do thing\", \"status\": \"in_progress\"}]}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "done"}}]},
            {"choices": [{"message": {"content": "done again"}}]},
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
        return _ToolThenFinalHost._extract_tool_calls(self, raw_response)

    def _execute_tool(self, tool_name, tool_input):
        return json.dumps(
            {
                "status": "success",
                "data": {
                    "todos": [{"id": "t1", "content": "do thing", "status": "in_progress"}],
                    "summary": "work",
                    "stats": {"total": 1, "pending": 0, "in_progress": 1, "completed": 0, "cancelled": 0},
                },
                "text": "todo updated",
                "context": {"params_input": tool_input},
            }
        )


def test_runtime_runner_executes_turn_loop_and_returns_final_answer():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "runner final answer"
    assert host.history_manager.messages[0]["role"] == "user"
    assert host.history_manager.messages[-1]["role"] == "assistant"
    assert host.context_engine.last_usage_tokens == 12
    assert host.llm_calls
    assert any(event[0] == "finish" for event in host.trace_logger.events)
    transitions = [event for event in host.trace_logger.events if event[0] == "state_transition"]
    assert any(event[2]["reason"] == "model_returned_final" for event in transitions)
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "completed"
        for event in host.trace_logger.events
    )


def test_permission_denial_is_appended_to_history_and_does_not_break_loop():
    from runtime.loop import RuntimeRunner

    host = _DeniedToolThenFinalHost()
    runner = RuntimeRunner(host)

    result = runner.run("write something", show_raw=False)

    assert result == "tool done"
    tool_messages = [message for message in host.history_manager.messages if message["role"] == "tool"]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0]["content"])
    assert payload["error"]["code"] == "PERMISSION_DENIED"


def test_permission_trace_event_is_preserved_in_runtime_history_flow():
    from runtime.loop import RuntimeRunner

    class _PermissionTraceOrchestrator(_RecordingOrchestrator):
        def run(self, tool_calls, *, step, trace_logger):
            trace_logger.log_event(
                "permission_decision",
                {
                    "tool_name": "Write",
                    "risk": "high",
                    "action": "deny",
                    "reason": "readonly_subagent blocks writes",
                    "policy_source": "permission_core",
                    "input_summary": '{"path":"a.txt"}',
                },
                step=step,
            )
            return [
                type(
                    "Obs",
                    (),
                    {
                        "tool_name": "Write",
                        "tool_call_id": "call_1",
                        "observation": '{"status":"error","error":{"code":"PERMISSION_DENIED","message":"blocked"}}',
                        "metadata": {"permission_action": "deny"},
                    },
                )()
            ]

    host = _ToolThenFinalHost()
    host.tool_orchestrator = _PermissionTraceOrchestrator()
    runner = RuntimeRunner(host)

    result = runner.run("write something", show_raw=False)

    assert result == "tool done"
    assert any(
        event[0] == "permission_decision"
        and event[2]["tool_name"] == "Write"
        for event in host.trace_logger.events
    )


def test_runtime_runner_builds_model_view_through_context_engine():
    from runtime.loop import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    assert any(event[0] == "model_view_build" for event in host.trace_logger.events)
    assert host.llm_calls[0]["messages"][0] == {"role": "system", "content": "system"}
    assert host.llm_calls[0]["messages"][1]["role"] == "user"


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
    assert any(
        event[0] == "model_error_classified" and event[2]["kind"] == "empty_response"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "model_recovery_attempted" and event[2]["kind"] == "empty_response"
        for event in host.trace_logger.events
    )


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
    assert any(
        event[0] == "model_recovery_failed" and event[2]["kind"] == "empty_response"
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


def test_runtime_runner_records_transcript_messages_transitions_and_terminal():
    from runtime.loop import RuntimeRunner

    host = _ToolThenFinalHost()
    host.transcript_recorder = _FakeTranscriptRecorder()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "tool done"
    assert [item["role"] for item in host.transcript_recorder.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert any(item["reason"] == "model_returned_tool_calls" for item in host.transcript_recorder.transitions)
    assert any(item["reason"] == "tools_executed" for item in host.transcript_recorder.transitions)
    assert host.transcript_recorder.terminals[-1]["reason"] == "completed"


def test_runtime_runner_records_tool_lifecycle_and_checkpoints_in_transcript():
    from runtime.loop import RuntimeRunner

    host = _CompressingHost()
    host.responses = [
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
    host.transcript_recorder = _FakeTranscriptRecorder()
    runner = RuntimeRunner(host)

    runner.run("hello world", show_raw=False)

    assert any(item["status"] == "requested" for item in host.transcript_recorder.tool_lifecycle)
    assert any(item["status"] == "started" for item in host.transcript_recorder.tool_lifecycle)
    assert any(item["status"] == "completed" for item in host.transcript_recorder.tool_lifecycle)
    assert host.transcript_recorder.checkpoints
    checkpoint_payload = host.transcript_recorder.checkpoints[-1]["payload"]
    assert checkpoint_payload["summary"].startswith("summary(")
    assert (
        checkpoint_payload["source_message_count"]
        == host.context_engine.compact_store.active_checkpoint.source_message_count
    )
    assert checkpoint_payload["created_at"]


def test_runtime_runner_notifies_host_when_context_compacts():
    from runtime.loop import RuntimeRunner

    host = _CompressingHost()
    compacted = []

    def on_context_compacted(info, messages):
        compacted.append((info, messages))

    host._on_context_compacted = on_context_compacted

    RuntimeRunner(host).run("hello world", show_raw=False)

    assert compacted
    assert compacted[-1][0]["compacted"] is True
    assert compacted[-1][1]


def test_resume_restored_history_is_still_projected_by_context_engine(tmp_path):
    from runtime.transcript import ResumeLoader, TranscriptStore

    path = tmp_path / "transcript.jsonl"
    store = TranscriptStore(path, session_id="session-1")
    store.append_message(run_id="run-1", step=0, role="user", content="hello")
    store.append_message(run_id="run-1", step=1, role="assistant", content="done")

    host = _FakeHost()
    resume = ResumeLoader(store).load(run_id="run-1")
    host.history_manager.load_messages(resume.history_messages)

    view = host.context_engine.build_model_view(history_manager=host.history_manager, pending_input="", step=0)

    assert view.messages[0] == {"role": "system", "content": "system"}
    assert [item["role"] for item in view.messages[1:]] == ["user", "assistant"]


def test_runtime_runner_simple_question_can_complete_without_verification():
    from runtime.loop import RuntimeRunner

    host = _SimpleQuestionHost()
    runner = RuntimeRunner(host)

    result = runner.run("what is 2+2?", show_raw=False)

    assert result == "runner final answer"
    assert any(event[0] == "completion_candidate" for event in host.trace_logger.events)
    assert any(
        event[0] == "completion_gate_verdict" and event[2]["verdict"] == "pass"
        for event in host.trace_logger.events
    )
    candidate_index = next(
        index for index, event in enumerate(host.trace_logger.events) if event[0] == "completion_candidate"
    )
    terminal_index = next(
        index for index, event in enumerate(host.trace_logger.events) if event[0] == "terminal"
    )
    assert candidate_index < terminal_index


def test_runtime_runner_requires_test_evidence_when_user_explicitly_requests_tests():
    from runtime.loop import RuntimeRunner

    host = _FinalWithoutEvidenceHost()
    runner = RuntimeRunner(host)

    result = runner.run("make the fix and run tests", show_raw=False)

    assert "无法在限定步数内完成" in result
    assert any(
        event[0] == "completion_gate_verdict" and event[2]["verdict"] == "fail"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "state_transition" and event[2]["reason"] == "stop_hook_blocking"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "completion_gate_blocked"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] in {"model_error_classified", "model_recovery_attempted", "model_recovery_failed"}
        for event in host.trace_logger.events
    )


def test_runtime_runner_passes_completion_gate_with_valid_verification_evidence():
    from runtime.loop import RuntimeRunner

    host = _BashVerificationHost()
    runner = RuntimeRunner(host)

    result = runner.run("make the fix and run tests", show_raw=False)

    assert result == "tests passed, task complete"
    assert any(
        event[0] == "completion_gate_verdict" and event[2]["verdict"] == "pass"
        for event in host.trace_logger.events
    )
    assert any(event[0] == "verification_evidence" for event in host.trace_logger.events)


def test_runtime_runner_can_finish_unverified_when_user_marks_verification_optional():
    from runtime.loop import RuntimeRunner

    host = _FinalWithoutEvidenceHost()
    runner = RuntimeRunner(host)

    result = runner.run("make the fix and run tests if possible", show_raw=False)

    assert result == "tests passed, task complete"
    assert any(
        event[0] == "completion_gate_verdict" and event[2]["verdict"] == "unverified"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "completed_unverified"
        for event in host.trace_logger.events
    )


def test_runtime_runner_invalidates_old_verification_after_file_modification():
    from runtime.loop import RuntimeRunner

    host = _VerificationInvalidatedByWriteHost()
    runner = RuntimeRunner(host)

    result = runner.run("make the fix and run tests", show_raw=False)

    assert "无法在限定步数内完成" in result
    evidence_events = [event for event in host.trace_logger.events if event[0] == "verification_evidence"]
    assert evidence_events
    assert any(event[2]["valid"] is False for event in evidence_events)
    verdict_events = [event for event in host.trace_logger.events if event[0] == "completion_gate_verdict"]
    assert verdict_events[-1][2]["reasons"] == ["verification_invalid:tests"]


def test_runtime_runner_blocks_when_todo_remains_incomplete():
    from runtime.loop import RuntimeRunner

    host = _TodoBlockingHost()
    runner = RuntimeRunner(host)

    result = runner.run("finish this task", show_raw=False)

    assert "无法在限定步数内完成" in result
    requirement_events = [event for event in host.trace_logger.events if event[0] == "completion_requirements"]
    assert requirement_events
    assert requirement_events[-1][2]["has_incomplete_todos"] is True
    verdict_events = [event for event in host.trace_logger.events if event[0] == "completion_gate_verdict"]
    assert verdict_events[-1][2]["reasons"] == ["incomplete_todos"]


def test_runtime_runner_api_error_does_not_enter_completion_gate():
    from runtime.loop import RuntimeRunner

    host = _ApiErrorHost()
    runner = RuntimeRunner(host)

    result = runner.run("do work", show_raw=False)

    assert "限定步数" in result
    assert any(
        event[0] == "model_error_classified" and event[2]["kind"] == "api_error"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "model_error"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] in {"completion_candidate", "completion_requirements", "completion_gate_verdict"}
        for event in host.trace_logger.events
    )


def test_runtime_runner_max_output_with_tool_calls_does_not_execute_tools():
    from runtime.loop import RuntimeRunner

    host = _MaxOutputWithToolCallsHost()
    runner = RuntimeRunner(host)

    result = runner.run("do work", show_raw=False)

    assert "限定步数" in result
    assert any(
        event[0] == "model_error_classified" and event[2]["kind"] == "max_output"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "terminal" and event[2]["reason"] == "model_error"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] == "state_transition" and event[2]["reason"] == "model_returned_tool_calls"
        for event in host.trace_logger.events
    )
    assert not any(event[0] == "completion_candidate" for event in host.trace_logger.events)


def test_runtime_runner_prompt_too_long_attempts_single_reactive_compact():
    from runtime.loop import RuntimeRunner

    host = _PromptTooLongHost()
    runner = RuntimeRunner(host)

    result = runner.run("do work", show_raw=False)

    assert "限定步数" in result
    assert len(host.context_engine.compact_calls) == 1
    assert any(
        event[0] == "model_error_classified" and event[2]["kind"] == "prompt_too_long"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "model_recovery_attempted" and event[2]["kind"] == "prompt_too_long"
        for event in host.trace_logger.events
    )
    assert any(
        event[0] == "model_recovery_failed" and event[2]["kind"] == "prompt_too_long"
        for event in host.trace_logger.events
    )
    assert not any(
        event[0] in {"completion_candidate", "completion_requirements", "completion_gate_verdict"}
        for event in host.trace_logger.events
    )
