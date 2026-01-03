import json
import re
import traceback as tb
from typing import Optional, List, Tuple, Any, Dict

from core.llm import HelloAgentsLLM
from core.context_builder import ContextBuilder
from core.trace_logger import TraceLogger, create_trace_logger
from tools.registry import ToolRegistry

class ReActEngine:
    """
    通用 ReAct 执行引擎。
    职责：
    1. 维护 ReAct 循环 (Loop)
    2. 解析 LLM 输出 (Parse)
    3. 执行工具 (Execute)
    4. 维护短期历史 (Scratchpad)
    """

    def __init__(
        self,
        llm: HelloAgentsLLM,
        tool_registry: ToolRegistry,
        max_steps: int = 12,
        verbose: bool = True,
        capture_raw: bool = False,
        context_builder: Optional[ContextBuilder] = None,
        trace_logger: Optional[TraceLogger] = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.verbose = verbose
        self.capture_raw = capture_raw
        self.last_response_raw = None
        # scratchpad 用于存储 ReAct 的思考链 (Thought -> Action -> Obs)
        self.scratchpad: List[str] = []
        if context_builder is None:
            raise ValueError("context_builder is required; prompt assembly is handled outside ReActEngine.")
        self.context_builder = context_builder
        
        # TraceLogger（可选）
        self.trace = trace_logger or create_trace_logger()
        self._trace_enabled = self.trace.enabled

    def run(self, question: str, context_prompt: str = "") -> str:
        """
        启动引擎处理任务。
        :param question: 用户的当前问题
        :param context_prompt: 业务特定的上下文（例如 AGENTS.md 的内容，或 CodeAgent 的 System Prompt）
        """
        self.scratchpad = [] # 每次运行前清空短期记忆
        
        if self.verbose:
            print(f"\n⚙️ Engine 启动: {question}")
        
        # 1. 记录 user_input
        if self._trace_enabled:
            self.trace.log_event("user_input", {"text": question}, step=0)
        
        try:
            return self._run_loop(question, context_prompt)
        except Exception as e:
            # 捕获异常并记录
            if self._trace_enabled:
                self.trace.log_event("error", {
                    "stage": "engine_run",
                    "error_code": "INTERNAL_ERROR",
                    "message": str(e),
                    "traceback": tb.format_exc(),
                }, step=0)
            raise
        finally:
            # 确保 finalize
            if self._trace_enabled:
                self.trace.finalize()
    
    def _run_loop(self, question: str, context_prompt: str) -> str:
        """ReAct 主循环（内部方法）"""

        for step in range(1, self.max_steps + 1):
            if self.verbose:
                print(f"\n--- Step {step}/{self.max_steps} ---")

            # 1. 构建完整的 Prompt
            prompt = self.context_builder.build(question, context_prompt, self.scratchpad)
            
            # 2. 调用 LLM（trace 启用时使用 invoke_raw 获取 usage）
            messages = [{"role": "user", "content": prompt}]
            usage = None
            
            if self._trace_enabled or self.capture_raw:
                raw_response = self.llm.invoke_raw(messages)
                if self.capture_raw:
                    self.last_response_raw = (
                        raw_response.model_dump()
                        if hasattr(raw_response, "model_dump")
                        else raw_response
                    )
                try:
                    response_text = raw_response.choices[0].message.content
                    # 提取 usage
                    if hasattr(raw_response, "usage") and raw_response.usage:
                        usage = {
                            "prompt_tokens": raw_response.usage.prompt_tokens,
                            "completion_tokens": raw_response.usage.completion_tokens,
                            "total_tokens": raw_response.usage.total_tokens,
                        }
                except Exception:
                    response_text = str(raw_response)
            else:
                self.last_response_raw = None
                response_text = self.llm.invoke(messages)
            
            # 3. 记录 model_output
            if self._trace_enabled:
                self.trace.log_event("model_output", {
                    "raw": response_text,
                    "usage": usage,
                }, step=step)

            if not response_text or not str(response_text).strip():
                self._record_observation("❌ LLM返回空响应，无法继续。")
                if self._trace_enabled:
                    self.trace.log_event("error", {
                        "stage": "llm_response",
                        "error_code": "INTERNAL_ERROR",
                        "message": "LLM returned empty response",
                    }, step=step)
                break

            # 4. 解析 Thought 和 Action
            thought, action = self._parse_thought_action(str(response_text))
            
            if self.verbose and thought:
                print()
                print(f"🤔 Thought:\n{thought}")
                print()

            if not action:
                finish_payload = self._extract_finish_direct(str(response_text))
                if finish_payload is not None:
                    if self.verbose:
                        print()
                        print("✅ Finish")
                        print()
                    # 6. 记录 finish
                    if self._trace_enabled:
                        self.trace.log_event("parsed_action", {
                            "thought": thought or "",
                            "action": "Finish",
                            "args": {"payload": finish_payload},
                        }, step=step)
                    if self._trace_enabled:
                        self.trace.log_event("finish", {"final": finish_payload}, step=step)
                    return finish_payload
                self._record_observation("⚠️ 未解析到 Action（请模型严格输出 Thought/Action）。")
                continue

            # 7. 处理 Finish 信号
            if action.strip().startswith("Finish["):
                final_answer = self._parse_bracket_payload(action)
                if self.verbose:
                    print()
                    print("✅ Finish")
                    print()
                # 8. 记录 finish
                if self._trace_enabled:
                    self.trace.log_event("parsed_action", {
                        "thought": thought or "",
                        "action": "Finish",
                        "args": {"payload": final_answer},
                    }, step=step)
                if self._trace_enabled:
                    self.trace.log_event("finish", {"final": final_answer}, step=step)
                return final_answer

            # 9. 处理 Tool Call
            tool_name, tool_raw_input = self._parse_tool_call(action)
            if not tool_name:
                self._record_observation(f"⚠️ Action格式不合法：{action}")
                continue

            # 10. 校验 JSON
            tool_input, parse_err = self._ensure_json_input(tool_raw_input)
            # 10.1 记录 parsed_action（含解析后的参数）
            if self._trace_enabled:
                self.trace.log_event("parsed_action", {
                    "thought": thought or "",
                    "action": action or "",
                    "args": tool_input if parse_err is None else {"raw": tool_raw_input},
                }, step=step)
            if parse_err:
                self.scratchpad.append(f"Action: {action}")
                self._record_observation(f"❌ 工具参数解析错误：{parse_err}\n原始参数：{tool_raw_input}")
                if self._trace_enabled:
                    self.trace.log_event("error", {
                        "stage": "param_parsing",
                        "error_code": "INVALID_PARAM",
                        "message": parse_err,
                        "tool": tool_name,
                        "args": tool_raw_input,
                    }, step=step)
                continue
            
            # 11. 记录 tool_call
            if self._trace_enabled:
                self.trace.log_event("tool_call", {
                    "tool": tool_name,
                    "args": tool_input,
                }, step=step)

            if self.verbose:
                print()
                print(f"🎬 Action: {tool_name}[{tool_input}]")
                print()

            # 12. 执行工具
            try:
                observation = self._execute_tool(tool_name, tool_input)
                
                # 13. 记录 tool_result
                if self._trace_enabled:
                    # 尝试解析为 JSON（工具返回的是标准协议格式）
                    try:
                        result_obj = json.loads(observation)
                        self.trace.log_event("tool_result", {
                            "tool": tool_name,
                            "result": result_obj,
                        }, step=step)
                    except json.JSONDecodeError:
                        # 如果不是 JSON，直接记录文本
                        self.trace.log_event("tool_result", {
                            "tool": tool_name,
                            "result": {"text": observation},
                        }, step=step)
                        
            except Exception as e:
                observation = f"❌ 工具执行异常: {str(e)}"
                
                # 14. 记录 error
                if self._trace_enabled:
                    self.trace.log_event("error", {
                        "stage": "tool_execution",
                        "error_code": "EXECUTION_ERROR",
                        "message": str(e),
                        "tool": tool_name,
                        "args": tool_input,
                        "traceback": tb.format_exc(),
                    }, step=step)

            if self.verbose:
                display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                print()
                print(f"👀 Observation: {display_obs}")
                print()

            # 15. 更新历史
            self.scratchpad.append(f"Action: {tool_name}[{json.dumps(tool_input, ensure_ascii=False)}]")
            self._record_observation(observation)

        return "抱歉，我无法在限定步数内完成这个任务。"

    # ---------- Helper Methods ----------

    def _record_observation(self, obs: str):
        self.scratchpad.append(f"Observation: {obs}")

    def _execute_tool(self, tool_name: str, tool_input: Any) -> str:
        # 简单封装，处理可能的类型差异
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
        if not spans: return None
        last = spans[-1]
        content = text[last.end():].strip()
        return content if content else None

    def _extract_finish_direct(self, text: str) -> Optional[str]:
        """
        兜底识别裸 Finish[...]（无 Action 前缀）。
        """
        matches = list(re.finditer(r"^Finish\[(.*)\]\s*$", text, flags=re.MULTILINE | re.DOTALL))
        if not matches:
            return None
        payload = matches[-1].group(1).strip()
        return payload if payload else ""

    def _parse_tool_call(self, action: str) -> Tuple[Optional[str], str]:
        m = re.match(r"^([A-Za-z0-9_\-]+)\[(.*)\]\s*$", action.strip(), flags=re.DOTALL)
        if not m: return None, ""
        return m.group(1), m.group(2).strip()

    def _parse_bracket_payload(self, action: str) -> str:
        m = re.match(r"^[A-Za-z0-9_\-]+\[(.*)\]\s*$", action.strip(), flags=re.DOTALL)
        return (m.group(1).strip() if m else "").strip()

    def _ensure_json_input(self, raw: str) -> Tuple[Any, Optional[str]]:
        if raw is None: return {}, None
        s = str(raw).strip()
        if not s: return {}, None
        try:
            return json.loads(s), None
        except Exception as e:
            return None, str(e)
