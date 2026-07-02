import json
import os
import logging
import sys
import hashlib
from pathlib import Path
from typing import Any, Optional, List, Tuple

from core.agent import Agent
from core.llm import HelloAgentsLLM
from core.config import Config
from core.env import load_env

load_env()
from runtime.history import HistoryManager, Message
from runtime.input_preprocess import preprocess_input
from runtime.session import build_session_snapshot, save_session_snapshot, load_session_snapshot
from runtime.session_memory import SessionMemory, SessionMemoryManager
from runtime.transcript import (
    ResumeLoader,
    ResumeState,
    TranscriptRecorder,
    TranscriptStore,
    resolve_transcript_session_id,
)
from tools.registry import ToolRegistry
from tools.builtin.list_files import ListFilesTool
from tools.builtin.memory import MemoryTool
from tools.builtin.search_files_by_name import SearchFilesByNameTool
from tools.builtin.search_code import GrepTool
from tools.builtin.read_file import ReadTool
from tools.builtin.write_file import WriteTool
from tools.builtin.edit_file import EditTool
from tools.builtin.edit_file_multi import MultiEditTool
from tools.builtin.todo_write import TodoWriteTool
from tools.builtin.skill import SkillTool
from tools.builtin.bash import BashTool
from tools.builtin.ask_user import AskUserTool
from tools.builtin.task import TaskTool
from tools.executor import ToolExecutor
from tools.orchestrator import ToolOrchestrator
from tools.context import ToolExecutionContext
from tools.permissions import PermissionContext, RiskClassifier
from extensions.tracing import NullTraceLogger, create_trace_logger
from utils import setup_logger
from runtime.factory import RuntimeComponentFactory
from runtime.loop import RuntimeRunner


def resolve_teammate_mode(requested_mode: Optional[str]):
    """Resolve teammate mode without importing experimental runtime on default boot."""
    from experimental.teams.display_mode import resolve_teammate_mode as _resolve_teammate_mode

    return _resolve_teammate_mode(requested_mode)


