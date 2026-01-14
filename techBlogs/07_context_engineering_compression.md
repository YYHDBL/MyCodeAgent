# 上下文工程（一）：压缩策略与结构化摘要

长对话是 Agent 最容易失控的场景。历史越来越长、工具输出越来越大、模型开始“忘记关键点”或者“记住了错误的点”。所以 MyCodeAgent 把上下文工程作为一等公民，先解决“历史如何被保存、何时压缩、压缩后如何可读”。

这一章只讲两个核心：**压缩触发**与**结构化摘要**。相关实现可以在这些文件中找到：

- `docs/上下文工程设计文档.md`
- `core/context_engine/history_manager.py`
- `core/context_engine/summary_compressor.py`
- `prompts/agents_prompts/summary_prompt.py`

## 1. 历史不是“越多越好”
MyCodeAgent 的设计假设很明确：

- 历史一定会增长
- 历史一定会超过模型窗口
- 超过之后如果不处理，会拖慢推理、放大噪声、甚至引发报错

因此系统给历史设置了“清晰的生命周期”：

- 最近对话必须保留
- 更久远的对话必须压缩
- 压缩必须可追踪、可解释

## 2. 触发压缩的规则
压缩触发逻辑在 `HistoryManager.should_compress()` 中。核心规则写在设计文档 A6：

- 使用上一次调用的 `usage.total_tokens` 作为精确基准
- 估算当前输入 `len(user_input) // 3`
- 当 `estimated_total >= context_window * compression_threshold` 时触发
- 消息数必须 >= 3，避免早期过度压缩

它不是“觉得差不多了就压缩”，而是一个明确、可计算的阈值机制。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一个阈值触发示意图：横轴是 token 估算值，纵轴是是否压缩，标出 0.8×context_window 的触发点。”

## 3. 保留区：至少 10 轮，但不是死规则
历史压缩不是“全盘清空”，它会保留最近 N 轮。规则写在 A4：

- 只压缩 user / assistant / tool 消息
- summary 不参与压缩（只追加）
- 一轮从 user 发起到 assistant 完成
- 压缩边界必须对齐完整轮次
- 默认保留最近 10 轮（`min_retain_rounds`）

这背后的设计动机很直接：**最近上下文必须稳定，而“记忆”应该有边界**。

## 4. Summary 是“归档”，不是“进度”
MyCodeAgent 的 Summary 不是随手写的摘要，而是结构化、固定模板的“档案”。模板来自 `prompts/agents_prompts/summary_prompt.py`，大致结构如下：

- Objectives & Status
- Technical Context
- Completed Milestones
- Key Insights & Decisions
- File System State

这套模板在 `docs/上下文工程设计文档.md` 里也有明确版本。重点是：**Summary 只包含已完成事项，不记录当前未完成任务**。这样可以避免“摘要里掺杂正在做的事”，导致后续推理误判。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一张结构化摘要卡片，包含 5 个固定区块（Objectives/Context/Milestones/Decisions/Files），排版清晰，强调‘归档’而非‘进度’。”

## 5. Summary 的生成机制
Summary 的生成逻辑在 `core/context_engine/summary_compressor.py`：

- 把待压缩消息序列化成文本（含 user/assistant/tool）
- 拼接 `SUMMARY_PROMPT` 生成最终 prompt
- 调用模型生成 summary
- 超时（默认 120s）就降级为“只截断、不摘要”

这是一种工程化的折中：如果摘要失败，不阻塞整个系统，而是优先保证可用性。

## 6. Summary 在历史里怎么存
Summary 并不是简单插入一条“assistant 消息”。它以 `role=summary` 的形式存进 `HistoryManager`，最终会被序列化为 `role=system`：

- 保证 Summary 不会再被压缩
- 保证 Summary 的优先级高于普通对话
- 避免模型把 Summary 当成“某个用户的输入”

这一点体现在 `HistoryManager.to_messages()` 的实现里。

## 7. 压缩不是“删”，而是“降维”
压缩的目标不是删除信息，而是把高成本信息降维：

- 最近 10 轮保留原始信息
- 更早的内容通过 Summary 保留关键事实
- 工具输出超大时走统一截断（下一章重点）

这样，模型在“当前任务”上仍然有完整上下文，但不会因为历史膨胀而失控。

## 8. 小结
这一章的核心可以总结成一句话：

**MyCodeAgent 把“记忆”当成系统工程，而不是 prompt 里的愿望。**

- 触发条件明确
- 保留区可控
- Summary 结构化
- 降级路径清晰

下一章会继续讲上下文工程的另一半：工具输出截断与长程任务的稳定性。
