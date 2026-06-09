"""Restricted subagents built on the canonical RuntimeRunner."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.config import Config
from core.llm import HelloAgentsLLM
from extensions.tracing import create_trace_logger
from runtime.completion import (
    CompletionCandidate,
    CompletionGateResult,
    CompletionGateVerdict,
    CompletionRequirements,
    DeterministicCompletionVerifier,
    VerificationEvidence,
)
from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.loop import RuntimeRunner
from runtime.prompt_builder import ContextBuilder
from runtime.session_memory import SessionMemory, SessionMemoryManager
from runtime.transcript import TranscriptRecorder, TranscriptStore
from tools.context import ToolExecutionContext
from tools.executor import ToolExecutor
from tools.orchestrator import ToolOrchestrator
from tools.permissions import PermissionContext, RiskClassifier
from tools.registry import ToolRegistry


READONLY_TOOLS = frozenset({"LS", "Glob", "Grep", "Read"})

EXPLORE_SYSTEM_PROMPT = """You are an Explore Agent.
Inspect the repository with read-only tools and return exactly one JSON object:
{"status":"completed|partial","summary":"...","findings":["..."],
"evidence":["relative/path.py:line"],"unresolved_questions":["..."]}.
Do not use markdown fences. Do not modify files, execute shell commands, ask the user,
or delegate to another agent."""

VERIFICATION_SYSTEM_PROMPT = """You are a Verification Agent.
Independently assess the supplied completion candidate using read-only repository tools.
Return exactly one JSON object:
{"verdict":"PASS|FAIL|PARTIAL|UNVERIFIED","reasons":["..."],
"findings":["..."],"evidence":["relative/path.py:line"]}.
Do not use markdown fences. Never modify files or delegate to another agent."""


class SubagentStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class VerificationVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    system_prompt: str
    tool_allowlist: frozenset[str]
    max_steps: int
    context_token_budget: int
    total_token_budget: int
    model_choice: str
    context_source_policy: str
    completion_policy: str
    result_contract: str
    recursive_subagents: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.system_prompt:
            raise ValueError("runtime profile requires name and system prompt")
        if self.max_steps <= 0 or self.context_token_budget <= 0 or self.total_token_budget <= 0:
            raise ValueError("runtime profile budgets must be positive")
        if self.model_choice not in {"main", "light"}:
            raise ValueError("runtime profile model choice must be main or light")
        if self.recursive_subagents or "Task" in self.tool_allowlist:
            raise ValueError("formal subagent profiles cannot recurse")
        forbidden = {"Write", "Edit", "MultiEdit", "Bash", "AskUser"}
        if forbidden & self.tool_allowlist:
            raise ValueError("formal subagent profiles must be strictly read-only")


EXPLORE_PROFILE = RuntimeProfile(
    name="explore",
    system_prompt=EXPLORE_SYSTEM_PROMPT,
    tool_allowlist=READONLY_TOOLS,
    max_steps=12,
    context_token_budget=16_000,
    total_token_budget=32_000,
    model_choice="light",
    context_source_policy="self_contained_task_and_structured_context",
    completion_policy="structured_result",
    result_contract="ExploreResult",
)

VERIFICATION_PROFILE = RuntimeProfile(
    name="verification",
    system_prompt=VERIFICATION_SYSTEM_PROMPT,
    tool_allowlist=READONLY_TOOLS,
    max_steps=10,
    context_token_budget=20_000,
    total_token_budget=40_000,
    model_choice="main",
    context_source_policy="completion_candidate_requirements_evidence",
    completion_policy="structured_result",
    result_contract="VerificationResult",
)

RUNTIME_PROFILES = {
    EXPLORE_PROFILE.name: EXPLORE_PROFILE,
    VERIFICATION_PROFILE.name: VERIFICATION_PROFILE,
}


@dataclass(frozen=True)
class SubagentRequest:
    profile_name: str
    task: str
    structured_context: dict[str, Any] = field(default_factory=dict)
    model_choice: str | None = None
    parent_session_id: str | None = None
    parent_run_id: str | None = None


@dataclass(frozen=True)
class ExploreResult:
    status: SubagentStatus
    summary: str
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    tool_usage: dict[str, int] = field(default_factory=dict)
    terminal_reason: str = "unknown"

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        tool_usage: dict[str, int],
        terminal_reason: str,
    ) -> "ExploreResult":
        payload = _parse_json_object(raw)
        status = SubagentStatus(str(payload.get("status", "")).lower())
        if status not in {SubagentStatus.COMPLETED, SubagentStatus.PARTIAL}:
            raise ValueError("ExploreResult status must be completed or partial")
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("ExploreResult requires summary")
        return cls(
            status=status,
            summary=summary.strip(),
            findings=_string_tuple(payload.get("findings")),
            evidence=_string_tuple(payload.get("evidence")),
            unresolved_questions=_string_tuple(payload.get("unresolved_questions")),
            tool_usage=dict(tool_usage),
            terminal_reason=terminal_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class VerificationResult:
    verdict: VerificationVerdict
    reasons: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    child_session_id: str | None = None
    child_run_id: str | None = None
    terminal_reason: str = "unknown"
    tool_usage: dict[str, int] = field(default_factory=dict)
    token_usage: int = 0

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        child_session_id: str | None = None,
        child_run_id: str | None = None,
        terminal_reason: str,
        tool_usage: dict[str, int] | None = None,
        token_usage: int = 0,
    ) -> "VerificationResult":
        payload = _parse_json_object(raw)
        verdict = VerificationVerdict(str(payload.get("verdict", "")).upper())
        return cls(
            verdict=verdict,
            reasons=_string_tuple(payload.get("reasons")),
            findings=_string_tuple(payload.get("findings")),
            evidence=_string_tuple(payload.get("evidence")),
            child_session_id=child_session_id,
            child_run_id=child_run_id,
            terminal_reason=terminal_reason,
            tool_usage=dict(tool_usage or {}),
            token_usage=token_usage,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verdict"] = self.verdict.value
        return payload


@dataclass(frozen=True)
class SubagentLaunchResult:
    status: SubagentStatus
    profile_name: str
    child_session_id: str
    child_run_id: str
    result: ExploreResult | VerificationResult | None
    model_used: str = "main"
    terminal_reason: str = "unknown"
    error: str | None = None
    elapsed_ms: int = 0
    tool_usage: dict[str, int] = field(default_factory=dict)
    token_usage: int = 0


SubagentResult = SubagentLaunchResult


class _RecordingTrace:
    def __init__(self, delegate: Any):
        self.delegate = delegate
        self.events: list[tuple[str, int, dict[str, Any]]] = []
        self.session_id = str(getattr(delegate, "session_id", f"child-{uuid.uuid4().hex}"))

    def log_event(self, name: str, payload: dict[str, Any], step: int = 0) -> None:
        self.events.append((name, step, payload))
        self.delegate.log_event(name, payload, step=step)

    def log_system_messages(self, messages: list[dict[str, Any]]) -> None:
        self.delegate.log_system_messages(messages)

    def finalize(self) -> None:
        self.delegate.finalize()


class _SubagentRuntimeHost:
    def __init__(
        self,
        *,
        profile: RuntimeProfile,
        llm: Any,
        registry: ToolRegistry,
        project_root: Path,
        trace_logger: Any,
    ):
        self.profile = profile
        self.llm = llm
        self.tool_registry = registry
        self.project_root = str(project_root)
        self.config = Config.from_env().model_copy(
            update={
                "context_window": profile.context_token_budget,
                "show_react_steps": False,
                "show_progress": False,
            }
        )
        self.max_steps = profile.max_steps
        self.max_total_tokens = profile.total_token_budget
        self.console_progress = False
        self.console_verbose = False
        self.logger = logging.getLogger(f"runtime.subagent.{profile.name}")
        self.last_response_raw = None
        self._skills_prompt = ""
        self._run_id = 0
        self._active_transcript_run_id = None
        self._system_messages_logged = False
        self.enable_agent_teams = False
        self.team_manager = None
        self.history_manager = HistoryManager(config=self.config)
        self.context_builder = ContextBuilder(
            tool_registry=registry,
            project_root=self.project_root,
            system_prompt_override=profile.system_prompt,
            mcp_tools_prompt="",
            skills_prompt="",
        )
        self.context_engine = ContextEngine(
            self.context_builder,
            config=self.config,
            summary_generator=lambda messages: f"Read-only child summary ({len(messages)} messages)",
        )
        self.trace_logger = trace_logger
        transcript_session = f"subagent-{trace_logger.session_id}"
        transcript_path = project_root / "memory" / "transcripts" / f"transcript-{transcript_session}.jsonl"
        self.transcript_store = TranscriptStore(transcript_path, session_id=transcript_session)
        self.session_memory_manager = SessionMemoryManager(on_update=self._apply_session_memory)
        self.session_memory = SessionMemory()
        self.transcript_recorder = TranscriptRecorder(
            self.transcript_store,
            on_recorded=self.session_memory_manager.ingest_event,
        )
        permission_context = PermissionContext(runtime_mode="readonly_subagent")
        self.tool_executor = ToolExecutor(
            registry,
            context=ToolExecutionContext(
                permission_decider=RiskClassifier().classify,
                permission_context=permission_context,
                project_root=self.project_root,
            ),
        )
        self.tool_orchestrator = ToolOrchestrator(self)
        self.completion_verifier = _StructuredResultCompletionVerifier(profile)

    def _apply_session_memory(self, memory: SessionMemory) -> None:
        self.session_memory = memory
        self.context_engine.set_session_memory(memory)

    def _refresh_skills_prompt(self) -> None:
        self._skills_prompt = ""

    def _log_system_messages_if_needed(self, trace_logger) -> None:
        if not self._system_messages_logged:
            trace_logger.log_system_messages(self.context_builder.get_system_messages())
            self._system_messages_logged = True

    def _log_message_write(self, *args, **kwargs) -> None:
        return None

    def _get_openai_tools_for_current_mode(self) -> list[dict[str, Any]]:
        return self.tool_registry.get_openai_tools()

    def _ensure_json_input(self, raw: Any):
        if isinstance(raw, dict):
            return raw, None
        try:
            return json.loads(raw or "{}"), None
        except Exception as exc:
            return None, exc

    @staticmethod
    def _extract_content(raw: Any) -> str:
        message = _response_message(raw)
        content = _attr(message, "content") or ""
        if isinstance(content, list):
            return "".join(str(_attr(part, "text") or "") for part in content)
        return str(content)

    @staticmethod
    def _extract_reasoning_content(raw: Any) -> str | None:
        return _attr(_response_message(raw), "reasoning_content")

    @staticmethod
    def _extract_tool_calls(raw: Any) -> list[dict[str, Any]]:
        message = _response_message(raw)
        calls = _attr(message, "tool_calls") or []
        result = []
        for call in calls:
            function = _attr(call, "function") or {}
            result.append(
                {
                    "id": _attr(call, "id"),
                    "name": _attr(function, "name") or _attr(call, "name"),
                    "arguments": _attr(function, "arguments") or _attr(call, "arguments") or {},
                }
            )
        return result

    @staticmethod
    def _extract_usage(raw: Any) -> dict[str, Any]:
        usage = _attr(raw, "usage") or {}
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        return dict(usage) if isinstance(usage, dict) else {}

    @staticmethod
    def _extract_response_meta(raw: Any) -> dict[str, Any]:
        choices = _attr(raw, "choices") or []
        choice = choices[0] if choices else {}
        return {"finish_reason": _attr(choice, "finish_reason")}

    @staticmethod
    def _extract_raw_response(raw: Any) -> Any:
        return raw.model_dump() if hasattr(raw, "model_dump") else raw


class SubagentLauncher:
    def __init__(
        self,
        *,
        project_root: Path,
        main_llm: Any,
        tool_registry: ToolRegistry,
        light_llm: Any = None,
        parent_trace_logger: Any = None,
        parent_history_manager: Any = None,
        parent_context_engine: Any = None,
        parent_host: Any = None,
    ):
        self.project_root = Path(project_root)
        self.main_llm = main_llm
        self.light_llm = light_llm
        self.tool_registry = tool_registry
        self.parent_trace_logger = parent_trace_logger
        self.parent_history_manager = parent_history_manager
        self.parent_context_engine = parent_context_engine
        self.parent_host = parent_host

    def build_registry(self, profile: RuntimeProfile) -> ToolRegistry:
        filtered = ToolRegistry()
        for tool in self.tool_registry.get_all_tools():
            if tool.name in profile.tool_allowlist:
                filtered.register_tool(tool)
        return filtered

    def launch(self, request: SubagentRequest) -> SubagentLaunchResult:
        started = time.monotonic()
        profile = RUNTIME_PROFILES.get(request.profile_name)
        if profile is None:
            raise ValueError(f"unsupported runtime profile: {request.profile_name}")
        requested_model = request.model_choice or profile.model_choice
        if requested_model not in {"main", "light"}:
            raise ValueError(f"unsupported subagent model choice: {requested_model}")
        llm, model_choice = self._select_llm(requested_model)
        child_trace = _RecordingTrace(create_trace_logger())
        child_session_id = child_trace.session_id
        child_run_id = "run-1"
        self._parent_event(
            "subagent_requested",
            request,
            profile,
            child_session_id=child_session_id,
            child_run_id=child_run_id,
            model=model_choice,
        )
        self._parent_event(
            "subagent_started",
            request,
            profile,
            child_session_id=child_session_id,
            child_run_id=child_run_id,
            model=model_choice,
        )
        try:
            host = _SubagentRuntimeHost(
                profile=profile,
                llm=llm,
                registry=self.build_registry(profile),
                project_root=self.project_root,
                trace_logger=child_trace,
            )
            prompt = _render_request(request)
            raw_result = RuntimeRunner(host).run(prompt)
            terminal_reason, tool_usage, token_usage = _child_metrics(child_trace.events)
            if terminal_reason == "unknown" and raw_result:
                terminal_reason = "completed"
            if terminal_reason not in {"completed", "completed_unverified"}:
                raise ValueError(f"child terminal reason: {terminal_reason}")
            if profile.result_contract == "ExploreResult":
                structured = ExploreResult.from_json(
                    raw_result,
                    tool_usage=tool_usage,
                    terminal_reason=terminal_reason,
                )
                status = structured.status
                verdict = structured.status.value
            else:
                structured = VerificationResult.from_json(
                    raw_result,
                    child_session_id=child_session_id,
                    child_run_id=child_run_id,
                    terminal_reason=terminal_reason,
                    tool_usage=tool_usage,
                    token_usage=token_usage,
                )
                status = (
                    SubagentStatus.COMPLETED
                    if structured.verdict is VerificationVerdict.PASS
                    else SubagentStatus.UNVERIFIED
                    if structured.verdict is VerificationVerdict.UNVERIFIED
                    else SubagentStatus.PARTIAL
                )
                verdict = structured.verdict.value
            elapsed_ms = int((time.monotonic() - started) * 1000)
            result = SubagentLaunchResult(
                status=status,
                profile_name=profile.name,
                child_session_id=child_session_id,
                child_run_id=child_run_id,
                result=structured,
                model_used=model_choice,
                terminal_reason=terminal_reason,
                elapsed_ms=elapsed_ms,
                tool_usage=tool_usage,
                token_usage=token_usage,
            )
            self._parent_event(
                "subagent_completed",
                request,
                profile,
                child_session_id=child_session_id,
                child_run_id=child_run_id,
                model=model_choice,
                terminal_reason=terminal_reason,
                tool_usage=tool_usage,
                token_usage=token_usage,
                verdict=verdict,
                elapsed_ms=elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._parent_event(
                "subagent_failed",
                request,
                profile,
                child_session_id=child_session_id,
                child_run_id=child_run_id,
                model=model_choice,
                terminal_reason="runtime_error",
                elapsed_ms=elapsed_ms,
                error=str(exc),
            )
            return SubagentLaunchResult(
                status=SubagentStatus.FAILED,
                profile_name=profile.name,
                child_session_id=child_session_id,
                child_run_id=child_run_id,
                result=None,
                model_used=model_choice,
                terminal_reason="runtime_error",
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
        finally:
            child_trace.finalize()

    def _select_llm(self, requested_model: str) -> tuple[Any, str]:
        if requested_model == "light":
            if self.light_llm is None:
                self.light_llm = _create_light_llm()
            if self.light_llm is not None:
                return self.light_llm, "light"
        return self.main_llm, "main"

    def _parent_event(
        self,
        name: str,
        request: SubagentRequest,
        profile: RuntimeProfile,
        **payload: Any,
    ) -> None:
        if self.parent_trace_logger is None:
            return
        parent_session_id = request.parent_session_id or str(
            getattr(self.parent_trace_logger, "session_id", "")
        )
        parent_run_id = request.parent_run_id or str(
            getattr(self.parent_host, "_active_transcript_run_id", "") or ""
        )
        self.parent_trace_logger.log_event(
            name,
            {
                "parent_session_id": parent_session_id,
                "parent_run_id": parent_run_id,
                "profile": profile.name,
                "max_steps": profile.max_steps,
                "context_token_budget": profile.context_token_budget,
                "total_token_budget": profile.total_token_budget,
                **payload,
            },
            step=0,
        )


class SubagentCompletionVerifier:
    """Run deterministic checks first, then an optional readonly verifier child."""

    def __init__(self, launcher: SubagentLauncher):
        self.launcher = launcher
        self.deterministic = DeterministicCompletionVerifier()

    def evaluate(
        self,
        candidate: CompletionCandidate,
        requirements: CompletionRequirements,
        evidence: list[VerificationEvidence],
        history_messages: list[Any],
    ) -> CompletionGateResult:
        deterministic = self.deterministic.evaluate(candidate, requirements, evidence, history_messages)
        if deterministic.verdict is not CompletionGateVerdict.PASS:
            return deterministic
        if not requirements.requires_verification:
            return deterministic
        request = SubagentRequest(
            profile_name="verification",
            task="Independently verify this completion candidate.",
            structured_context={
                "candidate": candidate.to_trace_payload(),
                "requirements": requirements.to_trace_payload(),
                "evidence": [item.to_trace_payload() for item in evidence],
            },
        )
        try:
            launched = self.launcher.launch(request)
            result = launched.result
            if not isinstance(result, VerificationResult):
                raise ValueError("invalid verification result")
        except Exception:
            return CompletionGateResult(
                verdict=CompletionGateVerdict.UNVERIFIED,
                reasons=("verification_agent_error",),
                passed_evidence=deterministic.passed_evidence,
            )
        if result.verdict is VerificationVerdict.PASS:
            return deterministic
        if result.verdict is VerificationVerdict.UNVERIFIED:
            return CompletionGateResult(
                verdict=CompletionGateVerdict.UNVERIFIED,
                reasons=result.reasons or ("verification_agent_unverified",),
                passed_evidence=deterministic.passed_evidence,
            )
        reasons = result.reasons or (f"verification_agent_{result.verdict.value.lower()}",)
        return CompletionGateResult(
            verdict=CompletionGateVerdict.FAIL,
            reasons=reasons,
            blocking_feedback="Independent verification did not pass: " + "; ".join(reasons),
            passed_evidence=deterministic.passed_evidence,
        )


class _StructuredResultCompletionVerifier:
    """Validate a child contract without inheriting parent completion requirements."""

    def __init__(self, profile: RuntimeProfile):
        self.profile = profile

    def evaluate(
        self,
        candidate: CompletionCandidate,
        requirements: CompletionRequirements,
        evidence: list[VerificationEvidence],
        history_messages: list[Any],
    ) -> CompletionGateResult:
        try:
            if self.profile.result_contract == "ExploreResult":
                ExploreResult.from_json(
                    candidate.final_text,
                    tool_usage={},
                    terminal_reason="completed",
                )
            else:
                VerificationResult.from_json(
                    candidate.final_text,
                    terminal_reason="completed",
                )
        except Exception as exc:
            return CompletionGateResult(
                verdict=CompletionGateVerdict.FAIL,
                reasons=("invalid_subagent_result",),
                blocking_feedback=f"Return only a valid {self.profile.result_contract} JSON object: {exc}",
            )
        return CompletionGateResult(verdict=CompletionGateVerdict.PASS)


def _render_request(request: SubagentRequest) -> str:
    context = json.dumps(request.structured_context, ensure_ascii=False, sort_keys=True)
    return f"{request.task.strip()}\n\nStructured context:\n{context}"


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        raise ValueError("structured child result must not use markdown fences")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("structured child result must be an object")
    return payload


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("result list fields must be string arrays")
    return tuple(item for item in value if item.strip())


def _attr(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _response_message(raw: Any) -> Any:
    choices = _attr(raw, "choices") or []
    return _attr(choices[0], "message") if choices else {}


def _child_metrics(events: list[tuple[str, int, dict[str, Any]]]) -> tuple[str, dict[str, int], int]:
    terminal_reason = "unknown"
    tool_usage: dict[str, int] = {}
    token_usage = 0
    for name, _step, payload in events:
        if name == "tool_call":
            tool = str(payload.get("tool") or "unknown")
            tool_usage[tool] = tool_usage.get(tool, 0) + 1
        elif name == "model_output":
            usage = payload.get("usage") or {}
            token_usage += int(usage.get("total_tokens") or 0)
        elif name == "terminal":
            terminal_reason = str(payload.get("reason") or terminal_reason)
    return terminal_reason, tool_usage, token_usage


def _create_light_llm() -> HelloAgentsLLM | None:
    model = os.getenv("LIGHT_LLM_MODEL_ID")
    if not model:
        return None
    try:
        return HelloAgentsLLM(
            model=model,
            api_key=os.getenv("LIGHT_LLM_API_KEY"),
            base_url=os.getenv("LIGHT_LLM_BASE_URL"),
            provider=os.getenv("LIGHT_LLM_PROVIDER", "auto"),
            temperature=float(os.getenv("LIGHT_LLM_TEMPERATURE", "0.5")),
        )
    except Exception:
        logging.getLogger("runtime.subagent").warning(
            "Failed to initialize light subagent model; falling back to main",
            exc_info=True,
        )
        return None


__all__ = [
    "EXPLORE_PROFILE",
    "RUNTIME_PROFILES",
    "VERIFICATION_PROFILE",
    "ExploreResult",
    "RuntimeProfile",
    "SubagentCompletionVerifier",
    "SubagentLaunchResult",
    "SubagentLauncher",
    "SubagentRequest",
    "SubagentResult",
    "SubagentStatus",
    "VerificationResult",
    "VerificationVerdict",
]
