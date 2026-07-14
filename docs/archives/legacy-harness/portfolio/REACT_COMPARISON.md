# 普通 ReAct 对照实验

这里的“普通 ReAct”指最小循环：模型返回工具调用就执行，否则把文本当 final。对照不是比较提示词质量，而是比较 Runtime 是否拥有独立、可测试的控制语义。

## 场景一：模型提前宣布完成

用户要求运行测试，脚本模型直接回复“tests passed, task complete”。

| 普通 ReAct | Harness Runtime |
|---|---|
| 无 tool calls，立即返回 final | 生成 `CompletionCandidate` |
| 相信模型文本中的“tests passed” | 只接受真实 Bash 工具结果作为 evidence |
| 任务被错误标记完成 | Gate 阻塞；有限重试后明确 `completion_gate_blocked` |

证据：

- Demo：`.venv/bin/python demo/harness_portfolio.py agent-loop`
- Trace：[`agent-loop.json`](../traces/agent-loop.json)
- 测试：`tests/runtime/test_runner.py`、`tests/runtime/test_completion.py`

## 场景二：工具权限或执行失败

脚本模型在 readonly 子 Agent 中请求两个只读工具和一个 Edit。

| 普通 ReAct | Harness Runtime |
|---|---|
| 常见实现按工具名直接 dispatch，Edit 可能落地 | registry allowlist + Permission Core 双重检查 |
| 并发工具按完成时间返回，消息顺序可能错配 | 只读批次并发，但 observation 保持调用顺序 |
| 工具异常可能抛出循环 | 错误和拒绝统一变成 tool observation |
| 无法解释为什么没执行 | Trace 记录 risk、action、reason、policy source |

证据：

- Demo：`.venv/bin/python demo/harness_portfolio.py tool-harness`
- Trace：[`tool-harness.json`](../traces/tool-harness.json)
- 测试：`tests/tools/test_orchestrator.py`、`tests/tools/test_permissions.py`

## 场景三：长上下文压缩与会话恢复

会话历史超过预算；另一个 run 在 Edit started 后中断。

| 普通 ReAct | Harness Runtime |
|---|---|
| 截断 messages 会永久丢失旧事实 | History 保留完整事实，Model View 只做读时投影 |
| 把 summary 当成新的唯一历史 | checkpoint 有 source boundary，可回到 Transcript |
| 恢复时重新执行最后一条工具调用 | completed 不重放；started mutation 标记 uncertain |
| “记忆”通常混在 prompt/messages | Transcript、Session、Long-term、Model View 生命周期分离 |

证据：

- Demo：`.venv/bin/python demo/harness_portfolio.py context-engineering`
- Demo：`.venv/bin/python demo/harness_portfolio.py memory-subagent`
- Trace：[`context-engineering.json`](../traces/context-engineering.json)、[`memory-subagent.json`](../traces/memory-subagent.json)
- 测试：`tests/runtime/test_context_compaction.py`、`tests/runtime/test_transcript.py`

## 结论

普通 ReAct 的主要问题不是循环代码少，而是把四个决定交给模型或隐式状态：

1. 什么时候算完成。
2. 哪个动作可以执行。
3. 模型本轮应该看到什么。
4. 中断后哪些事实可信、哪些副作用不确定。

MyCodeAgent 的 Harness Runtime 把这些决定变成独立模块、结构化状态、有限预算和 Trace 事件。这是它与“ReAct 加更多文档”的实质区别。
