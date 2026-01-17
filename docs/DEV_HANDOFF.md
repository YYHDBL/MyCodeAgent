# 项目现状与交接说明

## 项目概况（当前结构）
- `core/`：基础能力（`Agent` 抽象基类、`HelloAgentsLLM`、`Message`、`Config`、异常体系）。
- `agents/`：Agent 实现（`CodeAgent`）。
- `tools/`：工具系统
  - `base.py`：`Tool` 抽象基类 + `ToolParameter` 数据模型 + 响应协议支持。
  - `registry.py`：`ToolRegistry` 工具注册表（支持 Tool 对象和函数注册）。
- `tools/builtin/`：内置工具
  - `list_files.py`：`ListFilesTool` (LS) - 目录浏览工具。
  - `search_files_by_name.py`：`SearchFilesByNameTool` (Glob) - 文件搜索工具。
  - `search_code.py`：`GrepTool` (Grep) - 代码内容搜索工具。
  - `read_file.py`：`ReadTool` (Read) - 文件读取工具。
  - `write_file.py`：`WriteTool` (Write) - 文件写入工具。
  - `edit_file.py`：`EditTool` (Edit) - 单点编辑工具。
  - `edit_file_multi.py`：`MultiEditTool` (MultiEdit) - 多点编辑工具。
  - `todo_write.py`：`TodoWriteTool` (TodoWrite) - 任务清单管理工具。
  - `skill.py`：`SkillTool` (Skill) - 加载项目内技能指令。
  - `task.py`：`TaskTool` (Task) - 子代理委派（MVP）。
  - `bash.py`：`BashTool` (Bash) - 命令执行工具。
- `scripts/`：交互脚本（`chat_test_agent.py`）。
- `prompts/tools_prompts/`：工具提示词（`list_file_prompt.py`、`glob_prompt.py`、`grep_prompt.py`、`read_prompt.py`、`write_prompt.py`、`edit_prompt.py`、`multi_edit_prompt.py`、`todo_write_prompt.py`、`skill_prompt.py`、`task_prompt.py`、`bash_prompt.py`）。
- `docs/`：文档（`DEV_HANDOFF.md`、`通用工具响应协议.md`）。

## 当前进度摘要
1. **Agent 运行链路打通**
   - `CodeAgent` 内置 ReAct 循环，能展示 Thought / Action / Observation。
   - `chat_test_agent.py` 可打印 `--show-raw` 原始模型响应。

2. **工具体系完善**
   - **LS（list_files）**：支持安全目录浏览、分页、隐藏文件控制、软链安全展示。
   - **Glob（tool name: Glob）**：支持 glob 模式搜索、双熔断（访问数+时间）、确定性结果。
   - **Grep（tool name: Grep）**：支持正则内容搜索、rg 优先、mtime 排序与超时保护。
   - 所有工具统一由框架注入 `project_root` 与 `working_dir`，确保沙箱一致性。
   - 工具通过 `ToolRegistry` 统一管理，支持 Tool 对象和函数两种注册方式。

3. **响应协议重构**
   - 所有内置工具已遵循《通用工具响应协议》（`docs/通用工具响应协议.md`）。
   - 统一顶层字段：`status`、`data`、`text`、`error`（仅 error 时存在）、`stats`、`context`。
  - 框架层统一要求工具直接返回协议格式。

4. **关键 Bug 修复**
   - Glob：匹配锚点改为相对 `path`；修复 `**/*.md` 根目录匹配问题；`project_root` 强制注入。
   - LS：安全过滤、分页、软链安全展示与 ignore 行为已对齐设计说明。

## 关键使用方式
- 运行交互式测试：
  ```bash
  python scripts/chat_test_agent.py --show-raw
  ```

- Glob 查询建议（pattern 永远相对 path）：
  - `{"pattern": "*.py", "path": "core"}`
  - `{"pattern": "**/*.py", "path": "core"}`

---

# 工具开发文档（交接用）

## 工具系统架构

### 响应协议
所有工具返回必须遵循《通用工具响应协议》（详见 `docs/通用工具响应协议.md`）。

