import json
import logging
from dataclasses import dataclass
from pathlib import Path

from runtime.completion import CompletionGateResult, CompletionGateVerdict
from runtime.context import ContextEngine
from runtime.evals import summarize_trace as summarize_trace_metrics
from runtime.history import Message
from runtime.loop import RuntimeRunner
from tools.context import ToolExecutionContext
from tools.executor import ToolExecutor
from tools.orchestrator import ToolOrchestrator
from tools.permissions import PermissionContext, RiskClassifier
from tools.registry import ToolRegistry


class RecordingTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, name, payload, step=0):
        self.events.append((name, step, payload))

    def log_system_messages(self, messages):
        self.events.append(("system_messages", 0, {"messages": messages}))

    def get_current_run_events(self):
        return []

    def clear_current_run_events(self):
        pass


class ScenarioHistoryManager:
    def __init__(self):
        self.messages = []

    def append_user(self, content):
        self.messages.append({"role": "user", "content": content})

    def append_assistant(self, content, metadata=None, reasoning_content=None):
        self.messages.append({"role": "assistant", "content": content, "metadata": metadata or {}})

    def append_tool(self, tool_name, raw_result, metadata=None, project_root=None):
        self.messages.append({"role": "tool", "content": raw_result, "metadata": metadata or {}})

    def get_messages(self):
        return [
            Message(content=item["content"], role=item["role"], metadata=item.get("metadata", {}))
            for item in self.messages
        ]

    def get_message_count(self):
        return len(self.messages)

    def get_rounds_count(self):
        return max(1, len(self.messages) // 2)


class ScenarioContextBuilder:
    def __init__(self):
        self.skills_prompt = ""

    def set_skills_prompt(self, prompt):
        self.skills_prompt = prompt

    def get_system_messages(self):
        return [{"role": "system", "content": "system"}]

    def get_prompt_assembly(self):
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


class BaseScenarioHost:
    def __init__(self):
        self.console_progress = False
        self.console_verbose = False
        self.logger = logging.getLogger("test.scenarios.phase0")
        self._skills_prompt = ""
        self.config = type(
            "Config",
            (),
            {"context_window": 128000, "compression_threshold": 0.8, "min_retain_rounds": 2},
        )()
        self.context_builder = ScenarioContextBuilder()
        self.context_engine = ContextEngine(
            self.context_builder,
            config=self.config,
            summary_generator=lambda messages: f"summary({len(messages)})",
        )
        self.trace_logger = RecordingTraceLogger()
        self.history_manager = ScenarioHistoryManager()
        self._run_id = 0
        self.max_steps = 3
        self.enable_agent_teams = False
        self.team_manager = None
        self.project_root = "."
        self.last_response_raw = None
        self.logged_messages = []
        self.llm_calls = []
        self.tool_orchestrator = ToolOrchestrator(self)

    def _refresh_skills_prompt(self):
        self._skills_prompt = "skills"

    def _log_system_messages_if_needed(self, trace_logger):
        trace_logger.log_system_messages([{"role": "system", "content": "system"}])

    def _log_message_write(self, trace_logger, role, content, metadata, step=0):
        self.logged_messages.append((role, content, metadata, step))

    def _get_openai_tools_for_current_mode(self):
        return []

    def _get_openai_tools_fingerprint_for_current_mode(self):
        return "tool-schema"

    def _extract_content(self, raw_response):
        return raw_response["choices"][0]["message"]["content"]

    def _extract_reasoning_content(self, raw_response):
        return None

    def _extract_usage(self, raw_response):
        return {"total_tokens": 12}

    def _extract_response_meta(self, raw_response):
        return {}

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

    def _extract_raw_response(self, raw_response):
        return raw_response

    def _ensure_json_input(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args, None
        try:
            return json.loads(raw_args), None
        except Exception as exc:
            return {}, exc

    def _execute_tool(self, tool_name, tool_input):
        return '{"status": "success", "data": {"tool": "%s"}}' % tool_name

    def _print_context_preview(self, messages):
        self.logged_messages.append(("preview", str(messages), {}, 0))

    def _console(self, message):
        self.logged_messages.append(("console", message, {}, 0))


class FinalOnlyScenarioHost(BaseScenarioHost):
    def __init__(self):
        super().__init__()

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return {"choices": [{"message": {"content": "runner final answer"}}]}

        self.llm = _FakeLLM(self)


class EmptyThenFinalScenarioHost(BaseScenarioHost):
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


class ToolThenFinalScenarioHost(BaseScenarioHost):
    def __init__(self, tool_name="Read", final_text="tool done"):
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
                                        "name": tool_name,
                                        "arguments": '{"path": "."}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": final_text}}]},
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


class ToolFailureScenarioHost(ToolThenFinalScenarioHost):
    def _execute_tool(self, tool_name, tool_input):
        raise RuntimeError(f"{tool_name} failed")


class PermissionDeniedScenarioHost(ToolThenFinalScenarioHost):
    def __init__(self):
        super().__init__(tool_name="Write")
        registry = ToolRegistry()

        def _unexpected_write(_input):
            raise AssertionError("permission denied scenario must not execute Write")

        registry.register_function("Write", "write fixture", _unexpected_write)
        classifier = RiskClassifier()
        self.tool_executor = ToolExecutor(
            registry,
            context=ToolExecutionContext(
                permission_context=PermissionContext(runtime_mode="readonly_subagent"),
                permission_decider=classifier.classify,
                project_root=self.project_root,
            ),
        )


class CompletionGateBlockedScenarioHost(BaseScenarioHost):
    def __init__(self):
        super().__init__()
        self.responses = [
            {"choices": [{"message": {"content": "tests passed, task complete"}}]},
            {"choices": [{"message": {"content": "tests passed, task complete"}}]},
        ]
        self.completion_verifier = _AlwaysBlockingVerifier()

        class _FakeLLM:
            def __init__(self, outer):
                self.outer = outer

            def invoke_raw(self, messages, tools=None, tool_choice=None):
                self.outer.llm_calls.append(
                    {"messages": messages, "tools": tools, "tool_choice": tool_choice}
                )
                return self.outer.responses.pop(0)

        self.llm = _FakeLLM(self)


class _AlwaysBlockingVerifier:
    def evaluate(self, candidate, requirements, evidence, history_messages):
        return CompletionGateResult(
            verdict=CompletionGateVerdict.FAIL,
            reasons=("missing_verification_evidence:tests",),
            blocking_feedback="Run tests before concluding.",
            passed_evidence=(),
        )


class AlwaysToolScenarioHost(ToolThenFinalScenarioHost):
    def __init__(self):
        super().__init__()
        self.max_steps = 1
        self.responses = [self.responses[0]]


class AlwaysEmptyScenarioHost(BaseScenarioHost):
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


class CompressingScenarioHost(FinalOnlyScenarioHost):
    def __init__(self):
        super().__init__()
        self.config = type(
            "Config",
            (),
            {"context_window": 1000, "compression_threshold": 0.1, "min_retain_rounds": 1},
        )()
        self.history_manager = ScenarioHistoryManager()
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


def summarize_trace(events):
    return summarize_trace_metrics(events)


def run_phase0_mock_scenarios(output_path: str | Path | None = None):
    cases = [
        ("normal_complete", FinalOnlyScenarioHost()),
        ("tool_call", ToolThenFinalScenarioHost()),
        ("completion_gate_block", CompletionGateBlockedScenarioHost()),
        ("model_recovery", EmptyThenFinalScenarioHost()),
        ("permission_deny", PermissionDeniedScenarioHost()),
        ("context_compaction", CompressingScenarioHost()),
    ]
    scenarios = []
    for scenario_name, host in cases:
        result = RuntimeRunner(host).run(scenario_name, show_raw=False)
        metrics = summarize_trace(host.trace_logger.events)
        scenarios.append(
            {
                "scenario_name": scenario_name,
                "result": result,
                "metrics": metrics,
            }
        )

    report = {
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "aggregate": {
            "permission_denied_count": sum(item["metrics"]["permission_denied_count"] for item in scenarios),
            "completion_gate_block_count": sum(item["metrics"]["completion_gate_block_count"] for item in scenarios),
            "model_recovery_count": sum(item["metrics"]["model_recovery_count"] for item in scenarios),
            "context_compaction_count": sum(item["metrics"]["context_compaction_count"] for item in scenarios),
        },
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
