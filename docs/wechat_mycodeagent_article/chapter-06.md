# 六、长对话的困境：我的上下文工程改造

调用协议稳定之后，问题很快转移到了另一块：**长对话一多，模型开始"变笨"**。

症状挺明显的——明明刚确认过的约束，过几轮就忘；会话越长，越容易用错工具；工具输出堆成山，最终答案越来越水。

这不只是我遇到的问题。 像Calude Code,Manus等业界主流的agent产品都不约而同的提出一点："在长期运行、多轮决策和工具协同的场景下，模型能否稳定发挥，往往取决于它所'看到'的上下文是否清晰、是否连贯。"

我的改造思路是：**从堆消息到分层治理，从工具输出堆积到统一截断，从无限历史到可控压缩。**

---

## 1、先把上下文分层：L1 / L2 / L3 的稳定结构

参考上下文工程的分层思路，我把上下文拆成三层：

| 层级 | 内容 | 稳定性 | 作用 |
|-----|------|--------|------|
| L1 系统静态层 | System Prompt + 工具提示词 | 固定 | 提供不变的行为准则 |
| L2 项目规则层 | `CODE_LAW.md` | 半固定 | 项目特定的规范约束 |
| L3 会话历史层 | user / assistant / tool 消息 | 动态 | 当前任务的状态流转 |

拼接顺序固定：
```
L1 → L2 → L3 → 当前 user → Todo recap
```

正如那篇文章强调的："上下文不再只是输入的一部分，而是系统状态的集中体现"。**L1/L2 稳定，L3 才能稳定**，模型需要知道什么是永远不变的规则。

---

## 2、统一截断：Observation 进历史前必须"瘦身"

上下文膨胀的最大来源，不是用户说的话，而是**工具输出**。

一次 Grep / Read 打出来几千行，如果不截断，历史很快就被"证据垃圾"淹没。

我的统一截断策略：
- **MAX_LINES = 2000**
- **MAX_BYTES = 50KB**
- 超出就截断 + 落盘 `tool-output/`

在 `HistoryManager.append_tool()` 里，所有工具结果写入前都会走：
```python
truncated_result = truncate_observation(tool_name, raw_result, project_root)
```

**截断后的回查流程：**

```
工具输出超长 → 被截断 → 返回 full_output_path → 用 Read/Grep 回查
```

举个栗子，Grep 返回 2000+ 行，被截断后响应里会带上：

```json
{
  "status": "partial",
  "data": {"matches": [...], "truncated": true},
  "text": "Found 2156 matches (showing first 2000)...",
  "full_output_path": "tool-output/grep_20250115_143022.txt"
}
```

如果模型发现关键结果被截断，会收到明确提示，然后用 Read 读取完整文件，或者用 Grep 在落盘文件里进一步筛选。

**上下文保持精简，但完整证据始终可查。**

---

## 3、压缩触发：明确阈值，自动收敛

历史越积越多，模型会被噪声淹没。

我设定的压缩触发条件：
- `estimated_tokens >= 0.8 * context_window`
- `messages >= 3`

默认配置：
- `context_window = 10000`
- `compression_threshold = 0.8`
- `min_retain_rounds = 10`

**超过 8k token 就触发压缩，但至少保留最近 10 轮完整对话。**

"保留完整轮次"非常关键：一轮必须从 user 发起到 assistant 完成，中间的工具调用链不能拆。这是保证 Agent 行为连贯性的底线。

---

## 4、Summary 归档：旧历史压缩成"记忆卡片"

压缩不是删除，而是归档。我用 Summary 把旧历史提炼成关键信息。

`summary_compressor.py` 在压缩时生成 Summary：
- 生成超时：**120 秒**
- 超时则降级：不生成 summary，只保留最近轮次

Summary 模板结构：Objectives / Technical Context / Completed Milestones / Decisions / File State。

HistoryManager 把 Summary 作为 **role=summary** 存进去，序列化时变成 **system message 注入**：

```python
messages.append({
  "role": "system",
  "content": f"## Archived History Summary\n{msg.content}"
})
```

**Summary 永远不再压缩。** 它是"旧历史的档案"，不是"当前任务的进度"。

---

## 5、噪声控制：@file 不再直接塞内容

以前做 @file 时，我习惯直接把文件内容拼进上下文，结果就是——上下文越用越肥，模型越用越糊。

现在改成：**只插入 system-reminder，不直接注入内容。**

`input_preprocessor.py` 规则：
- 只匹配路径样式的 @file
- 最多 5 个，超出提示 "(and N more…)"
- 插入提醒：必须先 Read

用户输入：
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

**上下文里只留下"提醒"，而不是"垃圾"。**

---

## 6、写在最后

这一轮改造之后，效果挺明显的：

- 工具输出不会无限堆积
- 历史能在阈值时自动收敛
- Summary 把旧历史压成"稳定记忆"
- @file 不再制造垃圾上下文

正如那篇上下文工程的文章所说："真正决定系统上限的，是上下文如何被构建、更新和管理。"

**上下文不是塞得越多越好，而是要治理得清晰、可追溯。**

---

**下一章**：可观测性——当工具、协议和上下文都稳定后，如何让 Agent 的每一步都可追踪、可复盘。
