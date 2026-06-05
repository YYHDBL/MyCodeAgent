# MyCodeAgent Agent Loop State v1 设计文档

## 目标

这份文档定义 `MyCodeAgent` 第一版 Agent Loop State 设计。

项目定位是学习型 MVP，不追求企业级产品复杂度。这里要学习的是 Claude Code 最核心的 harness 思想：Agent Loop 不是简单 while loop，而是一个能够记录继续原因、恢复状态、防止死循环、维持消息一致性的运行时骨架。

第一版目标不是重写整个 loop，而是在现有 `runtime/loop.py` 上建立一个轻量状态层，让后续工具编排、上下文工程、Stop Hook、fallback、长任务恢复都有可挂载的位置。

## 参考来源

Claude Code 源码里主循环的关键设计点：

- `free-code/src/query.ts` 中的 `State` 是跨轮状态容器。
- 每个 `continue` 点都会构造新的 `State`，而不是零散修改多个变量。
- `transition.reason` 记录为什么进入下一轮。
- `Terminal.reason` 记录为什么退出。
- 状态字段主要服务于恢复路径，而不是为了形式化建模。

Claude Code 的状态字段大致包括：

```text
messages
toolUseContext
autoCompactTracking
maxOutputTokensRecoveryCount
hasAttemptedReactiveCompact
maxOutputTokensOverride
pendingToolUseSummary
stopHookActive
turnCount
transition
```

这些字段有一个共同点：如果漏掉，就可能导致恢复失败、重复压缩、重复 retry、工具结果错位、Stop Hook 死循环或上下文不一致。

## 设计取舍

`MyCodeAgent` 不需要先复刻 Claude Code 的完整产品能力。

第一版暂不做：

- 流式 tool_use 到达即执行
- tombstone 可撤销流式事件
- SDK 级 withhold-release 协议
- 完整 Context Collapse store
- 多模型 fallback 状态重建
- token budget continuation
- 后台 memory prefetch / skill prefetch
- 复杂 analytics 和远程会话状态

第一版必须保留：

- 显式 LoopState
- 显式 TransitionReason
- 显式 TerminalReason
- 每个继续点构造 next state
- 每种恢复路径有 attempt guard
- trace 中能看到状态转移

这是学习 harness 工程的最小骨架。

## 当前代码问题

当前 `runtime/loop.py` 的 `_react_loop()` 已经有很多真实状态，但它们还是隐式代码路径：

```text
用户输入
-> 上下文压缩判断
-> 构造模型 messages
-> 调用模型
-> 空响应重试
-> 解析 tool_calls
-> 执行工具
-> 写入 tool result
-> 继续下一轮
-> 或输出 final
```

现在的问题不是功能缺失，而是这些路径没有统一回答：

```text
这一轮为什么继续？
这次继续是正常继续，还是恢复继续？
是否已经尝试过某种恢复？
如果停止，是正常完成、失败、还是达到步数限制？
```

这会影响后续扩展。比如增加 Stop Hook、fallback、reactive compact、token budget continuation 时，如果没有状态记录，很容易在 loop 里继续堆 `if/continue/break`。

## v1 核心模型

新增一个轻量状态模块：

```text
runtime/state.py
```

建议包含三个数据结构。

### LoopState

```python
@dataclass
class LoopState:
    messages: list[dict[str, Any]]
    step: int
    turn_count: int
    tool_choice: str
    transition: Transition | None = None
    compact_attempted: bool = False
    empty_response_retry_used: bool = False
    max_output_recovery_count: int = 0
    stop_hook_active: bool = False
    last_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    last_response_meta: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
```

字段解释：

- `messages`：当前轮真正要继续传递的模型视图，不等于完整历史。
- `step`：当前主循环步数。
- `turn_count`：模型调用轮次，后续可以和 max turns 对齐。
- `tool_choice`：当前工具选择策略。
- `transition`：上一轮为什么进入这一轮。
- `compact_attempted`：防止同一轮恢复路径反复压缩。
- `empty_response_retry_used`：防止空响应无限重试。
- `max_output_recovery_count`：为后续 max output tokens 恢复预留。
- `stop_hook_active`：为后续 Stop Hook 阻塞重试预留。
- `last_tool_calls`：上一轮模型返回的工具调用。
- `last_response_meta`：上一轮模型响应元信息。
- `last_error`：最近一次错误摘要。

