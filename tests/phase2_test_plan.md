# Phase 2 测试方案：上下文工程核心

## 概述

Phase 2 测试上下文工程核心组件，这是 ReAct Agent 的关键基础设施。

| 测试文件 | 覆盖组件 | 测试类 | 用例数 |
|---------|---------|--------|--------|
| test_history_manager.py | HistoryManager | 7 | ~50 |
| test_summary_compressor.py | SummaryCompressor | 4 | ~30 |
| test_context_builder.py | ContextBuilder | 5 | ~35 |

---

## 1. test_history_manager.py - 历史记录管理器测试

### 核心职责（来自代码注释）
1. **轮内写入**：同步写入 assistant（Thought/Action）与 tool（截断结果）消息
2. **轮间管理**：基于 user 消息分轮，提供 append/get/compact 接口
3. **截断策略**：调用 ObservationTruncator 截断工具输出
4. **触发 Summary**：检测压缩条件并生成 Summary

### 测试类结构
```
TestHistoryManager(unittest.TestCase)
├── TestMessageAppend (消息追加)
├── TestRoundIdentification (轮次识别)
├── TestCompressionTrigger (压缩触发检测)
├── TestCompressionExecution (压缩执行)
├── TestSerialization (消息序列化)
├── TestToolMessageFormat (工具消息格式)
└── TestEdgeCases (边界条件)
```

### 1.1 TestMessageAppend 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_append_user | 追加 user 消息 | role="user"，消息被添加 |
| test_append_assistant | 追加 assistant 消息 | role="assistant" |
| test_append_tool_with_truncation | 追加 tool 消息（截断） | 调用 truncate_observation |
| test_append_summary | 追加 summary 消息 | role="summary"，不参与压缩 |
| test_append_with_metadata | 带 metadata 的消息 | metadata 正确保留 |
| test_get_messages_copy | get_messages 返回副本 | 修改不影响内部 |
| test_get_message_count | 消息计数 | 返回正确数量 |
| test_clear | 清空历史 | 所有消息被清除 |

### 1.2 TestRoundIdentification 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_identify_single_round | 单轮对话 | rounds 长度为 1 |
| test_identify_multiple_rounds | 多轮对话 | user 开启新轮 |
| test_identify_round_with_tools | 包含工具调用的轮 | assistant + tool 同轮 |
| test_identify_summary_excluded | summary 不参与分轮 | summary 被跳过 |
| test_identify_consecutive_users | 连续 user 消息 | 每个 user 开启新轮 |
| test_get_rounds_count | 获取轮次数量 | 返回正确值 |

**轮次定义**（A4）：从 user 发起到 assistant 完成回答（中间允许多次工具调用）

### 1.3 TestCompressionTrigger 测试用例

| 用例名称 | 描述 | 条件 | 验证点 |
|---------|------|------|--------|
| test_should_compress_false_few_messages | 消息数不足 | < 3 条 | 返回 False |
| test_should_compress_true_threshold | 触发压缩 | >= 阈值 | 返回 True |
| test_should_compress_false_below_threshold | 未达阈值 | < 阈值 | 返回 False |
| test_should_compress_exact_threshold | 正好达阈值 | == 阈值 | 返回 True |
| test_should_compress_token_estimate | Token 预估计算 | last_usage + input//3 | 计算正确 |

**触发条件**（A6）：
- `estimated_total = last_usage_tokens + len(user_input) // 3`
- `estimated_total >= context_window * compression_threshold`
- 且消息数 >= 3

### 1.4 TestCompressionExecution 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_compress_not_enough_rounds | 轮次不足 | 返回 False，reason="rounds_not_enough" |
| test_compress_with_summary | 成功压缩（有 Summary） | 生成 Summary，旧消息删除 |
| test_compress_without_summary_generator | 无 Summary 生成器 | 仅截断，不生成 Summary |
| test_compress_summary_generator_fails | Summary 生成失败 | 降级为仅截断 |
| test_compress_retain_minimum_rounds | 保留最少轮次 | min_retain_rounds 被保留 |
| test_compress_preserves_existing_summaries | 保留现有 summary | 旧 summary 不被删除 |
| test_compress_emits_events | 事件触发 | on_event 回调被调用 |
| test_compress_return_info | return_info=true | 返回详细压缩信息 |

