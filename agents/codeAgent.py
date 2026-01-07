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
    def __init__(
        self, 
        name: str, 
        llm: HelloAgentsLLM, 
        tool_registry: ToolRegistry,
        project_root: str,  # Code Agent 特有的属性
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
        # 注册 LS/list_files 工具
        self.tool_registry.register_tool(
            ListFilesTool(project_root=self.project_root, working_dir=self.project_root)
        )
        # 注册 Glob/search_files_by_name 工具
        self.tool_registry.register_tool(SearchFilesByNameTool(project_root=self.project_root))
        # 注册 Grep 工具
        self.tool_registry.register_tool(GrepTool(project_root=self.project_root))
        # 注册 Read 工具
        self.tool_registry.register_tool(ReadTool(project_root=self.project_root))
        # 注册 Write 工具
        self.tool_registry.register_tool(WriteTool(project_root=self.project_root))
        # 注册 Edit 工具
        self.tool_registry.register_tool(EditTool(project_root=self.project_root))
        # 注册 MultiEdit 工具
        self.tool_registry.register_tool(MultiEditTool(project_root=self.project_root))
        # 注册 TodoWrite 工具
        self.tool_registry.register_tool(TodoWriteTool(project_root=self.project_root))
        # 注册 Bash 工具
        self.tool_registry.register_tool(BashTool(project_root=self.project_root))
        
        # 上下文构建器
        self.context_builder = ContextBuilder(
            tool_registry=self.tool_registry,
            project_root=self.project_root,
            system_prompt_override=self.system_prompt,
        )

    def run(self, input_text: str, **kwargs) -> str:
        """
        Code Agent 的入口。
       
        """
        show_raw = kwargs.pop("show_raw", False)
        if not show_raw:
            self.last_response_raw = None

        # self.logger.info("CodeAgent start")
        # self.logger.info("input_text=%s", input_text)

        history_lines = "\n".join(
            f"{m.role}: {m.content}" for m in self.get_history()
        ) or "(empty)"
        context_prompt = f"[Chat History]\n{history_lines}"

        trace_logger = create_trace_logger()
        scratchpad: List[str] = []

        if self.verbose:
            print(f"\n⚙️ Engine 启动: {input_text}")

        # 记录 user_input
        trace_logger.log_event("user_input", {"text": input_text}, step=0)

        try:
            response_text = self._react_loop(
                input_text=input_text,
                context_prompt=context_prompt,
                scratchpad=scratchpad,
                show_raw=show_raw,
                trace_logger=trace_logger,
            )
        finally:
            trace_logger.finalize()

        user_message = Message(content=input_text, role="user")
        self.add_message(user_message)
        assistant_message = Message(content=response_text, role="assistant")
        self.add_message(assistant_message)

        # Avoid duplicating full assistant output in stdout; keep detailed content at DEBUG.
        self.logger.debug("response=%s", response_text)
        self.logger.info("history_size=%d", len(self.get_history()))
        return response_text

    # ---------- ReAct Core ----------

    def _react_loop(
        self,
        input_text: str,
        context_prompt: str,
        scratchpad: List[str],
        show_raw: bool,
        trace_logger,
    ) -> str:
        for step in range(1, self.max_steps + 1):
            if self.verbose:
                print(f"\n--- Step {step}/{self.max_steps} ---")

            prompt = self.context_builder.build(input_text, context_prompt, scratchpad)
            trace_logger.log_event(
                "context_build",
                {"prompt_chars": len(prompt), "scratchpad_items": len(scratchpad)},
                step=step,
            )

            messages = [{"role": "user", "content": prompt}]
            usage = None
            if trace_logger.enabled or show_raw:
                raw_response = self.llm.invoke_raw(messages)
                if show_raw:
                    self.last_response_raw = (
                        raw_response.model_dump()
                        if hasattr(raw_response, "model_dump")
                        else raw_response
                    )
                try:
                    response_text = raw_response.choices[0].message.content
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

            trace_logger.log_event(
                "model_output",
                {"raw": response_text, "usage": usage},
                step=step,
            )

            if not response_text or not str(response_text).strip():
                self._record_observation(scratchpad, "❌ LLM返回空响应，无法继续。")
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "llm_response",
                        "error_code": "INTERNAL_ERROR",
                        "message": "LLM returned empty response",
                    },
                    step=step,
                )
                break

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
                    trace_logger.log_event(
                        "parsed_action",
                        {"thought": thought or "", "action": "Finish", "args": {"payload": finish_payload}},
                        step=step,
                    )
                    trace_logger.log_event("finish", {"final": finish_payload}, step=step)
                    return finish_payload
                self._record_observation(scratchpad, "⚠️ 未解析到 Action（请模型严格输出 Thought/Action）。")
                continue

            if action.strip().startswith("Finish["):
                final_answer = self._parse_bracket_payload(action)
                if self.verbose:
                    print()
                    print("✅ Finish")
                    print()
                trace_logger.log_event(
                    "parsed_action",
                    {"thought": thought or "", "action": "Finish", "args": {"payload": final_answer}},
                    step=step,
                )
                trace_logger.log_event("finish", {"final": final_answer}, step=step)
                return final_answer

            tool_name, tool_raw_input = self._parse_tool_call(action)
            if not tool_name:
                self._record_observation(scratchpad, f"⚠️ Action格式不合法：{action}")
                continue

            tool_input, parse_err = self._ensure_json_input(tool_raw_input)
            trace_logger.log_event(
                "parsed_action",
                {
                    "thought": thought or "",
                    "action": action or "",
                    "args": tool_input if parse_err is None else {"raw": tool_raw_input},
                },
                step=step,
            )
            if parse_err:
                scratchpad.append(f"Action: {action}")
                self._record_observation(
                    scratchpad,
                    f"❌ 工具参数解析错误：{parse_err}\n原始参数：{tool_raw_input}",
                )
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "param_parsing",
                        "error_code": "INVALID_PARAM",
                        "message": parse_err,
                        "tool": tool_name,
                        "args": tool_raw_input,
                    },
                    step=step,
                )
                continue

            trace_logger.log_event("tool_call", {"tool": tool_name, "args": tool_input}, step=step)

            if self.verbose:
                print()
                print(f"🎬 Action: {tool_name}[{tool_input}]")
                print()

            try:
                observation = self._execute_tool(tool_name, tool_input)
                try:
                    result_obj = json.loads(observation)
                    trace_logger.log_event(
                        "tool_result",
                        {"tool": tool_name, "result": result_obj},
                        step=step,
                    )
                except json.JSONDecodeError:
                    trace_logger.log_event(
                        "tool_result",
                        {"tool": tool_name, "result": {"text": observation}},
                        step=step,
                    )
            except Exception as e:
                observation = f"❌ 工具执行异常: {str(e)}"
                trace_logger.log_event(
                    "error",
                    {
                        "stage": "tool_execution",
                        "error_code": "EXECUTION_ERROR",
                        "message": str(e),
                        "tool": tool_name,
                        "args": tool_input,
                        "traceback": tb.format_exc(),
                    },
                    step=step,
                )

            if self.verbose:
                display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                print()
                print(f"👀 Observation: {display_obs}")
                print()

            scratchpad.append(
                f"Action: {tool_name}[{json.dumps(tool_input, ensure_ascii=False)}]"
            )
            self._record_observation(scratchpad, observation)

        return "抱歉，我无法在限定步数内完成这个任务。"

    def _record_observation(self, scratchpad: List[str], obs: str) -> None:
        scratchpad.append(f"Observation: {obs}")

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
