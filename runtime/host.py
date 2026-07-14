import os
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional

from core.llm import HelloAgentsLLM
from core.config import Config

from runtime.history import Message
from runtime.session_memory import SessionMemory
from runtime.transcript import (
    ResumeLoader,
    ResumeState,
    TranscriptRecorder,
    TranscriptSession,
    TranscriptStore,
)
from tools.registry import ToolRegistry
from tools.builtin.glob import GlobTool
from tools.builtin.search_code import GrepTool
from tools.builtin.read_file import ReadTool
from tools.builtin.edit_file import EditTool
from tools.builtin.todo_write import TodoWriteTool
from tools.builtin.bash import BashTool
from tools.builtin.task import TaskTool
from tools.executor import ToolExecutor
from tools.orchestrator import ToolOrchestrator
from tools.context import ToolExecutionContext
from tools.permissions import PermissionContext, RiskClassifier
from extensions.tracing import NullTraceLogger, create_trace_logger
from utils import setup_logger
from runtime.factory import (
    build_runtime_context,
    build_runtime_persistence,
    create_subagent_launcher,
)
from runtime.events import RuntimeEvent
from runtime.loop import RuntimeRunner


class CodeAgent:
    """
    Code Agent - 基于 ReAct 的代码助手
    
    上下文工程改造（按方案 D3）：
    - 使用 HistoryManager 管理会话历史
    - ReAct 每一步同步写入 assistant/tool 消息到 history
    - 支持压缩触发和 Summary 生成
    """
    class _DeferredSubagentLauncher:
        """Expose the Task launcher protocol without paying its startup cost."""

        def __init__(self, get_launcher):
            self._get_launcher = get_launcher

        def launch(self, request):
            return self._get_launcher().launch(request)
    
    def __init__(
        self, 
        name: str, 
        llm: HelloAgentsLLM, 
        tool_registry: ToolRegistry,
        project_root: str,
        package_resource_root: Optional[str] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        enable_mcp: Optional[bool] = None,
        enable_skills: Optional[bool] = None,
        enable_tracing: Optional[bool] = None,
        logger=None,
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or Config.from_env()
        self.project_root = project_root
        self.package_resource_root = package_resource_root
        self.tool_registry = tool_registry
        self.logger = logger or setup_logger(
            name=f"agent.{self.name}",
            level=self.config.log_level,
        )
        self.last_response_raw: Optional[Any] = None
        self.max_steps = 50
        self.verbose = bool(self.config.debug)
        self.console_verbose = bool(self.config.show_react_steps)
        self.console_progress = bool(self.config.show_progress)
        self.enable_mcp = self.config.enable_mcp if enable_mcp is None else bool(enable_mcp)
        self.enable_skills = self.config.enable_skills if enable_skills is None else bool(enable_skills)
        self.enable_tracing = self.config.enable_tracing if enable_tracing is None else bool(enable_tracing)
        self._initialize_runtime_components()

    def _initialize_runtime_components(self) -> None:
        """Build runtime components in dependency order."""
        build_runtime_context(self)
        build_runtime_persistence(
            self,
            trace_logger_factory=lambda trace_dir: create_trace_logger(
                trace_dir,
                project_root=self.project_root,
                enabled=True,
            ),
            null_trace_logger_factory=NullTraceLogger,
        )
        self.tool_executor = ToolExecutor(
            self.tool_registry,
            context=ToolExecutionContext(
                permission_decider=self._classify_tool_permission,
                permission_context=PermissionContext(runtime_mode="main_agent"),
                project_root=self.project_root,
            ),
        )
        self.tool_orchestrator = ToolOrchestrator(self)
        self.runner = RuntimeRunner(self)
        self.subagent_launcher = None
        if self.config.enable_verification_agent:
            from runtime.subagents import SubagentCompletionVerifier

            self.completion_verifier = SubagentCompletionVerifier(
                self._get_subagent_launcher()
            )
        self.tool_registry.register_tool(
            TaskTool(
                project_root=Path(self.project_root),
                launcher=self._DeferredSubagentLauncher(self._get_subagent_launcher),
            )
        )

    def _get_subagent_launcher(self):
        """Create the optional launcher when Task or verification explicitly needs it."""

        if self.subagent_launcher is None:
            return create_subagent_launcher(self)
        return self.subagent_launcher

    def _apply_session_memory(self, memory: SessionMemory) -> None:
        self.session_memory = memory
        if hasattr(self.context_engine, "set_session_memory"):
            self.context_engine.set_session_memory(memory)
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        self.tool_registry.register_tool(GlobTool(project_root=self.project_root))
        self.tool_registry.register_tool(GrepTool(project_root=self.project_root))
        self.tool_registry.register_tool(ReadTool(project_root=self.project_root))
        self.tool_registry.register_tool(EditTool(project_root=self.project_root))
        self.tool_registry.register_tool(TodoWriteTool(project_root=self.project_root))
        if self._skill_loader is not None:
            from tools.builtin.skill import SkillTool

            self.tool_registry.register_tool(
                SkillTool(
                    project_root=self.project_root,
                    skill_loader=self._skill_loader,
                    refresh_on_call=self.config.skills_refresh_on_call,
                )
            )
        self.tool_registry.register_tool(BashTool(project_root=self.project_root))
    def _refresh_skills_prompt(self) -> None:
        if not self.enable_skills or self._skill_loader is None:
            self._skills_prompt = ""
            return
        refresh = self.config.skills_refresh_on_call
        if refresh:
            self._skill_loader.refresh_if_stale()
        elif not self._skills_prompt:
            self._skill_loader.scan()
        budget = int(os.getenv("SKILLS_PROMPT_CHAR_BUDGET", "12000"))
        from extensions.skills.prompt import format_skills_for_prompt
        self._skills_prompt = format_skills_for_prompt(self._skill_loader.list_skills(refresh=False), budget)

    def _register_mcp_tools(self) -> None:
        """可选：注册 MCP 工具（基于 MCP_SERVERS 配置）"""
        try:
            from extensions.mcp.bootstrap import MCPExtraRequiredError, register_mcp_servers
            from extensions.mcp.prompt import format_mcp_tools_prompt
            clients, tools_meta = register_mcp_servers(self.tool_registry, self.project_root)
            self._mcp_clients = clients
            self._mcp_tools_prompt = format_mcp_tools_prompt(tools_meta)
            if tools_meta:
                self.logger.info("MCP tools loaded: %d", len(tools_meta))
                if self.logger.isEnabledFor(logging.DEBUG):
                    for tool in tools_meta:
                        name = tool.get("name") or ""
                        description = (tool.get("description") or "").strip()
                        if description:
                            self.logger.debug("MCP tool: %s - %s", name, description)
                        else:
                            self.logger.debug("MCP tool: %s", name)
        except MCPExtraRequiredError:
            raise
        except Exception as exc:
            if self.logger:
                self.logger.warning("MCP registration skipped: %s", exc)

    def run(self, input_text: str, **kwargs) -> str:
        return self.runner.run(input_text, **kwargs)

    def __str__(self) -> str:
        return f"Agent(name={self.name}, provider={self.llm.provider})"

    def __repr__(self) -> str:
        return self.__str__()

    def close(self):
        """关闭 Agent 并写入 trace 总结"""
        if self.trace_logger:
            self.trace_logger.finalize()
            self.trace_logger = None
        for client in getattr(self, "_mcp_clients", []):
            try:
                client.close_sync()
            except Exception:
                pass

    def emit_runtime_event(
        self,
        *,
        run_id: str,
        step: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Accept a neutral tool callback and create the typed runtime fact."""

        self.runtime_event_sink.emit(
            RuntimeEvent(run_id=run_id, step=step, type=event_type, payload=payload)
        )

    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _log_system_messages_if_needed(self, trace_logger) -> None:
        if self._system_messages_logged or not trace_logger:
            return
        system_messages = self._get_system_messages_for_run()
        trace_logger.log_system_messages(system_messages)
        self._system_messages_logged = True

    def _get_system_messages_for_run(self) -> List[dict]:
        return self.context_builder.get_system_messages()

    def transcript_path(self) -> Path:
        """Return the already-durable append-only session record."""

        return self.transcript_store.path

    def load_transcript(self, path: str, *, run_id: str | None = None) -> ResumeState:
        """从 transcript 恢复恢复事实，不恢复执行中的线程或进程。"""
        session_id = TranscriptStore.infer_session_id(path)
        if session_id is None:
            store = self.transcript_store
            if not store.import_legacy_snapshot(path):
                raise ValueError(
                    "Legacy snapshot was not imported because the selected transcript already contains facts"
                )
        else:
            store = TranscriptStore(path, session_id=session_id)
        loader = ResumeLoader(store)
        resume = loader.load(run_id=run_id) if run_id is not None else loader.load_session()
        self.session_memory_manager.memory = resume.session_memory
        on_recorded = self.session_memory_manager.ingest_event
        self.transcript_store = store
        self.transcript_recorder = TranscriptRecorder(store, on_recorded=on_recorded)
        resume.apply_to_host(self)
        self.resume_state = resume
        self.session_memory = resume.session_memory
        self._run_id = max(self._run_id, self._latest_transcript_run_number(store))
        return resume

    def list_transcript_sessions(self) -> list[TranscriptSession]:
        """List durable sessions belonging to this host's selected project."""

        return TranscriptStore.list_sessions(Path(self.project_root) / "memory" / "transcripts")

    def resume_transcript(self, session_id: str | None = None) -> ResumeState:
        """Restore the latest transcript-backed turn for a selected session."""

        session = TranscriptStore.resolve_session(
            Path(self.project_root) / "memory" / "transcripts",
            session_id,
        )
        if not session.latest_run_id:
            raise ValueError(f"Transcript session has no resumable run: {session.session_id}")
        return self.load_transcript(str(session.path))

    def get_session_status(self) -> dict[str, Any]:
        """Return small, CLI-ready facts without exposing trace internals."""

        return {
            "project_root": self.project_root,
            "model": self.llm.model,
            "provider": self.llm.provider,
            "session_id": self.transcript_store.session_id,
            "permission_mode": self._get_runtime_mode(),
            "extensions": {
                "mcp": self.enable_mcp,
                "skills": self.enable_skills,
            },
            "context_usage": {
                "last_tokens": self.context_engine.last_usage_tokens,
                "total_tokens": self.context_engine.total_usage_tokens,
                "messages": self.history_manager.get_message_count(),
            },
        }

    def cancel_active_turn(self) -> dict[str, Any]:
        """Record an interrupted terminal fact for the currently incomplete turn."""

        active_run_id = self._active_transcript_run_id
        if active_run_id is None and self._turn_cancelled:
            return {"cancelled": False, "run_id": None}
        run_id = active_run_id or self._incomplete_transcript_run_id()
        if not run_id:
            return {"cancelled": False, "run_id": None}
        events = self.transcript_store.read_events(run_id=str(run_id))
        if any(event.event_type.value == "terminal" for event in events):
            self._active_transcript_run_id = None
            return {"cancelled": False, "run_id": None}
        step = max((event.step for event in events), default=0)
        self.runtime_event_sink.emit(
            RuntimeEvent(
                run_id=str(run_id),
                step=step,
                type="terminal",
                payload={"reason": "interrupted", "details": {"cancelled": True}},
            )
        )
        self._active_transcript_run_id = None
        self._turn_cancelled = True
        return {"cancelled": True, "run_id": str(run_id)}

    def _incomplete_transcript_run_id(self) -> str | None:
        events = self.transcript_store.read_events()
        terminal_runs = {
            event.run_id
            for event in events
            if event.event_type.value == "terminal"
        }
        for event in reversed(events):
            if event.run_id not in terminal_runs:
                return event.run_id
        return None

    @staticmethod
    def _latest_transcript_run_number(store: TranscriptStore) -> int:
        latest = 0
        for event in store.read_events():
            prefix, separator, value = event.run_id.rpartition("-")
            if prefix == "run" and separator and value.isdigit():
                latest = max(latest, int(value))
        return latest

    def _print_context_preview(
        self,
        messages: list[dict],
        max_messages: int = 10,
        content_limit: int = 200,
    ) -> None:
        if not messages:
            if self.console_verbose:
                self._console("（当前上下文为空）")
            else:
                self.logger.debug("当前上下文为空")
            return
        total = len(messages)
        preview = messages[:max_messages]
        if self.console_verbose:
            self._console(f"\n📌 当前上下文（最多显示 {max_messages} 条）")
        else:
            self.logger.debug("当前上下文（最多显示 %d 条）", max_messages)
        for msg in preview:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content = str(content).replace("\n", "\\n")
            if len(content) > content_limit:
                content = content[:content_limit] + "...(truncated)"
            if self.console_verbose:
                self._console(f'message({role}, "{content}")')
            else:
                self.logger.debug('message(%s, "%s")', role, content)
        if total > max_messages:
            if self.console_verbose:
                self._console(f"...（其余 {total - max_messages} 条已省略）")
            else:
                self.logger.debug("其余 %d 条已省略", total - max_messages)

    def _console(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def _execute_tool(self, tool_name: str, tool_input: Any):
        return self.tool_executor.execute(tool_name, tool_input)

    def _get_runtime_mode(self) -> str:
        return "main_agent"

    def _classify_tool_permission(self, tool_name: str, tool_input: dict[str, Any], context: PermissionContext):
        runtime_context = PermissionContext(
            runtime_mode=self._get_runtime_mode(),
            ask_policy=context.ask_policy,
        )
        return RiskClassifier().classify(tool_name, tool_input, runtime_context)

    def _get_openai_tools_for_current_mode(self) -> list[dict[str, Any]]:
        return self.tool_registry.get_openai_tools()

    # =========================================================================
    # Agent base-history hooks backed by HistoryManager
    # =========================================================================
    
    def add_message(self, message: Message):
        """Add a message to the managed runtime history."""
        if message.role == "user":
            self.history_manager.append_user(message.content, message.metadata)
        elif message.role == "assistant":
            self.history_manager.append_assistant(message.content, message.metadata)
        elif message.role == "tool":
            # 注意：旧接口没有 tool_name，使用 metadata 中的值
            tool_name = (message.metadata or {}).get("tool_name", "unknown")
            self.history_manager.append_tool(
                tool_name, 
                message.content, 
                message.metadata,
            )
        elif message.role == "summary":
            self.history_manager.append_summary(message.content)
    
    def clear_history(self):
        """Clear managed runtime history."""
        self.history_manager.clear()
        self.context_engine.reset()
    
    def get_history(self) -> List[Message]:
        """Return managed runtime history."""
        return self.history_manager.get_messages()
