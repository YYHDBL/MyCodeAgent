"""Factories for assembling runtime host components."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from extensions.skills import SkillLoader
from runtime.context import ContextEngine
from runtime.history import HistoryManager
from runtime.loop import RuntimeRunner
from runtime.memory import LongTermMemoryStore
from runtime.prompt_builder import ContextBuilder
from runtime.session_memory import SessionMemory, SessionMemoryManager
from runtime.subagents import SubagentCompletionVerifier, SubagentLauncher
from runtime.summary import create_summary_generator
from runtime.transcript import (
    TranscriptRecorder,
    TranscriptStore,
    resolve_transcript_session_id,
)
class RuntimeComponentFactory:
    """Assemble context, persistence, and subagent components for a host."""

    def __init__(
        self,
        host: Any,
        *,
        trace_logger_factory: Callable[[], Any],
        null_trace_logger_factory: Callable[[], Any],
    ) -> None:
        self.host = host
        self.trace_logger_factory = trace_logger_factory
        self.null_trace_logger_factory = null_trace_logger_factory

    def initialize_context(self) -> None:
        host = self.host
        summary_generator = create_summary_generator(
            llm=host.llm,
            config=host.config,
            verbose=host.verbose,
        )
        host.history_manager = HistoryManager(config=host.config)
        host.long_term_memory_store = None
        host.long_term_memory_snapshot = None
        if host.config.long_term_memory_enabled:
            host.long_term_memory_store = LongTermMemoryStore(
                project_root=host.project_root,
                memory_char_limit=int(getattr(host.config, "memory_char_limit", 3000) or 3000),
                user_memory_char_limit=int(
                    getattr(host.config, "user_memory_char_limit", 1500) or 1500
                ),
                user_memory_path=getattr(host.config, "user_memory_path", None),
            )
            host.long_term_memory_snapshot = host.long_term_memory_store.load()

        host._skills_prompt = ""
        host._skill_loader = SkillLoader(host.project_root) if host.enable_skills else None
        host._refresh_skills_prompt()
        host._register_builtin_tools()

        host._mcp_clients = []
        host._mcp_tools_prompt = ""
        if host.enable_mcp:
            host._register_mcp_tools()

        host.context_builder = ContextBuilder(
            tool_registry=host.tool_registry,
            project_root=host.project_root,
            system_prompt_override=host.system_prompt,
            mcp_tools_prompt=host._mcp_tools_prompt,
            skills_prompt=host._skills_prompt,
            tool_prompt_allowlist=frozenset(host.tool_registry.list_tools()) | {"Task"},
        )
        host.context_engine = ContextEngine(
            host.context_builder,
            config=host.config,
            summary_generator=summary_generator,
        )
        if host.long_term_memory_snapshot is not None:
            host.context_engine.set_long_term_memory_snapshot(host.long_term_memory_snapshot)

    def initialize_persistence(self) -> None:
        host = self.host
        host.trace_logger = (
            self.trace_logger_factory()
            if host.enable_tracing
            else self.null_trace_logger_factory()
        )
        if host.long_term_memory_snapshot is not None:
            snapshot = host.long_term_memory_snapshot
            host.trace_logger.log_event(
                "long_term_memory_loaded",
                {
                    "memory_entry_count": snapshot.memory.usage.entry_count,
                    "memory_usage_chars": snapshot.memory.usage.chars,
                    "memory_limit_chars": snapshot.memory.usage.limit,
                    "user_entry_count": snapshot.user.usage.entry_count,
                    "user_usage_chars": snapshot.user.usage.chars,
                    "user_limit_chars": snapshot.user.usage.limit,
                },
                step=0,
            )

        session_id = resolve_transcript_session_id(
            getattr(host.trace_logger, "session_id", None)
        )
        host.transcript_store = TranscriptStore(
            Path(host.project_root) / "memory" / "transcripts" / f"transcript-{session_id}.jsonl",
            session_id=session_id,
        )
        host.session_memory_manager = SessionMemoryManager(on_update=host._apply_session_memory)
        host.transcript_recorder = TranscriptRecorder(
            host.transcript_store,
            on_recorded=host.session_memory_manager.ingest_event,
        )
        host.resume_state = None
        host.session_memory = SessionMemory()
        host._system_messages_logged = False
        host._run_id = 0
        host._system_messages_override = None

    def initialize_subagents(self) -> None:
        host = self.host
        host.runner = RuntimeRunner(host)
        host.subagent_launcher = SubagentLauncher(
            project_root=Path(host.project_root),
            main_llm=host.llm,
            tool_registry=host.tool_registry,
            parent_trace_logger=host.trace_logger,
            parent_history_manager=host.history_manager,
            parent_context_engine=host.context_engine,
            parent_host=host,
        )
        if host.config.enable_verification_agent:
            host.completion_verifier = SubagentCompletionVerifier(host.subagent_launcher)


__all__ = ["RuntimeComponentFactory"]