def _get_response_attr(obj, key: str):
    """Safely get attribute from dict or object (OpenAI response)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


class CodeAgent(Agent):
    """
    Code Agent - 基于 ReAct 的代码助手
    
    上下文工程改造（按方案 D3）：
    - 使用 HistoryManager 管理会话历史
    - ReAct 每一步同步写入 assistant/tool 消息到 history
    - 支持压缩触发和 Summary 生成
    """
    DELEGATION_ALLOWED_TOOLS = {
        "TeamCreate",
        "SendMessage",
        "TeamStatus",
        "TeamDelete",
        "TeamCleanup",
        "TeamApprovals",
        "TeamApprovePlan",
        "TeamFanout",
        "TeamCollect",
        "TeamTaskCreate",
        "TeamTaskGet",
        "TeamTaskUpdate",
        "TeamTaskList",
        "TodoWrite",
        "AskUser",
    }
    
    def __init__(
        self, 
        name: str, 
        llm: HelloAgentsLLM, 
        tool_registry: ToolRegistry,
        project_root: str,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        enable_mcp: bool = True,
        enable_skills: bool = True,
        enable_tracing: bool = True,
        enable_skill_evolution: bool = False,
        logger=None,
    ):
        super().__init__(name, llm, system_prompt=system_prompt, config=config)
        self.project_root = project_root
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
        self.enable_mcp = bool(enable_mcp)
        self.enable_skills = bool(enable_skills)
        self.enable_tracing = bool(enable_tracing)
        self.interactive = os.getenv("AGENT_INTERACTIVE", "true").lower() in {"1", "true", "yes", "y", "on"}
        self.enable_agent_teams = self.config.enable_agent_teams
        self.team_store_dir = str(getattr(self.config, "agent_teams_store_dir", ".teams") or ".teams")
        self.task_store_dir = str(getattr(self.config, "agent_tasks_store_dir", ".tasks") or ".tasks")
        self.teammate_mode = str(getattr(self.config, "teammate_mode", "auto") or "auto")
        if self.enable_agent_teams:
            self.teammate_runtime_mode, self.teammate_mode_warning = resolve_teammate_mode(self.teammate_mode)
        else:
            self.teammate_runtime_mode, self.teammate_mode_warning = "disabled", None
        self.delegate_mode = self.config.delegate_mode
        if self.teammate_mode_warning:
            self.logger.warning(self.teammate_mode_warning)
        self.team_manager = None
        if self.enable_agent_teams:
            try:
                from experimental.teams.manager import TeamManager
                self.team_manager = TeamManager(
                    project_root=self.project_root,
                    team_store_dir=self.team_store_dir,
                    task_store_dir=self.task_store_dir,
                    llm=self.llm,
                    tool_registry=self.tool_registry,
                    teammate_runtime_mode=self.teammate_runtime_mode,
                )
            except Exception as exc:
                self.logger.warning("Failed to initialize TeamManager, AgentTeams disabled: %s", exc)
                self.enable_agent_teams = False
        self.logger.info(
            "AgentTeams enabled=%s, team_store_dir=%s, task_store_dir=%s, teammate_mode=%s, teammate_runtime_mode=%s, delegate_mode=%s",
            self.enable_agent_teams,
            self.team_store_dir,
            self.task_store_dir,
            self.teammate_mode,
            self.teammate_runtime_mode,
            self.delegate_mode,
        )

        self.enable_skill_evolution = bool(enable_skill_evolution)
        self._skill_evolution_manager = None
        
        self._initialize_runtime_components()

    def _initialize_runtime_components(self) -> None:
        """Build runtime components in dependency order."""
        factory = RuntimeComponentFactory(
            self,
            trace_logger_factory=create_trace_logger,
            null_trace_logger_factory=NullTraceLogger,
        )
        factory.initialize_context()
        factory.initialize_persistence()
        self.tool_executor = ToolExecutor(
            self.tool_registry,
            context=ToolExecutionContext(
                permission_checker=self._is_tool_allowed_in_delegate_mode,
                permission_decider=self._classify_tool_permission,
                permission_context=PermissionContext(runtime_mode=self._get_runtime_mode()),
                project_root=self.project_root,
            ),
        )
        self.tool_orchestrator = ToolOrchestrator(self)
        factory.initialize_subagents()
        self.tool_registry.register_tool(
            TaskTool(
                project_root=Path(self.project_root),
                launcher=self.subagent_launcher,
            )
        )

    def _on_run_finished(self, processed_input: str):
        if self._skill_evolution_manager is None:
            return
        try:
            events = self.trace_logger.get_current_run_events()
            session_id = self.trace_logger.session_id
            run_id = self._run_id
            self._skill_evolution_manager.on_run_finished(
                trace_events=events,
                session_id=session_id,
                run_id=run_id,
                processed_input=processed_input,
            )
        except Exception:
            self.logger.warning("Skill Evolution on_run_finished failed", exc_info=True)

    def _apply_session_memory(self, memory: SessionMemory) -> None:
        self.session_memory = memory
        if hasattr(self.context_engine, "set_session_memory"):
            self.context_engine.set_session_memory(memory)
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        self.tool_registry.register_tool(
            ListFilesTool(project_root=self.project_root, working_dir=self.project_root)
        )
        self.tool_registry.register_tool(SearchFilesByNameTool(project_root=self.project_root))
        self.tool_registry.register_tool(GrepTool(project_root=self.project_root))
        self.tool_registry.register_tool(ReadTool(project_root=self.project_root))
        self.tool_registry.register_tool(WriteTool(project_root=self.project_root))
        self.tool_registry.register_tool(EditTool(project_root=self.project_root))
        self.tool_registry.register_tool(MultiEditTool(project_root=self.project_root))
        self.tool_registry.register_tool(TodoWriteTool(project_root=self.project_root))
        if self.long_term_memory_store is not None:
            self.tool_registry.register_tool(
                MemoryTool(project_root=self.project_root, store=self.long_term_memory_store)
            )
        if self._skill_loader is not None:
            self.tool_registry.register_tool(
                SkillTool(project_root=self.project_root, skill_loader=self._skill_loader)
            )
        self.tool_registry.register_tool(BashTool(project_root=self.project_root))
        self.tool_registry.register_tool(
            AskUserTool(project_root=self.project_root, interactive=self.interactive)
        )
        if self.enable_agent_teams:
            self._register_agent_teams_tools()

    def _register_agent_teams_tools(self) -> None:
        try:
            from tools.builtin.team_create import TeamCreateTool
            from tools.builtin.send_message import SendMessageTool
            from tools.builtin.team_status import TeamStatusTool
            from tools.builtin.team_delete import TeamDeleteTool
            from tools.builtin.team_cleanup import TeamCleanupTool
            from tools.builtin.team_approvals import TeamApprovalsTool
            from tools.builtin.team_approve_plan import TeamApprovePlanTool
            from tools.builtin.team_fanout import TeamFanoutTool
            from tools.builtin.team_collect import TeamCollectTool
            from tools.builtin.team_task_create import TeamTaskCreateTool
            from tools.builtin.team_task_get import TeamTaskGetTool
            from tools.builtin.team_task_update import TeamTaskUpdateTool
            from tools.builtin.team_task_list import TeamTaskListTool
        except Exception as exc:
            self.logger.warning("AgentTeams enabled but team tools unavailable: %s", exc)
            return

        self.tool_registry.register_tool(TeamCreateTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(SendMessageTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamStatusTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamDeleteTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamCleanupTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamApprovalsTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamApprovePlanTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamFanoutTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamCollectTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamTaskCreateTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamTaskGetTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamTaskUpdateTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamTaskListTool(project_root=self.project_root, team_manager=self.team_manager))

    def _refresh_skills_prompt(self) -> None:
        if not self.enable_skills or self._skill_loader is None:
            self._skills_prompt = ""
            return
        refresh = os.getenv("SKILLS_REFRESH_ON_CALL", "true").lower() in {"1", "true", "yes", "y", "on"}
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
            from extensions.mcp.bootstrap import register_mcp_servers
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
        except Exception as exc:
            if self.logger:
                self.logger.warning("MCP registration skipped: %s", exc)

    def run(self, input_text: str, **kwargs) -> str:
        return self.runner.run(input_text, **kwargs)

    def close(self):
        """关闭 Agent 并写入 trace 总结"""
        manager = getattr(self, "_skill_evolution_manager", None)
        if manager is not None:
            try:
                if hasattr(manager, "on_session_end"):
                    manager.on_session_end(self._history_as_dicts())
                if hasattr(manager, "shutdown"):
                    manager.shutdown()
            except Exception:
                self.logger.warning("Skill Evolution shutdown failed", exc_info=True)
        if self.trace_logger:
            self.trace_logger.finalize()
            self.trace_logger = None
        for client in getattr(self, "_mcp_clients", []):
            try:
                client.close_sync()
            except Exception:
                pass

    def _history_as_dicts(self) -> list[dict]:
        return [
            {
                "role": message.role,
                "content": message.content,
                "metadata": dict(message.metadata or {}),
            }
            for message in self.history_manager.get_messages()
        ]

    # =========================================================================
    # ReAct Core（Message List 自然累积模式）
    # =========================================================================

    def _react_loop(
        self,
        pending_input: str,
        show_raw: bool,
        trace_logger,
    ) -> str:
        return self.runner._react_loop(pending_input, show_raw, trace_logger)

    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _log_message_write(self, trace_logger, role: str, content: str, metadata: dict, step: int = 0):
        """辅助：记录消息写入到 trace"""
        trace_logger.log_event("message_written", {
            "role": role,
            "content": content,
            "metadata": metadata,
        }, step=step)

    def _log_system_messages_if_needed(self, trace_logger) -> None:
        if self._system_messages_logged or not trace_logger:
            return
        system_messages = self._get_system_messages_for_run()
        trace_logger.log_system_messages(system_messages)
        self._system_messages_logged = True

    def _get_system_messages_for_run(self) -> List[dict]:
        if self._system_messages_override:
            return [dict(m) for m in self._system_messages_override]
        return self.context_builder.get_system_messages()

    def refresh_long_term_memory_snapshot(self):
        if self.long_term_memory_store is None:
            self.long_term_memory_snapshot = None
            self.context_engine.set_long_term_memory_snapshot(None)
            return None
        self.long_term_memory_snapshot = self.long_term_memory_store.load()
        self.context_engine.set_long_term_memory_snapshot(self.long_term_memory_snapshot)
        return self.long_term_memory_snapshot

    def reset_long_term_memory_snapshot(self):
        return self.refresh_long_term_memory_snapshot()

    def _build_messages(self, history_messages: list[dict]) -> list[dict]:
        system_messages = self._get_system_messages_for_run()
        return list(system_messages) + list(history_messages)

    def save_session(self, path: str) -> None:
        """保存会话快照（含 system messages）。"""
        system_messages = self._get_system_messages_for_run()
        history_messages = self.history_manager.serialize_messages()
        tool_schema = self._get_openai_tools_for_current_mode()
        teams_snapshot = self.team_manager.export_state() if self.team_manager else {}
        snapshot = build_session_snapshot(
            system_messages=system_messages,
            history_messages=history_messages,
            tool_schema=tool_schema,
            project_root=self.project_root,
            cwd=".",
            code_law_text=self.context_builder._cached_code_law,
            skills_prompt=self._skills_prompt,
            mcp_tools_prompt=self._mcp_tools_prompt,
            read_cache=self.tool_registry.export_read_cache(),
            tool_output_dir="tool-output",
            schema_version=1,
            teams_snapshot=teams_snapshot,
            parallel_work_index=(teams_snapshot.get("work_items", {}) if isinstance(teams_snapshot, dict) else {}),
            team_store_dir=self.team_store_dir,
            task_store_dir=self.task_store_dir,
        )
        save_session_snapshot(path, snapshot)

    def load_session(self, path: str) -> None:
        """从快照恢复会话（scheme B）。"""
        snapshot = load_session_snapshot(path)
        self.context_engine.reset()
        self._system_messages_override = snapshot.get("system_messages") or []
        history_items = snapshot.get("history_messages") or []
        self.history_manager.load_messages(history_items)
        self.tool_registry.import_read_cache(snapshot.get("read_cache") or {})
        if self.team_manager:
            self.team_manager.import_state(snapshot.get("teams_snapshot") or {})
            if hasattr(self.context_builder, "set_runtime_system_blocks"):
                self.context_builder.set_runtime_system_blocks(
                    ["[Team Runtime]\n- Team state restored from session snapshot."]
                )

    def load_transcript(self, path: str, *, run_id: str) -> ResumeState:
        """从 transcript 恢复恢复事实，不恢复执行中的线程或进程。"""
        previous_session_id = self.transcript_store.session_id
        session_id = TranscriptStore.infer_session_id(path) or self.transcript_store.session_id
        store = TranscriptStore(path, session_id=session_id)
        resume = ResumeLoader(store).load(run_id=run_id)
        if hasattr(self, "session_memory_manager"):
            self.session_memory_manager.memory = resume.session_memory
        resume.apply_to_host(self)
        self.resume_state = resume
        self.session_memory = resume.session_memory
        manager = getattr(self, "_skill_evolution_manager", None)
        if manager is not None:
            try:
                manager.on_session_switch(
                    session_id,
                    parent_session_id=previous_session_id,
                    reason="transcript_resume",
                )
            except Exception:
                self.logger.warning("Skill Evolution session switch failed", exc_info=True)
        return resume

    def _on_context_compacted(self, info: dict, messages: list) -> None:
        manager = getattr(self, "_skill_evolution_manager", None)
        if manager is None:
            return
        try:
            manager.on_context_compacted(
                info,
                [
                    {
                        "role": getattr(message, "role", ""),
                        "content": getattr(message, "content", ""),
                        "metadata": dict(getattr(message, "metadata", {}) or {}),
                    }
                    for message in messages
                ],
            )
        except Exception:
            self.logger.warning("Skill Evolution context compaction hook failed", exc_info=True)

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

    @staticmethod
    def _format_runtime_system_blocks(
        events: list[dict],
        runtime_state: Optional[dict] = None,
        max_lines: int = 16,
    ) -> list[str]:
        has_events = bool(events)
        state = runtime_state if isinstance(runtime_state, dict) else {}
        teams = state.get("teams") if isinstance(state.get("teams"), dict) else {}
        work_items = state.get("work_items") if isinstance(state.get("work_items"), dict) else {}
        approvals = state.get("approvals") if isinstance(state.get("approvals"), dict) else {}
        task_board = state.get("task_board") if isinstance(state.get("task_board"), dict) else {}
        if not has_events and not work_items:
            return []
        lines = ["[Team Runtime]"]

        for team_name in sorted(work_items.keys()):
            counts = work_items.get(team_name)
            if not isinstance(counts, dict):
                continue
            queued = int(counts.get("queued", 0) or 0)
            running = int(counts.get("running", 0) or 0)
            succeeded = int(counts.get("succeeded", 0) or 0)
            failed = int(counts.get("failed", 0) or 0)
            lines.append(
                f"- {team_name} work queued={queued} running={running} succeeded={succeeded} failed={failed}"
            )
            team_state = teams.get(team_name) if isinstance(teams, dict) else {}
            if isinstance(team_state, dict):
                idle_members = team_state.get("idle_teammates")
                active_members = team_state.get("active_teammates")
                if isinstance(idle_members, list) or isinstance(active_members, list):
                    idle_count = len(idle_members) if isinstance(idle_members, list) else 0
                    active_count = len(active_members) if isinstance(active_members, list) else 0
                    lines.append(f"- {team_name} teammates active={active_count} idle={idle_count}")
                last_error = str(team_state.get("last_error") or "").strip()
                if last_error:
                    compact_error = " ".join(last_error.split())
                    if len(compact_error) > 120:
                        compact_error = f"{compact_error[:117]}..."
                    lines.append(f"- {team_name} last_error={compact_error}")
            approval_counts = approvals.get(team_name) if isinstance(approvals, dict) else {}
            if isinstance(approval_counts, dict):
                pending = int(approval_counts.get("pending", 0) or 0)
                approved = int(approval_counts.get("approved", 0) or 0)
                rejected = int(approval_counts.get("rejected", 0) or 0)
                if pending or approved or rejected:
                    lines.append(
                        f"- {team_name} approvals pending={pending} approved={approved} rejected={rejected}"
                    )
            board_counts = task_board.get(team_name) if isinstance(task_board, dict) else {}
            if isinstance(board_counts, dict):
                blocked = int(board_counts.get("blocked", 0) or 0)
                pending_tasks = int(board_counts.get("pending", 0) or 0)
                in_progress = int(board_counts.get("in_progress", 0) or 0)
                if blocked or pending_tasks or in_progress:
                    lines.append(
                        f"- {team_name} tasks blocked={blocked} pending={pending_tasks} in_progress={in_progress}"
                    )

        deduped_events: list[dict] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for event in events:
            if not isinstance(event, dict):
                continue
            team = str(event.get("team", "unknown"))
            event_type = str(event.get("type", "event"))
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            signature = (
                team,
                event_type,
                str(payload.get("message_id") or ""),
                str(payload.get("work_id") or ""),
                str(payload.get("status") or ""),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped_events.append(event)

        max_event_lines = 8
        for event in deduped_events[:max_event_lines]:
            team = event.get("team", "unknown")
            event_type = event.get("type", "event")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            status = payload.get("status")
            message_id = payload.get("message_id")
            work_id = payload.get("work_id")
            if work_id and status:
                lines.append(f"- event {team}:{event_type} work={work_id} status={status}")
            elif message_id and status:
                lines.append(f"- event {team}:{event_type} message={message_id} status={status}")
            elif message_id:
                lines.append(f"- event {team}:{event_type} message={message_id}")
            else:
                lines.append(f"- event {team}:{event_type}")
        if len(deduped_events) > max_event_lines:
            lines.append(f"- ... {len(deduped_events) - max_event_lines} more events")

        limit = max(2, int(max_lines or 0))
        if len(lines) > limit:
            hidden = len(lines) - (limit - 1)
            lines = lines[: limit - 1] + [f"- ... {hidden} more lines"]

        return ["\n".join(lines)]

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        return self.tool_executor.execute(tool_name, tool_input)

    def _get_runtime_mode(self) -> str:
        return "readonly_subagent" if self.delegate_mode else "main_agent"

    def _classify_tool_permission(self, tool_name: str, tool_input: dict[str, Any], context: PermissionContext):
        runtime_context = PermissionContext(
            runtime_mode=self._get_runtime_mode(),
            ask_policy=context.ask_policy,
        )
        return RiskClassifier().classify(tool_name, tool_input, runtime_context)

    def set_delegate_mode(self, enabled: bool) -> None:
        self.delegate_mode = bool(enabled)
        if hasattr(self.config, "delegate_mode"):
            self.config.delegate_mode = self.delegate_mode
        if getattr(self, "tool_executor", None) is not None:
            self.tool_executor.context.permission_context = PermissionContext(
                runtime_mode=self._get_runtime_mode(),
                ask_policy=self.tool_executor.context.permission_context.ask_policy,
            )
        self.logger.info("Delegate mode set to %s", self.delegate_mode)

    def _is_tool_allowed_in_delegate_mode(self, tool_name: str) -> bool:
        if not self.delegate_mode:
            return True
        return str(tool_name or "") in self.DELEGATION_ALLOWED_TOOLS

    def _get_openai_tools_for_current_mode(self) -> list[dict[str, Any]]:
        tools = self.tool_registry.get_openai_tools()
        if not self.delegate_mode:
            return tools
        filtered: list[dict[str, Any]] = []
        for item in tools:
            function = item.get("function") if isinstance(item, dict) else None
            name = function.get("name") if isinstance(function, dict) else ""
            if self._is_tool_allowed_in_delegate_mode(str(name or "")):
                filtered.append(item)
        return filtered

    def _get_openai_tools_fingerprint_for_current_mode(self) -> str:
        tools = self._get_openai_tools_for_current_mode()
        payload = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _ensure_json_input(self, raw: str) -> Tuple[Any, Optional[str]]:
        if raw is None:
            return {}, None
        if isinstance(raw, (dict, list)):
            return raw, None
        s = str(raw).strip()
        if not s:
            return {}, None
        try:
            return json.loads(s), None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _extract_content(raw_response: Any) -> Optional[str]:
        try:
            if hasattr(raw_response, "choices"):
                content = raw_response.choices[0].message.content
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
            if isinstance(raw_response, dict) and raw_response.get("choices"):
                content = raw_response["choices"][0]["message"].get("content")
                if isinstance(content, list):
                    return "".join(part.get("text", "") for part in content if isinstance(part, dict))
                return content
        except Exception:
            return str(raw_response)

    @staticmethod
    def _extract_reasoning_content(raw_response: Any) -> Optional[str]:
        try:
            choices = _get_response_attr(raw_response, "choices")
            if not choices:
                return None
            choice = choices[0]
            message = _get_response_attr(choice, "message")
            if not message:
                return None

            reasoning = _get_response_attr(message, "reasoning_content") or _get_response_attr(message, "reasoning")
            if reasoning:
                return reasoning

            model_extra = None
            if isinstance(message, dict):
                model_extra = message.get("model_extra") or message.get("additional_kwargs")
            else:
                model_extra = getattr(message, "model_extra", None) or getattr(message, "additional_kwargs", None)
            if isinstance(model_extra, dict):
                return model_extra.get("reasoning_content") or model_extra.get("reasoning")
        except Exception:
            return None
        return None

    @staticmethod
    def _extract_usage(raw_response: Any) -> Optional[dict]:
        try:
            if hasattr(raw_response, "usage"):
                usage = raw_response.usage
                if not usage:
                    return None
                return {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
            if isinstance(raw_response, dict) and raw_response.get("usage"):
                usage = raw_response["usage"]
                return {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
        except Exception:
            return None

    @staticmethod
    def _extract_tool_calls(raw_response: Any) -> list[dict[str, Any]]:
        """
        从原始响应中提取 tool_calls，统一成 {id,name,arguments} 列表。
        """
        try:
            choices = _get_response_attr(raw_response, "choices")
            if not choices:
                return []
            choice = choices[0]
            message = _get_response_attr(choice, "message")
            if not message:
                return []
            tool_calls = _get_response_attr(message, "tool_calls") or []
            calls: list[dict[str, Any]] = []
            if tool_calls:
                for call in tool_calls:
                    fn = _get_response_attr(call, "function") or {}
                    name = _get_response_attr(fn, "name") or _get_response_attr(call, "name") or "unknown_tool"
                    arguments = _get_response_attr(fn, "arguments") or _get_response_attr(call, "arguments") or {}
                    call_id = _get_response_attr(call, "id")
                    calls.append({
                        "id": call_id,
                        "name": name,
                        "arguments": arguments,
                    })
                return calls

            # 兼容旧 function_call
            function_call = _get_response_attr(message, "function_call")
            if function_call:
                name = _get_response_attr(function_call, "name") or "unknown_tool"
                arguments = _get_response_attr(function_call, "arguments") or {}
                return [{"id": None, "name": name, "arguments": arguments}]
        except Exception:
            return []

        return []

    @staticmethod
    def _extract_response_meta(raw_response: Any) -> dict:
        """提取响应元信息，辅助定位空响应原因"""
        meta: dict = {}
        try:
            choices = _get_response_attr(raw_response, "choices") or []
            if not choices:
                return meta
            choice = choices[0]
            meta["finish_reason"] = _get_response_attr(choice, "finish_reason")
            message = _get_response_attr(choice, "message")
            if not message:
                return meta
            meta["role"] = _get_response_attr(message, "role")

            content = _get_response_attr(message, "content")
            reasoning_content = _get_response_attr(message, "reasoning_content") or _get_response_attr(message, "reasoning")
            refusal = _get_response_attr(message, "refusal")
            tool_calls = _get_response_attr(message, "tool_calls")
            function_call = _get_response_attr(message, "function_call")

            meta["content_len"] = len(str(content)) if content is not None else 0
            meta["reasoning_len"] = len(str(reasoning_content)) if reasoning_content is not None else 0
            meta["refusal_present"] = refusal is not None
            meta["tool_calls_count"] = len(tool_calls) if isinstance(tool_calls, list) else (1 if tool_calls else 0)
            meta["function_call_present"] = function_call is not None
        except Exception:
            return meta
        return meta

    @staticmethod
    def _extract_raw_response(raw_response: Any) -> dict:
        """将原始响应转换为可序列化结构（用于 trace 记录）"""
        try:
            if hasattr(raw_response, "model_dump"):
                return raw_response.model_dump()
            if isinstance(raw_response, dict):
                return raw_response
        except Exception:
            pass
        return {"raw": str(raw_response)}
    
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
                project_root=self.project_root,
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
