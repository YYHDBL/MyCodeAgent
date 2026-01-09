# 上下文工程构建总结 (Context Engineering Build Summary)

本文档总结了 MyCodeAgent 上下文工程（Context Engineering）的设计与实现状态。该系统旨在解决长对话场景下的 Token 溢出问题，通过历史压缩、工具结果精简和智能摘要机制，确保 Agent 能够长时间保持高效运行。

## 1. 核心目标

*   **防止 Token 溢出**：在有限的 Context Window (200k) 内维持对话。
*   **保留关键信息**：确保压缩后的历史仍包含代码修改、文件状态等关键上下文。
*   **无感压缩**：自动触发压缩和摘要，对用户透明。
*   **高效复用**：将 ReAct 过程中的 Scratchpad（完整）与 History（压缩）分离。

## 2. 架构概览

系统由以下核心模块组成：

| 模块 | 文件路径 | 职责 | 核心策略 |
| :--- | :--- | :--- | :--- |
| **HistoryManager** | `core/history_manager.py` | 历史消息存储、轮次管理、压缩触发 | 分离 Scratchpad/History，基于轮次压缩 |
| **ToolResultCompressor** | `core/tool_result_compressor.py` | 工具结果压缩 | 丢弃 text/stats，仅保留 status/data 关键字段 |
| **InputPreprocessor** | `core/input_preprocessor.py` | 用户输入预处理 | 解析 `@file`，注入 system-reminder |
| **ContextBuilder** | `core/context_builder.py` | Prompt 组装 | 分层拼接 (L1-L6)，动态加载 |
| **SummaryCompressor** | `core/summary_compressor.py` | 摘要生成 | 归档旧历史，生成结构化 Summary |
| **ReadTool (Enhanced)** | `tools/builtin/read_file.py` | 文件读取增强 | mtime 追踪，检测外部修改 |

---

## 3. 模块实现细节

### 3.1 HistoryManager (历史管理器)
*   **轮次管理**：以 User 消息作为新一轮的起点。压缩时保证轮次完整性，不切断 Tool Call / Result 对。
*   **双层存储**：
    *   **Scratchpad** (ReAct Loop 内)：保留**完整**的 Observation，供当前步推理使用。
    *   **History** (长期存储)：存储**压缩后**的 Tool Result，供未来轮次参考。
*   **压缩触发 (A6 规则)**：
    *   公式：`last_usage + len(input)//3 >= 0.8 * context_window`
    *   条件：消息数 >= 3
*   **压缩动作**：保留最近 `min_retain_rounds` (默认10) 轮，旧消息替换为 Summary。
*   **序列化**：输出格式为 `[role] content`，工具消息带名称 `[tool:Name] JSON`。

### 3.2 ToolResultCompressor (工具压缩器)
针对不同工具实施定制化压缩策略（A3 规则），大幅减少 Token 占用：

| 工具 | 压缩策略 | 保留的关键信息 |
| :--- | :--- | :--- |
| **LS** | 截断列表 | 前10项 + 真实总数 (`total_entries`) + 路径 |
| **Grep** | 截断匹配 | 前5条匹配 + 真实总数 (`total_matches`) + 模式 |
| **Read** | 截断内容 | 前500行 + 路径 + mtime + 外部修改标记 |
| **Edit/Multi**| 变更摘要 | 路径 + 应用状态 + Diff 前10行 + 替换数 |
| **Write** | 写入摘要 | 路径 + 操作类型(create/update) + Diff 前10行 |
| **Bash** | 截断输出 | stdout 摘要 + stderr 尾部20行 + exit_code |
| **通用** | 协议清洗 | 仅保留 `status`, `data`, `error`，丢弃 `text`, `stats` |

### 3.3 ContextBuilder (上下文构建器)
采用分层结构组装最终 Prompt (D4 方案)：

1.  **L1: System & Tools**: 静态系统提示词和工具定义。
2.  **L2: CODE_LAW**: 项目级规则 (如果存在 `CODE_LAW.md`)。
3.  **L3: Chat History**: 序列化后的历史记录 (含 Summary 和压缩后的消息)。
4.  **L4: Current Question**: 预处理后的用户输入 (含 `@file` 提示)。
5.  **L5: Todo Recap**: (预留接口，暂未实现)。
6.  **L6: Scratchpad**: 当前轮次正在进行的思考和行动。

