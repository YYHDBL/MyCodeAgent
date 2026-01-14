# 日志与可观测性：trace、断点调试与异常回放

一个 Agent 是否“工程化”，很大程度上取决于你能不能复盘它的行为。模型输出是临时的，工具调用是瞬时的，如果没有完整轨迹，调试只能靠猜。

MyCodeAgent 把“可观测性”当成核心系统能力来做，而不是只靠几行 `print()`。这一章基于以下实现与文档：

- `core/context_engine/trace_logger.py`
- `docs/TraceLogging设计文档.md`
- `agents/codeAgent.py`（埋点位置）

## 1. Trace 是“完整轨迹”，不是普通日志
普通日志关注“运行过程”，而 trace 关注“可回放”。

MyCodeAgent 的 trace 记录包含：

- 用户输入
- 模型原始输出（含 Thought）
- 解析后的 Action
- 工具调用与工具结果
- 错误与 Finish
- token 使用量

这些内容在 `docs/TraceLogging设计文档.md` 中有详细结构规范。它的目标很明确：**让一次会话可以被完整复盘。**

## 2. Trace 输出格式：JSONL + Markdown
`TraceLogger` 会为每个会话写两份文件：

- **JSONL**：每一步一个 JSON 对象，适合程序处理
- **Markdown**：人类可读的审计视图

文件默认在 `memory/traces/`，命名形如：

```
trace-s-YYYYMMDD-HHMMSS-xxxx.jsonl
trace-s-YYYYMMDD-HHMMSS-xxxx.md
```

这套机制完全由 `core/context_engine/trace_logger.py` 实现。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一个文件结构示意图：memory/traces 下同时出现 jsonl 和 md 两个文件，旁边标注用途。”

## 3. Trace 事件覆盖了 ReAct 的关键节点
在 `agents/codeAgent.py` 中，你可以看到 trace 的埋点基本覆盖了整个循环：

- `run_start` / `run_end`
- `user_input`
- `context_build`
- `model_output`
- `parsed_action`
- `tool_call` / `tool_result`
- `error` / `finish`

这意味着：

- 你能看到模型到底输出了什么
- 你能看到它解析成了什么 Action
- 你能看到工具实际返回了什么结果

它不是“事后推断”，而是“真实现场”。

## 4. Trace 是断点调试的基础
很多人想要“断点”，但在 Agent 这种异步、长链路系统里，断点其实就是“可回放的轨迹”。

当模型卡住或行为异常时，你可以用 trace 做这些事：

- 找到卡住的 step
- 对比模型输出与解析结果
- 检查工具返回是否异常
- 判断错误是模型误判还是工具异常

在没有 trace 的情况下，这些只能靠“复述”或“推测”。

## 5. 关键环境开关
Trace 的开关在 `create_trace_logger()` 中实现，支持环境变量控制：

- `TRACE_ENABLED`：是否启用 trace（代码中默认 true）
- `TRACE_DIR`：轨迹文件目录（默认 `memory/traces`）

同时，CLI 还有一些辅助调试开关（在 `core/config.py` 中读取）：

- `SHOW_REACT_STEPS`
- `SHOW_PROGRESS`
- `DEBUG` / `LOG_LEVEL`

这些不会替代 trace，但能在运行时提供即时可见的进度反馈。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一张简洁的开关面板图，列出 TRACE_ENABLED / TRACE_DIR / SHOW_REACT_STEPS / DEBUG 等配置项。”

## 6. 异常回放与故障定位
Trace 的价值不仅是“好看”，而是真能定位问题。例如：

- **工具调用失败**：`error` 事件会记录错误码与 traceback
- **模型输出异常**：`model_output` 里保留原始输出
- **解析失败**：`parsed_action` 可以暴露 Action 格式问题

这些信息都可以在 JSONL 文件中逐条检索，适合后续做自动化诊断或测试回归。

## 7. 小结
日志与可观测性并不是“可有可无”的工程细节，而是 Agent 稳定性的底座。

- trace 提供可回放轨迹
- JSONL 适合分析，Markdown 适合审计
- 关键埋点覆盖 ReAct 全流程
- 通过环境变量与 CLI 开关控制粒度

当系统复杂到一定程度，“没有 trace 就等于闭着眼开车”。
