

# MyCodeAgent
<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg) ![License](https://img.shields.io/badge/License-MIT-green.svg) 


</div>

一个面向学习与实验的 **代码代理框架**，聚焦 **工具协议**、**上下文工程**、**子代理机制** 与 **可观测性** 的系统化实践。

> 目标：让“Agent 能做什么”与“Agent 为什么能做”都可追溯、可验证、可扩展。

---

## 适用场景

- 学习 function calling + 工具协议的真实落地
- 研究上下文工程（截断、压缩、持久化）
- 实验 Skills / Task 子代理协作
- 快速搭建可扩展的本地 Agent 试验场

---

## 核心特性

- **Function Calling 工具调用**（不依赖 Action 文本解析）
- **统一工具响应协议**：`status/data/text/stats/context/error`
- **内置工具**：LS / Glob / Grep / Read / Write / Edit / MultiEdit / Bash / TodoWrite / Skill / Task / AskUser
- **上下文工程**：分层注入、历史压缩、@file 强制读取
- **工具输出截断与落盘**：超限结果写入 `tool-output/`
- **轻量熔断**：连续失败工具自动临时禁用
- **Trace 追踪**：JSONL + HTML 双轨日志 + 脱敏
- **会话持久化**：支持 `/save` 与 `/load`
- **MCP 扩展**：通过 `mcp_servers.json` 接入外部工具
- **Enhanced CLI UI**：工具调用树、token 统计、进度显示

---

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

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

### 开启原始输出（调试）

```bash
python scripts/chat_test_agent.py --show-raw
```

---

## 项目结构（概要）

```
agents/               主代理实现
core/                 核心运行时与上下文工程
tools/                工具系统与注册表
prompts/              系统提示词与工具提示词
docs/                 设计与协议文档
scripts/              CLI 入口
tests/                测试集
memory/               trace/session 输出（本地）
tool-output/          长输出落盘目录
mcp_servers.json      MCP 工具配置
```

---

## 技术栈

- Python 3.x
- openai / pydantic / mcp / anyio
- rich / prompt_toolkit

---

## Skills（技能）

目录约定：

```
skills/
  <skill-name>/
    SKILL.md
```

`SKILL.md` 示例：

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

`$ARGUMENTS` 会被 Skill 工具传入的 `args` 替换。

---

## Task 子代理（MVP）

- 子代理类型：`general / explore / plan / summary`
- 主代理按复杂度选择模型：`main | light`
- 子代理工具权限隔离（只读/受限）

---

## MCP 工具集成

在项目根目录配置 `mcp_servers.json`（命令式启动）：

```json
{
  "mcpServers": {
    "example": {
      "command": "npx",
      "args": ["-y", "some-mcp-server", "--api-key", "${API_KEY}"]
    }
  }
}
```

---

## 关键环境变量

### Context / 历史

- `CONTEXT_WINDOW`（默认 10000）
- `COMPRESSION_THRESHOLD`（默认 0.8）
- `MIN_RETAIN_ROUNDS`（默认 10）
- `SUMMARY_TIMEOUT`（默认 120s）

### 工具输出截断

- `TOOL_OUTPUT_MAX_LINES`（默认 2000）
- `TOOL_OUTPUT_MAX_BYTES`（默认 51200）
- `TOOL_OUTPUT_TRUNCATE_DIRECTION`（head|tail|head_tail）
- `TOOL_OUTPUT_HEAD_TAIL_LINES`（默认 40，仅当 head_tail 生效）
- `TOOL_OUTPUT_DIR`（默认 tool-output）
- `TOOL_OUTPUT_RETENTION_DAYS`（默认 7）

### Skills

- `SKILLS_REFRESH_ON_CALL`（默认 true）
- `SKILLS_PROMPT_CHAR_BUDGET`（默认 12000）

### Subagent

- `SUBAGENT_MAX_STEPS`（默认 50）
- `LIGHT_LLM_MODEL_ID / LIGHT_LLM_API_KEY / LIGHT_LLM_BASE_URL`

### Trace

- `TRACE_ENABLED`（默认 true）
- `TRACE_DIR`（默认 memory/traces）
- `TRACE_SANITIZE`（默认 true）
- `TRACE_HTML_INCLUDE_RAW_RESPONSE`（默认 false）

---

## 文档入口

- 工具协议：`docs/通用工具响应协议.md`
- 上下文工程：`docs/上下文工程设计文档.md`
- 工具输出截断：`docs/工具输出截断设计文档.md`
- Trace 设计：`docs/TraceLogging设计文档.md`
- Task 子代理：`docs/task(subagent)设计文档.md`
- Skill 机制：`docs/skillTool设计文档.md`
- 交接说明：`docs/DEV_HANDOFF.md`

---

## 使用示例
测试提示词
```
  你需要分析自己的源代码，基于代码剖析的结果，创建一个面向用户的Agent自我介绍网页（以第一人称视角介绍自己）。
  - 请合理使用完成任务所需的所有工具，按照最优步骤执行
  - 内容与要求：
    - 可以使用mcp联网搜索获取同类竞品，分析优劣进行对比
    - 若你具备UI/UX相关技能（Skill），请调用并应用
    - 网页风格可自行选择（如玻璃拟态、拟物化、新拟态等均可）
    - 最终输出一个HTML文件，保存至demo/目录下（文件名可自定义
```
生成网页
[text](demo/agent-introduction.html)

![demo](/docs/assest/demo.png)

视频演示：
[MyCodeAgent 视频演示](https://www.bilibili.com/video/BV1vhkMBpEzq)

Todo List 能力
![todoList](/docs/assest/todoList.png)

MCP 能力
![mcp](/docs/assest/mcp.png)

Subagent 能力
![subagent](/docs/assest/subagent.png)

Skills 能力
![skill](/docs/assest/skill.png)


恢复会话能力
![load](/docs/assest/load.png)

---

## 参考资源（References）


> - 感谢 [Datawhale](https://github.com/datawhalechina) 提供的优秀开源教程 [HelloAgent](https://github.com/jjyaoao/HelloAgents.git)
> - 感谢 [shareAI-lab](https://github.com/shareAI-lab) 的[Kode-Cli](https://github.com/shareAI-lab/Kode-cli.git)项目
> - 感谢 [MiniMax-AI](https://github.com/MiniMax-AI)的[Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent)项目
> - 感谢[anomalyco](https://github.com/anomalyco)的**[opencode](https://github.com/anomalyco/opencode)**项目

---

## 测试

```bash
python -m pytest tests/ -v
```

---

## License

本项目采用 MIT许可证 授权。
