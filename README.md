

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
- **AgentTeams MVP（实验性）**：TeamCreate / SendMessage / TeamStatus / TeamDelete + Task persistent teammate
- **上下文工程**：分层注入、历史压缩、@file 强制读取
- **工具输出截断与落盘**：超限结果写入 `tool-output/`
- **轻量熔断**：连续失败工具自动临时禁用
- **Trace 追踪**：JSONL + HTML 双轨日志 + 脱敏
- **会话持久化**：支持 `/save` 与 `/load`
- **MCP 扩展**：通过 `mcp_servers.json` 接入外部工具
- **Enhanced CLI UI**：工具调用树、token 统计、进度显示

---

## 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd MyCodeAgent

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置环境变量

创建 `.env` 文件或设置以下环境变量：

```bash
# LLM 配置
export OPENAI_API_KEY="your-api-key"
export DEFAULT_MODEL="gpt-4"
export TEMPERATURE="0.7"

# AgentTeams（可选，默认为关闭）
export ENABLE_AGENT_TEAMS="true"

# 上下文配置
export CONTEXT_WINDOW="128000"
export COMPRESSION_THRESHOLD="0.8"
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

## AgentTeams（MVP）

> ⚠️ `AgentTeams` 已加入当前版本，但仍为**实验性功能**，默认关闭。  
> 建议仅在开发/测试环境启用。

- Feature Flag：`ENABLE_AGENT_TEAMS=true` 启用（默认关闭，便于快速回滚）
- Claude 兼容开关：`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Team 工具：`TeamCreate` / `SendMessage` / `TeamStatus` / `TeamDelete`
- 并行分工工具：`TeamFanout` / `TeamCollect`
- Task 双模式：
  - `mode=oneshot`（默认，兼容旧行为）
  - `mode=persistent`（创建持久 teammate，参数：`team_name` + `teammate_name`）
  - `mode=parallel`（快捷 fanout，参数：`team_name` + `tasks`）
- 消息 ACK 三态：`pending / delivered / processed`
- work item 状态：`queued / running / succeeded / failed / canceled`
- runtime 通知通过 system block 注入，不污染 user 轮次

最小示例（交互中由主代理触发工具调用）：
1. `TeamCreate(team_name="demo")`
2. `Task(mode="persistent", team_name="demo", teammate_name="dev", ...)`
3. `SendMessage(team_name="demo", from_member="lead", to_member="dev", text="...")`
4. `TeamStatus(team_name="demo")`
5. `TeamDelete(team_name="demo")`

并行分工示例：
1. `TeamCreate(team_name="demo")`
2. `Task(mode="persistent", team_name="demo", teammate_name="dev1", ...)`
3. `Task(mode="persistent", team_name="demo", teammate_name="dev2", ...)`
4. `Task(mode="parallel", team_name="demo", tasks=[{"owner":"dev1","title":"impl","instruction":"..."},{"owner":"dev2","title":"test","instruction":"..."}])`
5. `TeamCollect(team_name="demo")`（轮询直到 succeeded/failed 收敛）

快速回滚：将 `ENABLE_AGENT_TEAMS` 设为 `false`（或删除该环境变量）。

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

### AgentTeams

- `ENABLE_AGENT_TEAMS`（默认 false）
- `AGENT_TEAMS_STORE_DIR`（默认 `.teams`）
- `AGENT_TASKS_STORE_DIR`（默认 `.tasks`）

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
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_message.py -v

# 运行测试并查看覆盖率
python -m pytest tests/ --cov=.
```

---

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 代码规范

- 使用 4 空格缩进（PEP 8）
- 类名使用 PascalCase
- 函数和变量使用 snake_case
- 常量使用 UPPER_SNAKE_CASE
- 函数必须添加类型注解
- 为新功能添加单元测试

---

## 常见问题

**Q: 如何启用 AgentTeams 功能？**

A: 设置环境变量 `ENABLE_AGENT_TEAMS=true`，然后重启 CLI。

**Q: 工具调用失败怎么办？**

A: 使用 `--show-raw` 参数运行，查看详细错误信息。常见原因包括 API Key 配置错误或网络问题。

**Q: 如何调试上下文压缩问题？**

A: 设置 `TRACE_ENABLED=true` 并查看 `memory/traces/` 目录下的日志文件。

**Q: 支持哪些 LLM 提供商？**

A: 支持 OpenAI、Anthropic、Zhipu（智谱）等兼容 OpenAI API 格式的提供商。

---

## License

本项目采用 MIT 许可证 授权。
