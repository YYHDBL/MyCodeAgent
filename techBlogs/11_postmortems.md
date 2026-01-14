# 真实案例与失败复盘：卡住、输出污染、tool_call_id 与稳定性修复

这一章不讲设计理想，讲真实踩坑。很多问题不是“理论上会发生”，而是已经在 trace 里发生过。下面按三个最典型的故障来复盘：卡住、输出污染、tool_call_id 兼容性。

涉及代码与文件：

- `agents/codeAgent.py`
- `core/context_engine/history_manager.py`
- `tools/builtin/task.py`
- `prompts/agents_prompts/*`
- `memory/traces/*.jsonl`

## 1. 卡住：模型长时间无输出

### 现象
任务执行到某个 step，UI 显示一直“处理中”，但模型迟迟不返回有效内容。trace 里可能出现：

- `model_output` 为空
- usage 返回但 content 为空
- 模型返回函数调用结构，但 content 缺失

### 根因
常见原因有三类：

1) **Provider 行为不一致**：有些模型会在 `tool_calls` 字段里返回内容，而 `content` 为空。
2) **输出格式违规**：模型输出不符合 prompt 约束（比如多行混杂、残留 XML tag）。
3) **超长上下文**：模型接近窗口上限时更容易返回“空内容”或异常结构。

### 解决方案（代码层）
在 `agents/codeAgent.py` 里做了两个关键补丁：

- **空响应恢复**：`_recover_empty_response()` 会从 `tool_calls` / `function_call` 里恢复 Action。
- **二次重试机制**：`empty_response_retry` 会追加提示再重试一次。

这两个逻辑并不是“让模型更聪明”，而是**在不稳定输出条件下维持最小可用性**。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一个故障诊断流程图：模型空响应 → 解析 tool_calls → 失败则追加 hint 重试 → 最终失败记录 error。”

## 2. 输出污染：`<tool_call>` 标签混入

### 现象
模型返回的文本里混入类似：

```
Action: LS[{"path":"."}]<tool_call>...</tool_call>
```

这会导致 Action 解析失败，甚至污染 history。

### 根因
部分模型会“同时输出文本格式和 XML tool_call 标签”，尤其是在 prompt 里存在 tool call 的示例或 provider 对 tool call 有默认格式时。这不是一个单纯的提示词问题，而是模型行为差异。

### 解决方案（双层防线）

1) **提示词约束**：在 L1 与 subagent prompt 中明确写死
   - “只能输出 `Action: ToolName[JSON]`，禁止 `<tool_call>` 标签”。
   - 对应文件：`prompts/agents_prompts/L1_system_prompt.py`、`subagent_*_prompt.py`

2) **输出清洗**：在 `CodeAgent` 中新增 `_strip_tool_call_tags()`，在解析 Action 前强制剔除 `<tool_call>` 残留。

此外，Task 子代理的 `_parse_tool_call()` 也增加了同样的清洗逻辑，避免子代理污染主代理。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一张对比图：左侧是被污染的 Action（带 `<tool_call>`），右侧是清洗后的 Action，视觉上突出‘污染→净化’。”

## 3. tool_call_id：严格校验导致调用失败

### 现象
在某些 provider（比如严格 OpenAI 协议实现）上，模型报错：

- `missing field tool_call_id`

但在 GLM 等宽松实现上却能正常运行。

### 根因
当启用 OpenAI-style 的 tool 角色时，协议要求：

- assistant 消息里必须有 `tool_calls` 数组
- tool 消息里必须有匹配的 `tool_call_id`

如果历史里缺失 `tool_call_id`，严格 provider 会直接拒绝请求。

### 解决方案

1) **统一生成 tool_call_id**
   - 在 `CodeAgent` 每次工具调用时生成 `tool_call_id`，并写入 assistant/tool metadata。

2) **严格序列化**
   - `HistoryManager.to_messages()` 在 strict 模式下会输出 `tool_calls` 和 `role=tool` 的消息。
   - 缺失 `tool_call_id` 时会自动 fallback 到 compat 模式（Observation 文本）。

3) **Task 子代理同步支持**
   - `tools/builtin/task.py` 在 strict 模式下同样生成 `tool_call_id` 并写入 `role=tool`。

**插图位置建议**：放在本节之后。  
**图片内容描述**：
“一个 tool_call_id 绑定示意图：assistant 的 tool_calls 与 tool 消息通过同一个 id 连接，形成闭环。”

## 4. 为什么这些修复重要
这些问题听起来像“细节”，但如果不解决，会直接影响稳定性：

- 卡住 → 会话无法完成
- 输出污染 → Action 解析失败
- tool_call_id 缺失 → 直接被 provider 拒绝

它们不是“优化”，而是系统能否长期运行的生死线。

## 5. 小结
真实故障往往不出现在“架构大方向”，而是出在看似不起眼的细节上。MyCodeAgent 的修复路径可以总结为：

- **模型输出不可控 → 先做清洗与兜底**
- **多 Provider 差异 → 严格/宽松双模式**
- **故障复盘靠 trace → 让问题可重现**

这也是我一直强调“工程化”的原因：
**没有可观察性，没有边界控制，就没有稳定的 Agent。**
