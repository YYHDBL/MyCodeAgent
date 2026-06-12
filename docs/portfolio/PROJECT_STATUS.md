# 项目边界与测试口径

## 2026-06-12 收口快照

```text
pytest total                         739
formal Core/Tool/Extension/Scenario 629
experimental Teams                  110
tests/scenarios collected            11
```

统计命令：

```bash
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest --collect-only -q tests --ignore=tests/experimental
.venv/bin/python -m pytest --collect-only -q tests/experimental
.venv/bin/python -m pytest --collect-only -q tests/scenarios
```

场景口径：

- Phase 0 表驱动基线覆盖 10 条 Runtime 路径。
- Phase 0 批量 eval report 固定输出 6 条核心对比场景。
- Phase 7 有 Explore 隔离和 Verification 两条场景证据。
- Phase 9 有四个可运行 portfolio Demo。
- 上述维度有重叠，不将它们简单相加为“独立 benchmark 数”。

## 正式 Harness Core

正式维护范围：

- `app/`：CLI 与装配。
- `runtime/`：Loop、Completion、Recovery、Context、Transcript、Memory、Subagent。
- `tools/`：Registry、Executor、Permission、Orchestrator、内置工具。
- `extensions/`：Trace、MCP、Skills。
- `tests/` 中除 `tests/experimental/` 外的对应测试。

正式 Task 只支持 Explore。Verification 由 Completion Gate 调用。两者复用 `RuntimeRunner`。

## Experimental

`experimental/teams/` 与 `tests/experimental/` 保留以下研究实现：

- persistent worker。
- mailbox/message router。
- task board 与 parallel work item。
- tmux orchestration。
- plan approval 与 team UI。

它们不属于默认单 Agent Harness，不作为 README 的产品能力承诺。Phase 9 未修改该目录。

## 保留的历史设计资料

工具级中文设计文档、Phase 6A/7/8 实施计划和协议文档仍有参考价值，因此保留。它们用于解释演进过程，不替代 [`docs/HARNESS.md`](../HARNESS.md) 的当前架构。

已删除的旧 `demo/` 项目概览、网页和执行复盘引用了不存在的目录与旧子 Agent 模式，继续保留会造成事实冲突。

## 没有完整复刻 Claude Code

明确不实现：

- StreamingToolExecutor 与产品级流式 UI。
- 跨模型 fallback 的状态重建。
- OS/容器/网络级完整沙箱。
- 自动 Coordinator、DAG、远程 worker 和正式 Agent Teams。
- 后台自动记忆提取、embedding 和云端 memory provider。
- Feature Flag、A/B 平台、远程 telemetry/dashboard。
- 插件市场、IDE 集成和账号/计费系统。

取舍原因：

- 项目目标是展示 Harness 的控制语义，不是复制闭源产品。
- 上述能力需要大量平台基础设施，会稀释 Loop、Tool、Context、Resume 四条核心论述。
- 当前实现优先选择本地、确定、可测试、可从 Trace 解释的机制。

## 维护状态

Phase 9 后不再新增 Agent Runtime 功能。允许的后续工作：

- 修复正式验收测试证明的缺陷。
- 改进 deterministic scenario 与 eval 指标。
- 修正文档和 Trace 证据。
- 在不改变核心边界的前提下做兼容性维护。
