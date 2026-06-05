# ToolOrchestrator v2 设计文档

## 目标

ToolOrchestrator v2 的目标是学习 Claude Code 工具编排里最核心的一层：工具执行不是普通 for 循环，而是一个“安全分区 + 有序提交”的调度系统。

v1 已经完成边界抽取：

```text
RuntimeRunner -> ToolOrchestrator.run_serial() -> ToolExecutor
```

v2 不做 StreamingToolExecutor，也不做复杂 hooks。v2 只解决一个问题：

```text
模型一次返回多个 tool_calls 时，哪些可以并发，哪些必须串行？
```

但要注意，v2 的目的不是追求极致性能，而是学习 harness 的判断方式：并发是一种被证明安全后的执行策略，不是默认优化。

## Claude Code 参考

Claude Code 中相关设计集中在：

```text
free-code/src/services/tools/toolOrchestration.ts
free-code/src/services/tools/StreamingToolExecutor.ts
free-code/src/services/tools/toolExecution.ts
```

其中 v2 只学习 `toolOrchestration.ts` 的非流式部分：

```text
runTools()
partitionToolCalls()
runToolsConcurrently()
runToolsSerially()
```

核心模式：

```text
按模型输出顺序扫描 tool_calls
连续 concurrency-safe 工具合并成一个并发 batch
遇到不安全工具，单独成 batch
批次按顺序执行
批次内部可并发
并发批次的上下文修改延迟到批次结束后按原始顺序提交
```

对 `MyCodeAgent` 来说，v2 只学习前四点。上下文修改延迟提交可以先用概念保留，因为当前工具执行还没有显式 context modifier。

## 设计取舍

v2 做：

- 给工具增加并发安全判断入口。
- 在 `ToolOrchestrator` 中增加 `partition_tool_calls()`。
- 连续并发安全工具组成并发批次。
- 不安全工具独占批次。
- 批次按模型输出顺序执行。
- 并发批次结果按原始 tool_call 顺序返回给 RuntimeRunner。
- 分类失败、参数解析失败、工具不存在时默认不并发。

v2 不做：

- streaming tool execution。
- 工具到达即执行。
- Bash AI classifier。
- Bash sibling cancellation。
- PreToolUse / PostToolUse hooks。
- context modifier。
- result budget。
- 大结果持久化。
- permission mode 重构。

这个取舍符合学习型 MVP：学会工具调度的骨架，但不把产品复杂度提前引入。

## 并发安全判断

Claude Code 的关键洞察是：并发安全不是只由工具名决定，而是由“工具 + 本次输入”共同决定。

v2 可以先用一个轻量规则：

```text
Read       safe
Grep       safe
Glob       safe
ListFiles  safe
Skill      unsafe
TodoWrite  unsafe
Write      unsafe
Edit       unsafe
MultiEdit  unsafe
Bash       unsafe by default
Task       unsafe by default
MCP tools  unsafe by default
unknown    unsafe
```

这比 Claude Code 更保守，但适合 MVP。

未来 v3/v4 可以再细化：

```text
Bash("ls", "pwd", "git status") -> safe
Bash("rm", "git checkout", "npm install") -> unsafe
MCP read-only resources -> safe
```

第一版不要做 Bash 命令分类。Bash 分类复杂度很高，容易把 v2 拖歪。

## 数据结构

新增或放在 `tools/orchestrator.py`：

```python
@dataclass(frozen=True)
class ToolCallPlan:
    call: dict[str, Any]
    tool_name: str
    tool_call_id: str
    parsed_input: dict[str, Any]
    parse_error: Exception | None
    concurrency_safe: bool


@dataclass(frozen=True)
class ToolBatch:
    concurrency_safe: bool
    calls: list[ToolCallPlan]
```

注意：即使有 `parse_error`，也仍然生成 `ToolCallPlan`。这样 orchestrator 可以统一返回一个 `INVALID_PARAM` observation。

## 分区算法

使用贪心分区，不做全局调度。

伪代码：

```text
batches = []

for plan in plans:
    if plan.concurrency_safe and last_batch is concurrency_safe:
        append to last_batch
    else:
        create new batch
```

这样保留模型输出顺序，又能让连续只读工具并发。

示例：

```text
Read, Grep, Glob, Edit, Read, Bash, Read
```

分区：

