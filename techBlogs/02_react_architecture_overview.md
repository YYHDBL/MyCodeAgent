# 核心 ReAct 架构总览：Agent 的“思考-行动-反馈”主循环

这一章只做一件事：把 MyCodeAgent 的主循环拆开，用代码里的真实结构讲清楚它是怎么“运转”的。所有描述都能在仓库里找到对应实现，核心入口是 `agents/codeAgent.py`。

## 1. 主循环之前：输入先被“整理”
Agent 并不是拿到用户输入就直接喂给模型。MyCodeAgent 在真正进入 ReAct 之前，会做三件事：

1) **预处理输入**  
`core/context_engine/input_preprocessor.py` 会扫描用户输入中的 `@file` 引用，并追加一个 `system-reminder`，强制模型先读这些文件。这一步很关键，它把“应该读文件”变成了明确的规则，而不是模型的习惯。

2) **判断是否需要压缩历史**  
`HistoryManager.should_compress()` 会基于历史 token 的估算值判断是否触发压缩。压缩是上下文工程的核心能力，具体策略会在后面的章节展开。

3) **把用户输入写进历史**  
`HistoryManager.append_user()` 会开启新一轮对话。也就是说，每一次输入都会成为 ReAct 循环的起点。

这一阶段结束后，Agent 才真正进入循环。

## 2. ReAct 循环是怎么跑起来的
`CodeAgent._react_loop()` 是整个系统的心脏。它不是抽象逻辑，而是实打实的步骤驱动循环。流程可以概括为：

1) **构建上下文 messages**  
`ContextBuilder.build_messages()` 把 system prompt、CODE_LAW（如果存在）、历史消息拼成最终的消息列表。L1 prompt 来自 `prompts/agents_prompts/L1_system_prompt.py`，工具提示来自 `prompts/tools_prompts/`。

2) **调用模型**  
`HelloAgentsLLM.invoke_raw()` 发起调用，返回原始结构体。随后会解析出 `content`、`usage` 等信息，并写入 trace。

3) **解析 Thought / Action**  
`_parse_thought_action()` 会在模型输出中寻找最后一个 Thought 和 Action。MyCodeAgent 采用严格格式：

```
Thought: ...
Action: ToolName[JSON]
```

4) **Finish 或 Tool 调用**  
- 如果是 `Finish[...]`，直接写入 history 并结束。
- 如果是工具调用，则解析参数、执行工具、记录 observation，然后进入下一轮。

这就是一个完整的 ReAct 回合。

## 3. “Message List 模式”是核心设计
MyCodeAgent 走的是一种更清晰的“消息列表模式”，而不是把所有状态拼成 scratchpad：

- System prompt 是独立的 `role=system` 消息
- 历史对话由 `HistoryManager.to_messages()` 管理
- 工具结果在 strict 模式下会以 `role=tool` 写入（带 `tool_call_id`）

这个设计在 `core/context_engine/context_builder.py` 有明确说明，优势是：

- 消息结构透明，便于调试
- 工具调用可追踪，便于对齐不同 Provider 的格式
- 历史管理与上下文压缩更可控

## 4. 工具调用的“闭环”
一次工具调用在代码里是一个完整闭环：

1) **解析 Action**：`_parse_tool_call()` 取出工具名与 JSON 参数  
2) **写入 assistant 消息**：带上 `tool_call_id`，明确这次调用的身份  
3) **执行工具**：`ToolRegistry.execute_tool()` 返回统一协议的 JSON 字符串  
4) **写入 tool 消息**：`HistoryManager.append_tool()` 负责截断与落盘  
5) **继续循环**：Observation 成为下一轮的上下文

这里有一个很重要的细节：`ToolRegistry` 不只是调用工具，还会自动注入 Read/Write 的乐观锁元信息（比如 mtime），避免“写入覆盖”这种隐性风险。这个部分的设计会在工具章节展开。

## 5. 为什么这个循环“可调试”
在 `_react_loop()` 里，每一步都会记录 trace 事件：`context_build`、`model_output`、`tool_call`、`tool_result` 等。日志记录来自 `core/context_engine/trace_logger.py`，会生成 JSONL 文件。你能看到模型每次到底输出了什么、到底调用了哪个工具、为什么会卡住。

这也是我写 MyCodeAgent 的一个重要理由：**让“模型在做什么”变成可观察事件，而不是一种主观体验。**

## 6. 小结
这一章的目标是把 ReAct 的主循环讲清楚。只要你看过 `agents/codeAgent.py` 和 `core/context_engine/context_builder.py`，你就能在脑子里画出这条链路：

- 输入预处理
- 历史管理
- 构建上下文
- 调用模型
- 解析 Thought/Action
- 工具闭环或 Finish
- 下一轮

后续章节会把这条链路再拆开：工具系统、上下文工程、日志与复盘，都会在这个主循环里找到落点。

---

## 配图建议（可选）

1) **插图位置：放在“2. ReAct 循环是怎么跑起来的”小节之后**  
**图片内容描述**：
“一个简洁的流程图，从‘用户输入’开始，经过‘预处理 → 构建 messages → 模型输出 → 解析 Thought/Action → 工具调用/Finish → 写入历史’，形成循环箭头。整体风格极简、技术感、无过多装饰。”

2) **插图位置：放在“3. Message List 模式是核心设计”小节之后**  
**图片内容描述**：
“一张并列对比图：左侧是‘scratchpad 拼接’的长文本块，右侧是‘Message List’的结构化列表（system/user/assistant/tool）。用简洁的灰蓝色配色。”

3) **插图位置：放在“4. 工具调用的闭环”小节之后**  
**图片内容描述**：
“一个放射式的闭环示意图：中心是 ToolRegistry，外圈依次是‘解析 Action、写入 assistant、执行工具、写入 tool、进入下一轮’。线条干净，中文标注。”
