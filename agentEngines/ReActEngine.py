import json
import re
from typing import Optional, List, Tuple, Any, Dict

# 假设这些类在你原本的项目结构中
from core.llm import HelloAgentsLLM
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

    DEFAULT_PROMPT_TEMPLATE = """你是一个具备推理和行动能力的AI助手。你需要通过多轮“思考->调用工具->观察->再思考”完成任务。

## 可用工具（带参数定义和用法示例）
下方列出了所有可用工具的：
- 工具描述
- 工具用法
- 参数列表（名称 / 类型 / 是否必填 / 默认值）
- 调用示例（ToolName[{{...}}]）

调用工具时必须遵守以下规则：
1. Action 行格式固定为：Action: 工具名[JSON参数]
2. JSON参数必须是一个合法的 JSON 对象（或数组），键名必须来自该工具的参数列表，不要发明新字段。
3. 如不确定如何调用某个工具，先查看对应的 Parameters 和 Examples，而不要凭空猜测。
以下是可用工具列表：
{tools}

## 输出格式（必须严格遵守）
每次只输出一组 Thought + Action：

Thought: 你的简短分析（可多行）
Action: 工具名[JSON参数]  或  Finish[最终答案]
Action 必须单行；如需换行请使用 \\n。

### 重要规则
- Action 里 **工具参数必须是合法 JSON**（对象或数组）。
- 每次只做一个动作；拿到 Observation 后再继续下一步。
- 当信息不足时继续调用工具；足够回答时再 Finish。
- 结束任务时必须使用：Action: Finish[最终答案]（单独输出 Finish[...] 视为不合规）。

## 任务背景
{context}

## 当前问题
Question: {question}

## 执行历史（Action/Observation）
{history}

现在开始："""

    def __init__(
        self,
        llm: HelloAgentsLLM,
        tool_registry: ToolRegistry,
        max_steps: int = 12,
        verbose: bool = True,
        capture_raw: bool = False
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.verbose = verbose
        self.capture_raw = capture_raw
        self.last_response_raw = None
        # scratchpad 用于存储 ReAct 的思考链 (Thought -> Action -> Obs)
        self.scratchpad: List[str] = []

    def run(self, question: str, context_prompt: str = "") -> str:
        """
        启动引擎处理任务。
        :param question: 用户的当前问题
        :param context_prompt: 业务特定的上下文（例如 AGENTS.md 的内容，或 CodeAgent 的 System Prompt）
        """
        self.scratchpad = [] # 每次运行前清空短期记忆
        
        if self.verbose:
            print(f"\n⚙️ Engine 启动: {question}")

        for step in range(1, self.max_steps + 1):
            if self.verbose:
                print(f"\n--- Step {step}/{self.max_steps} ---")

            # 1. 构建完整的 Prompt
            prompt = self._build_prompt(question, context_prompt)
            
            # 2. 调用 LLM
            messages = [{"role": "user", "content": prompt}]
            if self.capture_raw:
                raw_response = self.llm.invoke_raw(messages)
                self.last_response_raw = (
                    raw_response.model_dump()
                    if hasattr(raw_response, "model_dump")
                    else raw_response
                )
                try:
                    response_text = raw_response.choices[0].message.content
                except Exception:
                    response_text = str(raw_response)
            else:
                self.last_response_raw = None
                response_text = self.llm.invoke(messages)

            if not response_text or not str(response_text).strip():
                self._record_observation("❌ LLM返回空响应，无法继续。")
                break

            # 3. 解析 Thought 和 Action
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
                        print(f"✅ Finish: {finish_payload}")
                        print()
                    return finish_payload
                self._record_observation("⚠️ 未解析到 Action（请模型严格输出 Thought/Action）。")
                continue

            # 4. 处理 Finish 信号
            if action.strip().startswith("Finish["):
                final_answer = self._parse_bracket_payload(action)
                if self.verbose:
                    print()
                    print(f"✅ Finish: {final_answer}")
                    print()
                return final_answer

            # 5. 处理 Tool Call
            tool_name, tool_raw_input = self._parse_tool_call(action)
            if not tool_name:
                self._record_observation(f"⚠️ Action格式不合法：{action}")
                continue

            # 6. 校验 JSON
            tool_input, parse_err = self._ensure_json_input(tool_raw_input)
            if parse_err:
                self.scratchpad.append(f"Action: {action}")
                self._record_observation(f"❌ 工具参数解析错误：{parse_err}\n原始参数：{tool_raw_input}")
                continue

            if self.verbose:
                print()
                print(f"🎬 Action: {tool_name}[{tool_input}]")
                print()

            # 7. 执行工具
            try:
                observation = self._execute_tool(tool_name, tool_input)
            except Exception as e:
                observation = f"❌ 工具执行异常: {str(e)}"

            if self.verbose:
                display_obs = observation[:300] + "..." if len(observation) > 300 else observation
                print()
                print(f"👀 Observation: {display_obs}")
                print()

            # 8. 更新历史
            self.scratchpad.append(f"Action: {tool_name}[{json.dumps(tool_input, ensure_ascii=False)}]")
            self._record_observation(observation)

        return "抱歉，我无法在限定步数内完成这个任务。"

    # ---------- Helper Methods ----------

    def _record_observation(self, obs: str):
        self.scratchpad.append(f"Observation: {obs}")

    def _build_prompt(self, question: str, context: str) -> str:
        tools_desc = self.tool_registry.get_tools_description()
        history_str = "\n".join(self.scratchpad) if self.scratchpad else "(empty)"
        return self.DEFAULT_PROMPT_TEMPLATE.format(
            tools=tools_desc,
            context=context,
            question=question,
            history=history_str,
        )



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
