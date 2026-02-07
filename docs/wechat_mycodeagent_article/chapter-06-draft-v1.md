# 第6章：上下文“腐烂”——从“堆消息”到“分层治理”

工具体系稳定之后，问题很快转移到了另一块：
**长对话一多，模型开始“变笨”。**

症状非常直观：
- 明明刚刚确认过的约束，过几轮就忘；
- 会话越长，越容易用错工具；
- 工具输出堆成山，最终答案越来越水。

我把这类问题统称为：**上下文腐烂**。

这一章就是我当时做的“上下文工程”改造：
从堆消息，到分层治理；从工具输出堆积，到统一截断；
从“无限历史”，到“可控压缩”。

---

## 01｜先把上下文分层：L1 / L2 / L3 的稳定结构

我先明确了一件事：
**系统提示词必须稳定，历史才有稳定的“锚”。**

所以我把上下文明确拆成三层：

- **L1 系统静态层**：System Prompt + 工具提示词（固定前缀）
- **L2 项目规则层**：`CODE_LAW.md`（有就注入，无则为空）
- **L3 会话历史层**：user / assistant / tool 消息 + summary

拼接顺序固定：

```
L1 → L2 → L3 → 当前 user → Todo recap
```

在 `core/context_engine/context_builder.py` 里就是这么做的：
先拿 system + tools，再加 CODE_LAW，再拼 history。
L1 稳定、L2 稳定，L3 才能稳定。

这一步解决的不是“记住更多”，
而是**让模型知道什么是永远不变的规则**。

---

## 02｜统一截断：Observation 进入历史前必须“瘦身”

上下文腐烂的最大来源，不是用户说的话，而是工具输出。
一次 Grep / Read 打出来几千行，如果不截断，
历史很快就被“证据垃圾”淹没。

所以我做了统一截断：

- **MAX_LINES = 2000**
- **MAX_BYTES = 50KB**
- 超出就截断 + 落盘 `tool-output/`

在 `HistoryManager.append_tool()` 里，所有工具结果写入前都会走：

```python
truncated_result = truncate_observation(tool_name, raw_result, project_root)
```

而 `ObservationTruncator` 的逻辑就是：
超过阈值 → 截断 → 落盘 → 返回 `full_output_path`。

这一步带来的改变很直接：历史不再爆炸，而且需要完整输出时还能**精准回查**。

具体流程是这样的：

```
工具输出超长 → 被截断 → 返回 full_output_path → 用 Read/Grep 回查
```

比如 Grep 返回了 2000+ 行匹配结果，被截断后会在响应里带上：

```json
{
  "status": "partial",
  "data": {"matches": [...], "truncated": true},
  "text": "Found 2156 matches (showing first 2000). Full output: tool-output/grep_20250115_143022.txt",
  "full_output_path": "tool-output/grep_20250115_143022.txt"
}
```

如果模型发现关键结果可能被截断了，它会收到明确的提示，然后可以用 Read 工具读取完整文件，或者用 Grep 在这个落盘文件里进一步筛选。

**这样一来，上下文保持精简，但完整证据始终可查。**

旧版的 `tool_result_compressor.py` 也就被废弃了，
所有工具一视同仁，统一截断。

---

## 03｜压缩触发：不是“觉得长了”，而是明确阈值

真正的大问题是：**历史越积越多，模型被噪声淹没。**
所以我加了明确的压缩触发条件：

- `estimated_tokens >= 0.8 * context_window`
- `messages >= 3`

代码在 `HistoryManager.should_compress()`：

```python
threshold = int(self._config.context_window * self._config.compression_threshold)
return estimated_total >= threshold
```

默认配置写死在 `core/config.py`：

- `context_window = 10000`
- `compression_threshold = 0.8`
- `min_retain_rounds = 10`

也就是说：
**超过 8k token 就触发压缩，但至少保留最近 10 轮完整对话。**

“保留完整轮次”非常关键：
一轮必须从 user 发起到 assistant 完成，中间的 tool_use / tool_result 不允许拆。
否则工具调用链就断了。

---

## 04｜Summary 归档：旧历史进档案，不再继续膨胀

压缩不是“删掉”，而是“归档”。

我用 `summary_compressor.py` 在压缩时生成 Summary：

- 生成超时：**120 秒**
- 超时则降级：不生成 summary，只保留最近轮次

Summary 模板在 `prompts/agents_prompts/summary_prompt.py`，
结构固定：Objectives / Technical Context / Completed Milestones / Decisions / File State。

HistoryManager 会把 Summary 作为 **role=summary** 存进去，
序列化时变成 **system message 注入**：

```python
messages.append({
  "role": "system",
  "content": f"## Archived History Summary\n{msg.content}"
})
```

并且 **Summary 永远不再压缩**。
它就是“旧历史的档案”，不是“当前任务的进度”。

---

## 05｜噪声控制：@file 不再直接塞内容

以前我做 @file 的时候，习惯直接把文件内容拼进上下文，
结果就是——上下文越用越肥，模型越用越糊。

现在我改成：**只插入 system-reminder，不直接注入内容。**

`input_preprocessor.py` 里规则很明确：
- 只匹配路径样式的 @file
- 最多 5 个，超出提示 “(and N more…)”
- 插入提醒：必须先 Read

例如用户输入：

```
请看一下 @core/llm.py 和 @agents/codeAgent.py
```

最终会被改写成：

```
<system-reminder>
The user mentioned @core/llm.py, @agents/codeAgent.py.
You MUST read these files with the Read tool before answering.
</system-reminder>
```

这一下，
**上下文里只留下“提醒”，而不是“垃圾”。**

---

## 06｜最终结果：上下文稳定 ≠ 上下文越长越好

这一轮改造之后，效果非常明显：

- 工具输出不会无限堆积
- 历史能在阈值时自动收敛
- Summary 把旧历史压成“稳定记忆”
- @file 不再制造垃圾上下文

一句话总结：

**上下文稳定不是“塞得更多”，而是“治理得更清晰”。**

---

下一章我会继续讲一个关键能力：
**Skills 与任务委派**，让 Code Agent 能把复杂任务拆成子任务，而不是一次性硬冲。
