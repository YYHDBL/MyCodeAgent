# Harness Completion Gate

本文档记录 Phase 2 之后主单 Agent runtime 的 Completion Gate 边界。

## 生命周期

```text
model final text
  -> CompletionCandidate
  -> CompletionRequirements
  -> VerificationEvidence
  -> deterministic verifier
  -> PASS / FAIL / UNVERIFIED
  -> terminal or continue
```

## 1. CompletionCandidate

`CompletionCandidate` 是模型 final response 的运行时包装，不等同于终止。

当前字段：

- `final_text`
- `step`
- `response_meta`
- `last_tool_name`
- `last_tool_status`

约束：

- 模型没有继续发 tool calls 时，runtime 仍必须先生成 candidate。
- Trace 必须先记录 `completion_candidate`，再允许 terminal。

## 2. CompletionRequirements

`CompletionRequirements` 只表达可靠、显式、可从运行时状态推导的完成条件。

当前只处理：

- 用户显式要求运行测试、lint、typecheck、build
- 用户是否允许“如果可以/尽量”这类 `UNVERIFIED`
- 最新 `TodoWrite` 中是否还有 `pending` / `in_progress`

当前不做：

- 复杂自然语言需求抽取
- 从模型自述反推需求
- 跨轮语义猜测

## 3. VerificationEvidence

`VerificationEvidence` 只来自工具执行，不来自模型文本。

当前最小映射：

- `Bash` 命令包含 `pytest` / `test` / `lint` / `typecheck` / `build` 时，产生对应验证证据

字段：

- `requirement_id`
- `tool_name`
- `command`
- `status`
- `step`
- `valid`
- `invalid_reason`

失效规则：

- 如果验证后发生 `Edit` 成功修改，较早证据会被标记为失效

## 4. Verdict 语义

- `PASS`：所有显式 requirement 都被满足，且不存在未完成 Todo
- `FAIL`：存在阻塞 requirement，例如缺少验证证据、证据失效、Todo 未完成
- `UNVERIFIED`：存在显式验证 requirement，但用户明确允许“如果可以”且当前没有足够证据

约束：

- 模型文本中的“测试通过”“已经验证”不能作为 evidence
- Gate 阻塞必须进入下一轮，而不是直接静默失败
- Gate 阻塞重试有上限，超过上限后以明确 terminal reason 结束

## 5. Trace

Phase 2 新增辅助 Trace 事件：

- `completion_candidate`
- `completion_requirements`
- `verification_evidence`
- `completion_gate_verdict`

以及相关终止原因：

- `completed`
- `completed_unverified`
- `completion_gate_blocked`

这些事件是核心 Trace 的补充，不替代 `state_transition` 与 `terminal`。
