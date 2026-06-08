# MyCodeAgent

MyCodeAgent 是一个用于学习 code agent harness 工程的本地 Python 项目。它不追求企业级平台能力，而是用尽量小的代码展示生产级 Agent 最重要的三个骨架：

- Agent Loop 状态机
- 工具编排与结果预算
- 非破坏性的上下文工程

## 架构

```text
main.py
  -> app/                 CLI 与依赖装配
  -> runtime/             Agent Loop、状态、历史、上下文、会话
  -> tools/               工具执行、编排、内置工具
  -> extensions/          MCP、Skills、Tracing
  -> experimental/teams/  实验性多 Agent 运行时
```

默认路径是单 Agent：

```text
RuntimeRunner
  -> ContextEngine.build_model_view()
  -> LLM
  -> ToolOrchestrator
  -> HistoryManager
  -> next loop state
```

详细设计见 [docs/HARNESS.md](docs/HARNESS.md)。
核心 Trace 协议见 [docs/HARNESS_TRACE_PROTOCOL.md](docs/HARNESS_TRACE_PROTOCOL.md)。

## 当前能力

### Agent Loop

- `runtime/loop.py` 是唯一的主循环
- `runtime.host.CodeAgent` 只负责装配依赖并委托给 `RuntimeRunner`
- `runtime/state.py` 记录显式 transition 和 terminal reason
- 支持空响应重试、最大步数终止、工具调用继续和上下文压缩转移
- trace 可以解释每一轮为什么继续或结束

### Tool Harness

- `tools/orchestrator.py` 负责工具规划、分批和执行
- 连续的只读工具可以并发，副作用工具保持串行
- 工具结果保持模型调用顺序
- 支持单工具和单轮聚合结果预算
- 大结果落盘，模型只接收稳定的压缩视图

### Context Engineering

- `HistoryManager` 只保存完整运行历史
- `ContextEngine` 负责预算判断、usage、compact 和模型视图
- `CompactCheckpoint` 保存摘要边界，不删除原始历史
- `ProjectionBuilder` 在请求模型时投影 `summary + recent history`
- 清空或加载会话时同步重置 context runtime 状态

### Tools

内置文件读取、搜索、写入、编辑、Bash、Todo、Skill、Task 和用户询问工具。工具响应遵循 [通用工具响应协议](docs/通用工具响应协议.md)。

注意：

- `Task` 当前仍连接到 `experimental/teams/` 的实验性子运行时。
- 这条路径在 Phase 0 只做边界标记，不算默认单 Agent harness 的正式入口。

## 快速开始

环境要求：Python 3.10+，推荐使用 `uv`。

```bash
git clone <repository-url>
cd MyCodeAgent
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

至少配置：

```bash
LLM_PROVIDER=siliconflow
LLM_MODEL_ID=your-model
LLM_API_KEY=your-api-key
```

运行：

```bash
.venv/bin/python main.py
```

覆盖模型配置：

```bash
.venv/bin/python main.py --provider zhipu --model GLM-4.7
```

## 测试

全量测试：

```bash
.venv/bin/python -m pytest -q
```

按 harness 层验证：

```bash
.venv/bin/python -m pytest tests/runtime tests/tools -q
.venv/bin/python -m pytest tests/extensions -q
.venv/bin/python -m pytest tests/scenarios -q
.venv/bin/python -m pytest tests/experimental -q
```

## 目录

```text
app/                 CLI 与启动装配
core/                配置、LLM、基础抽象
runtime/             单 Agent 运行时
runtime/context/     上下文运行时
tools/               工具边界、编排器与内置工具
extensions/          可选 MCP / Skills / Tracing
experimental/teams/  实验性多 Agent 系统
tests/               按运行时边界组织的测试
docs/                当前设计与工具协议
```

## 设计原则

- 学习 harness，而不是堆产品功能
- 完整历史与模型视图分离
- 模型提出行动，运行时决定如何安全执行
- 状态转移必须可观察、可测试
- 默认选择简单、确定、可恢复的实现
