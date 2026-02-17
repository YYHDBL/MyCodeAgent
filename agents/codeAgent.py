import json
import uuid
import os
import logging
import sys
import traceback as tb
from typing import Any, Optional, List, Tuple

from core.agent import Agent
from core.llm import HelloAgentsLLM
from core.message import Message
from core.config import Config
from core.context_engine.context_builder import ContextBuilder
from core.context_engine.trace_logger import create_trace_logger
from core.env import load_env

load_env()
from core.context_engine.history_manager import HistoryManager
from core.context_engine.input_preprocessor import preprocess_input
from core.context_engine.summary_compressor import create_summary_generator
from core.session_store import build_session_snapshot, save_session_snapshot, load_session_snapshot
from tools.registry import ToolRegistry
from tools.builtin.list_files import ListFilesTool
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
from tools.mcp.loader import register_mcp_servers, format_mcp_tools_prompt
from utils import setup_logger
from core.skills.skill_loader import SkillLoader


class CodeAgent(Agent):
    """
    Code Agent - 基于 ReAct 的代码助手
    
    上下文工程改造（按方案 D3）：
    - 使用 HistoryManager 管理会话历史
    - ReAct 每一步同步写入 assistant/tool 消息到 history
    - 支持压缩触发和 Summary 生成
    """
    
    def __init__(
        self, 
        name: str, 
        llm: HelloAgentsLLM, 
        tool_registry: ToolRegistry,
        project_root: str,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
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
        self.interactive = os.getenv("AGENT_INTERACTIVE", "true").lower() in {"1", "true", "yes", "y", "on"}
        self.enable_agent_teams = bool(getattr(self.config, "enable_agent_teams", False))
        self.team_store_dir = str(getattr(self.config, "agent_teams_store_dir", ".teams") or ".teams")
        self.task_store_dir = str(getattr(self.config, "agent_tasks_store_dir", ".tasks") or ".tasks")
        self.team_manager = None
        if self.enable_agent_teams:
            try:
                from core.team_engine.manager import TeamManager
                self.team_manager = TeamManager(
                    project_root=self.project_root,
                    team_store_dir=self.team_store_dir,
                    task_store_dir=self.task_store_dir,
                )
            except Exception as exc:
                self.logger.warning("Failed to initialize TeamManager, AgentTeams disabled: %s", exc)
                self.enable_agent_teams = False
        self.logger.info("AgentTeams enabled=%s, team_store_dir=%s, task_store_dir=%s",
                         self.enable_agent_teams, self.team_store_dir, self.task_store_dir)
        
        # 创建 Summary 生成器（Phase 7）
        summary_generator = create_summary_generator(
            llm=self.llm,
            config=self.config,
            verbose=self.verbose,
        )
        
        # 历史管理器（替代 Agent._history）
        self.history_manager = HistoryManager(
            config=self.config,
            summary_generator=summary_generator,
        )
        
        # Skills
        self._skill_loader = SkillLoader(self.project_root)
        self._skills_prompt = ""
        self._refresh_skills_prompt()

        # 注册工具
        self._register_builtin_tools()
        self._mcp_clients = []
        self._mcp_tools_prompt = ""
        self._register_mcp_tools()
        
        # 上下文构建器
        self.context_builder = ContextBuilder(
            tool_registry=self.tool_registry,
            project_root=self.project_root,
            system_prompt_override=self.system_prompt,
            mcp_tools_prompt=self._mcp_tools_prompt,
            skills_prompt=self._skills_prompt,
        )

        # Trace 日志（单实例贯穿 Agent 生命周期）
        self.trace_logger = create_trace_logger()
        self._system_messages_logged = False
        self._run_id = 0
        self._system_messages_override: Optional[List[dict]] = None
    
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
        self.tool_registry.register_tool(
            SkillTool(project_root=self.project_root, skill_loader=self._skill_loader)
        )
        self.tool_registry.register_tool(BashTool(project_root=self.project_root))
        self.tool_registry.register_tool(
            AskUserTool(project_root=self.project_root, interactive=self.interactive)
        )
        # Task tool for subagent delegation
        self.tool_registry.register_tool(
            TaskTool(
                project_root=self.project_root,
                main_llm=self.llm,
                tool_registry=self.tool_registry,
            )
        )
        if self.enable_agent_teams:
            self._register_agent_teams_tools()

    def _register_agent_teams_tools(self) -> None:
        try:
            from tools.builtin.team_create import TeamCreateTool
            from tools.builtin.send_message import SendMessageTool
            from tools.builtin.team_status import TeamStatusTool
            from tools.builtin.team_delete import TeamDeleteTool
        except Exception as exc:
            self.logger.warning("AgentTeams enabled but team tools unavailable: %s", exc)
            return

        self.tool_registry.register_tool(TeamCreateTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(SendMessageTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamStatusTool(project_root=self.project_root, team_manager=self.team_manager))
        self.tool_registry.register_tool(TeamDeleteTool(project_root=self.project_root, team_manager=self.team_manager))

    def _refresh_skills_prompt(self) -> None:
        refresh = os.getenv("SKILLS_REFRESH_ON_CALL", "true").lower() in {"1", "true", "yes", "y", "on"}
        if refresh:
            self._skill_loader.refresh_if_stale()
        elif not self._skills_prompt:
            self._skill_loader.scan()
        budget = int(os.getenv("SKILLS_PROMPT_CHAR_BUDGET", "12000"))
        self._skills_prompt = self._skill_loader.format_skills_for_prompt(budget)

    def _register_mcp_tools(self) -> None:
        """可选：注册 MCP 工具（基于 MCP_SERVERS 配置）"""
        try:
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
        """
        Code Agent 的入口（Message List 自然累积模式）
        
        流程：
        1. 预处理用户输入（@file 解析）
        2. 检查是否需要压缩历史
        3. 将用户消息写入 history（轮次开始）
        4. 运行 ReAct 循环（每步 assistant/tool 消息自然累积）
        5. 返回最终结果
        
        Message List 模式：
        - 不再使用 scratchpad 拼接
        - 每步的 messages 由 history 自然累积
        - L1/L2 作为 system messages
        - L3 是累积的 user/assistant/tool
        """
        show_raw = kwargs.pop("show_raw", False)
        if not show_raw:
            self.last_response_raw = None

        if self.console_progress:
            self._console("⏳ Agent 正在处理，请稍候...")

        # 1. 预处理用户输入（@file 解析）
        self._refresh_skills_prompt()
        self.context_builder.set_skills_prompt(self._skills_prompt)
        preprocess_result = preprocess_input(input_text)
        processed_input = preprocess_result.processed_input
        
        if preprocess_result.mentioned_files:
            mentioned = ", ".join(preprocess_result.mentioned_files)
            if self.console_verbose:
                self._console(f"\n📎 检测到文件引用: {mentioned}")
                if preprocess_result.truncated_count > 0:
                    self._console(f"   (另有 {preprocess_result.truncated_count} 个文件被省略)")
            elif self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("检测到文件引用: %s", mentioned)
                if preprocess_result.truncated_count > 0:
                    self.logger.debug("另有 %d 个文件被省略", preprocess_result.truncated_count)

        trace_logger = self.trace_logger
        self._run_id += 1
        run_id = self._run_id

        self._log_system_messages_if_needed(trace_logger)
        trace_logger.log_event(
            "run_start",
            {
                "run_id": run_id,
                "input": input_text,
                "processed": processed_input,
            },
            step=0,
        )
        
        # 2. 压缩检测改为每次 ReAct 之前（循环内）

        # 3. 将用户消息写入 history（轮次开始时写入）
        self.history_manager.append_user(processed_input)
        trace_logger.log_event("user_input", {"text": input_text, "processed": processed_input}, step=0)
        self._log_message_write(trace_logger, "user", processed_input, {}, step=0)

        if self.console_verbose:
            self._console(f"\n⚙️ Engine 启动: {input_text}")
        elif self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Engine 启动: %s", input_text)

        response_text = ""
        try:
            response_text = self._react_loop(
                pending_input=processed_input,
                show_raw=show_raw,
                trace_logger=trace_logger,
            )
        finally:
            trace_logger.log_event(
                "run_end",
                {"run_id": run_id, "final": response_text if "response_text" in locals() else ""},
                step=0,
            )
        if self.console_progress:
            self._console("✅ Agent 已完成")

        self.logger.debug("response=%s", response_text)
        self.logger.info("history_size=%d, rounds=%d", 
                        self.history_manager.get_message_count(),
                        self.history_manager.get_rounds_count())
        return response_text

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

    # =========================================================================
    # ReAct Core（Message List 自然累积模式）
    # =========================================================================

    def _react_loop(
        self,
        pending_input: str,
        show_raw: bool,
        trace_logger,
    ) -> str:
        """
        ReAct 循环（Message List 模式）
        
        每步：
        1. 构建 messages = system(L1/L2) + history(user/assistant/tool)
        2. 调用 LLM
        3. 解析 Thought/Action
        4. 若为 Finish：返回结果
        5. 若为工具调用：执行工具，将 assistant + tool 消息追加到 history
        """
        tools_schema = self.tool_registry.get_openai_tools()
        tool_choice = "auto"

        for step in range(1, self.max_steps + 1):
            if self.console_verbose:
                self._console(f"\n--- Step {step}/{self.max_steps} ---")
            elif self.console_progress:
                self._console(f"… Step {step}/{self.max_steps}")
            elif self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Step %d/%d", step, self.max_steps)

            # 每次 ReAct 前检查是否需要压缩
            if self.history_manager.should_compress(pending_input):
                estimated_tokens = self.history_manager.estimate_context_tokens(pending_input)
                threshold = int(self.config.context_window * self.config.compression_threshold)
                trace_logger.log_event("history_compression_triggered", {
                    "estimated_tokens": estimated_tokens,
                    "threshold": threshold,
                    "total_usage_tokens": self.history_manager.get_total_usage_tokens(),
                    "message_count": self.history_manager.get_message_count(),
                }, step=step)

                if self.console_verbose:
                    self._console("\n📦 触发历史压缩...")
                elif self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("触发历史压缩")

                rounds_before = self.history_manager.get_rounds_count()
                messages_before = self.history_manager.get_message_count()

                compress_info = self.history_manager.compact(
                    on_event=lambda ev, payload: trace_logger.log_event(ev, payload, step=step),
                    return_info=True,
                )
                compressed = bool(compress_info.get("compressed"))

                if compressed:
                    rounds_after = self.history_manager.get_rounds_count()
                    messages_after = self.history_manager.get_message_count()

                    trace_logger.log_event("history_compression_completed", {
                        "rounds_before": rounds_before,
                        "rounds_after": rounds_after,
                        "messages_compressed": messages_before - messages_after,
                        "summary_generated": compress_info.get("summary_generated", False),
                        "details": compress_info,
                    }, step=step)

                    # 记录压缩后的最终上下文（system + history）
                    compressed_history = self.history_manager.to_messages()
                    final_context = self.context_builder.build_messages(compressed_history)
                    trace_logger.log_event(
                        "history_compression_final_context",
                        {"message_count": len(final_context), "messages": final_context},
                        step=step,
                    )

                    if self.console_verbose:
                        self._console(f"✅ 压缩完成，当前轮次数: {rounds_after}")
                        self._print_context_preview(final_context)
                    elif self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("压缩完成，当前轮次数: %d", rounds_after)
                        self._print_context_preview(final_context)

            # 构建 messages 列表
            history_messages = self.history_manager.to_messages()
            messages = self._build_messages(history_messages)
            base_messages = messages
            
            trace_logger.log_event(
                "context_build",
                {"message_count": len(messages), "history_count": len(history_messages)},
                step=step,
            )

            usage = None
            empty_retry_used = False
            response_text = ""
            tool_calls: list[dict[str, Any]] = []

            while True:
                # 调用 LLM
                raw_response = self.llm.invoke_raw(messages, tools=tools_schema, tool_choice=tool_choice)
                if show_raw:
                    self.last_response_raw = (
                        raw_response.model_dump()
                        if hasattr(raw_response, "model_dump")
                        else raw_response
                    )

                response_text = self._extract_content(raw_response) or ""
                reasoning_content = self._extract_reasoning_content(raw_response)
                usage = self._extract_usage(raw_response)
                if usage and usage.get("total_tokens") is not None:
                    self.history_manager.update_last_usage(usage["total_tokens"])

                response_meta = self._extract_response_meta(raw_response)
                tool_calls = self._extract_tool_calls(raw_response)
                raw_dump = self._extract_raw_response(raw_response)
                trace_logger.log_event(
                    "model_output",
                    {
                        "raw": response_text,
                        "usage": usage,
                        "meta": response_meta,
                        "raw_response": raw_dump,
                        "tool_calls": tool_calls,
                    },
                    step=step,
                )

                if self.console_verbose and reasoning_content:
                    display_reasoning = reasoning_content
                    if len(display_reasoning) > 1200:
                        display_reasoning = display_reasoning[:1200] + "...(truncated)"
                    self._console(f"\n🧠 Reasoning: {display_reasoning}\n")

                if tool_calls or (response_text and str(response_text).strip()):
                    break

                # 重试一次并追加提示
                if not empty_retry_used:
                    empty_retry_used = True
                    hint = "上次 content 为空且未返回 tool_calls，请在 content 中回复最终答案，或使用工具调用。"
                    messages = base_messages + [{"role": "user", "content": hint}]
                    trace_logger.log_event(
                        "empty_response_retry",
                        {
                            "finish_reason": response_meta.get("finish_reason"),
                            "content_len": response_meta.get("content_len"),
                            "reasoning_len": response_meta.get("reasoning_len"),
                            "hint": hint,
                        },
                        step=step,
                    )
                    if self.console_verbose:
                        self._console("⚠️ LLM返回空响应，追加提示后重试一次")
                    else:
                        self.logger.warning("LLM返回空响应，追加提示后重试一次")
                    continue

                if self.console_verbose:
                    self._console("❌ LLM返回空响应")
                else:
                    self.logger.error("LLM返回空响应")
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "llm_response",
                        "error_code": "INTERNAL_ERROR",
                        "message": "Empty response",
                        "meta": response_meta,
                    },
                    step=step,
                )
                break

            if not tool_calls and (not response_text or not str(response_text).strip()):
                break
            # 有工具调用：写入 assistant + 执行 tools
            if tool_calls:
                # ensure each tool_call has an id (OpenAI strict requirement)
                for call in tool_calls:
                    if not call.get("id"):
                        call["id"] = f"call_{uuid.uuid4().hex}"
                assistant_content = str(response_text or "")
                self.history_manager.append_assistant(
                    content=assistant_content,
                    metadata={
                        "step": step,
                        "action_type": "tool_call",
                        "tool_calls": tool_calls,
                    },
                    reasoning_content=reasoning_content,  # ⚠️ 传递 reasoning_content
                )
                self._log_message_write(
                    trace_logger,
                    "assistant",
                    assistant_content,
                    {"action_type": "tool_call", "tool_calls": tool_calls},
                    step,
                )

                for call in tool_calls:
                    tool_name = call.get("name") or "unknown_tool"
                    tool_call_id = call.get("id") or f"call_{uuid.uuid4().hex}"
                    raw_args = call.get("arguments") or {}
                    tool_input, parse_err = self._ensure_json_input(raw_args)
                    if parse_err:
                        error_result = {
                            "status": "error",
                            "error": {"code": "INVALID_PARAM", "message": f"Tool arguments parse error: {parse_err}"},
                            "data": {},
                        }
                        observation = json.dumps(error_result, ensure_ascii=False)
                        trace_logger.log_event(
                            "error",
                            {
                                "stage": "tool_call_parse",
                                "error_code": "INVALID_PARAM",
                                "message": str(parse_err),
                                "tool": tool_name,
                                "tool_call_id": tool_call_id,
                            },
                            step=step,
                        )
                    else:
                        trace_logger.log_event("tool_call", {"tool": tool_name, "args": tool_input, "tool_call_id": tool_call_id}, step=step)
                        if self.console_verbose:
                            self._console(f"\n🎬 Action: {tool_name}[{tool_input}]\n")
                        elif self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug("Action: %s %s", tool_name, tool_input)
                        try:
                            observation = self._execute_tool(tool_name, tool_input)
                            try:
                                result_obj = json.loads(observation)
                                trace_logger.log_event("tool_result", {"tool": tool_name, "result": result_obj}, step=step)
                            except json.JSONDecodeError:
                                trace_logger.log_event("tool_result", {"tool": tool_name, "result": {"text": observation}}, step=step)
                        except Exception as e:
                            error_result = {"status": "error", "error": {"code": "EXECUTION_ERROR", "message": str(e)}, "data": {}}
                            observation = json.dumps(error_result, ensure_ascii=False)
                            trace_logger.log_event("error", {"stage": "tool_execution", "error_code": "EXECUTION_ERROR", "message": str(e), "tool": tool_name, "traceback": tb.format_exc()}, step=step)

                    self.history_manager.append_tool(
                        tool_name=tool_name,
                        raw_result=observation,
                        metadata={"step": step, "tool_call_id": tool_call_id},
                        project_root=self.project_root,
                    )
                    self._log_message_write(
                        trace_logger,
                        "tool",
                        observation,
                        {"tool_name": tool_name, "tool_call_id": tool_call_id},
                        step,
                    )

                    if self.console_verbose:
                        display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                        self._console(f"\n👀 Observation: {display_obs}\n")
                    elif self.logger.isEnabledFor(logging.DEBUG):
                        display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                        self.logger.debug("Observation: %s", display_obs)
                continue

            # 无工具调用：视为最终回答
            final_text = str(response_text).strip()
            self.history_manager.append_assistant(
                content=final_text,
                metadata={"step": step, "action_type": "final"},
                reasoning_content=reasoning_content,  # ⚠️ 传递 reasoning_content
            )
            self._log_message_write(trace_logger, "assistant", final_text, {"action_type": "final"}, step)
            trace_logger.log_event("finish", {"final": final_text}, step=step)
            return final_text

        return "抱歉，我无法在限定步数内完成这个任务。"

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

    def _build_messages(self, history_messages: list[dict]) -> list[dict]:
        system_messages = self._get_system_messages_for_run()
        return list(system_messages) + list(history_messages)

    def save_session(self, path: str) -> None:
        """保存会话快照（含 system messages）。"""
        system_messages = self._get_system_messages_for_run()
        history_messages = self.history_manager.serialize_messages()
        tool_schema = self.tool_registry.get_openai_tools()
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
        )
        save_session_snapshot(path, snapshot)

    def load_session(self, path: str) -> None:
        """从快照恢复会话（scheme B）。"""
        snapshot = load_session_snapshot(path)
        self._system_messages_override = snapshot.get("system_messages") or []
        history_items = snapshot.get("history_messages") or []
        self.history_manager.load_messages(history_items)
        self.tool_registry.import_read_cache(snapshot.get("read_cache") or {})

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

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        res = self.tool_registry.execute_tool(tool_name, tool_input)
        return str(res)

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
        def _get_attr(obj, key: str):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        try:
            choices = _get_attr(raw_response, "choices")
            if not choices:
                return None
            choice = choices[0]
            message = _get_attr(choice, "message")
            if not message:
                return None

            reasoning = _get_attr(message, "reasoning_content") or _get_attr(message, "reasoning")
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
        def _get_attr(obj, key: str):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        try:
            choices = _get_attr(raw_response, "choices")
            if not choices:
                return []
            choice = choices[0]
            message = _get_attr(choice, "message")
            if not message:
                return []
            tool_calls = _get_attr(message, "tool_calls") or []
            calls: list[dict[str, Any]] = []
            if tool_calls:
                for call in tool_calls:
                    fn = _get_attr(call, "function") or {}
                    name = _get_attr(fn, "name") or _get_attr(call, "name") or "unknown_tool"
                    arguments = _get_attr(fn, "arguments") or _get_attr(call, "arguments") or {}
                    call_id = _get_attr(call, "id")
                    calls.append({
                        "id": call_id,
                        "name": name,
                        "arguments": arguments,
                    })
                return calls

            # 兼容旧 function_call
            function_call = _get_attr(message, "function_call")
            if function_call:
                name = _get_attr(function_call, "name") or "unknown_tool"
                arguments = _get_attr(function_call, "arguments") or {}
                return [{"id": None, "name": name, "arguments": arguments}]
        except Exception:
            return []

        return []

    @staticmethod
    def _extract_response_meta(raw_response: Any) -> dict:
        """提取响应元信息，辅助定位空响应原因"""
        def _get_attr(obj, key: str):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        meta: dict = {}
        try:
            choices = _get_attr(raw_response, "choices") or []
            if not choices:
                return meta
            choice = choices[0]
            meta["finish_reason"] = _get_attr(choice, "finish_reason")
            message = _get_attr(choice, "message")
            if not message:
                return meta
            meta["role"] = _get_attr(message, "role")

            content = _get_attr(message, "content")
            reasoning_content = _get_attr(message, "reasoning_content") or _get_attr(message, "reasoning")
            refusal = _get_attr(message, "refusal")
            tool_calls = _get_attr(message, "tool_calls")
            function_call = _get_attr(message, "function_call")

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
            if hasattr(raw_response, "dict"):
                return raw_response.dict()
            if isinstance(raw_response, dict):
                return raw_response
        except Exception:
            pass
        return {"raw": str(raw_response)}
    
    # =========================================================================
    # 兼容 Agent 基类接口（使用 HistoryManager）
    # =========================================================================
    
    def add_message(self, message: Message):
        """兼容旧接口：添加消息到历史"""
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
        """兼容旧接口：清空历史"""
        self.history_manager.clear()
    
    def get_history(self) -> List[Message]:
        """兼容旧接口：获取历史"""
        return self.history_manager.get_messages()
