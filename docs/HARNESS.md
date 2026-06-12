# Harness Architecture

本文档描述 MyCodeAgent 当前有效架构。面试入口见 [README](../README.md)，四个重点模块的问答材料见 [portfolio](portfolio/)。

## 1. 正式调用链

```text
main.py
  -> app.cli
  -> runtime.host.CodeAgent
  -> RuntimeRunner.run()
  -> ContextEngine.build_model_view()
  -> LLM
  -> ToolOrchestrator.run()
  -> HistoryManager + TranscriptRecorder
  -> Completion Gate
  -> terminal / next transition
```

不变量：

- `runtime/loop.py` 是正式单 Agent 唯一循环。
- `CodeAgent` 负责依赖装配，不维护第二套循环。
- Explore / Verification 子 Agent 通过隔离 host 复用 `RuntimeRunner`。
- 正式 `Task` 路径不依赖 `experimental/teams/`。

## 2. Runtime Control

`LoopState`、`TransitionReason` 和 `TerminalReason` 让继续、恢复和结束路径可观察。模型 final text 先变成 `CompletionCandidate`，再由 Completion Gate 检查 Todo 和真实工具验证证据。

模型/API 错误按阶段分类。空响应和 prompt-too-long 等可恢复路径有独立次数上限；无法恢复时进入明确 terminal，不无限反思。

详见：

- [Agent Loop 与 Completion Gate](portfolio/AGENT_LOOP.md)
- [Completion Gate 协议](HARNESS_COMPLETION_GATE.md)

## 3. Tool Harness

```text
model tool calls
  -> parse / plan
  -> Permission Core
  -> safe batch partition
  -> serial or concurrent execution
  -> ordered observations
  -> single-tool / aggregate result budget
```

当前规则：

- `Read`、`Grep`、`Glob`、`ListFiles` 可组成连续并发批次。
- 写入、Bash、Task、Skill、Todo 等保持串行。
- 并发完成顺序不影响 observation 的模型调用顺序。
- 未知工具、参数解析失败和无法判断的权限默认关闭。
- Permission Core 是策略路由，不是 OS 级安全沙箱。
- 超预算完整输出落盘，Model View 只接收稳定替换结果。

详见 [Tool Harness、权限与编排](portfolio/TOOL_HARNESS.md)。

## 4. Context Engineering

```text
Prompt Assembly stable layers
HistoryManager full history
Session / Long-term Memory dynamic layers
  -> ContextBudgetPolicy
  -> CompactCheckpoint
  -> ProjectionBuilder
  -> MessageNormalizer
  -> ModelView
```

关键边界：

- Compact 创建 checkpoint，不修改或删除完整 history。
- Summary 失败时保留原消息和上一份有效状态。
- `ProjectionBuilder` 在读时生成 `summary + recent history`。
- Session Memory 和 Long-term Memory 作为有预算的动态 system message 注入，不改变稳定 prompt fingerprint。
- `RuntimeRunner` 只能通过 `ContextEngine.build_model_view()` 获取模型上下文。

详见：

- [Context Engineering、Compact 与 Model View](portfolio/CONTEXT_ENGINEERING.md)
- [Prompt Assembly](HARNESS_PROMPT_ASSEMBLY.md)

## 5. Durable State

四种状态不能合并成一份 messages：

| 状态 | 职责 |
|---|---|
| History | 当前进程内的完整消息历史 |
| Transcript | append-only 会话事实与恢复来源 |
| Session Memory | 从 Transcript 派生的目标、进度、风险和验证状态 |
| Long-term Memory | 跨会话稳定事实，使用 frozen snapshot 注入 |

Resume 采用 at-least-once 事实语义。已完成工具不会自动重放；已 started 但未完成的副作用工具标记为 `uncertain`，由后续检查或用户确认解决。

详见：

- [Transcript、Memory 与 Subagent](portfolio/MEMORY_SUBAGENT.md)
- [Long-term Memory](HARNESS_LONG_TERM_MEMORY.md)

## 6. Restricted Subagents

正式子 Agent 只有两个不可变 profile：

- Explore：只读搜索，返回 `ExploreResult`。
- Verification：独立检查完成候选，返回 `VerificationResult`。

两者使用独立 History、ContextEngine、Transcript、Session Memory 和 Trace；registry allowlist 与 `readonly_subagent` Permission Core 双重限制写入、Bash、Memory 和递归 Task。父 Agent 只接收有界结构化结果。

## 7. Trace 与 Eval

核心事件协议见 [HARNESS_TRACE_PROTOCOL.md](HARNESS_TRACE_PROTOCOL.md)。`runtime/evals.py` 汇总 step、模型/工具调用、权限拒绝、恢复、compact、Completion Gate 和子 Agent 指标。

确定性证据：

- [Agent Loop Trace](traces/agent-loop.json)
- [Tool Harness Trace](traces/tool-harness.json)
- [Context Trace](traces/context-engineering.json)
- [Memory / Subagent Trace](traces/memory-subagent.json)

## 8. 正式与实验边界

正式 Harness Core：

```text
app/ core/ runtime/ tools/ extensions/
```

实验区：

```text
experimental/teams/
```

Teams 中的 persistent workers、tmux orchestration、mailbox、task board 和 parallel coordination 不进入正式架构承诺。当前项目进入维护状态，后续只接受缺陷修复、评估改进和材料完善。
