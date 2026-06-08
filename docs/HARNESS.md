# Harness Design

本文档只描述 MyCodeAgent 当前有效的 harness 骨架。历史迁移过程和已完成的实施计划不再作为架构资料保留。

## 1. Agent Loop State

`runtime/loop.py` 不是单纯的模型/工具 while loop，而是显式状态转移的运行时。

```text
user input
  -> context decision
  -> model request
  -> tool calls or final answer
  -> tool orchestration
  -> next transition or terminal
```

`runtime/state.py` 定义：

- `LoopState`：当前 step、模型视图、工具调用、恢复计数等状态
- `TransitionReason`：为什么进入下一阶段
- `TerminalReason`：为什么结束

当前实现保留轻量取舍：不追求完整形式化状态机，但每条关键继续和结束路径必须有可观察原因。新增 fallback、hook、恢复机制时，应先定义状态转移，而不是在循环里增加隐式布尔变量。

### 正式入口与实验边界

Phase 0 之后，默认单 Agent 正式调用链固定为：

```text
main.py
  -> app.cli
  -> runtime.host.CodeAgent
  -> RuntimeRunner.run()
  -> RuntimeRunner._react_loop()
  -> ContextEngine.build_model_view()
  -> LLM
  -> ToolOrchestrator.run()
  -> HistoryManager
  -> terminal / run_end
```

约束：

- `CodeAgent.run()` 只委托给 `RuntimeRunner.run()`。
- `CodeAgent._react_loop()` 仅保留兼容委托，不是第二套正式 loop。
- `RuntimeRunner` 不在运行时临时构造新的 `ToolOrchestrator`；host 必须在装配阶段提供实例。
- `tools/builtin/task.py` 当前仍通过 `experimental.teams.turn_executor` 启动简化子流程，它是实验边界，不属于默认单 Agent runtime。
- `experimental/teams/` 在 Phase 7 前只允许被标记和隔离，不作为主运行时依赖扩张点。

## 2. Tool Orchestrator

模型只负责提出 tool calls，`ToolOrchestrator` 决定如何执行。

```text
tool calls
  -> parse and plan
  -> safe batch partition
  -> serial/concurrent execution
  -> ordered observations
  -> result budgeting
```

核心规则：

- `Read`、`Grep`、`Glob`、`ListFiles` 是显式并发安全工具
- 写入、编辑、Bash、Task、Skill、Todo 等工具串行执行
- 未知工具和参数解析失败默认不安全
- 并发批次完成后仍按模型调用顺序返回结果
- 空结果会补充占位文本
- 单工具和单轮聚合输出都有预算
- 超预算结果保留完整落盘版本，历史只保存稳定的替换视图

这里不实现 StreamingToolExecutor、复杂权限 hooks 或 Bash 命令分类。对学习型 MVP，确定的安全分区比最大并发更重要。

## 3. Context Engineering

上下文系统区分“完整运行历史”和“模型本轮看到的视图”。

```text
HistoryManager full log
  -> ContextBudgetPolicy
  -> CompactStore / CompactCheckpoint
  -> ProjectionBuilder
  -> MessageNormalizer
  -> ModelView
```

职责边界：

- `HistoryManager`：追加、读取和持久化完整消息
- `ContextBudgetPolicy`：估算 active context 并决定是否 compact
- `ContextCompactor`：生成摘要 checkpoint
- `CompactStore`：保存当前 checkpoint
- `ProjectionBuilder`：读时生成 `summary + recent history`
- `MessageNormalizer`：转换为模型 API 消息
- `ContextEngine`：统一编排 usage、compact 和 model view

关键不变量：

- compact 不修改或删除完整历史
- summary 失败时不丢弃任何消息
- 同一份历史不会重复生成 checkpoint
- history clear/session load 会同步清理 context runtime 状态
- `RuntimeRunner` 只通过 `ContextEngine.build_model_view()` 获取模型上下文

## 4. 当前取舍

已经完成：

- 显式 loop transition/terminal
- 安全工具批次与结果预算
- 非破坏性 compact checkpoint
- 模型视图与完整历史分离
- Phase 0 核心 Trace 协议冻结，见 `docs/HARNESS_TRACE_PROTOCOL.md`
- Phase 0 mock 基线场景固定，见 `tests/scenarios/`

暂不实现：

- StreamingToolExecutor
- 多级 Context Collapse
- compact 后文件/技能自动恢复
- fallback 模型状态重建
- Stop Hooks
- token-budget continuation

后续能力只有在现有边界能够自然承载时才加入，不为模仿 Claude Code 而复制全部复杂度。
