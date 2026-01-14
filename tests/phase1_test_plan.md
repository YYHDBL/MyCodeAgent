# Phase 1 测试方案：缺失工具测试

## 1. test_list_files.py - LS 工具测试方案

### 测试类结构
```
TestListFilesTool(unittest.TestCase)
├── TestSuccess (成功场景)
├── TestPartial (部分成功场景)
├── TestError (错误场景)
├── TestSandbox (沙箱安全)
└── TestProtocol (协议合规性)
```

### 1.1 TestSuccess 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_success_list_current_dir | 列出当前目录 | entries 非空，status=success |
| test_success_list_nested_dir | 列出嵌套目录 | path_resolved 正确 |
| test_success_empty_directory | 列出空目录 | entries=[]，total=0 |
| test_success_default_ignore | 默认忽略 node_modules 等 | DEFAULT_IGNORE 生效 |
| test_success_include_hidden | include_hidden=true | 隐藏文件被列出 |
| test_success_custom_ignore | 自定义 ignore 模式 | ignore 参数生效 |
| test_success_sorting | 排序验证 | 目录在前，文件在后 |
| test_success_symlink_in_project | 项目内符号链接 | type="link" |
| test_success_offset_pagination | offset 分页 | 返回正确的分页结果 |
| test_success_limit_pagination | limit 分页 | 返回数量 <= limit |
| test_stats_counts | 统计信息验证 | dirs/files/links 正确 |

### 1.2 TestPartial 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_partial_truncated_large_dir | 大目录截断 | status=partial，truncated=true |
| test_partial_offset_exceeds_total | offset 超过总数 | 返回空列表 |
| test_partial_pagination_next_page | 分页下一页提示 | text 包含 offset 提示 |

### 1.3 TestError 测试用例

| 用例名称 | 错误码 | 触发条件 |
|---------|--------|----------|
| test_error_not_found | NOT_FOUND | 路径不存在 |
| test_error_is_file | INVALID_PARAM | 路径是文件 |
| test_error_offset_negative | INVALID_PARAM | offset < 0 |
| test_error_limit_zero | INVALID_PARAM | limit = 0 |
| test_error_limit_exceeds_max | INVALID_PARAM | limit > 200 |
| test_error_limit_negative | INVALID_PARAM | limit < 0 |
| test_error_ignore_not_list | INVALID_PARAM | ignore 不是数组 |
| test_error_access_denied_traversal | ACCESS_DENIED | ../ 路径遍历 |
| test_error_access_denied_absolute | ACCESS_DENIED | 绝对路径在项目外 |
| test_error_permission_denied | ACCESS_DENIED | 无权限目录 |

### 1.4 TestSandbox 测试用例

| 用例名称 | 描述 |
|---------|------|
| test_sandbox_block_traversal_parent | 阻止 ../../etc/passwd |
| test_sandbox_block_absolute_outside | 阻止 /etc/passwd |
| test_sandbox_allow_absolute_inside | 允许项目内绝对路径 |
| test_sandbox_symlink_outside_blocked | 符号链接指向项目外被阻止 |

---

## 2. test_glob_tool.py - Glob 工具测试方案

### 测试类结构
```
TestGlobTool(unittest.TestCase)
├── TestSuccess (成功场景)
├── TestPartial (部分成功/熔断)
├── TestError (错误场景)
├── TestPatternMatching (模式匹配)
├── TestCircuitBreaker (双熔断机制)
└── TestProtocol (协议合规性)
```

### 2.1 TestSuccess 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_success_exact_match | 精确文件名匹配 | paths 包含匹配文件 |
| test_success_wildcard_single | * 单层通配符 | *.py 匹配当前目录 |
| test_success_wildcard_recursive | ** 递归通配符 | **/*.py 匹配子目录 |
| test_success_extension_match | 扩展名匹配 | *.txt 匹配 |
| test_success_include_hidden | include_hidden=true | .hidden 文件被匹配 |
| test_success_include_ignored | include_ignored=true | node_modules 被遍历 |
| test_success_path_relative | 相对路径搜索 | path 参数生效 |
| test_success_limit | limit 限制 | 返回数量 <= limit |

### 2.2 TestPatternMatching 测试用例

| 用例名称 | 模式 | 验证点 |
|---------|------|--------|
| test_pattern_star_does_not_cross_dir | *.py | 不匹配 src/foo.py |
| test_pattern_double_star_crosses_dir | **/*.py | 匹配 src/foo.py |
| test_pattern_question_mark | file?.txt | 匹配 file1.txt，不匹配 file10.txt |
| test_pattern_bracket | file[0-9].txt | 匹配 file0.txt-file9.txt |
| test_pattern_leading_double_slash | **/foo.py | 可匹配 0 层或更多 |
| test_pattern_dot_slash_prefix | ./foo.py | 前缀被正确剥离 |

### 2.3 TestCircuitBreaker 双熔断测试

| 用例名称 | 熔断类型 | 触发条件 | 验证点 |
|---------|---------|----------|--------|
| test_circuit_count_limit | count_limit | 访问条目 > 20000 | aborted_reason="count_limit" |
| test_circuit_time_limit | time_limit | 耗时 > 2000ms | aborted_reason="time_limit" |
| test_circuit_no_results_timeout | 无结果超时 | 无结果且超时 | status=error，code=TIMEOUT |
| test_circuit_partial_timeout | 有结果超时 | 有结果且超时 | status=partial |
| test_circuit_max_results_limit | 最大结果限制 | 匹配数 > limit | truncated=true |