**压缩流程**：
1. 识别轮次边界
2. 计算保留区（最近 N 轮）
3. 对旧消息生成 Summary
4. 删除旧消息，插入 Summary

### 1.5 TestSerialization 测试用例

| 用例名称 | 格式模式 | 验证点 |
|---------|---------|--------|
| test_serialize_user_message | compat | role="user", content 直接输出 |
| test_serialize_assistant_compat | compat | role="assistant", content 包含 Thought/Action |
| test_serialize_tool_compat | compat | role="user", content="Observation (ToolName): {...}" |
| test_serialize_assistant_strict | strict | role="assistant", tool_calls 数组 |
| test_serialize_tool_strict | strict | role="tool", tool_call_id 存在 |
| test_serialize_summary | 通用 | role="system", content 包含 "Archived History Summary" |
| test_serialize_strict_missing_tool_call_id | strict 缺少 tool_call_id | 回退到 compat 模式 |

### 1.6 TestToolMessageFormat 测试用例

| 用例名称 | 格式 | 验证点 |
|---------|------|--------|
| test_tool_format_compat_default | 默认 compat | messages 为 compat 格式 |
| test_tool_format_strict | tool_message_format="strict" | messages 为 strict 格式 |
| test_tool_format_openai | tool_message_format="openai" | 等同于 strict |
| test_tool_format_case_insensitive | tool_message_format="STRICT" | 正确识别为 strict |

### 1.7 TestEdgeCases 测试用例

| 用例名称 | 描述 |
|---------|------|
| test_empty_history | 空历史记录 |
| test_only_user_messages | 只有 user 消息 |
| test_only_summaries | 只有 summary 消息 |
| test_update_last_usage | 更新 token 使用量 |
| test_round_with_multiple_tools | 一轮多次工具调用 |
| test_consecutive_summaries | 连续 summary 消息 |

---

## 2. test_summary_compressor.py - 上下文压缩测试

### 核心功能
1. 接收待压缩的历史消息列表
2. 调用 LLM 生成 Summary
3. 支持超时控制（120 秒）
4. 超时降级策略（返回 None）

### 测试类结构
```
TestSummaryCompressor(unittest.TestCase)
├── TestCreateGenerator (生成器创建)
├── TestSummaryGeneration (Summary 生成)
├── TestTimeoutHandling (超时处理)
├── TestErrorHandling (错误处理)
└── TestHelperFunctions (辅助函数)
```

### 2.1 TestCreateGenerator 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_create_generator_with_llm | 正常创建 | 返回可调用函数 |
| test_create_generator_default_config | 默认配置 | timeout=120 秒 |
| test_create_generator_custom_config | 自定义配置 | 使用传入的 config |
| test_create_generator_verbose_mode | verbose=true | 打印调试信息 |

### 2.2 TestSummaryGeneration 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_generate_summary_empty_messages | 空消息列表 | 返回 None |
| test_generate_summary_success | 成功生成 | 返回 Summary 字符串 |
| test_generate_summary_serialization | 消息序列化 | user/assistant/tool 正确格式化 |
| test_generate_summary_with_long_content | 长内容截断 | tool 消息截断到 500 字符 |
| test_generate_summary_preserves_summary_msg | summary 消息保留 | "[Previous Summary]: ..." |
| test_generate_summary_strips_result | 移除 "Final Answer:" | 清理 LLM 输出 |

### 2.3 TestTimeoutHandling 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_timeout_llm_slow_response | LLM 响应慢 | 超时返回 None |
| test_timeout_cancels_future | 取消 future | future.cancel() 被调用 |
| test_timeout_executor_shutdown | executor 关闭 | shutdown(wait=False) |
| test_timeout_custom_duration | 自定义超时 | 使用配置的 timeout |
| test_timeout_no_wait_on_shutdown | shutdown 不等待 | wait=False 避免阻塞 |