```text
[Read, Grep, Glob] concurrent
[Edit] serial
[Read] concurrent
[Bash] serial
[Read] concurrent
```

不要为了最大并发把最后两个 Read 提前。模型输出顺序可能隐含计划语义。

## 执行模型

新增：

```python
ToolOrchestrator.run(tool_calls, step, trace_logger)
```

它替代 v1 的 `run_serial()` 成为主入口。

内部流程：

```text
plan_tool_calls()
partition_tool_calls()
for batch in batches:
    if batch.concurrency_safe:
        execute_batch_concurrently()
    else:
        execute_batch_serially()
return ordered observations
```

为了保持行为稳定：

- 返回给 RuntimeRunner 的 observations 必须仍按原始 tool_calls 顺序排列。
- RuntimeRunner 仍按 observations 顺序写入 history。
- `TOOLS_EXECUTED` transition 不变。
- `tool_call` / `tool_result` / `error` trace 事件仍保留。

## 并发实现

v2 可以使用 Python 标准库：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

为什么用线程：

- 当前工具是同步 `run()`。
- 文件读取、grep、目录遍历多是 I/O。
- 不需要把工具接口整体改成 async。
- 学习成本低。

并发上限先设为小值：

```text
max_concurrency = 4
```

可通过环境变量覆盖：

```text
MYCODEAGENT_MAX_TOOL_CONCURRENCY
```

v2 不需要非常复杂的 executor 生命周期。每个并发 batch 创建一个局部 `ThreadPoolExecutor` 即可。

## 错误处理

v2 保持 v1 行为：

- 参数解析失败 -> `INVALID_PARAM`
- 工具执行异常 -> `EXECUTION_ERROR`
- 工具返回非 JSON -> 由 `ToolExecutor/ToolRegistry` 继续处理
- 未知工具 -> 由 `ToolExecutor/ToolRegistry` 继续处理

新增规则：

```text
并发批次中某个工具失败，不取消其他工具。
```

Claude Code 对 Bash 有 sibling cancellation，但 v2 不做。原因是 Bash 在 v2 默认不并发，不会出现在并发批次里。Read/Grep/Glob 失败时，其他只读工具继续执行更合理。

## Trace 事件

新增轻量 trace：

```text
tool_orchestration_plan
tool_batch_start
tool_batch_end
```

示例：

```json
{
  "batch_count": 3,
  "tool_count": 5,
  "batches": [
    {"concurrency_safe": true, "tools": ["Read", "Grep"]},
    {"concurrency_safe": false, "tools": ["Edit"]},
    {"concurrency_safe": true, "tools": ["Read"]}
  ]
}
```

这能帮助学习 harness：看到模型给的行动意图如何被调度器解释。

## 测试策略

重点测试分区和顺序，不要测试线程实现细节。

建议测试：

1. `partition_tool_calls()` 将连续只读工具合成一个 batch。
2. 写工具独占 batch。
3. Bash 默认 unsafe。
4. 解析失败默认 unsafe，但仍返回 `INVALID_PARAM` observation。
5. 并发 batch 的返回顺序等于输入顺序。
6. RuntimeRunner 通过 `ToolOrchestrator.run()` 执行工具，而不是 `run_serial()`。
7. 现有全量测试通过。

## 对 MyCodeAgent 的收益

v2 完成后，`MyCodeAgent` 会从“工具执行边界”进入“工具调度边界”。

收益不是单纯加速，而是学习到 Claude Code 的关键 harness 思维：

```text
模型只提出行动意图；
harness 决定这些行动如何安全落地。
```

具体收益：

- loop 继续保持干净。
- 工具执行策略有独立测试。
- 后续可以自然加入 result budget。
- 后续可以自然加入 permission mode。
- 后续可以自然加入 Bash 只读判断。
- 后续可以自然加入 StreamingToolExecutor。

v2 是 ToolOrchestrator 后续所有能力的基础。

## 后续版本

建议顺序：

```text
v2: batch partition + safe concurrent execution
v3: tool result budget + large output persistence
v4: permission modes + lifecycle hooks
v5: streaming tool executor
```

这个顺序比直接做 streaming executor 更稳。StreamingToolExecutor 需要流式模型输出、可撤销事件、tool_use 对齐和中断处理。你的 MVP 现在更适合先掌握非流式编排。

