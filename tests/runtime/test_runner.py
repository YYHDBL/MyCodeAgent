import logging

from runtime.agent_host import CodeAgent


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


class _FakeContextBuilder:
    def __init__(self):
        self.skills_prompt = ""

    def set_skills_prompt(self, prompt):
        self.skills_prompt = prompt


class _FakeHost:
    def __init__(self):
        self.console_progress = False
        self.console_verbose = False
        self.logger = logging.getLogger("test.runtime.runner")
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

    def _execute_tool(self, tool_name, tool_input):
        raise AssertionError("No tool call expected in this test")

    def _print_context_preview(self, messages):
        raise AssertionError("Compression preview should not be used in this test")

    def _console(self, message):
        self.logged_messages.append(("console", message, {}, 0))


def test_runtime_runner_executes_turn_loop_and_returns_final_answer():
    from runtime.runner import RuntimeRunner

    host = _FakeHost()
    runner = RuntimeRunner(host)

    result = runner.run("hello world", show_raw=False)

    assert result == "runner final answer"
    assert host.history_manager.messages[0]["role"] == "user"
    assert host.history_manager.messages[-1]["role"] == "assistant"
    assert host.history_manager.last_usage == 12
    assert host.llm_calls
    assert any(event[0] == "finish" for event in host.trace_logger.events)


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
