# Eval Harness

这套 eval harness 用来诊断 Harness 行为，不是模型质量评分器。

它回答的问题是：

- 这次 run 走了多少步
- 调了多少次模型和工具
- 有没有出现权限拒绝、Completion Gate 阻塞、模型恢复、上下文压缩
- 失败大致落在哪个阶段
- Prompt / tool schema 指纹是否发生变化

当前实现是轻量本地能力：

- 输入可以是 trace event list
- 也可以是 `memory/traces/trace-*.jsonl`
- 输出是 JSON summary / metrics dict
- 不依赖 Datadog、OpenTelemetry、远程存储或 dashboard

一个 Agent 生命周期内可能多次调用 `run()`，因此同一 trace 文件可能包含多个 run：

- `summarize_trace()` / `summarize_trace_file()` 默认返回最新 run 的指标
- `summarize_trace_runs()` / `summarize_trace_file_runs()` 返回全部 run 的独立指标
- 不会把不同 run 的 token、模型调用和终止原因混进同一份 summary

## 指标

`runtime/evals.py` 当前汇总：

- `run_id`
- `session_id`
- `terminal_reason`
- `failure_stage`
- `step_count`
- `model_call_count`
- `tool_call_count`
- `tool_error_count`
- `permission_denied_count`
- `completion_gate_block_count`
- `model_recovery_count`
- `context_compaction_count`
- `prompt_fingerprint`
- `tool_schema_fingerprint`
- `total_tokens`
- `projection_modes`
- `subagent_invocation_count`
- `child_tool_count`
- `child_token_usage`
- `child_failure_count`
- `verification_verdict`

其中 `failure_stage` 只用于粗粒度诊断，当前分类：

- `context`
- `model`
- `tool`
- `permission`
- `completion_gate`
- `max_steps`
- `unknown`

## 口径说明

- 这些指标反映的是 harness 行为，不是任务正确率。
- `permission_denied_count` 优先取显式 `permission_decision` 事件，避免和 `tool_result` 里的 `PERMISSION_DENIED` 双计数。
- `model_call_count` 统计成功返回的 `model_output`，以及调用期直接失败但被分类为 `model_invoke` 的情况。
- `completion_gate_block_count` 统计 `stop_hook_blocking` 转移次数，不只看最终是否以 `completion_gate_blocked` 终止。
- `total_tokens` 优先使用 trace 中累计值；若没有 session summary，则按 `model_output.usage.total_tokens` 求和。

## Phase 0 Mock 场景

`tests/scenarios/phase0_baselines.py` 提供批量 deterministic 场景：

- `normal_complete`
- `tool_call`
- `completion_gate_block`
- `model_recovery`
- `permission_deny`
- `context_compaction`

批量 runner 会输出 JSON summary，可用于改造前后对比。

## Phase 9 Portfolio Demo

`demo/harness_portfolio.py` 在 Phase 0 场景之外提供四个面试演示：

- `agent-loop`
- `tool-harness`
- `context-engineering`
- `memory-subagent`

每个 Demo 都输出逐事件 Trace。运行说明见
[`demo/README.md`](../../demo/README.md)。

## 样例

参见 [sample-summary.json](sample-summary.json)。
