"""Context builder for ReAct prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from tools.registry import ToolRegistry


DEFAULT_REACT_TEMPLATE = """你是一个具备推理和行动能力的AI助手。你需要通过多轮“思考->调用工具->观察->再思考”完成任务。

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


@dataclass
class ContextBuilder:
    """Builds the full prompt for ReActEngine."""

    tool_registry: ToolRegistry
    template: str = DEFAULT_REACT_TEMPLATE

    def build(self, question: str, context_prompt: str, scratchpad: List[str]) -> str:
        tools_desc = self.tool_registry.get_tools_description()
        history_str = "\n".join(scratchpad) if scratchpad else "(empty)"
        return self.template.format(
            tools=tools_desc,
            context=context_prompt,
            question=question,
            history=history_str,
        )