**顶层字段白名单**（禁止添加自定义顶层字段）：
- `status`: `"success"` | `"partial"` | `"error"`
- `data`: 核心载荷（对象，不允许 null）
- `text`: 给 LLM 阅读的格式化摘要
- `error`: 结构化错误（仅 `status="error"` 时存在）
- `stats`: 运行统计（必含 `time_ms`）
- `context`: 上下文信息（必含 `cwd`、`params_input`）

**状态判定规则**：
| 状态 | 条件 |
|------|------|
| `success` | 任务完全按预期完成，无截断、无回退、无错误 |
| `partial` | 结果可用但有折扣：截断(truncated)、回退(fallback)、干运行(dry-run)、部分失败 |
| `error` | 无法提供有效结果：权限不足、参数非法、超时且无结果 |

### Tool 基类（`tools/base.py`）
所有工具继承自 `Tool` 抽象基类，该基类提供：

**枚举类型**：
- `ToolStatus`：`SUCCESS` | `PARTIAL` | `ERROR`（序列化为小写字符串）
- `ErrorCode`：`NOT_FOUND` | `ACCESS_DENIED` | `PERMISSION_DENIED` | `INVALID_PARAM` | `TIMEOUT` | `INTERNAL_ERROR` | `EXECUTION_ERROR` | `IS_DIRECTORY` | `BINARY_FILE` | `CONFLICT`

**初始化参数**：
- `name`：工具名称
- `description`：工具描述
- `project_root`：项目根目录（沙箱边界）
- `working_dir`：当前工作目录（用于解析相对路径）

**抽象方法**：
- `run(parameters: Dict[str, Any]) -> str`：执行工具逻辑，返回 JSON 字符串。
- `get_parameters() -> List[ToolParameter]`：返回工具参数定义。

**响应辅助方法**：
- `get_cwd_rel() -> str`：获取相对项目根的工作目录路径。
- `create_success_response(data, text, stats, context) -> str`：创建成功响应。
- `create_partial_response(data, text, stats, context) -> str`：创建部分成功响应。
- `create_error_response(code, message, stats, context, data) -> str`：创建错误响应。
- `_build_response(status, data, text, stats, context, error) -> str`：内部构建方法。

**工具方法**：
- `validate_parameters(parameters: Dict[str, Any]) -> bool`：校验参数完整性。
- `to_dict() -> Dict[str, Any]`：序列化为字典（name、description、parameters）。

### ToolRegistry（`tools/registry.py`）
工具注册表支持两种注册方式：
1. **Tool 对象注册**（推荐）：`register_tool(tool: Tool)`
   - 提供完整的参数定义与验证能力。
   - 支持结构化参数传递（字典格式）。
2. **函数直接注册**（简便）：`register_function(name, description, func)`
   - 适用于简单工具，函数签名为 `func(input: str) -> str`。

**主要 API**：
- `execute_tool(name, input_text) -> str`：统一执行入口（含旧格式适配）。
- `get_tools_description() -> str`：生成工具列表描述（用于提示词）。
- `list_tools() -> List[str]`：列出所有工具名称。
- `get_all_tools() -> List[Tool]`：获取所有 Tool 对象。

全局注册表可通过 `tools.registry.global_registry` 访问。

### 旧格式适配器
旧格式适配器已移除，所有工具必须直接返回《通用工具响应协议》格式。

---

## 1) LS 工具（list_files）
**文件**：`tools/builtin/list_files.py`

### 设计目标
- 安全列目录（沙箱内）。
- 支持分页、隐藏文件控制、黑名单过滤、软链安全显示。
- 返回符合《通用工具响应协议》的结构化 JSON。

### 参数
- `path`: 要列出的目录路径（相对项目根或项目内绝对路径）。默认 `.`。
- `offset`: 分页起始索引，默认 `0`。
- `limit`: 最大返回条目数，默认 `100`，最大 `200`。
- `include_hidden`: 是否显示隐藏文件（`.` 开头）。默认 `false`。
- `ignore`: glob 过滤列表（支持 basename 与相对路径）。