### 2.4 TestErrorHandling 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_error_llm_exception | LLM 调用异常 | 返回 None，不抛出 |
| test_error_llm_returns_none | LLM 返回 None | 正确处理 |
| test_error_summary_prompt_missing | SUMMARY_PROMPT 缺失 | 使用内置 fallback |
| test_error_graceful_degradation | 优雅降级 | 失败时不影响主流程 |

### 2.5 TestHelperFunctions 测试用例

| 函数 | 用例 | 验证点 |
|------|------|--------|
| _serialize_messages_for_summary | user 消息 | "[User]: ..." |
| _serialize_messages_for_summary | assistant 消息 | "[Assistant]: ..." |
| _serialize_messages_for_summary | tool 消息 | "[Tool:Name]: ..." (截断) |
| _serialize_messages_for_summary | summary 消息 | "[Previous Summary]: ..." |
| _build_summary_prompt | prompt 构建 | 包含 SUMMARY_PROMPT + 对话文本 |

---

## 3. test_context_builder.py - L1-L4 消息构建测试

### Message List 模式架构
```
messages = [
    {"role": "system", "content": "L1 系统提示 + 工具说明"},
    {"role": "system", "content": "L2: CODE_LAW.md（如有）"},
    {"role": "user", "content": "L3/L4: 历史（含当前输入）"},
    ...
]
```

### 测试类结构
```
TestContextBuilder(unittest.TestCase)
├── TestBuildMessages (构建消息)
├── TestSystemPrompt (L1 系统提示)
├── TestCodeLaw (L2 CODE_LAW)
├── TestToolPrompts (工具提示)
├── TestCaching (缓存机制)
└── TestMCPAndSkills (MCP/Skills 集成)
```

### 3.1 TestBuildMessages 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_build_empty_history | 空历史 | 返回 system 消息 |
| test_build_with_user_messages | 包含 user 消息 | user 消息被追加 |
| test_build_with_assistant_messages | 包含 assistant 消息 | assistant 消息被追加 |
| test_build_with_tool_messages | 包含 tool 消息 | tool 消息被追加 |
| test_build_with_summary | 包含 summary 消息 | summary 消息被追加 |
| test_build_preserves_order | 消息顺序 | system → history 保持顺序 |

### 3.2 TestSystemPrompt 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_load_system_prompt_default | 默认系统提示 | 从 L1_system_prompt.py 加载 |
| test_load_system_prompt_override | override 优先 | system_prompt_override 被使用 |
| test_load_system_prompt_missing_file | 文件不存在 | 返回空字符串 |
| test_load_system_prompt_invalid_python | 无效 Python | 返回空字符串 |
| test_load_system_prompt_tools_injection | {tools} 占位符 | tools 被注入 |

### 3.3 TestCodeLaw 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_load_code_law_exists | CODE_LAW.md 存在 | 作为第二个 system 消息 |
| test_load_code_law_alternative_name | code_law.md (小写) | 正确加载 |
| test_load_code_law_missing | 文件不存在 | 不添加 system 消息 |
| test_load_code_law_prefix | CODE_LAW 前缀 | 添加 "# Project Rules (CODE_LAW)" |
| test_load_code_law_mtime_cache | 文件未修改 | 使用缓存 |
| test_load_code_law_mtime_refresh | 文件已修改 | 重新加载 |
| test_load_code_law_encoding | UTF-8 编码 | 正确读取中文 |

### 3.4 TestToolPrompts 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_load_tool_prompts_default | 加载所有工具提示 | 从 tools_prompts/ 目录 |
| test_load_tool_prompts_sorted | 按文件名排序 | 顺序一致 |
| test_load_tool_prompts_skip_private | 跳过 __ 开头文件 | __init__.py 被跳过 |
| test_load_tool_prompts_extract_prompt | 提取 _prompt 变量 | ls_prompt, grep_prompt 等 |
| test_load_tool_prompts_missing_dir | 目录不存在 | 返回空字符串 |

