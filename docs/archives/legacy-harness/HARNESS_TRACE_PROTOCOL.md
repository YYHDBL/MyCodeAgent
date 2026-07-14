# Harness Trace Protocol

本文档冻结 Phase 0 之后用于 harness 基线评估的核心 Trace 事件协议。后续阶段可以新增辅助事件，但不能破坏这里定义的核心事件名、基本语义和必填字段。

## 核心原则

- 核心事件只覆盖主单 Agent 运行时：`RuntimeRunner`、`ContextEngine`、`ToolOrchestrator`。
- 非核心辅助事件可以存在，例如 `message_written`、`context_compaction_decision`、`error`、`finish`，但不能替代核心事件。
- 一次运行必须能仅依赖核心事件复盘：
  - 哪次 run 开始。
  - 当前 step 构建了什么模型视图。
  - 模型输出了什么。
  - 为什么进入下一状态。
  - 调用了什么工具、拿到了什么结果。
  - 为什么终止。
  - run 如何结束。

## 核心事件

| Event | Owner | 必填 payload 字段 | 语义 |
| --- | --- | --- | --- |
| `run_start` | `RuntimeRunner.run()` | `run_id`, `input`, `processed` | 一次正式运行开始，记录原始输入和预处理结果 |
| `context_build` | `RuntimeRunner._react_loop()` | `message_count`, `history_count`, `source_message_count`, `projection_mode` | 本 step 用于请求模型的上下文统计 |
| `model_output` | `RuntimeRunner._react_loop()` | `raw`, `usage`, `meta`, `raw_response`, `tool_calls` | 一次模型响应的统一记录，不区分 final/tool-call |
| `state_transition` | `RuntimeRunner._transition()` | `step`, `turn_count`, `reason`, `message_count`, `details` | 主 loop 的显式继续原因 |
| `tool_call` | `ToolOrchestrator._execute_plan()` | `tool`, `args`, `tool_call_id` | 单个工具调用已经被 harness 接受并准备执行 |
| `tool_result` | `ToolOrchestrator._log_tool_result()` | `tool`, `result` | 单个工具结果已经被 harness 标准化 |
| `terminal` | `RuntimeRunner._terminal()` | `reason`, `details` | 主运行时的正式终止原因 |
| `run_end` | `RuntimeRunner.run()` | `run_id`, `final` | 本次 run 收尾完成，记录最终返回文本 |

## 非目标

- 不把 Trace 扩展成完整观测平台。
- 不冻结 HTML 展示格式。

## 测试与基线

- 协议常量：`extensions/tracing/protocol.py`
- 协议测试：`tests/extensions/test_trace_protocol.py`
- Phase 0 基线场景：`tests/scenarios/`

## Phase 1-2 辅助事件

这些事件不是 Phase 0 核心协议的一部分，但当前 harness 依赖它们解释提示词装配与完成判定：

| Event | 关键字段 | 语义 |
| --- | --- | --- |
| `prompt_assembly` | `constitution_fingerprint`, `tool_contracts_fingerprint`, `project_rules_fingerprint`, `runtime_signals_fingerprint`, `system_fingerprint`, `changed_layers` | 当前 step 的 Prompt Assembly 指纹和变化来源 |
| `tool_schema` | `fingerprint`, `tool_count`, `changed` | 当前工具 schema 指纹与变化状态 |
| `completion_candidate` | `final_text`, `final_length`, `step`, `response_meta`, `last_tool_name`, `last_tool_status` | 模型 final response 的候选完成声明 |
| `completion_requirements` | `requires_verification`, `verification_kinds`, `allow_unverified`, `has_incomplete_todos`, `incomplete_todos`, `explicit_user_constraints` | 当前 runtime 判断出的最小完成要求 |
| `verification_evidence` | `requirement_id`, `tool_name`, `command`, `status`, `step`, `valid`, `invalid_reason` | 实际工具执行产生的验证证据，以及是否仍有效 |
| `completion_gate_verdict` | `verdict`, `reasons`, `blocking_feedback`, `passed_evidence` | Completion Gate 对 candidate 的确定性判定 |

辅助终止原因补充：

- `completed_unverified`
- `completion_gate_blocked`
- `token_budget`

## Phase 7 父子运行事件

父 Agent Trace 只记录关联和汇总信息，不合并 child Trace 或 child model context。
child 运行使用独立 session/run、Transcript 和 Session Memory。

| Event | 关键字段 | 语义 |
| --- | --- | --- |
| `subagent_requested` | parent/child session/run id, `profile`, `model`, step/context/token budget | 父运行接受受限子任务请求 |
| `subagent_started` | parent/child session/run id, `profile` | 隔离 child runtime 已开始 |
| `subagent_completed` | IDs, `profile`, `terminal_reason`, `tool_usage`, `token_usage`, `verdict`, `elapsed_ms` | child 返回合法结构化结果 |
| `subagent_failed` | IDs, `profile`, `terminal_reason`, `elapsed_ms` | child 异常、超预算、超步数或结果契约无效 |

Eval summary 增加：

- `subagent_invocation_count`
- `child_tool_count`
- `child_token_usage`
- `child_failure_count`
- `verification_verdict`
