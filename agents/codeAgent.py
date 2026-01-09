import json
import re
import traceback as tb
from typing import Any, Optional, List, Tuple

from core.agent import Agent
from core.llm import HelloAgentsLLM
from core.message import Message
from core.config import Config
from core.context_builder import ContextBuilder
from core.trace_logger import create_trace_logger
from core.history_manager import HistoryManager
from core.input_preprocessor import preprocess_input
from core.summary_compressor import create_summary_generator
from tools.registry import ToolRegistry
from tools.builtin.list_files import ListFilesTool
from tools.builtin.search_files_by_name import SearchFilesByNameTool
from tools.builtin.search_code import GrepTool
from tools.builtin.read_file import ReadTool
from tools.builtin.write_file import WriteTool
from tools.builtin.edit_file import EditTool
from tools.builtin.edit_file_multi import MultiEditTool
from tools.builtin.todo_write import TodoWriteTool
from tools.builtin.bash import BashTool
from utils import setup_logger


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
        self.verbose = True
        
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
        
        # 注册工具
        self._register_builtin_tools()
        
        # 上下文构建器
        self.context_builder = ContextBuilder(
            tool_registry=self.tool_registry,
            project_root=self.project_root,
            system_prompt_override=self.system_prompt,
        )

        # Trace 日志（单实例贯穿 Agent 生命周期）
        self.trace_logger = create_trace_logger()
        self._system_messages_logged = False
        self._run_id = 0
    
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
        self.tool_registry.register_tool(BashTool(project_root=self.project_root))

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

        # 1. 预处理用户输入（@file 解析）
        preprocess_result = preprocess_input(input_text)
        processed_input = preprocess_result.processed_input
        
        if preprocess_result.mentioned_files and self.verbose:
            print(f"\n📎 检测到文件引用: {', '.join(preprocess_result.mentioned_files)}")
            if preprocess_result.truncated_count > 0:
                print(f"   (另有 {preprocess_result.truncated_count} 个文件被省略)")

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
        
        # 2. 检查是否需要压缩（A6 规则）
        if self.history_manager.should_compress(processed_input):
            estimated_tokens = self.history_manager._last_usage_tokens + len(processed_input) // 3
            threshold = int(self.config.context_window * self.config.compression_threshold)
            trace_logger.log_event("history_compression_triggered", {
                "estimated_tokens": estimated_tokens,
                "threshold": threshold,
                "message_count": self.history_manager.get_message_count(),
            }, step=0)
            
            if self.verbose:
                print("\n📦 触发历史压缩...")
            
            rounds_before = self.history_manager.get_rounds_count()
            messages_before = self.history_manager.get_message_count()
            
            compress_info = self.history_manager.compact(
                on_event=lambda ev, payload: trace_logger.log_event(ev, payload, step=0),
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
                }, step=0)

                # 记录压缩后的最终上下文（system + history）
                compressed_history = self.history_manager.to_messages()
                final_context = self.context_builder.build_messages(compressed_history)
                trace_logger.log_event(
                    "history_compression_final_context",
                    {"message_count": len(final_context), "messages": final_context},
                    step=0,
                )
                
                if self.verbose:
                    print(f"✅ 压缩完成，当前轮次数: {rounds_after}")
                    self._print_context_preview(final_context)

        # 3. 将用户消息写入 history（轮次开始时写入）
        self.history_manager.append_user(processed_input)
        trace_logger.log_event("user_input", {"text": input_text, "processed": processed_input}, step=0)
        self._log_message_write(trace_logger, "user", processed_input, {}, step=0)

        if self.verbose:
            print(f"\n⚙️ Engine 启动: {input_text}")

        response_text = ""
        try:
            response_text = self._react_loop(
                show_raw=show_raw,
                trace_logger=trace_logger,
            )
        finally:
            trace_logger.log_event(
                "run_end",
                {"run_id": run_id, "final": response_text if "response_text" in locals() else ""},
                step=0,
            )

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

    # =========================================================================
    # ReAct Core（Message List 自然累积模式）
    # =========================================================================

    def _react_loop(
        self,
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
        for step in range(1, self.max_steps + 1):
            if self.verbose:
                print(f"\n--- Step {step}/{self.max_steps} ---")

            # 构建 messages 列表
            history_messages = self.history_manager.to_messages()
            messages = self.context_builder.build_messages(history_messages)
            base_messages = messages
            
            trace_logger.log_event(
                "context_build",
                {"message_count": len(messages), "history_count": len(history_messages)},
                step=step,
            )

            usage = None
            empty_retry_used = False
            response_text = ""

            while True:
                # 调用 LLM
                raw_response = self.llm.invoke_raw(messages)
                if show_raw:
                    self.last_response_raw = (
                        raw_response.model_dump()
                        if hasattr(raw_response, "model_dump")
                        else raw_response
                    )

                response_text = self._extract_content(raw_response)
                usage = self._extract_usage(raw_response)
                if usage and usage.get("total_tokens") is not None:
                    self.history_manager.update_last_usage(usage["total_tokens"])

                response_meta = self._extract_response_meta(raw_response)
                raw_dump = self._extract_raw_response(raw_response)
                trace_logger.log_event(
                    "model_output",
                    {"raw": response_text, "usage": usage, "meta": response_meta, "raw_response": raw_dump},
                    step=step,
                )

                if response_text and str(response_text).strip():
                    break

                # 工具/函数调用恢复
                recovered_text, recover_meta = self._recover_empty_response(raw_response)
                if recovered_text:
                    response_text = recovered_text
                    trace_logger.log_event(
                        "empty_response_recovered",
                        {"source": recover_meta.get("source"), "details": recover_meta},
                        step=step,
                    )
                    break

                # 重试一次并追加提示
                if not empty_retry_used:
                    empty_retry_used = True
                    hint = "上次 content 为空，请务必在 content 输出 Thought/Action 或 Finish"
                    messages = base_messages + [{"role": "system", "content": hint}]
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
                    if self.verbose:
                        print("⚠️ LLM返回空响应，追加提示后重试一次")
                    continue

                if self.verbose:
                    print("❌ LLM返回空响应")
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

            if not response_text or not str(response_text).strip():
                break

            thought, action = self._parse_thought_action(str(response_text))

            if self.verbose and thought:
                print(f"\n🤔 Thought:\n{thought}\n")

            # 处理无 Action 的情况
            if not action:
                finish_payload = self._extract_finish_direct(str(response_text))
                if finish_payload is not None:
                    # Finish 路径：仅记录最终回答内容
                    assistant_content = finish_payload
                    self.history_manager.append_assistant(
                        content=assistant_content,
                        metadata={"step": step, "action_type": "finish"},
                    )
                    self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "finish"}, step)
                    if self.verbose:
                        print("\n✅ Finish\n")
                    trace_logger.log_event(
                        "parsed_action",
                        {"thought": thought or "", "action": "Finish", "args": {"payload": finish_payload}},
                        step=step,
                    )
                    trace_logger.log_event("finish", {"final": finish_payload}, step=step)
                    return finish_payload
                
                # 无 Action：按普通对话记录原始回复并结束
                assistant_content = str(response_text).strip()
                self.history_manager.append_assistant(
                    content=assistant_content,
                    metadata={"step": step, "action_type": "no_action"},
                )
                self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "no_action"}, step)
                return assistant_content

            # 处理 Finish Action
            if action.strip().startswith("Finish["):
                final_answer = self._parse_bracket_payload(action)
                assistant_content = final_answer
                self.history_manager.append_assistant(
                    content=assistant_content,
                    metadata={"step": step, "action_type": "finish"},
                )
                self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "finish"}, step)
                
                if self.verbose:
                    print("\n✅ Finish\n")
                trace_logger.log_event(
                    "parsed_action",
                    {"thought": thought or "", "action": "Finish", "args": {"payload": final_answer}},
                    step=step,
                )
                trace_logger.log_event("finish", {"final": final_answer}, step=step)
                return final_answer

            # 解析工具调用
            tool_name, tool_raw_input = self._parse_tool_call(action)
            if not tool_name:
                assistant_content = f"Thought: {thought or ''}\nAction: {action}\n(Invalid action format)"
                self.history_manager.append_assistant(content=assistant_content, metadata={"step": step, "action_type": "invalid_action"})
                self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "invalid_action"}, step)
                continue

            tool_input, parse_err = self._ensure_json_input(tool_raw_input)
            trace_logger.log_event("parsed_action", {"thought": thought or "", "action": action, "args": tool_input if parse_err is None else {"raw": tool_raw_input}}, step=step)
            
            if parse_err:
                assistant_content = f"Thought: {thought or ''}\nAction: {tool_name}[{tool_raw_input}]\n(Parameter parse error: {parse_err})"
                self.history_manager.append_assistant(content=assistant_content, metadata={"step": step, "action_type": "parse_error", "tool_name": tool_name})
                self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "parse_error"}, step)
                continue

            trace_logger.log_event("tool_call", {"tool": tool_name, "args": tool_input}, step=step)

            if self.verbose:
                print(f"\n🎬 Action: {tool_name}[{tool_input}]\n")

            # 写入 assistant 消息（Thought + Action）
            assistant_content = f"Thought: {thought or ''}\nAction: {tool_name}[{json.dumps(tool_input, ensure_ascii=False)}]"
            self.history_manager.append_assistant(content=assistant_content, metadata={"step": step, "action_type": "tool_call", "tool_name": tool_name})
            self._log_message_write(trace_logger, "assistant", assistant_content, {"action_type": "tool_call", "tool_name": tool_name}, step)

            # 执行工具
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

            # 写入 tool 消息到 history（压缩版）
            self.history_manager.append_tool(tool_name=tool_name, raw_result=observation, metadata={"step": step})
            self._log_message_write(trace_logger, "tool", observation, {"tool_name": tool_name}, step)

            if self.verbose:
                display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                print(f"\n👀 Observation: {display_obs}\n")

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
        system_messages = self.context_builder.get_system_messages()
        trace_logger.log_system_messages(system_messages)
        self._system_messages_logged = True

    def _print_context_preview(
        self,
        messages: list[dict],
        max_messages: int = 10,
        content_limit: int = 200,
    ) -> None:
        if not messages:
            print("（当前上下文为空）")
            return
        total = len(messages)
        preview = messages[:max_messages]
        print("\n📌 当前上下文（最多显示 10 条）")
        for msg in preview:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content = str(content).replace("\n", "\\n")
            if len(content) > content_limit:
                content = content[:content_limit] + "...(truncated)"
            print(f'message({role}, "{content}")')
        if total > max_messages:
            print(f"...（其余 {total - max_messages} 条已省略）")

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        res = self.tool_registry.execute_tool(tool_name, tool_input)
        return str(res)

    def _parse_thought_action(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        action_spans = list(re.finditer(r"^Action:\s*", text, flags=re.MULTILINE))
        if not action_spans:
            return self._extract_last_block(text, "Thought"), None
        last_action = action_spans[-1]
        action_content = text[last_action.end():].strip()
        action_line = action_content if action_content else None
        prefix = text[: last_action.start()]
        thought = self._extract_last_block(prefix, "Thought")
        return thought, action_line

    def _extract_last_block(self, text: str, tag: str) -> Optional[str]:
        spans = list(re.finditer(rf"^{re.escape(tag)}:\s*", text, flags=re.MULTILINE))
        if not spans:
            return None
        last = spans[-1]
        content = text[last.end():].strip()
        return content if content else None

    def _extract_finish_direct(self, text: str) -> Optional[str]:
        matches = list(re.finditer(r"^Finish\[(.*)\]\s*$", text, flags=re.MULTILINE | re.DOTALL))
        if not matches:
            return None
        payload = matches[-1].group(1).strip()
        return payload if payload else ""

    def _parse_tool_call(self, action: str) -> Tuple[Optional[str], str]:
        m = re.match(r"^([A-Za-z0-9_\-]+)\[(.*)\]\s*$", action.strip(), flags=re.DOTALL)
        if not m:
            return None, ""
        return m.group(1), m.group(2).strip()

    def _parse_bracket_payload(self, action: str) -> str:
        m = re.match(r"^[A-Za-z0-9_\-]+\[(.*)\]\s*$", action.strip(), flags=re.DOTALL)
        return (m.group(1).strip() if m else "").strip()

    def _ensure_json_input(self, raw: str) -> Tuple[Any, Optional[str]]:
        if raw is None:
            return {}, None
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
                return raw_response.choices[0].message.content
            if isinstance(raw_response, dict) and raw_response.get("choices"):
                return raw_response["choices"][0]["message"].get("content")
        except Exception:
            return str(raw_response)

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
    def _recover_empty_response(raw_response: Any) -> Tuple[Optional[str], Optional[dict]]:
        """
        尝试从空响应中恢复：
        - 支持 OpenAI function_call/tool_calls 返回但 content 为空的场景
        - 返回 (recovered_text, meta)；若无法恢复则返回 (None, None)
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
                return None, None
            choice = choices[0]
            message = _get_attr(choice, "message")
            if not message:
                return None, None

            tool_calls = _get_attr(message, "tool_calls") or []
            if tool_calls:
                call = tool_calls[0]
                fn = _get_attr(call, "function") or {}
                name = _get_attr(fn, "name") or "unknown_tool"
                arguments = _get_attr(fn, "arguments") or ""
                args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                return f"Action: {name}[{args_str}]", {"source": "tool_call", "tool": name}

            function_call = _get_attr(message, "function_call")
            if function_call:
                name = _get_attr(function_call, "name") or "unknown_function"
                arguments = _get_attr(function_call, "arguments") or ""
                args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
                return f"Action: {name}[{args_str}]", {"source": "function_call", "tool": name}

            content = _get_attr(message, "content")
            if content and str(content).strip():
                return str(content), {"source": "content"}
        except Exception:
            return None, None

        return None, None


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
            self.history_manager.append_tool(tool_name, message.content, message.metadata)
        elif message.role == "summary":
            self.history_manager.append_summary(message.content)
    
    def clear_history(self):
        """兼容旧接口：清空历史"""
        self.history_manager.clear()
    
    def get_history(self) -> List[Message]:
        """兼容旧接口：获取历史"""
        return self.history_manager.get_messages()
