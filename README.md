# MyCodeAgent

一个面向学习与实验的 ReAct 代码代理项目，用于实践：工具协议、上下文工程、技能系统与子代理机制。

## 适用场景
- 学习 ReAct 工作流与工具调用
- 研究上下文工程（截断、压缩、归档）
- 试验 Skills / Task 子代理能力
- 搭建可扩展的本地实验框架

## 核心功能
- ReAct 推理循环（Thought → Action → Observation）
- 统一工具响应协议（status/data/text/stats/context）
- 内置工具：LS / Glob / Grep / Read / Write / Edit / MultiEdit / TodoWrite / Bash / Skill / Task
- Skills（MVP）：从 `skills/**/SKILL.md` 按需加载技能
- Task 子代理（MVP）：general / explore / plan / summary
- 上下文工程：分层注入、历史压缩、@file 强制 Read、mtime 变化提醒
- 工具输出统一截断：超限结果落盘到 `tool-output/`
- MCP 工具集成：加载 `mcp_servers.json` 注册远程工具
- Enhanced UI：工具调用树、token 统计、进度显示

## 安装
```bash
pip install -r requirements.txt
```

## 使用方法
### 运行交互式 CLI
```bash
python scripts/chat_test_agent.py
```

### 指定模型与供应商
```bash
python scripts/chat_test_agent.py \
  --provider zhipu \
  --model GLM-4.7 \
  --api-key YOUR_API_KEY \
  --base-url https://open.bigmodel.cn/api/coding/paas/v4
```

### 输出原始响应（调试）
```bash
python scripts/chat_test_agent.py --show-raw
```

## Skills（技能）
### 目录约定
```
skills/
  <skill-name>/
    SKILL.md
```

### SKILL.md 格式
```markdown
---
name: code-review
description: Review code quality and risks
---
# Code Review

Use this checklist:
- ...

$ARGUMENTS
```

- `$ARGUMENTS` 会被 Skill 工具传入的 `args` 替换。

## Task 子代理（MVP）
- `general / explore / plan / summary` 四种子代理类型
- 主代理按复杂度选择 `model: main | light`
- 子代理工具权限隔离（只读/受限）

## MCP 工具集成
在项目根目录添加 `mcp_servers.json`：
```json
{
  "mcpServers": {
    "myServer": {
      "transport": "http",
      "url": "http://localhost:8000"
    }
  }
}
```

## 关键环境变量
### Context / 历史
- `CONTEXT_WINDOW`（默认 10000）
- `COMPRESSION_THRESHOLD`（默认 0.8）
- `MIN_RETAIN_ROUNDS`（默认 10）
- `SUMMARY_TIMEOUT`（默认 120s）

### 工具输出截断
- `TOOL_OUTPUT_MAX_LINES`（默认 2000）
- `TOOL_OUTPUT_MAX_BYTES`（默认 51200）
- `TOOL_OUTPUT_TRUNCATE_DIRECTION`（head|tail）
- `TOOL_OUTPUT_DIR`（默认 tool-output）
- `TOOL_OUTPUT_RETENTION_DAYS`（默认 7）

### Skills
- `SKILLS_REFRESH_ON_CALL`（默认 true）
- `SKILLS_PROMPT_CHAR_BUDGET`（默认 12000）

### Subagent
- `SUBAGENT_MAX_STEPS`（默认 15）
- `LIGHT_LLM_MODEL_ID / LIGHT_LLM_API_KEY / LIGHT_LLM_BASE_URL`

## 测试
```bash
python -m pytest tests/ -v
```

## 文档入口
- 工具协议：`docs/通用工具响应协议.md`
- 上下文工程：`docs/上下文工程设计文档.md`
- 工具输出截断：`docs/工具输出截断设计文档.md`
- Task（MVP）：`docs/task/task_mvp_design.md`
- Skills（MVP）：`docs/skills/skill_mvp_implementation_plan.md`
- 交接说明：`docs/DEV_HANDOFF.md`

## License
TBD
