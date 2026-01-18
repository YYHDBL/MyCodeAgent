# MyCodeAgent 项目概览

## 项目目标

MyCodeAgent 是一个学习/实验性质的 ReAct 代码助手项目，专注于实践以下核心技术：
- **工具协议**（Tool Protocols）
- **上下文工程**（Context Engineering）
- **技能系统**（Skill System）
- **子代理机制**（Subagent Mechanism）

该项目旨在构建一个能够理解、分析和操作代码的智能助手，通过 ReAct（推理-行动）循环与用户交互。

## 核心模块

### 1. Agent 核心架构

**基础抽象层**
- `core/agent.py` - `Agent` 抽象基类，定义了 agent 的基本接口
- `core/llm.py` - `HelloAgentsLLM` 包装器，统一不同 LLM 提供商的接口
- `core/message.py` - `Message` 数据模型，表示对话消息
- `core/config.py` - 配置管理，从环境变量读取配置

**主实现**
- `agents/codeAgent.py` - `CodeAgent` 主实现，包含完整的 ReAct 循环逻辑（约 805 行）
  - 集成了工具注册、历史管理、上下文构建等功能
  - 支持子代理委托和技能加载

### 2. 上下文工程（Context Engine）

位于 `core/context_engine/` 目录，采用 **Message List** 累积模式：

**分层结构**
- **L1**: 系统提示词 + 工具描述（`prompts/agents_prompts/L1_system_prompt.py`）
- **L2**: CODE_LAW.md（如果存在）
- **L3**: 来自 `HistoryManager` 的历史消息（user/assistant/tool/summary）
- **L4**: 当前用户输入（追加到历史）

**核心组件**
- `context_builder.py` - 构建用于 LLM 调用的消息列表
- `history_manager.py` - 管理会话历史，支持压缩
- `input_preprocessor.py` - 预处理用户输入（如 @file 引用强制 Read）
- `observation_truncator.py` - 截断大型工具输出
- `summary_compressor.py` - 当上下文窗口超出时生成摘要
- `tool_result_compressor.py` - 压缩工具结果
- `trace_logger.py` - 记录执行追踪到 `eval/traces/`
- `trace_sanitizer.py` - 清理追踪数据中的敏感信息

### 3. 工具系统（Tool System）

**统一协议**
所有工具遵循 **Universal Tool Response Protocol**（见 `docs/通用工具响应协议.md`）：

必需响应字段：
- `status`: `"success"` | `"partial"` | `"error"`
- `data`: 核心载荷（对象）
- `text`: LLM 的自然语言摘要
- `error`: 结构化错误（仅当 `status="error"` 时）
- `stats`: 运行时指标（必须包含 `time_ms`）
- `context`: 执行上下文（必须包含 `cwd`, `params_input`）

**工具注册中心**
- `tools/registry.py` - 中央工具注册表，支持 Write/Edit 工具的乐观锁自动注入

**内置工具**（位于 `tools/builtin/`）
| 工具 | 文件 | 功能 |
|------|------|------|
| LS | `list_files.py` | 目录列表，支持分页 |
| Glob | `search_files_by_name.py` | Glob 模式匹配，双熔断器 |
| Grep | `search_code.py` | 正则内容搜索，优先使用 ripgrep |
| Read | `read_file.py` | 文件读取，支持行数限制 |
| Write | `write_file.py` | 文件写入，乐观锁保护 |
| Edit | `edit_file.py` | 单点编辑 |
| MultiEdit | `edit_file_multi.py` | 多点编辑 |
| TodoWrite | `todo_write.py` | 任务列表管理 |
| Skill | `skill.py` | 从 `skills/**/SKILL.md` 加载技能 |
| Task | `task.py` | 子代理委托（general/explore/plan/summary） |
| Bash | `bash.py` | Shell 命令执行 |
| AskUser | `ask_user.py` | 向用户提问获取信息 |

**工具提示词**
- `prompts/tools_prompts/` - 各工具的提示词模板（Python 字符串常量）

### 4. 技能系统（Skill System）

**技能格式**
技能存储在 `skills/<skill-name>/SKILL.md`，使用 frontmatter 元数据：

```markdown
---
name: code-review
description: Review code quality and risks
---
# Code Review
...
$ARGUMENTS
```

**技能加载器**
- `core/skills/skill_loader.py` - 扫描并缓存项目本地技能
  - 支持技能名称验证（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）
  - 自动检测文件变化并刷新缓存
  - 解析 frontmatter 元数据

### 5. 子代理机制（Subagent）

**子代理类型**
- `general` - 复杂执行或专注的子工作
- `explore` - 代码库扫描、入口点、文件发现
- `plan` - 实现步骤、依赖项、风险
- `summary` - 压缩长输出或多文件发现

