# Context Engineering、Compact 与 Model View

## 核心职责

- Prompt Assembly 分离稳定 Constitution、Tool Contracts、Project Rules 与动态 Runtime Signals。
- `HistoryManager` 保存完整消息事实。
- `ContextBudgetPolicy` 判断是否需要 compact。
- `ContextCompactor` 创建摘要 checkpoint。
- `ProjectionBuilder` 读时生成 `summary + recent history`。
- `ContextEngine` 注入有预算的 Session/Long-term Memory 并产出本轮 `ModelView`。

## 关键不变量

- Compact 不删除、不改写完整 History。
- Summary 失败不丢失原消息。
- 同一 source message count 不重复 compact。
- 模型只通过 `ContextEngine.build_model_view()` 获取消息。
- Session/Long-term Memory 是动态层，不改变稳定 prompt fingerprint。
- Model View 是本轮投影，不是新的事实源。
- Session clear/load 会同步重置 context runtime state。

## 典型失败路径

| 失败 | Runtime 行为 |
|---|---|
| 预算超过阈值 | 创建 `CompactCheckpoint`，投影模式变为 `compact_checkpoint` |
| 摘要生成失败 | 保留 full history，不激活破损 checkpoint |
| API 返回 prompt too long | 触发一次 reactive compact 后重试 |
| checkpoint 已覆盖当前 history | 跳过重复 compact |
| 动态记忆过大 | Session 与 Long-term Memory 使用独立字符预算 |

## 对应测试

- `tests/runtime/test_context_budget.py`
- `tests/runtime/test_context_compaction.py`
- `tests/runtime/test_context_engine.py`
- `tests/runtime/test_prompt.py`
- `tests/runtime/test_prompt_assembly_trace.py`
- `tests/runtime/test_runner.py::test_resume_restored_history_is_still_projected_by_context_engine`
- `tests/scenarios/test_phase9_portfolio_demos.py`

## 对应 Trace

运行：

```bash
.venv/bin/python demo/harness_portfolio.py context-engineering
```

证据：[`docs/traces/context-engineering.json`](../traces/context-engineering.json)

关键字段：

```text
context_compaction_decision.should_compact=true
context_compaction_completed.checkpoint_id=...
model_view_build.source_message_count=6
model_view_build.projection_mode=compact_checkpoint
```

Demo 同时断言 `history_preserved=true`。

## 已实现

- Prompt 四层生命周期与 fingerprint。
- 预算估算、主动/响应式 compact。
- 非破坏性 checkpoint 与读时投影。
- Tool call/result 正规化。
- Session/Long-term Memory 动态注入与独立预算。

## 明确未实现

- 多级 Context Collapse。
- 自动文件、Skill 或 MCP 状态重建。
- 真实 provider prompt cache 命中遥测。
- 跨模型 token 估算精确兼容矩阵。
- 向量检索驱动的上下文选择。
