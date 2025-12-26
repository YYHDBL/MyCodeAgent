# 项目现状与交接说明

## 项目概况（当前结构）
- `core/`：基础能力（`Agent` 抽象基类、`HelloAgentsLLM`、`Message`、`Config`、异常体系）。
- `agents/`：Agent 实现（`TestAgent`、`CodeAgent`）。
- `agentEngines/`：推理引擎（`ReActEngine`）。
- `tools/`：工具系统
  - `base.py`：`Tool` 抽象基类 + `ToolParameter` 数据模型。
  - `registry.py`：`ToolRegistry` 工具注册表（支持 Tool 对象和函数注册）。
- `tools/builtin/`：内置工具
  - `list_files.py`：`ListFilesTool` (LS) - 目录浏览工具。
  - `search_files_by_name.py`：`SearchFilesByNameTool` (Glob) - 文件搜索工具。
  - `search_code.py`：`GrepTool` (search_code) - 代码内容搜索工具。
  - `calculator.py`：`CalculatorTool` - 数学计算工具。
- `scripts/`：交互脚本（`chat_test_agent.py`）。
- `prompts/tools_prompts/`：工具提示词（`list_file_prompt.md`、`glob_prompt.md`、`grep_prompt.md`）。

## 当前进度摘要
1. **Agent 运行链路打通**
   - `TestAgent`/`CodeAgent` 已接入 `ReActEngine`，能展示 Thought / Action / Observation。
   - `chat_test_agent.py` 支持选择 `--agent test|code` 并可打印 `--show-raw` 原始模型响应。

2. **工具体系完善**
   - **LS（list_files）**：支持安全目录浏览、分页、隐藏文件控制、软链安全展示。
   - **Glob（search_files_by_name）**：支持 glob 模式搜索、双熔断（访问数+时间）、确定性结果。
   - **Grep（search_code）**：支持正则内容搜索、rg 优先、mtime 排序与超时保护。
   - **Calculator（python_calculator）**：支持安全的数学表达式计算，使用 AST 解析。
   - 所有工具统一由框架注入 `project_root`，避免各自猜测根目录导致沙箱不一致。
   - 工具通过 `ToolRegistry` 统一管理，支持 Tool 对象和函数两种注册方式。

3. **关键 Bug 修复**
   - Glob：匹配锚点改为相对 `path`；修复 `**/*.md` 根目录匹配问题；`project_root` 强制注入。
   - LS：安全过滤、分页、软链安全展示与 ignore 行为已对齐设计说明。

4. **输出格式**
   - LS / Glob / Grep 均返回 JSON 结构化数据（`context/stats/flags/text`），便于框架解析。

## 关键使用方式
- 运行交互式测试：
  ```bash
  python scripts/chat_test_agent.py --agent code --show-raw
  ```

- Glob 查询建议（pattern 永远相对 path）：
  - `Glob[{"pattern": "*.py", "path": "core"}]`
  - `Glob[{"pattern": "**/*.py", "path": "core"}]`

---

# 工具开发文档（交接用）

## 工具系统架构

### Tool 基类（`tools/base.py`）
所有工具继承自 `Tool` 抽象基类，该基类提供：
- **`ToolParameter`**：使用 Pydantic 定义工具参数（name, type, description, required, default）。
- **抽象方法**：
  - `run(parameters: Dict[str, Any]) -> str`：执行工具逻辑。
  - `get_parameters() -> List[ToolParameter]`：返回工具参数定义。
- **工具方法**：
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
- `execute_tool(name, input_text) -> str`：统一执行入口。
- `get_tools_description() -> str`：生成工具列表描述（用于提示词）。
- `list_tools() -> List[str]`：列出所有工具名称。
- `get_all_tools() -> List[Tool]`：获取所有 Tool 对象。

全局注册表可通过 `tools.registry.global_registry` 访问。

---

## 1) LS 工具（list_files）
**文件**：`tools/builtin/list_files.py`

### 设计目标
- 安全列目录（沙箱内）。
- 支持分页、隐藏文件控制、黑名单过滤、软链安全显示。
- 返回结构化 JSON + 可读文本（`text` 字段）。

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
- **参数结构**：通过 `get_parameters()` 返回标准 `ToolParameter` 列表。

### 输出结构（JSON）
```json
{
  "items": ["core/", "agents/"],
  "context": {"root_resolved": "."},
  "stats": {"total": 10, "dirs": 3, "files": 6, "links": 1, "start": 0, "end": 10},
  "flags": {"truncated": false},
  "warnings": [],
  "text": "Directory: .\n[Summary: ...]\n\ncore/\nagents/\n..."
}
```

### 注意点
- 截断分页时 `warnings` 包含提示（引导使用 `offset`）。
- `text` 字段仍提供人类可读输出。

---

## 2) Glob 工具（search_files_by_name）
**文件**：`tools/builtin/search_files_by_name.py`

