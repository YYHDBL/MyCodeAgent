# Deterministic Harness Demos

四个 Demo 使用 mock LLM、临时目录和现有 Harness 组件，不读取 `.env`，不需要 API Key。

统一运行：

```bash
.venv/bin/python demo/harness_portfolio.py all
```

单独运行：

```bash
.venv/bin/python demo/harness_portfolio.py agent-loop
.venv/bin/python demo/harness_portfolio.py tool-harness
.venv/bin/python demo/harness_portfolio.py context-engineering
.venv/bin/python demo/harness_portfolio.py memory-subagent
```

保存输出：

```bash
.venv/bin/python demo/harness_portfolio.py agent-loop \
  --output /tmp/agent-loop.json
```

输出结构：

```json
{
  "demo": "agent-loop",
  "purpose": "mechanism being demonstrated",
  "summary": {},
  "trace": [
    {"event": "state_transition", "step": 0, "payload": {}}
  ]
}
```

| Demo | 观察重点 | 已提交样例 |
|---|---|---|
| `agent-loop` | final candidate 被 Completion Gate 阻塞并有限终止 | [`agent-loop.json`](../docs/traces/agent-loop.json) |
| `tool-harness` | 只读并发批次、原顺序 observation、Write 权限拒绝 | [`tool-harness.json`](../docs/traces/tool-harness.json) |
| `context-engineering` | compact checkpoint 与 `compact_checkpoint` Model View | [`context-engineering.json`](../docs/traces/context-engineering.json) |
| `memory-subagent` | uncertain resume、Session/Long-term 注入、child 隔离 | [`memory-subagent.json`](../docs/traces/memory-subagent.json) |

回归测试：

```bash
.venv/bin/python -m pytest tests/scenarios/test_phase9_portfolio_demos.py -q
```
