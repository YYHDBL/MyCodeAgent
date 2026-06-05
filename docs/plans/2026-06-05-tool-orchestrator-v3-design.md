# ToolOrchestrator v3 设计文档

## 目标

ToolOrchestrator v3 的目标是学习 Claude Code 工具编排里的下一层核心能力：工具结果不是普通日志，而是上下文资源。

v1 已经把工具执行从 `RuntimeRunner` 中抽出。
v2 已经实现安全分区和并发批次。
v3 不继续追求更复杂的并发，而是补上工具执行之后的结果治理：

```text
工具执行完成
-> 结果进入预算评估
-> 大结果落盘
-> 模型上下文只接收稳定的压缩视图
-> RuntimeRunner 写入 history
```

这一版要解决的问题是：

```text
模型一次返回多个 tool_calls 时，工具结果总体不能把下一轮上下文打爆。
```

v3 的核心判断是：

**工具结果是模型上下文的一部分，必须被 harness 管理，而不是无脑塞回 history。**

## Claude Code 参考

Claude Code 的相关设计集中在工具结果处理和工具结果存储逻辑中，核心思想包括：

```text
单个工具结果有预算
一组工具结果也有聚合预算
大结果完整落盘
上下文里只放摘要、路径和预览
一旦某个结果被替换，后续保持替换版本，避免 prompt cache 抖动
空结果也要填充占位文本
```

这和第 4 章里提到的两个原则一致：

```text
工具结果是上下文资源，不是日志。
完整数据保留，模型视图压缩。
```

MyCodeAgent 已经有 `runtime.observation_store`，并且 `HistoryManager.append_tool()` 现在会做单工具截断。但这个位置偏晚，而且只能处理单条 tool result，无法看到一次批次里的总量。

v3 要把预算判断前移到 `ToolOrchestrator`，让工具编排层拿到整组 observations 后统一决策。

## 设计取舍

v3 做：

- 在 `ToolOrchestrator` 中增加工具结果预算管线。
- 保留完整工具输出落盘能力，复用 `runtime.observation_store`。
- 对单个工具结果做预算处理。
- 对一轮 tool_calls 的聚合结果做预算处理。
- 返回给 RuntimeRunner 的 observation 已经是模型可见版本。
- 保持 observations 顺序不变。
- 为预算处理增加 trace 事件。
- 为被替换的结果记录 metadata，避免重复处理和缓存抖动。
- 给空工具结果补占位文本。

v3 不做：

- StreamingToolExecutor。
- 工具到达即执行。
- Bash 只读分类。
- Bash sibling cancellation。
- PreToolUse / PostToolUse hooks。
- 权限模式重构。
- Context Collapse。
- 模型摘要式压缩。

原因很简单：v3 是工具结果层，不是权限层，也不是流式调度层。

## 三个备选方向

### 方案 A：继续做 Bash 只读分类

优点是可以让 `Bash("pwd")`、`Bash("git status")` 这类命令并发执行。

缺点是分类规则很容易变复杂，尤其是 shell 语法、管道、重定向、命令替换、别名、环境变量都会影响安全性。对学习型 MVP 来说，这一步会把注意力从 harness 结构转向 shell 安全细节。

不推荐 v3 做。

### 方案 B：做 StreamingToolExecutor

优点是最接近 Claude Code 的交互体验，模型流式输出 tool_use 时工具就可以开始执行。

缺点是它依赖更复杂的流式协议、可撤销事件、tool_use block 对齐、中断处理和 tombstone。当前项目还没有稳定的流式事件层，直接做会把 v3 变成过大的改造。

不推荐 v3 做。

### 方案 C：做工具结果预算与稳定替换

优点是直接补齐 v2 后最重要的上下文治理能力，而且项目里已有 `observation_store` 可以复用。

这一步能让 ToolOrchestrator 从“执行调度器”升级成“执行结果治理器”。它仍然小，但学习价值很高。

推荐 v3 做。

## 当前代码现状

当前链路是：

```text
ToolOrchestrator.run()
-> 返回 ToolObservation(observation=raw_result)
-> RuntimeRunner 调 history_manager.append_tool()
-> HistoryManager 内部调用 observation_store.truncate_observation()
-> history 保存截断后的 tool message
```

这个设计已经能防止单个工具输出太大，但有三个不足：

```text
ToolOrchestrator 看不到结果预算决策
无法处理一组工具结果的聚合超限
预算处理结果没有显式 metadata，后续难以 trace 和测试
```

v3 不应该删除现有 `observation_store`。它应该把这个能力封装成工具结果预算层，并让 history 层避免重复处理。

## 新增数据结构

在 `tools/orchestrator.py` 中扩展 `ToolObservation`：

```python
@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    tool_call_id: str
    observation: str
    raw_observation: str | None = None
    metadata: dict[str, Any] | None = None
```

含义：

```text
observation       模型可见版本，写入 history
raw_observation   原始工具结果，可选，不进入模型上下文
metadata          预算处理信息，如是否截断、原始大小、路径
```

v3 也可以新增：

```python
@dataclass(frozen=True)
class ToolResultBudget:
    max_tool_bytes: int
    max_message_bytes: int
```

默认值：

```text
MYCODEAGENT_MAX_TOOL_RESULT_BYTES=50000
MYCODEAGENT_MAX_TOOL_MESSAGE_BYTES=200000
```

这些数值和 Claude Code 的思想接近，但不需要完全一致。

## 结果预算管线

`ToolOrchestrator.run()` 在所有 batch 执行完成后，新增一步：