### Transition

```python
@dataclass
class Transition:
    reason: TransitionReason
    details: dict[str, Any] = field(default_factory=dict)
```

### TransitionReason

第一版先保留少量原因：

```text
user_input
context_compacted
model_empty_retry
model_empty_failed
model_returned_tool_calls
tools_executed
model_returned_final
stop_hook_blocking
max_steps_exceeded
unrecoverable_error
```

后续再加：

```text
reactive_compact_retry
max_output_tokens_recovery
fallback_retry
token_budget_continuation
context_collapse_retry
```

## TerminalReason

Agent Loop 的退出也要显式记录：

```text
completed
empty_response_failed
max_steps
tool_error_unrecoverable
user_abort
model_error
```

第一版可以先不改变 `run()` 的返回值，只在 trace 中记录 terminal reason。后续如果要提供 SDK 或更强测试，再把返回值升级成：

```python
@dataclass
class LoopTerminal:
    reason: TerminalReason
    final_text: str = ""
    error: str | None = None
```

## 状态转移原则

第一版只遵守三条规则。

### 1. 每个 continue 都必须有 reason

当前 loop 里的 `continue` 不能只是控制流跳转。它应该代表一次状态转移。

示例：

```python
state = state.next(
    messages=next_messages,
    transition=Transition(
        reason=TransitionReason.TOOLS_EXECUTED,
        details={"tool_count": len(tool_calls)},
    ),
)
continue
```

### 2. 恢复路径必须有 guard

凡是恢复动作，都必须记录是否尝试过或尝试次数。

例如：

```text
empty_response_retry_used
compact_attempted
max_output_recovery_count
stop_hook_active
```

这不是为了复杂，而是为了防止死亡螺旋。

### 3. messages 是当前模型视图，不是完整历史

完整历史仍由 `HistoryManager` 保存。`LoopState.messages` 只表示“当前准备继续发给模型的视图”。

这个边界为后续 Context Collapse 做准备：

```text
HistoryManager: 完整历史
LoopState.messages: 当前模型视图
Context projection: 从完整历史投影到模型视图
```

## 当前代码映射

### 上下文压缩

当前位置：

```text
runtime/loop.py:119
```

当前行为：

```text
should_compress -> compact -> 继续构造 messages
```

v1 状态含义：

```text
transition.reason = context_compacted
compact_attempted = true
```

### 空响应重试

当前位置：

```text
runtime/loop.py:192
```

当前行为：

```text
LLM 空响应 -> 注入 hint -> 重试一次
```

v1 状态含义：

```text
transition.reason = model_empty_retry
empty_response_retry_used = true
```

如果仍为空：

```text
terminal.reason = empty_response_failed
```

### 工具调用

当前位置：

```text
runtime/loop.py:270
```

当前行为：

```text
append assistant tool_call
for call in tool_calls: execute
append tool result
continue
```

v1 状态含义：

```text
transition.reason = tools_executed
last_tool_calls = tool_calls
```

第一版仍然可以串行执行工具，不必马上做 ToolOrchestrator。但 loop 要先知道“这次继续是工具执行后的继续”。

### 最终回答

当前位置：

```text
runtime/loop.py:387
```

当前行为：

```text
append assistant final
return final_text
```

v1 状态含义：

```text
terminal.reason = completed
transition.reason = model_returned_final
```

### 步数耗尽

当前位置：

```text
runtime/loop.py:403
```

当前行为：

```text
return "抱歉，我无法在限定步数内完成这个任务。"
```

v1 状态含义：

```text
terminal.reason = max_steps
transition.reason = max_steps_exceeded
```

## Trace 事件

新增统一 trace 事件：

```text
state_transition
```

事件内容：

```json
{
  "step": 2,
  "turn_count": 2,
  "from": "tool_calls",
  "to": "model_call",
  "reason": "tools_executed",
  "details": {
    "tool_count": 3
  }
}
```