### 3.4 InputPreprocessor (输入预处理)
*   **@file 解析**：正则匹配 `(?<![a-zA-Z0-9])@path/to/file`。
*   **System Reminder**：自动在 User 消息后追加 `<system-reminder>`，提示 Agent 读取相关文件。
*   **限制**：自动去重，最多处理 5 个文件，仅支持英文路径。

### 3.5 SummaryCompressor (摘要生成)
*   **结构化模板**：生成包含目标、技术栈、已完成任务、关键决策、文件系统快照的 Markdown 摘要。
*   **超时控制**：默认 120s 超时。若超时，执行降级策略（仅截断历史，不生成 Summary）。
*   **线程安全**：使用非阻塞的 Executor 关闭策略，防止死锁。

### 3.6 mtime 追踪 (ReadTool)
*   **乐观锁机制**：内存缓存文件 `mtime`。
*   **变更检测**：每次读取时比对 `mtime`，若发现外部修改，在返回结果中标记 `modified_externally=True` 并通过 Text 提示。

---

## 4. 关键流程图解

### 4.1 ReAct 循环与消息流转
```mermaid
graph TD
    User[用户输入] --> Preprocessor[InputPreprocessor]
    Preprocessor -->|@file注入| Check{触发压缩?}
    
    Check -- Yes --> Compressor[SummaryCompressor]
    Compressor -->|生成Summary/截断| History
    Check -- No --> History
    
    History --> Builder[ContextBuilder]
    Scratchpad --> Builder
    Builder --> LLM
    
    LLM -->|Thought/Action| History(Assistant Msg)
    LLM -->|Thought/Action| Scratchpad
    
    LLM -->|Tool Call| ToolExec[执行工具]
    ToolExec -->|Full Result| Scratchpad
    ToolExec -->|Full Result| ResultComp[ToolResultCompressor]
    ResultComp -->|Compressed Result| History(Tool Msg)
```

## 5. 配置参数 (Config)

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `context_window` | 200,000 | Token 窗口上限 |
| `compression_threshold` | 0.8 | 触发压缩的比例阈值 (160k) |
| `min_retain_rounds` | 10 | 压缩时保留的最近完整轮次数 |
| `summary_timeout` | 120 | 摘要生成超时秒数 |

## 6. 当前限制与未来计划

*   **Todo Recap**: L5 层暂未实现，计划在未来集成任务管理模块后添加。
*   **@file 路径支持**: 目前仅支持英文路径，未来可扩展支持带空格或非 ASCII 路径。
*   **ContextBuilder**: 接口已完全重写，不再兼容旧版 Agent。

## 7. 验证状态

所有核心功能已通过单元测试验证 (`tests/test_context_engineering.py`)，覆盖：
*   所有工具的压缩逻辑（含边界情况）。
*   历史管理与轮次识别。
*   输入预处理正则。
*   Bug 修复验证（路径丢失、格式错误等）。

---

# 🚀 技术分享：如何让 Code Agent 在 200k Token 中“永生”？——上下文工程实践

> *“AI 的记忆不是无限的，但我们可以让它看起来是。”*

在构建长期运行的 Code Agent（编程智能体）时，我们很快就会撞上一堵墙：**Context Window（上下文窗口）**。即使现在的模型支持 200k 甚至更长的 Token，ReAct 循环（Thought-Action-Observation）产生的海量日志也会迅速填满它。

更糟糕的是，充满了无关细节的上下文不仅浪费 Token 成本，还会**稀释模型的注意力**，导致它在长对话后变得“变笨”。

本文将分享我们在 `MyCodeAgent` 项目中落地的**上下文工程（Context Engineering）**方案，探讨如何通过精细的架构设计，让 Agent 在长达数小时的编码任务中保持清醒。

## 1. 核心矛盾：精度 vs. 长度

Code Agent 的工作模式决定了它的上下文具有极高的**冗余性**：
*   **读文件**：为了修改一行代码，可能需要读取整个文件。
*   **列目录**：为了找一个文件，可能列出了成百上千个无关文件。
*   **报错调试**：一次失败的尝试可能包含几千行的 StackTrace。