```text
observations = execute_batches(...)
observations = apply_result_budget(observations)
return observations
```

预算管线分三步：

```text
1. normalize_empty_results
2. apply_single_tool_budget
3. apply_aggregate_message_budget
```

### 1. 空结果占位

如果工具返回空字符串、空 JSON、或者没有 `text/data/error` 中任何有效内容，就补一个稳定占位。

示例：

```json
{
  "status": "success",
  "data": {},
  "text": "Bash completed with no output."
}
```

这里不要做复杂模型推理，只做确定性规则。

### 2. 单工具预算

每个 observation 先按单工具预算评估。

如果单条结果超过 `max_tool_bytes`，调用现有：

```python
runtime.observation_store.truncate_observation(
    tool_name,
    raw_result,
    project_root,
)
```

注意：这一步不是简单裁字符串，而是完整落盘后返回压缩后的 JSON。

预算处理后 metadata 应包含：

```text
budgeted: true
replaced: true/false
reason: "single_tool_budget"
raw_bytes
visible_bytes
full_output_path
```

### 3. 聚合预算

单工具预算后，还要计算这一轮所有 observations 的总大小。

如果总大小超过 `max_message_bytes`：

```text
按 visible_bytes 从大到小选择结果
逐个替换成压缩版本
直到总量降到预算内
```

如果某个结果已经被单工具预算替换，不要恢复原文，也不要重复落盘。

这就是 Claude Code 的缓存稳定性思想：

**一旦替换，就保持替换。**

## 和 HistoryManager 的关系

v3 推荐最小改法：

1. `ToolOrchestrator` 返回的 `obs.observation` 已经是预算处理后的模型可见结果。
2. `RuntimeRunner` 调用 `append_tool()` 时，把 `obs.metadata` 一起传进去。
3. `HistoryManager.append_tool()` 如果看到 `metadata["budgeted"] is True`，就跳过再次 `truncate_observation()`。

这样避免双重截断，同时保留旧路径兼容：

```text
旧调用方没有 budgeted metadata -> history 继续兜底截断
新 orchestrator 路径有 budgeted metadata -> history 直接保存模型视图
```

这比直接删除 history 截断更安全。

## Trace 事件

新增轻量 trace：

```text
tool_result_budget_start
tool_result_budget_item
tool_result_budget_end
```

示例 payload：

```json
{
  "tool_count": 4,
  "max_tool_bytes": 50000,
  "max_message_bytes": 200000,
  "raw_total_bytes": 310000,
  "visible_total_bytes": 180000,
  "replaced_count": 2
}
```

单项事件可以记录：

```json
{
  "tool": "Grep",
  "tool_call_id": "call_2",
  "reason": "aggregate_message_budget",
  "raw_bytes": 150000,
  "visible_bytes": 12000,
  "full_output_path": "tool-output/tool_20260605_..."
}
```

这些 trace 的目的不是产品展示，而是学习 harness：工具结果为什么被替换，替换前后大小是多少。

## 测试策略

新增或修改测试：

1. 小结果不被替换，`metadata["replaced"]` 为 false 或不存在。
2. 单个大结果触发落盘和替换。
3. 多个中等结果单个未超限，但总量超限时触发聚合预算。
4. 聚合预算从最大的结果开始替换。
5. 已替换结果不会被恢复成原文。
6. 空工具结果会被填充占位文本。
7. RuntimeRunner 写入 history 时保留预算后的 observation。
8. `HistoryManager.append_tool()` 对 `budgeted` metadata 跳过二次截断。
9. 原有 `tests/test_observation_truncator.py` 继续通过。
10. 全量测试通过。

建议命令：

```text
.venv/bin/pytest tests/tools/test_orchestrator.py -q
.venv/bin/pytest tests/test_observation_truncator.py -q
.venv/bin/pytest tests/test_history_manager.py -q
.venv/bin/pytest tests/runtime/test_runner.py -q
.venv/bin/pytest -q
```

## 对 MyCodeAgent 的收益

v3 完成后，MyCodeAgent 的 ToolOrchestrator 不再只是“调用工具”，而是开始承担工具结果的上下文治理责任。

直接收益：

```text
工具结果不会轻易撑爆下一轮上下文
一轮多个工具结果有总量控制
大结果完整保留，模型只看压缩视图
history 写入更稳定
trace 能解释预算决策
后续 Context Engineering 更容易接上
```

更重要的是学习收益：

```text
模型不是直接读取世界；
harness 负责把世界的反馈整理成模型可消费的视图。
```

这就是工具工程和上下文工程的交界处。

## 不变量

v3 实现必须保持这些不变量：

```text
ToolObservation 顺序等于模型 tool_calls 顺序
RuntimeRunner 仍负责写 history
ToolOrchestrator 不直接修改 history
大结果完整落盘，不只截断丢弃
预算处理是确定性的
旧调用方仍有 history 截断兜底
```

如果实现时需要在“更强功能”和“不变量”之间选择，优先保护不变量。

## 后续版本

建议后续顺序：

```text
v3: tool result budget + stable replacement
v4: permission modes + tool lifecycle hooks
v5: Bash read-only classifier + failure-domain cancellation
v6: StreamingToolExecutor
```

不要急着做 StreamingToolExecutor。

Streaming 是体验层和调度层的综合改造，需要事件协议、可撤销输出、tool_use 对齐和中断控制。当前更有学习价值的是先把非流式 harness 的状态、调度、预算、权限这些骨架打稳。