### 关键实现逻辑
- **初始化**：必须传入 `project_root`（沙箱根目录）与 `working_dir`（用于解析相对路径）。
- **沙箱校验**：使用 `target.relative_to(project_root)` 确保路径在项目范围内。
- **过滤策略**：
  - `include_hidden=False` 时过滤隐藏文件（`.` 开头）与 `DEFAULT_IGNORE` 列表。
  - `DEFAULT_IGNORE` 包含：`node_modules`, `__pycache__`, `.git`, `.vscode`, `build`, `dist`, `venv` 等。
- **ignore 匹配**：同时匹配相对项目根的路径（`rel_root`）与相对目标目录的路径（`rel_target`）；支持 `**/` 递归模式。
- **软链处理**：
  - symlink 显示为 `name@` 或 `name@/`（目录）。
  - 若链接指向沙箱外，则显示 `-> <Outside Sandbox>`；若损坏显示 `-> <Broken Link>`。
- **排序**：目录优先，同类型按名称字母排序。

### 输出结构（JSON）
```json
{
  "status": "partial",
  "data": {
    "entries": [
      {"path": "core/", "type": "dir"},
      {"path": "agents/", "type": "dir"},
      {"path": "README.md", "type": "file"},
      {"path": "config@", "type": "link"}
    ],
    "truncated": true
  },
  "text": "Listed 4 entries in '.' (truncated from 150 total). Use 'offset' to paginate.",
  "stats": {
    "time_ms": 12,
    "total": 150,
    "dirs": 5,
    "files": 143,
    "links": 2
  },
  "context": {
    "cwd": ".",
    "params_input": {"path": ".", "limit": 4},
    "path_resolved": "."
  }
}
```

### 状态判定
- `success`：无截断。
- `partial`：`data.truncated = true`。
- `error`：路径不存在、越权访问等。

---

## 2) Glob 工具（tool name: Glob）
**文件**：`tools/builtin/search_files_by_name.py`

### 设计目标
- 全局按 glob 模式搜索文件。
- 双熔断：最大访问数 & 时间限制。
- 结果确定性（遍历排序）。
- 返回符合《通用工具响应协议》的结构化 JSON。

### 参数
- `pattern`（必填）：相对 `path` 的 glob 模式（如 `**/*.py`）。
- `path`：搜索起点（相对项目根）。默认 `.`。
- `limit`：最大返回条数，默认 `50`，最大 `200`。
- `include_hidden`：是否遍历隐藏目录/文件。
- `include_ignored`：是否进入黑名单目录。

### 关键实现逻辑
- **初始化**：必须传入 `project_root`（由框架统一注入），避免工具自我猜测根目录。
- **匹配锚点**：`pattern` 始终相对于 `path` 参数（搜索起点）。
- **路径处理**：
  - **匹配基准路径**：`rel_match_path` 相对于搜索起点 `root`（即 `path` 参数）。
  - **展示路径**：`rel_display_path` 相对于项目根 `project_root`（便于后续编辑/读取）。
- **`**/` 兼容**：当 pattern 以 `**/` 开头时，额外做零层匹配兜底（例如 `**/*.md` 能匹配根目录文件）。
- **遍历策略**：
  - 使用 `os.walk` 递归遍历，确定性排序（dirs 和 files 均按字母排序）。
  - 通过原地修改 `dirs` 列表实现剪枝（避免遍历不需要的目录）。
  - 根据 `include_hidden` 和 `include_ignored` 控制剪枝行为。
- **熔断机制**：
  - `MAX_VISITED_ENTRIES = 20_000`：最大访问条目数。
  - `MAX_DURATION_MS = 2_000`：最大搜索时间（2秒）。
  - 达到任一限制时提前终止并在 `data.aborted_reason` 中说明原因。
- **输出路径**：返回路径相对项目根，便于后续编辑/读取。

