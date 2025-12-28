# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行智能体交互
python scripts/chat_test_agent.py --agent code --show-raw
python scripts/chat_test_agent.py --agent test --show-raw
python scripts/chat_test_agent.py --agent code --provider zhipu --model GLM-4.7

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
core/           → 基础层（Agent 基类、HelloAgentsLLM、Message、Config）
  agents/       → 具体智能体（CodeAgent、TestAgent）
  agentEngines/ → 推理引擎（ReActEngine：Thought → Action → Observation 循环）
  tools/        → 工具层（Tool 基类、ToolRegistry、协议辅助）
  tools/builtin/ → 内置工具（LS、Glob、Grep、Read、Write）
  prompts/tools_prompts/ → 工具提示词（作为工具描述的字符串常量）
```

- **HelloAgentsLLM**：统一 LLM 接口，支持 OpenAI、DeepSeek、Qwen、智谱等
- **ReActEngine**：管理思考-行动-观察的推理循环
- **ToolRegistry**：工具注册中心，所有工具必须遵循通用工具响应协议

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
| 文件修改 (edit/write) | `applied: boolean`, `operation` |

## 编码规范

- Python 3，4 空格缩进
- `snake_case` 用于函数/变量，`PascalCase` 用于类
- 优先使用项目绝对导入：`from core.llm import HelloAgentsLLM`
- 对外暴露的工具名称：**LS**、**Glob**、**Grep**、**Read**、**Write**
- 修改工具行为时，同步更新 `prompts/tools_prompts/` 中的对应提示词

## 配置

环境变量（通过 .env 文件或本地环境）：
- `OPENAI_API_KEY`：OpenAI API 密钥
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥
- `GLM_API_KEY`：智谱 AI API 密钥
- `LLM_BASE_URL`：LLM 服务基础 URL
- `ENABLE_LEGACY_ADAPTER=false`：禁用传统适配器转换

## 使用中文回答用户问题