**提示词模板**（位于 `prompts/agents_prompts/`）
- `L1_system_prompt.py` - 主系统提示词
- `subagent_general_prompt.py` - 通用子代理提示词
- `subagent_explore_prompt.py` - 探索子代理提示词
- `subagent_plan_prompt.py` - 规划子代理提示词
- `subagent_summary_prompt.py` - 摘要子代理提示词
- `init_prompt.py` - 初始化提示词（CODE_LAW 生成）
- `summary_prompt.py` - 摘要生成提示词

**实现**
- `tools/builtin/task.py` - Task 工具，启动子代理会话
- 子代理使用受限工具集，返回单个最终结果

### 6. MCP 集成（Model Context Protocol）

**配置文件**
- `mcp_servers.json` - MCP 服务器注册

**当前配置的 MCP 服务器**
```json
{
  "mcpServers": {
    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"] },
    "context7": { "command": "npx", "args": ["-y", "@upstash/context7-mcp", "--api-key", "${CTX7_API_KEY}"] },
    "tavily-mcp": { "command": "npx", "args": ["-y", "tavily-mcp@0.1.4"] }
  }
}
```

**MCP 工具加载器**
- `tools/mcp/loader.py` - 注册 MCP 服务器并格式化工具提示词

### 7. 评估系统（Evaluation）

**评估运行器**
- `eval/run_eval.py` - 评估套件运行器

**评估套件**
- `eval/tasks/base.json` - 基础评估任务
- `eval/tasks/long_horizon.json` - 长期任务评估

**测试固件**
- `eval/fixtures/py/` - Python 测试固件
  - `buggy_math.py` - 有缺陷的数学函数
  - `path_utils.py` - 路径工具
  - `test_buggy_math.py` - 测试文件
  - `test_path_utils.py` - 测试文件
- `eval/fixtures/ts/` - TypeScript 测试固件
  - `source.py` - 源代码

**追踪输出**
- `eval/traces/` - 执行追踪 JSONL 文件，用于工具使用检查

## 主要功能

### 1. 交互式代码助手
- 通过 CLI 与用户交互（`scripts/chat_test_agent.py`）
- 支持 Rich UI 增强显示
- 支持命令历史（FileHistory）
- 支持调试模式（`--show-raw` 显示原始 LLM 响应）

### 2. 文件操作
- 列出目录内容（LS）
- 按名称搜索文件（Glob）
- 按内容搜索代码（Grep）
- 读取文件内容（Read）
- 创建/覆盖文件（Write）
- 单点编辑（Edit）
- 多点编辑（MultiEdit）

### 3. 任务管理
- TodoWrite 工具管理多步骤任务
- 支持任务状态跟踪（pending/in_progress/completed/cancelled）
- 自动持久化到 markdown 日志

### 4. 技能加载与执行
- 动态加载项目本地技能
- 技能可包含特定知识、工作流或工具集成
- 支持参数化（`$ARGUMENTS` 占位符）

### 5. 子代理委托
- 将复杂、多步骤任务委托给子代理
- 子代理在隔离会话中运行
- 支持不同类型的子代理（explore/plan/summary/general）

### 6. 外部工具集成
- 通过 MCP 协议集成外部工具
- 当前集成：fetch（网页抓取）、context7（文档查询）、tavily-mcp（网络搜索）
- 支持动态注册新的 MCP 服务器

### 7. 上下文管理
- 智能历史压缩（当超过上下文窗口时）
- 工具输出截断（防止输出过大）
- 敏感信息清理（追踪日志中）
- 会话快照保存/加载

## 入口点

### 主要入口
- **`scripts/chat_test_agent.py`** - 交互式 CLI 入口
  - 支持自定义 provider/model/api-key/base-url
  - 支持调试模式
  - 支持显示原始响应

### 运行方式
```bash
# 默认设置
python scripts/chat_test_agent.py

# 自定义 provider/model
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7 --api-key YOUR_KEY --base-url https://open.bigmodel.cn/api/coding/paas/v4

# 调试模式
python scripts/chat_test_agent.py --show-raw
```

### 评估入口
- **`eval/run_eval.py`** - 评估运行器
```bash
python eval/run_eval.py --suite base
python eval/run_eval.py --suite long_horizon
python eval/run_eval.py --suite all
```

### 测试入口
- **`tests/`** - pytest 测试套件
```bash
python -m pytest tests/ -v
```

## 关键环境变量

### 上下文/历史
- `CONTEXT_WINDOW` (默认: 10000) - 上下文窗口大小
- `COMPRESSION_THRESHOLD` (默认: 0.8) - 压缩阈值
- `MIN_RETAIN_ROUNDS` (默认: 10) - 最小保留轮数
- `SUMMARY_TIMEOUT` (默认: 120s) - 摘要生成超时

