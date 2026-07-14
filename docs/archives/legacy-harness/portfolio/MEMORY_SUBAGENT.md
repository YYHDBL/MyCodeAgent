# Transcript、Session Memory、Long-term Memory 与 Subagent

## 核心职责

- Transcript 以 append-only JSONL 记录消息、状态转移、工具生命周期、checkpoint 和 terminal。
- Resume 从 Transcript 重建 History、LoopState、工具状态和 Session Memory。
- Session Memory 是 Transcript 的有来源派生摘要，保存当前目标、进度、失败、Todo 和验证状态。
- Long-term Memory 保存跨会话稳定事实，按项目/用户文件分离，并以 frozen snapshot 注入。
- Explore/Verification 子 Agent 复用 `RuntimeRunner`，但拥有独立状态、预算、工具面和 Trace。

## 关键不变量

- Transcript 是恢复事实源，不被 Session/Long-term Memory 覆写。
- 已完成工具不会自动重放。
- 已 started 但未完成的副作用工具恢复为 `uncertain`，默认不可重放。
- Session Memory 可从 Transcript 重建，生成失败保留上一有效版本。
- Long-term Memory 只能显式写入；当前用户指令优先。
- 会话内长期记忆写入不改变当前 frozen snapshot。
- 子 Agent 不读取或修改父 History/ContextEngine，父只接收结构化结果。
- readonly child 不注册 Task/Memory，且 Permission Core 再次拒绝写入与 Bash。

## 典型失败路径

| 失败 | Runtime 行为 |
|---|---|
| Transcript 尾部半条 JSON | 读取忽略尾部破损记录，下一次 append 前修复 |
| Edit 在 started 后进程中断 | Resume 标记 uncertain，加入 Session Memory Todo |
| Session summary/refiner 抛异常 | 保留上一有效 Session Memory |
| Long-term Memory 超预算或含危险模式 | 拒绝写入并记录安全原因 |
| 子 Agent 返回非法 JSON contract | Completion Gate 阻塞；耗尽后 child failed |
| 子 Agent 失败 | 父 Trace 记录 `subagent_failed`，父会话不被破坏 |

## 对应测试

- `tests/runtime/test_transcript.py`
- `tests/runtime/test_session_memory.py`
- `tests/runtime/test_long_term_memory_store.py`
- `tests/tools/test_memory_tool.py`
- `tests/runtime/test_subagents.py`
- `tests/scenarios/test_phase7_subagents.py`
- `tests/scenarios/test_phase9_portfolio_demos.py`

## 对应 Trace

运行：

```bash
.venv/bin/python demo/harness_portfolio.py memory-subagent
```

证据：[`docs/traces/memory-subagent.json`](../traces/memory-subagent.json)

Trace 与 summary 展示：

- `Edit(edit-uncertain)` 只有 requested/started，`replay_allowed=false`。
- `model_view_build.dynamic_context_sources` 同时包含 Session 与 Long-term Memory。
- parent Trace 包含 `subagent_requested`、`subagent_started`、`subagent_completed`。
- child 返回有界 `ExploreResult`，父 history 不合并 child 过程。

## 已实现

- Transcript JSONL、尾部修复、Resume reconstruction。
- completed/pending/failed/uncertain 工具恢复语义。
- 可追溯 Session Memory 与读时注入。
- 有界文件型 Long-term Memory、原子写入、安全检查、frozen snapshot。
- Explore 与 Verification 两个 readonly RuntimeProfile。

## 明确未实现

- 外部副作用 exactly-once 或自动回滚。
- 分布式 durable execution。
- 自动后台记忆提取、embedding、向量数据库。
- 子 Agent 递归、共享可写状态、自动 DAG。
- persistent/parallel Teams 作为正式能力。
