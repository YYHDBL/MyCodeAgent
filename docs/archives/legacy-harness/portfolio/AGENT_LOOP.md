# Agent Loop 与 Completion Gate

## 核心职责

- `RuntimeRunner` 是唯一正式循环，组织 Context、模型、工具和终止。
- `LoopState` 记录 step、恢复计数和最近工具状态。
- Completion Gate 把模型 final text 转成候选，并依据 Todo 与真实验证证据决定通过、阻塞或未验证完成。
- Model Recovery 对空响应、prompt-too-long 等失败做有上限的合法转移。

## 关键不变量

- 模型无工具调用不等于任务完成。
- 模型自述“测试通过”不是 `VerificationEvidence`。
- 验证后发生 Edit 会使旧证据失效。
- 确定性检查先于可选 Verification Agent，确定性失败不能被模型推翻。
- 每条继续和终止路径都有 `TransitionReason` 或 `TerminalReason`。
- 所有自动恢复与 Completion Gate 阻塞都有次数上限。

## 典型失败路径

| 失败 | Runtime 行为 |
|---|---|
| 模型提前宣布完成 | `completion_gate_verdict=fail`，注入阻塞反馈并继续 |
| 连续缺少验证证据 | 达到 retry limit，`terminal=completion_gate_blocked` |
| 空响应 | `model_empty_retry`，一次提示恢复；耗尽后明确失败 |
| Prompt 过长 | 尝试 reactive compact；失败或耗尽后 `model_error` |
| 工具循环不结束 | 达到 `max_steps` 后终止 |

## 对应测试

- `tests/runtime/test_runner.py`
  - Completion Gate pass/fail/unverified
  - 有效与失效验证证据
  - 空响应、模型错误、最大步数
- `tests/runtime/test_completion.py`
  - requirement inference 与 evidence 收集
- `tests/scenarios/test_phase0_baselines.py`
  - `completion_gate_block`、`empty_response_recovery`、`max_steps`
- `tests/scenarios/test_phase9_portfolio_demos.py`

## 对应 Trace

运行：

```bash
.venv/bin/python demo/harness_portfolio.py agent-loop
```

证据：[`docs/traces/agent-loop.json`](../traces/agent-loop.json)

关键事件顺序：

```text
completion_candidate
completion_requirements(requires_verification=true)
completion_gate_verdict(fail)
state_transition(stop_hook_blocking)
...有限重试...
terminal(completion_gate_blocked)
```

## 已实现

- 显式状态转移与终止原因。
- Completion Candidate / Requirements / Evidence / Verdict。
- Todo 与 Bash 验证证据检查。
- 验证后修改导致证据失效。
- 有限模型恢复与独立 Verification profile。

## 明确未实现

- 通用形式化证明。
- Verification Agent 自动修复代码。
- 无限自我反思。
- 跨模型 fallback 后的完整状态重建。
- Streaming continuation 与 Stop Hook 平台。
