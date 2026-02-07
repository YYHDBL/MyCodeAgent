# 七、把黑盒拆开：可观测性 / 日志 / 会话回放

工具与上下文都稳定后，我才真正遇到一个硬伤：**Agent 出错时，我无法还原“它到底做了什么”。**

有一次模型连续失败 3 步，最后干脆自己放弃了。我翻控制台日志，只看到一句：

> tool failed

没有完整参数、没有前后文、也看不到之前几步的决策链。**我只能猜：路径写错了？权限不够？还是工具本身有 bug？**

那一刻我意识到：**没有审计轨迹的 Agent，就像没有行车记录仪的自动驾驶——出事了你只能干瞪眼。**

于是我补上了可观测性这一层：Trace 轨迹 + 会话快照。

---

## 1、TraceLogger：会话级审计轨迹

我没有再用“散乱的运行日志”，而是做了一个会话级轨迹记录器：`TraceLogger`。

它只做一件事：**把一次会话的每一步，按顺序完整记录下来。**

输出两份文件：
- `JSONL`：每一步一个 JSON 对象，方便机器处理
- `HTML`：人类可读的审计视图，打开就能复盘

文件名以 session_id 命名：
```
memory/traces/trace-s-20260103-201533-a3f2.jsonl
memory/traces/trace-s-20260103-201533-a3f2.html
```

所有事件统一结构：
```json
{
  "ts": "2026-01-03T20:15:33.112Z",
  "session_id": "s-20260103-201533-a3f2",
  "step": 4,
  "event": "tool_call",
  "payload": {}
}
```

**一旦有了统一结构，问题就不再是“有没有日志”，而是“你想看哪一步”。**

---

## 2、关键证据链：每一步都打点

Trace 的价值不在“存”，而在“打点是否精准”。

在 `agents/codeAgent.py` 里，我把 ReAct 关键节点全部打点了：

- `run_start / run_end`
- `user_input`
- `context_build`
- `model_output`（含 token usage）
- `tool_call / tool_result`
- `error`
- `finish`
- `history_compression_triggered / completed`
- `message_written`

工具调用与结果绑定靠 `tool_call_id`：

```python
trace_logger.log_event(
    "tool_call",
    {"tool": tool_name, "args": tool_input, "tool_call_id": tool_call_id},
    step=step,
)

trace_logger.log_event(
    "tool_result",
    {"tool": tool_name, "result": result_obj},
    step=step,
)
```

**这条“证据链”保证了：每一次调用，都能精确对上结果。**

此外，每次 `model_output` 都会记录 usage，用来排查“为什么突然变慢 / 为什么 token 暴涨”。

---

## 3、HTML 可视化：把轨迹变成“可读回放”

JSONL 更适合程序分析，但人类复盘需要“看得懂”。

TraceLogger 会同步生成一份 HTML，可直接打开。

打开后大概是这样（简化示意）：

```
┌─ Run #1 ─────────────────────────────┐
│ ▼ Step 1: user_input                  │
│   "帮我找一下 context 相关代码"        │
│                                       │
│ ▼ Step 2: tool_call (Grep)            │
│   args: {"pattern": "context"}         │
│   result: Found 3 files... [展开]     │
│                                       │
│ ▼ Step 3: model_output                │
│   tokens: 1234 / 456 / 1690           │
│   content: "找到 3 个文件..." [展开]  │
└───────────────────────────────────────┘
```

**点开每一步，就能看到完整的 input / output / token / 截断提示，像在逐帧回放。**

如果要看原始模型响应，可通过：
```
TRACE_HTML_INCLUDE_RAW_RESPONSE=true
```

---

## 4、一个真实复盘案例：Trace 怎么救了我

还记得我前面提到那次“连续失败 3 步”吗？

后来我用 Trace 复盘，过程是这样的：

1) Step 2 里模型调用了 `Read`，但参数里传了一个绝对路径：
```json
{"tool": "Read", "args": {"path": "/Users/yyhdbl/Downloads/tmp.py"}}
```

2) 紧接着 `tool_result` 给了 `ACCESS_DENIED`：
```json
{"status": "error", "error": {"code": "ACCESS_DENIED"}}
```

3) 模型没意识到越界，而是继续使用同一条路径，又失败了一次。

**结论很清楚：不是工具 bug，而是模型路径越界 + 我没在 prompt 里强调“必须相对路径”。**

有了这条证据链，我修改了 L1 提示词，问题就再没复现。

这就是 Trace 的价值：**你不是在猜错误，而是在看证据。**

---

## 5.1 会话快照：断点续跑的秘密

Trace 解决“事后复盘”，会话快照解决“断点续跑”。

CLI 支持：
```
/save [path]
/load [path]
```

默认路径：
```
memory/sessions/session-latest.json
```

我经常让它跑 30 分钟长任务，断网或退出后用 `/load` 继续跑，**基本不会丢上下文。**

脚本里还做了自动保存：
- Ctrl+C / exit 时自动落盘
- 异常退出也能恢复

---

## 5.2 快照不止是历史：它存的是“环境”

Session 快照里不仅是对话历史，还有：
- `tool_schema_hash`
- `read_cache`（乐观锁元信息）
- `code_law / skills / mcp prompt` 的 hash

一句话总结：**快照不是“存对话”，而是“存环境”。**

这保证了你恢复会话时，工具版本、上下文状态、读前约束都一致。

---

## 6、安全与脱敏：日志不能变成泄露源

日志是证据，但也可能成为风险点。

`TraceSanitizer` 默认开启（`TRACE_SANITIZE=true`）：
- `sk-***` / `Bearer ***`
- key 级别脱敏：`api_key / token / session_id / tool_call_id`
- 路径脱敏：`/Users/<name>` → `/Users/***`

实现非常直接：
```python
safe_payload = self._sanitizer.sanitize(payload)
```

**排查问题够用，但不会把敏感信息原样写盘。**

---

## 7、可配置性：用开关控制成本

可观测性不能成为性能负担，所以全部有开关：
```
TRACE_ENABLED=true|false
TRACE_DIR=memory/traces
TRACE_SANITIZE=true|false
TRACE_HTML_INCLUDE_RAW_RESPONSE=true|false
```

此外，Summary 生成也有超时控制（`SUMMARY_TIMEOUT`），避免压缩阶段拖死主流程。

---

## 8、这一章的结论

如果说工具和上下文是“让 Agent 能做事”，
那么可观测性就是“让你知道它到底做了什么”。

**从“猜错误”到“看证据”，这一层是工程化的分水岭。**

---

**下一章**：Skills 与子代理——把复杂任务拆成可控的小任务。