对于**当前步骤**，这些细节至关重要；但对于**十轮之后的历史**，这些只是噪音。

我们的核心解法是：**双层记忆架构（Dual Memory Architecture）**。

## 2. 架构设计：Scratchpad 与 History 的分离

我们将 Agent 的记忆分为“短期工作记忆”和“长期情节记忆”。

### 🧠 短期记忆：Scratchpad (L6)
*   **内容**：当前 ReAct 轮次内产生的所有 Thought、完整的 Tool Action 和**未经压缩的 Observation**。
*   **作用**：保证模型在当前推理步拥有最完整的细节（例如，看到完整的文件内容才能准确修改）。
*   **生命周期**：仅存活于当前轮次，轮次结束（Finish）后即被清空。

### 📚 长期记忆：History (L3)
*   **内容**：过去轮次的对话记录。
*   **作用**：提供任务背景和连贯性。
*   **特殊处理**：**所有进入 History 的工具结果（Tool Result）必须经过压缩。**
*   **生命周期**：持久保存，但随着 Token 增长会被“归档”为 Summary。

## 3. 关键战术：给工具结果“瘦身”

这是我们最引以为豪的部分——`ToolResultCompressor`。我们不盲目截断，而是针对不同工具定制压缩策略。

**实战案例：**

*   **LS (列文件)**:
    *   *原始*：返回 100 个文件的详细列表。
    *   *压缩后*：`{"entries": [前10个文件...], "total_count": 100, "truncated": true}`。
    *   *逻辑*：历史记录只需要知道“这里有很多文件”以及“前几个长啥样”，不需要全貌。

*   **Read (读文件)**:
    *   *原始*：返回 2000 行代码。
    *   *压缩后*：`{"content": "...", "lines": 500, "truncated": true}`。
    *   *逻辑*：如果通过 grep 找到了位置，历史里留 500 行上下文足够回忆起文件结构。

*   **Edit (编辑)**:
    *   *原始*：包含应用前后的完整 diff preview。
    *   *压缩后*：`{"applied": true, "path": "src/main.py", "diff_summary": "前10行diff..."}`。
    *   *逻辑*：知道“改了哪里”和“改成功了”比“具体怎么改的”更重要。

这种**语义级压缩**使得 History 的 Token 密度极高，全是干货。

## 4. 动态归档：Summary 机制

当即使压缩后的历史也超过阈值（如 160k Token）时，我们启动**轮次级归档**：

1.  **完整轮次识别**：我们绝不在 Agent 思考一半时切断。压缩总是发生在 User 和 Assistant 一问一答结束之后。
2.  **LLM 摘要**：启动一个并行线程，将最早的 N 轮对话发给 LLM，生成一份结构化的《Archived Session Summary》。
3.  **结构化模板**：Summary 不是一段流水账，而是包含“已完成任务”、“技术栈信息”、“关键决策”的结构化数据。这就像给模型留了一份“交接文档”。

```markdown
### ✅ Completed Milestones
* [✓] Implemented authentication logic in `auth.ts`
* [✓] Fixed memory leak in HistoryManager
```

## 5. 用户体验优化：@file 与 mtime

除了后端架构，我们在前端交互上也做了微创新：

*   **`@file` 语法糖**：
    用户输入 `请检查 @core/config.py`，预处理器会自动将其展开为 System Reminder：`You MUST read core/config.py with Read tool...`。这比单纯 Prompt 引导更稳定。

*   **mtime 追踪（防幻觉）**：
    Agent 经常会“以为”文件内容还是上一轮读取的样子。我们在 `ReadTool` 中内置了乐观锁机制，记录文件 `mtime`。如果 Agent 再次读取时文件被外部修改了，工具会显式返回 `modified_externally: true`，强迫模型重新审视内容。

## 6. 总结

上下文工程不仅仅是简单的“截断字符串”，它本质上是一种**注意力管理（Attention Management）**。

通过**Scratchpad/History 分离**，我们保证了当下的精度；通过**语义压缩**，我们保证了历史的密度；通过**结构化 Summary**，我们保证了长期记忆的深度。

这一套组合拳，让 Code Agent 不再是“金鱼记忆”，而是一个能胜任复杂项目开发的资深工程师。

