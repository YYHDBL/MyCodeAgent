# 工具实践（三）Task 子 Agent：边界、稳定性与 schema 约束

如果说工具系统解决的是“做什么”，那 Task 子代理解决的是“谁来做”。它不是一个神秘的“多智能体系统”，而是一个受限、可控、同步执行的小型代理。

这一章基于 `tools/builtin/task.py` 和 `docs/task(subagent)设计文档.md`，聊清楚三件事：Task 的边界、Task 的稳定性设计、以及它如何保持结构化输出。

## 1. 为什么需要 Task 子代理
主 Agent 的 ReAct 循环适合“边走边做”，但一旦任务变复杂，比如：

- 需要先探索目录结构再总结
- 需要跨多个文件查找线索
- 需要形成一个中间结论再回到主线

就很容易把主对话拖得冗长、上下文负担过重。

Task 的作用就是把这些探索性工作“打包外包”，在一个隔离会话里完成，然后把结果带回来。

## 2. Task 并不是“无限自由的子模型”
在 `task.py` 里，Task 的边界是被硬编码出来的：

- **禁用工具**：`Task / Write / Edit / MultiEdit / Bash` 被明确拒绝
- **允许工具**：默认只给 `LS / Glob / Grep / Read / TodoWrite`
- **子代理类型**：`general / explore / summary / plan`

这意味着 Task 子代理是“只读的研究员”，而不是“能直接改代码的执行者”。

这种限制的好处是显而易见的：

- 避免递归调用 Task（防止无限子代理）
- 避免子代理修改文件（保持主 Agent 对改动的唯一控制权）
- 保证每个子任务的风险边界清晰

## 3. 子代理的系统 Prompt 是“角色化”的
Task 并不是一个统一的 prompt，而是按子代理类型选择系统提示：

- `general`：通用执行
- `explore`：文件探索
- `summary`：内容总结
- `plan`：规划拆解

这些提示词位于 `prompts/agents_prompts/subagent_*_prompt.py`，比如 `subagent_explore_prompt.py` 会明确要求“只读、只用 LS/Glob/Grep/Read”。

这是一种非常工程化的做法：**把角色能力写进 prompt，而不是靠模型自由发挥。**

## 4. 两种模型：main vs light
Task 支持两档模型：`main` 和 `light`。轻模型配置来自环境变量：

- `LIGHT_LLM_MODEL_ID`
- `LIGHT_LLM_API_KEY`
- `LIGHT_LLM_BASE_URL`

如果轻模型不可用，就自动回退到主模型。这样可以把“探索和总结”用更便宜的模型完成，而把“关键决策”留给主模型。

## 5. 子代理的执行是同步的
Task 的执行在 MVP 阶段是同步的：

- 主 Agent 发起 Task
- 子代理在独立会话中完成 ReAct
- Task 返回结果与工具使用统计

这样做虽然没有并发，但换来的是更简单的调试路径，也更适合初期的稳定性验证。

## 6. schema 约束与输出稳定性
子代理的输出依然必须遵循工具协议：

- Task 输出有固定的 `status/data/text/stats/context`
- `data` 中会包含 `result`、`tool_summary`、`model_used`、`subagent_type`
- 输出结构是主 Agent 可预测、可解析的

同时，Task 内部也处理了“工具调用格式”问题：

- 如果启用 strict 模式，会附带 `tool_call_id`
- 会过滤 `<tool_call>` 这类 XML 标签

这些细节不是为了“更漂亮”，而是为了让主 Agent 能在不同 Provider 下稳定接收子代理结果。

## 7. Task 的最佳使用场景
在实际使用中，Task 更适合：

- 目录结构扫描
- 搜索与归纳总结
- 复杂问题的资料准备
- 长文本的摘要压缩

它不应该被用于“直接改代码”。这是主 Agent 的职责。

## 8. 小结
Task 子代理不是“更聪明的模型”，而是一个被严格限制、可预测的工具：

- 只读、隔离、同步
- 有明确的角色与提示词
- 有清晰的模型选择逻辑
- 有结构化输出与稳定性保障

这些设计让 Task 更像“一个安全的分身”，而不是失控的多智能体系统。

---

## 配图建议（可选）

1) **插图位置建议**：放在“2. Task 并不是无限自由的子模型”小节之后。  
**图片内容描述**：
“一个权限边界图：中央是 Task 子代理，周围圈出允许工具（LS/Glob/Grep/Read/TodoWrite）和禁用工具（Task/Write/Edit/MultiEdit/Bash），用对比颜色标注。”

2) **插图位置建议**：放在“4. 两种模型：main vs light”小节之后。  
**图片内容描述**：
“两层模型选择图：主 Agent 选择 main 或 light，light 不可用时回退到 main。风格简洁、流程清楚。”

3) **插图位置建议**：放在“6. schema 约束与输出稳定性”小节之后。  
**图片内容描述**：
“一个结构化输出示意图：固定的 status/data/text/stats/context 信封，data 内部突出 result/tool_summary/model_used/subagent_type。”