第一版不要求完整 `from/to phase`。如果想保持更轻，可以只记录：

```json
{
  "step": 2,
  "turn_count": 2,
  "reason": "tools_executed",
  "details": {
    "tool_count": 3
  }
}
```

重点是让 trace 能回答“为什么继续”。

## 实施顺序

### Step 1: 新增状态模块

新增：

```text
runtime/state.py
```

只定义数据结构，不改变行为。

### Step 2: 在 RuntimeRunner 中初始化 LoopState

在 `_react_loop()` 开头创建 state。

第一版可以继续使用现有 `for step in range(...)`，不必改成 `while True`。

### Step 3: 增加 `_transition()`

在 `RuntimeRunner` 内增加一个小方法：

```python
def _transition(self, state, reason, trace_logger, **details) -> LoopState:
    ...
```

职责：

- 更新 `state.transition`
- 写 trace
- 返回新 state

### Step 4: 给关键路径打 transition

优先覆盖：

- compact completed
- empty response retry
- tool calls returned
- tools executed
- final answer
- max steps

### Step 5: 补最小测试

测试重点不是复杂行为，而是 transition reason。

建议测试：

- 模型返回 final 时，terminal reason 是 `completed`
- 模型返回 tool_calls 后，出现 `tools_executed`
- 空响应只 retry 一次
- 超过 max_steps 时，terminal reason 是 `max_steps`
- compact 触发时，出现 `context_compacted`

## 后续演进

Agent Loop State v1 做完后，后续能力会自然挂上来。

### v2: ToolOrchestrator

把当前工具执行的 for 循环抽成工具编排层。

学习重点：

```text
schema validate
permission check
concurrency safe classify
batch partition
execute
result budget
post hook
```

第一版工具编排不需要流式，只做批次分区：

```text
连续只读工具并发
写工具 / Bash 风险命令独占
分类失败默认不并发
批次完成后按原始顺序提交结果
```

### v3: Context Projection

把完整历史和模型视图分开。

学习重点：

```text
HistoryManager 保留完整历史
project_messages_for_model() 生成模型视图
tool result budget 先作用在模型视图上
compact/collapse 不直接破坏完整历史
```

这一步是学习 Context Collapse 的前置条件。

### v4: Stop Hook / Completion Gate

把“模型说完成”改成“候选完成”。

学习重点：

```text
final answer
-> completion gate
-> blocking errors?
-> 注入错误继续
-> 或真正结束
```

第一版 Stop Hook 可以很简单：

- 是否跑过测试
- 是否还有失败工具结果
- 是否有未完成 todo
- 是否违反只读/编辑模式

### v5: Recovery Paths

再学习更高级的恢复路径：

```text
max_output_tokens_recovery
reactive_compact_retry
fallback_retry
token_budget_continuation
```

这些都依赖 v1 的 state 和 transition reason。没有 v1，这些功能会变成散落的 if。

## 学完 State 后应该学什么

学完 Agent Loop State 后，下一块最应该学的是 ToolOrchestrator，而不是上下文工程。

原因：

```text
State 解决“为什么继续”
ToolOrchestrator 解决“行动如何安全落地”
Context Engineering 解决“给模型看什么”
Stop Hook 解决“什么时候允许结束”
```

Agent Loop 的下一层核心就是工具。模型通过 tool_use 提出行动意图，但 harness 必须决定：

- 工具是否存在
- 参数是否合法
- 权限是否允许
- 是否可以并发
- 出错后影响哪些任务
- 结果是否太大
- 结果如何进入下一轮上下文

这正是 Claude Code 第四章最值得学的地方。

建议学习顺序：

```text
1. Agent Loop State
2. Tool Execution Lifecycle
3. Tool Orchestration / Batch Partition
4. Tool Result Budget
5. Context Projection
6. Stop Hook / Completion Gate
7. Recovery Paths
```

这个顺序适合 `MyCodeAgent` 的学习型 MVP：先把 harness 骨架搭起来，再逐步学习 Claude Code 如何给 agent 提供工具、安全、上下文和恢复能力。