### 3.5 TestCaching 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_system_messages_cached | system 消息缓存 | 第二次调用返回缓存 |
| test_cache_invalidated_on_code_law_change | CODE_LAW 变更 | 缓存失效 |
| test_cache_invalidated_on_mcp_change | MCP 工具变更 | set_mcp_tools_prompt 清空缓存 |
| test_cache_invalidated_on_skills_change | Skills 变更 | set_skills_prompt 清空缓存 |

### 3.6 TestMCPAndSkills 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_mcp_tools_prompt_section | MCP 工具提示 | 添加 "# MCP Tools" |
| test_mcp_tools_prompt_injection | 注入到系统提示 | MCP 工具被包含 |
| test_skills_prompt_injection | Skills 提示注入 | {{available_skills}} 被替换 |
| test_set_mcp_tools_prompt | 设置 MCP 提示 | set_mcp_tools_prompt 生效 |
| test_set_skills_prompt | 设置 Skills 提示 | set_skills_prompt 生效 |

---

## 测试辅助设施

### Mock LLM
```python
@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.invoke = Mock(return_value="Summary content here")
    return llm

@pytest.fixture
def slow_llm():
    """模拟慢响应 LLM（用于超时测试）"""
    llm = Mock()
    def slow_invoke(*args, **kwargs):
        time.sleep(5)  # 超过默认超时
        return "Late response"
    llm.invoke = slow_invoke
    return llm
```

### Mock Config
```python
@pytest.fixture
def test_config():
    return Config(
        context_window=1000,
        compression_threshold=0.8,
        min_retain_rounds=3,
        summary_timeout=2,  # 2 秒超时（测试用）
        tool_message_format="compat",
    )
```

### Mock ToolRegistry
```python
@pytest.fixture
def mock_tool_registry():
    registry = Mock()
    registry.get_all_tools.return_value = []
    return registry
```

---

## 关键测试场景

### HistoryManager 关键场景

1. **轮次边界识别**
   - user → assistant → tool（同一轮）
   - user → assistant → tool → assistant → tool（同一轮）
   - user → assistant（新轮）

2. **压缩触发条件**
   - 阈值计算：`context_window * compression_threshold`
   - Token 预估：`last_usage + input_length // 3`

3. **压缩保留策略**
   - 保留最近 `min_retain_rounds` 轮
   - 保留所有现有 summary 消息
   - 生成新的 summary 替换旧消息

### SummaryCompressor 关键场景

1. **超时降级**
   - ThreadPoolExecutor + future.result(timeout=...)
   - 超时后取消 future，关闭 executor
   - 返回 None 由 HistoryManager 处理

2. **消息序列化**
   - user: `[User]: ...`
   - assistant: `[Assistant]: ...`
   - tool: `[Tool:Name]: ...`（截断到 500 字符）
   - summary: `[Previous Summary]: ...`

### ContextBuilder 关键场景

1. **L1/L2 分离**
   - L1: system prompt + tools
   - L2: CODE_LAW.md（如有）
   - 两者都是 system role

2. **缓存失效**
   - CODE_LAW.md mtime 变化
   - MCP/Skills 提示更新
   - 缓存失效时重新构建

---

## 实施优先级

1. **test_history_manager.py** - 核心中的核心，最优先
2. **test_summary_compressor.py** - 依赖 mock LLM，独立测试
3. **test_context_builder.py** - 文件系统依赖较多

## 预估测试用例数量

| 测试文件 | 测试类 | 测试用例数 |
|---------|--------|-----------|
| test_history_manager.py | 7 | ~50 |
| test_summary_compressor.py | 5 | ~30 |
| test_context_builder.py | 6 | ~35 |
| **总计** | **18** | **~115** |
