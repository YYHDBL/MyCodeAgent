# Phase 0 Baseline Scenarios

这些场景用于冻结 Phase 0 的单 Agent harness 基线。它们不验证后续 Phase 的 Completion Gate、Recovery 分类、Permission Core 或 Subagent Runtime。

## 自动化 mock 场景

测试入口：`tests/scenarios/test_phase0_baselines.py`

覆盖：

- `read_only_search`: 只读工具调用后完成
- `file_edit`: 副作用工具调用后完成
- `tool_failure`: 工具执行报错但仍形成标准化 observation
- `context_compaction`: 触发 ContextEngine compact 路径
- `empty_response_recovery`: 空响应追加提示后恢复
- `max_steps`: 工具循环导致最大步数终止
- `empty_response_failed`: 连续空响应后终止

基线指标：

- `step_count`
- `tool_call_count`
- `projection_modes`
- `terminal_reason`

## 真实模型场景

真实模型场景不进入默认 `pytest`，避免把外部 API 波动混入单元测试。

建议人工回归 5 个场景，并保存 Trace 文件用于后续阶段对照：

1. 只读搜索并总结结果
2. 修改一个临时文件并说明改动
3. 故意调用失败工具路径
4. 输入超长上下文触发 compact
5. 构造空响应或弱提示词样本观察恢复行为

执行要求：

- 每次运行保存 `memory/traces/trace-*.jsonl`
- 记录步数、工具数、`projection_mode`、`terminal.reason`
- 与 mock 场景分开存档，不混入默认测试结果
