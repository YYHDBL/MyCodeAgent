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
- 不为 experimental teams 定义统一协议。
- 不冻结 HTML 展示格式。

## 测试与基线

- 协议常量：`extensions/tracing/protocol.py`
- 协议测试：`tests/extensions/test_trace_protocol.py`
- Phase 0 基线场景：`tests/scenarios/`
