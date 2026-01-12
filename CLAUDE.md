# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行智能体交互（默认智谱 GLM-4.6）
python scripts/chat_test_agent.py

# 指定提供商和模型
python scripts/chat_test_agent.py --provider zhipu --model GLM-4.7
python scripts/chat_test_agent.py --provider openai --model gpt-4

# 调试模式：显示原始 LLM 响应
python scripts/chat_test_agent.py --show-raw

# 首次使用：初始化 CODE_LAW.md
python scripts/chat_test_agent.py
# 启动后输入 'init' 让 Agent 探索项目并生成 CODE_LAW.md

# 运行测试
python -m pytest tests/ -v
python tests/run_all_tests.py

# 单个工具测试
python -m pytest tests/test_write_tool.py -v
python -m pytest tests/test_read_tool.py -v
python -m pytest tests/test_protocol_compliance.py -v
```

## 高层架构

这是一个基于 ReAct（Reasoning + Acting）架构的 AI 智能体框架：

```
core/              → 基础层
  ├── agent.py              # Agent 基类
  ├── llm.py                # HelloAgentsLLM 统一接口
  ├── message.py            # 消息系统
  ├── config.py             # 配置管理
  ├── context_engine/       # 上下文工程组件
  │   ├── context_builder.py    # 上下文构建（L1/L2/L3 拼接、CODE_LAW 加载）
  │   ├── history_manager.py    # 历史管理与压缩
  │   ├── input_preprocessor.py # @file 预处理
  │   ├── summary_compressor.py # Summary 生成器
  │   ├── tool_result_compressor.py  # 工具结果压缩器
  │   └── trace_logger.py       # 轨迹记录器（JSONL + Markdown）
agents/            → 具体智能体
  └── codeAgent.py   # 代码智能体（内置 ReAct 循环）
tools/             → 工具层
  ├── base.py          # Tool 基类、ToolStatus、ErrorCode
  ├── registry.py      # ToolRegistry 工具注册中心
  └── builtin/         # 内置工具实现
      ├── list_files.py       # LS（目录列表）
      ├── search_files_by_name.py  # Glob（通配搜索）
      ├── search_code.py      # Grep（代码搜索）
      ├── read_file.py        # Read（文件读取）
      ├── write_file.py       # Write（文件写入）
      ├── edit_file.py        # Edit（单次编辑）
      ├── edit_file_multi.py  # MultiEdit（批量编辑）
      ├── todo_write.py       # TodoWrite（任务管理）
      └── bash.py             # Bash（命令执行）
prompts/           → 提示词
  ├── agents_prompts/  # 智能体提示词（L1_system_prompt、summary 等）
  └── tools_prompts/   # 工具描述字符串常量
```

- **HelloAgentsLLM**：统一 LLM 接口，支持 OpenAI、DeepSeek、Qwen、智谱等
- **CodeAgent**：内置 ReAct 循环（Thought → Action → Observation），管理思考-行动-观察
- **ToolRegistry**：工具注册中心，所有工具必须遵循通用工具响应协议
- **TraceLogger**：记录完整会话轨迹到 `memory/traces/`（JSONL + Markdown）
- **ContextBuilder**：三层上下文拼接（L1 系统层 + L2 CODE_LAW + L3 历史）
- **ToolResultCompressor**：压缩工具结果后写入历史（LS/Glob/Grep 截断列表，Edit/Write 仅保留摘要）

## 工具响应协议（重要）

所有工具必须遵循 `docs/通用工具响应协议.md`：

### 顶层字段（固定）
```json
{
  "status": "success" | "partial" | "error",
  "data": { ... },
  "text": "人类可读摘要",
  "stats": { "time_ms": number, ... },
  "context": {
    "cwd": ".",  // 必填，相对项目根目录
    "params_input": { ... },  // 必填
    "path_resolved": "..."  // 涉及路径时必填
  },
  "error": { "code": "...", "message": "..." }  // 仅 status="error" 时存在
}
```

### 状态判定
- `success`：任务完全按预期完成，无截断、无降级
- `partial`：结果可用但存在折扣（截断、fallback、dry-run、部分失败）
- `error`：无法提供有效结果（NOT_FOUND、ACCESS_DENIED、INVALID_PARAM 等）

### 截断处理
- 设置 `status = "partial"`
- 设置 `data.truncated = true`
- 在 `text` 中明确说明并提供下一步建议

### 统一 data 字段约定
| 工具类型 | 推荐字段 |
|---------|---------|
| 目录探索 (ls) | `entries: Array<{path, type}>`, `truncated` |
| 通配匹配 (glob) | `paths: string[]`, `truncated` |
| 内容搜索 (grep) | `matches: Array<{file, line, text}>`, `truncated` |
| 文件读取 (read) | `content`, `truncated` |
| 文件写入 (write) | `applied: boolean`, `operation` |
| 单次编辑 (edit) | `applied: boolean`, `diff_preview`, `diff_truncated`, `replacements` |
| 多次编辑 (multi_edit) | `applied: boolean`, `diff_preview`, `diff_truncated`, `replacements` |
| 任务管理 (todo_write) | `todos: Array<{id, content, status}>`, `recap`, `summary` |

## 编码规范

- Python 3，4 空格缩进
- `snake_case` 用于函数/变量，`PascalCase` 用于类
- 优先使用项目绝对导入：`from core.llm import HelloAgentsLLM`
- 对外暴露的工具名称：**LS**、**Glob**、**Grep**、**Read**、**Write**、**Edit**、**MultiEdit**、**TodoWrite**
- 修改工具行为时，同步更新 `prompts/tools_prompts/` 中的对应提示词

## 工具选择

- **Write**：创建新文件或完全覆盖现有文件
- **Edit**：修改已存在文件的单处内容（需先 Read，old_string 必须唯一）
- **MultiEdit**：同一文件的多处原子性批量编辑（需先 Read）
- **Read**：读取文件，框架自动缓存元信息供 Edit/MultiEdit 乐观锁使用

## 框架机制

- **乐观锁**：Read 后自动缓存 `file_mtime_ms`/`file_size_bytes`，Edit/MultiEdit 自动注入校验
- **Legacy Adapter**：由 `ENABLE_LEGACY_ADAPTER` 环境变量控制（默认 true），迁移期自动转换旧格式响应
- **LLM 自动检测**：HelloAgentsLLM 支持 openai/deepseek/qwen/zhipu 等提供商，provider=`auto` 时根据 base_url 自动推断
- **三层上下文**：L1（系统提示词+工具描述）+ L2（CODE_LAW.md）+ L3（会话历史）
- **结果压缩**：工具结果写入历史时自动压缩（LS/Glob/Grep 截断列表，Edit/Write 仅保留摘要）

## 配置

环境变量（通过 .env 文件或本地环境）：
- `OPENAI_API_KEY`：OpenAI API 密钥
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥
- `GLM_API_KEY`：智谱 AI API 密钥
- `LLM_BASE_URL`：LLM 服务基础 URL
- `ENABLE_LEGACY_ADAPTER=false`：禁用传统适配器转换

## CODE_LAW.md

项目根目录的 `CODE_LAW.md` 是项目的**规则文件**，会被 ContextBuilder 自动注入 L2 层：
- 存储常用命令（build、test、lint 等）
- 记录代码风格偏好
- 维护代码库结构信息

首次使用可运行 `python scripts/chat_test_agent.py`，输入 `init` 让 Agent 探索项目并生成该文件。

## 使用中文回答用户问题