### 2.4 TestError 测试用例

| 用例名称 | 错误码 | 触发条件 |
|---------|--------|----------|
| test_error_missing_pattern | INVALID_PARAM | pattern 缺失 |
| test_error_limit_too_small | INVALID_PARAM | limit < 1 |
| test_error_limit_too_large | INVALID_PARAM | limit > 200 |
| test_error_not_found | NOT_FOUND | 搜索路径不存在 |
| test_error_not_directory | INVALID_PARAM | 搜索路径不是目录 |
| test_error_access_denied | ACCESS_DENIED | 路径在项目外 |

---

## 3. test_grep_tool.py - Grep 工具测试方案

### 测试类结构
```
TestGrepTool(unittest.TestCase)
├── TestSuccessRipgrep (ripgrep 模式)
├── TestFallbackPython (Python 回退模式)
├── TestPartial (部分成功场景)
├── TestError (错误场景)
├── TestSearchOptions (搜索选项)
└── TestProtocol (协议合规性)
```

### 3.1 TestSuccessRipgrep 测试用例

| 用例名称 | 描述 | 验证点 |
|---------|------|--------|
| test_success_simple_pattern | 简单模式搜索 | matches 非空 |
| test_success_case_sensitive | case_sensitive=true | 区分大小写生效 |
| test_success_case_insensitive | case_sensitive=false (默认) | 不区分大小写 |
| test_success_include_glob | include 过滤 | 只搜索匹配文件 |
| test_success_regex_pattern | 正则表达式 | 支持复杂正则 |
| test_success_multiple_matches | 多文件匹配 | 返回多个匹配项 |
| test_sorted_by_mtime | 按 mtime 降序排序 | 结果按修改时间排序 |

### 3.2 TestFallbackPython 测试用例

| 用例名称 | 触发条件 | 验证点 |
|---------|----------|--------|
| test_fallback_rg_not_found | ripgrep 不可用 | data.fallback_used=true |
| test_fallback_rg_failed | ripgrep 失败 | data.fallback_reason="rg_failed" |
| test_fallback_search_works | Python 回退搜索 | 返回正确结果 |
| test_fallback_timeout | Python 搜索超时 | aborted_reason="timeout" |

### 3.3 TestPartial 测试用例

| 用例名称 | 触发条件 | 验证点 |
|---------|----------|--------|
| test_partial_max_results_truncated | 匹配数 > 100 | status=partial，truncated=true |
| test_partial_timeout_with_results | 搜索超时但有结果 | status=partial |
| test_partial_fallback_used | 使用回退模式 | status=partial |

### 3.4 TestError 测试用例

| 用例名称 | 错误码 | 触发条件 |
|---------|--------|----------|
| test_error_missing_pattern | INVALID_PARAM | pattern 缺失/空 |
| test_error_invalid_regex | INVALID_PARAM | 无效正则表达式 |
| test_error_include_not_string | INVALID_PARAM | include 不是字符串 |
| test_error_case_sensitive_not_bool | INVALID_PARAM | case_sensitive 不是布尔 |
| test_error_not_found | NOT_FOUND | 搜索路径不存在 |
| test_error_not_directory | INVALID_PARAM | 搜索路径不是目录 |
| test_error_access_denied | ACCESS_DENIED | 路径在项目外 |
| test_error_timeout_no_results | TIMEOUT | 超时且无结果 |

### 3.5 TestSearchOptions 测试用例

| 用例名称 | 选项 | 验证点 |
|---------|------|--------|
| test_option_include_py | include="*.py" | 只搜索 .py 文件 |
| test_option_include_multiple | include="**/*.{js,ts}" | 支持多扩展名 |
| test_option_case_sensitive_match | "Hello" 只匹配大写 | 大小写敏感生效 |
| test_option_case_insensitive_match | "hello" 匹配 "Hello" | 大小写不敏感生效 |

---

## 测试辅助函数

### 共享 Fixtures
```python
@pytest.fixture
def temp_project():
    """创建临时测试项目"""
    # 包含预设文件结构：
    # - src/main.py
    # - src/utils.py
    # - tests/test_main.py
    # - node_modules/ignored.js
    # - .hidden_file.txt
    # - README.md
    # - link_to_src -> src/ (symlink)
```

### 协议验证辅助
```python
def assert_protocol_compliance(response, tool_type):
    """验证通用工具响应协议"""
    # 验证 status ∈ {success, partial, error}
    # 验证必需字段存在
    # 验证 stats.time_ms 存在
    # 验证 context.cwd/params_input 存在
```

---

## 实施优先级

1. **test_list_files.py** - 最简单，先完成
2. **test_glob_tool.py** - 中等复杂度，双熔断机制是重点
3. **test_grep_tool.py** - 最复杂，需要处理 ripgrep/回退两种模式

## 预估测试用例数量

| 测试文件 | 测试类 | 测试用例数 |
|---------|--------|-----------|
| test_list_files.py | 5 | ~35 |
| test_glob_tool.py | 6 | ~40 |
| test_grep_tool.py | 6 | ~45 |
| **总计** | **17** | **~120** |