### 输出结构（JSON）
```json
{
  "status": "success",
  "data": {
    "paths": ["core/agent.py", "core/llm.py", "agents/codeAgent.py"],
    "truncated": false,
    "aborted_reason": null
  },
  "text": "Found 3 files matching '**/*.py' in 'core'.\n\ncore/agent.py\ncore/llm.py\nagents/codeAgent.py",
  "stats": {
    "time_ms": 48,
    "matched": 3,
    "visited": 120
  },
  "context": {
    "cwd": ".",
    "params_input": {"pattern": "**/*.py", "path": "."},
    "path_resolved": "."
  }
}
```

### 状态判定
- `success`：无截断、无熔断。
- `partial`：`data.truncated = true` 或有 `data.aborted_reason` 但仍有结果。
- `error`：熔断且无结果（`aborted_reason` 存在且 `paths` 为空）、参数非法等。

### 工具提示词
- `prompts/tools_prompts/glob_prompt.py`
- 已明确：pattern 永远相对 path。

---

## 3) Grep 工具（tool name: Grep）
**文件**：`tools/builtin/search_code.py`

### 设计目标
- 正则内容搜索，优先使用 ripgrep（rg），不可用时 Python fallback。
- 输出按文件修改时间（mtime）倒序排列，优先展示活跃文件。
- 超时保护（2 秒），避免正则或大文件拖垮执行时间。
- 返回符合《通用工具响应协议》的结构化 JSON。

### 参数
- `pattern`（必填）：正则模式（如 `class\\s+User`）。
- `path`：搜索起点（相对项目根）。默认 `.`。
- `include`：glob 过滤（如 `*.ts` 或 `src/**/*.py`）。推荐使用。
- `case_sensitive`：是否区分大小写，默认 `false`。

### 关键实现逻辑
- **搜索策略**：优先 `rg --json`，失败或缺失时使用 Python 遍历。
- **路径一致性**：输出路径统一相对 `project_root`。
- **排序**：收集结果后按 `mtime` 倒序排序。
- **截断**：超过 `MAX_RESULTS=100` 会截断并标记 `data.truncated`。
- **超时**：超时返回已有结果，并标记在 `data` 或状态中。
- **rg 状态**：rg 不可用时记录 `data.fallback_used = true` 和 `data.fallback_reason`。

### 输出结构（JSON）
```json
{
  "status": "partial",
  "data": {
    "matches": [
      {"file": "src/auth/User.ts", "line": 42, "text": "export class User {"},
      {"file": "src/models/User.py", "line": 15, "text": "class User(Base):"}
    ],
    "truncated": false,
    "fallback_used": true,
    "fallback_reason": "rg_not_found"
  },
  "text": "Found 2 matches for 'class.*User' in 2 files (sorted by mtime desc). Using Python fallback (ripgrep not available).\n\nsrc/auth/User.ts:42: export class User {\nsrc/models/User.py:15: class User(Base):",
  "stats": {
    "time_ms": 156,
    "matched_files": 2,
    "matched_lines": 2
  },
  "context": {
    "cwd": ".",
    "params_input": {"pattern": "class.*User", "path": "."},
    "path_resolved": ".",
    "sorted_by": "mtime_desc"
  }
}
```

### 状态判定
- `success`：无截断、无回退、无超时。
- `partial`：使用了 fallback（`fallback_used = true`）或截断（`truncated = true`）。
- `error`：超时且无结果、正则语法错误等。

### 工具提示词
- `prompts/tools_prompts/grep_prompt.py`

---

# 后续建议
- **统一工具注册**：封装 `register_builtin_tools(project_root)` 函数，简化工具初始化流程。
- **测试覆盖**：为 LS/Glob/Grep 增加单元测试用例，覆盖：
  - 路径解析与沙箱逃逸防护。
  - 边界条件（空目录、大文件列表、熔断触发等）。
  - pattern 匹配逻辑（特别是 `**/` 零层匹配）。
  - 响应协议字段完整性验证。
  - 状态判定逻辑（success/partial/error）。
- **文档与提示词**：保持 `prompts/tools_prompts/` 中的提示词与代码实现同步更新。
- **协议一致性**：
  - 保证所有工具始终输出《通用工具响应协议》。
- **扩展性**：考虑添加更高层的工程工具（如 lint/format/test/诊断类），新工具必须遵循《通用工具响应协议》。