### 设计目标
- 全局按 glob 模式搜索文件。
- 双熔断：最大访问数 & 时间限制。
- 结果确定性（遍历排序）。
- 输出结构化 JSON + 可读文本。

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
  - 达到任一限制时提前终止并在 `flags.aborted_reason` 中说明原因。
- **输出路径**：返回路径相对项目根，便于后续编辑/读取。
- **参数结构**：通过 `get_parameters()` 返回标准 `ToolParameter` 列表。

### 输出结构（JSON）
```json
{
  "matches": ["core/agent.py", "core/llm.py"],
  "context": {
    "root_resolved": "core",
    "pattern_normalized": "**/*.py"
  },
  "stats": {
    "matched": 2,
    "visited": 120,
    "time_ms": 48
  },
  "flags": {
    "truncated": false,
    "aborted_reason": null
  },
  "text": "Search Pattern: **/*.py (in 'core')\n[Stats: Found 2 matches. Scanned 120 items in 48ms.]\n\ncore/agent.py\ncore/llm.py"
}
```

### 工具提示词
- `prompts/tools_prompts/glob_prompt.md`
- 已明确：pattern 永远相对 path。

---

## 3) Calculator 工具（python_calculator）
**文件**：`tools/builtin/calculator.py`

### 设计目标
- 安全执行数学计算表达式。
- 支持基本运算符和常用数学函数。
- 使用 AST 解析确保安全性（避免任意代码执行）。

### 参数
- `input` 或 `expression`（必填）：要计算的数学表达式字符串。

### 支持的操作
- **运算符**：`+`, `-`, `*`, `/`, `**`（幂）, `^`（异或）, `-`（负号）
- **函数**：`abs`, `round`, `max`, `min`, `sum`, `sqrt`, `sin`, `cos`, `tan`, `log`, `exp`

---

## 4) Grep 工具（search_code）
**文件**：`tools/builtin/search_code.py`

### 设计目标
- 正则内容搜索，优先使用 ripgrep（rg），不可用时 Python fallback。
- 输出按文件修改时间（mtime）倒序排列，优先展示活跃文件。
- 超时保护（2 秒），避免正则或大文件拖垮执行时间。
- 返回结构化 JSON + 可读文本（`text` 字段）。

### 参数
- `pattern`（必填）：正则模式（如 `class\\s+User`）。
- `path`：搜索起点（相对项目根）。默认 `.`。
- `include`：glob 过滤（如 `*.ts` 或 `src/**/*.py`）。推荐使用。
- `case_sensitive`：是否区分大小写，默认 `false`。

### 关键实现逻辑
- **搜索策略**：优先 `rg --json`，失败或缺失时使用 Python 遍历。
- **路径一致性**：输出路径统一相对 `project_root`。
- **排序**：收集结果后按 `mtime` 倒序排序。
- **截断**：超过 `MAX_RESULTS=100` 会截断并标记 `flags.truncated`。
- **超时**：超时返回已有结果，并标记 `flags.aborted_reason = "timeout"`。
- **rg 状态**：rg 不可用时 `aborted_reason = "rg_not_found"`；rg 执行失败时 `aborted_reason = "rg_failed"`。

### 输出结构（JSON）
```json
{
  "matches": [
    {"file": "src/auth/User.ts", "line": 42, "text": "export class User {"}
  ],
  "context": {"pattern": "class\\\\s+User", "root_resolved": "src", "sorted_by": "mtime_desc"},
  "stats": {"matched_files": 1, "matched_lines": 1, "time_ms": 45},
  "flags": {"truncated": false, "aborted_reason": null},
  "text": "Search Pattern: class\\\\s+User (in 'src')\\n[Stats: Found 1 matches in 1 files. Sorted by mtime desc. Took 45ms.]\\n\\nsrc/auth/User.ts:42: export class User {"
}
```
- **常量**：`pi`, `e`

### 关键实现逻辑
- **AST 解析**：使用 `ast.parse(expression, mode='eval')` 解析表达式。
- **递归求值**：`_eval_node` 方法递归处理 AST 节点。
- **白名单机制**：仅允许预定义的操作符和函数，确保安全。
- **错误处理**：捕获所有异常并返回友好错误信息。

### 示例
- `2+3*4` → `14`
- `sqrt(16)` → `4.0`
- `sin(pi/2)` → `1.0`

---

# 后续建议
- **统一工具注册**：封装 `register_builtin_tools(project_root)` 函数，简化工具初始化流程。
- **测试覆盖**：为 LS/Glob/Calculator 增加单元测试用例，覆盖：
  - 路径解析与沙箱逃逸防护。
  - 边界条件（空目录、大文件列表、熔断触发等）。
  - pattern 匹配逻辑（特别是 `**/` 零层匹配）。
  - Calculator 的表达式解析与错误处理。
- **文档与提示词**：保持 `prompts/tools_prompts/` 中的提示词与代码实现同步更新。
- **扩展性**：考虑添加更多内置工具（如 `read_file`、`write_file`、`grep` 等）。
