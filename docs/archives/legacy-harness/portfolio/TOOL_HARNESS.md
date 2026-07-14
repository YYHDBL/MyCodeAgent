# Tool Harness、权限与工具编排

## 核心职责

- `ToolRegistry` 管理 schema、函数/工具实例和稳定 fingerprint。
- `ToolExecutor` 负责规范化输入、权限决策、执行和统一响应封装。
- `ToolOrchestrator` 负责计划、批次、并发/串行、顺序保持和结果预算。
- Tool lifecycle 同时进入 Trace 与 Transcript。

## 关键不变量

- 模型只能请求工具，不能绕过 `ToolExecutor` 获得执行权。
- 未知工具、参数解析失败和无法判断的权限默认关闭。
- 连续只读工具才可并发；副作用工具保持串行。
- 并发完成顺序不改变 observation 的原始调用顺序。
- 权限拒绝是标准工具 observation，不使 Agent Loop 崩溃。
- 单工具和单轮聚合输出都受预算约束；完整大结果可落盘。
- 子 Agent 同时受 registry allowlist 和 Permission Core 限制。

## 典型失败路径

| 失败 | Runtime 行为 |
|---|---|
| 非法 JSON 参数 | 串行处理并返回 `INVALID_PARAM` |
| 未知工具 | Permission Core `DENY` |
| readonly child 请求 Edit/Bash/Memory/Task | `PERMISSION_DENIED`，工具函数不执行 |
| 工具抛异常 | 标准化为 `EXECUTION_ERROR`，其他安全批次仍可完成 |
| 输出过大 | 返回 `partial` 替换视图，记录 budget Trace |
| Bash 无法分类 | MVP 策略返回 `ASK`，默认 ask policy 可转为 deny |

## 对应测试

- `tests/tools/test_orchestrator.py`
  - 批次、并发、顺序、失败隔离、两级预算
- `tests/tools/test_executor.py`
  - 权限边界、allowlist、Memory Trace
- `tests/tools/test_permissions.py`
  - allow/deny/ask、未知工具失败关闭、readonly child
- `tests/test_protocol_compliance.py`
  - 通用工具响应协议
- `tests/scenarios/test_phase9_portfolio_demos.py`

## 对应 Trace

运行：

```bash
.venv/bin/python demo/harness_portfolio.py tool-harness
```

证据：[`docs/traces/tool-harness.json`](../traces/tool-harness.json)

Trace 展示：

- `Read + Grep` 被规划为并发安全批次。
- 较快完成的 `Grep` 不会越过 `Read` 返回。
- `Edit` 在 readonly profile 中产生 `permission_decision=deny`。

## 已实现

- 工具输入规范化与统一响应协议。
- 输入级 Permission Core。
- 只读并发、安全串行、顺序保持。
- 工具异常标准化、熔断和结果预算。
- 主 Agent/readonly child 不同权限上下文。

## 明确未实现

- OS、容器或网络级沙箱。
- 完整 Shell 语义分析和绕过检测。
- 组织级策略语言与审批服务。
- StreamingToolExecutor。
- 默认并行执行副作用工具或副作用 Agent。