### 工具输出截断
- `TOOL_OUTPUT_MAX_LINES` (默认: 2000) - 最大输出行数
- `TOOL_OUTPUT_MAX_BYTES` (默认: 51200) - 最大输出字节数
- `TOOL_OUTPUT_TRUNCATE_DIRECTION` (head|tail) - 截断方向
- `TOOL_OUTPUT_DIR` (默认: tool-output) - 截断输出缓存目录

### 技能
- `SKILLS_REFRESH_ON_CALL` (默认: true) - 调用时刷新技能
- `SKILLS_PROMPT_CHAR_BUDGET` (默认: 12000) - 技能提示词字符预算

### 子代理
- `SUBAGENT_MAX_STEPS` (默认: 15) - 子代理最大步数
- `LIGHT_LLM_MODEL_ID` / `LIGHT_LLM_API_KEY` / `LIGHT_LLM_BASE_URL` - 轻量级 LLM 配置

## 技术栈

### 核心依赖
- `openai>=1.0.0` - OpenAI API 客户端
- `pydantic>=1.10.0` - 数据验证
- `mcp>=1.0.0` - MCP 协议支持
- `anyio>=3.0.0` - 异步 I/O

### UI/交互
- `rich>=13.0.0` - 终端 UI 美化
- `prompt_toolkit>=3.0.0` - 交互式提示

### 测试
- `pytest>=7.0.0` - 测试框架
- `python-dotenv>=1.0.0` - 环境变量加载

## 代码风格与约定

### 编码规范
- Python 3.x
- 4 空格缩进
- `snake_case` 用于函数/变量
- `PascalCase` 用于类
- 优先使用仓库绝对导入（如 `from core.llm import HelloAgentsLLM`）

### 工具开发
- 所有工具必须继承 `tools/base.py:Tool`
- 严格遵循 Universal Tool Response Protocol
- 工具提示词位于 `prompts/tools_prompts/*.py`

### 测试
- 使用 pytest 风格
- 保持测试确定性和离线运行
- 测试文件位于 `tests/` 目录

### 安全
- 将密钥存储在 `.env` 或环境变量中
- 永不提交密钥到仓库
- 遵循安全最佳实践（不记录/提交密钥）

## 架构模式

### ReAct 循环
```
思考（Thought）→ 行动（Action）→ 观察（Observation）→ 重复
```

### 上下文工程
- 分层消息累积（L1-L4）
- 历史压缩与摘要生成
- 工具输出截断与缓存

### 工具注册与调用
- 中央工具注册表
- 乐观锁保护（Write/Edit）
- 统一响应协议

### 子代理委托
- 隔离会话
- 受限工具集
- 类型化提示词（explore/plan/summary/general）

## 项目结构

```
MyCodeAgent/
├── agents/              # Agent 实现
│   └── codeAgent.py     # 主 CodeAgent 实现
├── core/                # 核心类型/服务
│   ├── agent.py         # Agent 基类
│   ├── llm.py           # LLM 包装器
│   ├── message.py       # Message 模型
│   ├── config.py        # 配置管理
│   ├── context_engine/  # 上下文工程
│   └── skills/          # 技能系统
├── tools/               # 工具系统
│   ├── registry.py      # 工具注册表
│   ├── builtin/         # 内置工具
│   └── mcp/             # MCP 集成
├── prompts/             # 提示词模板
│   ├── agents_prompts/  # Agent 提示词
│   └── tools_prompts/   # 工具提示词
├── scripts/             # 入口点
│   └── chat_test_agent.py  # 交互式 CLI
├── skills/              # 技能定义
│   └── <skill-name>/SKILL.md
├── tests/               # 测试套件
├── eval/                # 评估系统
│   ├── run_eval.py      # 评估运行器
│   ├── tasks/           # 评估任务
│   ├── fixtures/        # 测试固件
│   └── traces/          # 执行追踪
├── utils/               # 工具函数
├── tool-output/         # 截断工具输出缓存
├── docs/                # 设计文档
├── mcp_servers.json     # MCP 服务器配置
├── requirements.txt     # 依赖列表
├── CLAUDE.md           # Claude Code 指南
├── AGENTS.md           # 仓库指南
└── code_law.md         # 项目规则（可选）
```

## 文档参考

- `CLAUDE.md` - Claude Code 工作指南
- `AGENTS.md` - 仓库指南与开发规范
- `docs/通用工具响应协议.md` - 通用工具响应协议
- `docs/DEV_HANDOFF.md` - 开发交接文档

---

*生成时间: 2025-01-18*
*基于文件: CLAUDE.md, AGENTS.md, agents/codeAgent.py, core/agent.py, core/context_engine/*, tools/builtin/*, requirements.txt*
