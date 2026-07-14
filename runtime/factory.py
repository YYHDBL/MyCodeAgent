"""Direct builders for the few runtime dependencies assembled at startup."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from runtime.context import ContextEngine
from runtime.events import create_runtime_event_sink
from runtime.history import HistoryManager
from runtime.prompt_builder import ContextBuilder
from runtime.session_memory import SessionMemory, SessionMemoryManager
from runtime.subagents import SubagentLauncher
from runtime.summary import create_summary_generator
from runtime.transcript import TranscriptRecorder, TranscriptStore, resolve_transcript_session_id


def build_runtime_context(host: Any) -> None:
    """Attach the context dependencies owned by one runtime host."""

    summary_generator = create_summary_generator(
        llm=host.llm, config=host.config, verbose=host.verbose
    )
    host.history_manager = HistoryManager(config=host.config)

    host._skills_prompt = ""
    if host.enable_skills and _project_has_skill_files(host.project_root):
        from extensions.skills import SkillLoader

        host._skill_loader = SkillLoader(host.project_root)
    else:
        host._skill_loader = None
    host._refresh_skills_prompt()
    host._register_builtin_tools()

    host._mcp_clients = []
    host._mcp_tools_prompt = ""
    if host.enable_mcp:
        host._register_mcp_tools()

    host.context_builder = ContextBuilder(
        tool_registry=host.tool_registry,
        project_root=host.project_root,
        resource_root=host.package_resource_root,
        system_prompt_override=host.system_prompt,
        mcp_tools_prompt=host._mcp_tools_prompt,
        skills_prompt=host._skills_prompt,
        tool_prompt_allowlist=frozenset(host.tool_registry.list_tools()) | {"Task"},
    )
    host.context_engine = ContextEngine(
        host.context_builder, config=host.config, summary_generator=summary_generator
    )


def build_runtime_persistence(
    host: Any,
    *,
    trace_logger_factory: Callable[[str], Any],
    null_trace_logger_factory: Callable[[], Any],
) -> None:
    """Attach tracing, transcript, and session-memory dependencies."""

    host.trace_logger = (
        trace_logger_factory(str(Path(host.project_root) / "memory" / "traces"))
        if host.enable_tracing
        else null_trace_logger_factory()
    )
    session_id = resolve_transcript_session_id(host.trace_logger.session_id)
    host.transcript_store = TranscriptStore(
        Path(host.project_root) / "memory" / "transcripts" / f"transcript-{session_id}.jsonl",
        session_id=session_id,
    )
    host.session_memory_manager = SessionMemoryManager(on_update=host._apply_session_memory)
    host.transcript_recorder = TranscriptRecorder(
        host.transcript_store, on_recorded=host.session_memory_manager.ingest_event
    )
    host.runtime_event_sink = create_runtime_event_sink(
        host.trace_logger, host.transcript_recorder
    )
    host.resume_state = None
    host.session_memory = SessionMemory()
    host._system_messages_logged = False
    host._run_id = 0


def create_subagent_launcher(host: Any) -> SubagentLauncher:
    """Construct the optional launcher at first Task or verification use."""

    launcher = SubagentLauncher(
        project_root=Path(host.project_root),
        main_llm=host.llm,
        tool_registry=host.tool_registry,
        parent_trace_logger=host.trace_logger,
        parent_history_manager=host.history_manager,
        parent_context_engine=host.context_engine,
        parent_host=host,
    )
    host.subagent_launcher = launcher
    return launcher


def _project_has_skill_files(project_root: str) -> bool:
    skills_dir = Path(project_root) / "skills"
    return skills_dir.is_dir() and next(skills_dir.rglob("SKILL.md"), None) is not None


__all__ = ["build_runtime_context", "build_runtime_persistence", "create_subagent_launcher"]
