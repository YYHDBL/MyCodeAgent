# AgentTeams 功能设计文档（MVP 当前实现对齐版）

## 1. 目标与范围

本设计文档描述 MyCodeAgent 当前 **AgentTeams MVP** 的真实实现状态，用于开发、测试与回归。

MVP 目标：
1. 在 `CodeAgent + ToolRegistry + TaskTool` 架构上提供可用的会话团队能力。
2. 支持团队创建、消息通信、并行分工执行、状态观测和清理。
3. 保持 `Task(mode=oneshot)` 兼容，不破坏原有一次性子代理路径。
4. 通过 feature flag 可快速关闭与回滚。

MVP 非目标：
1. 不做完整的多窗格交互 UI（如 Shift+Up/Down 焦点切换）。
2. 不做每个 teammate 的完整会话历史恢复。
3. 不做分布式调度、复杂事务、复杂重试编排。

## 2. 系统架构

核心模块位于 `core/team_engine/`：
1. `manager.py`：团队编排入口，管理消息、任务板、审批、worker 生命周期。
2. `store.py`：团队配置、inbox、work item 的文件化持久化与锁。
3. `task_board_store.py`：共享任务板（依赖、claim、状态更新）。
4. `message_router.py`：消息协议与 ACK 状态推进。
5. `execution.py`：teammate 工作执行服务（复用 TurnExecutor）。
6. `turn_executor.py`：单轮 LLM + tool call 执行内核。
7. `supervisor.py` + `worker.py`：worker 线程生命周期管理。
8. `approval.py`：计划审批状态机。

`CodeAgent` 挂载点：
1. 根据 `enable_agent_teams` 初始化 `TeamManager`。
2. 注册 Team 系列工具。
3. 每轮 ReAct 前注入 runtime system block（不污染 user 轮次）。
4. `save_session/load_session` 调用 team state 导出/恢复。

## 3. 功能工具面

已注册工具：
1. `TeamCreate`
2. `SendMessage`
3. `TeamStatus`
4. `TeamDelete`
5. `TeamCleanup`
6. `TeamFanout`
7. `TeamCollect`
8. `TeamTaskCreate`
9. `TeamTaskGet`
10. `TeamTaskUpdate`
11. `TeamTaskList`
12. `TeamApprovals`
13. `TeamApprovePlan`

Task 相关模式：
1. `Task(mode=oneshot)`：保持原行为（默认）。
2. `Task(mode=persistent)`：创建持久 teammate。
3. `Task(mode=parallel)`：快捷并行分发（底层走 fanout）。

## 4. 协议与状态机

### 4.1 消息类型

支持消息类型：
1. `message`
2. `broadcast`
3. `shutdown_request`
4. `shutdown_response`
5. `plan_approval_response`

### 4.2 ACK 状态

消息 ACK 状态：
1. `pending`
2. `delivered`
3. `processed`

### 4.3 work item 状态

work item 状态：
1. `queued`
2. `running`
3. `succeeded`
4. `failed`
5. `canceled`

### 4.4 执行语义（MVP 实现）

当前语义：
1. `message/broadcast` 不仅 ACK，会进入 teammate 的执行语义（自动入 work item 并执行）。
2. `shutdown_request` 收到后会回发 `shutdown_response`，并携带同一 `request_id`，再执行停止流程。
3. `plan_approval_response` 与审批请求关联，审批通过后才会派发对应工作项。

## 5. 存储模型

默认目录：
1. `.teams/`
2. `.tasks/`

团队配置：
1. `.teams/<team>/config.json`
2. `members` 中保留 `name/role/tool_policy`

消息存储：
1. `.teams/<team>/<member>_inbox.jsonl`
2. inbox 追加写入，配合锁保护。

并行工作项存储：
1. `.teams/<team>/work_items/work_items_<teammate>.jsonl`
2. 每个 teammate 独立分片，降低锁竞争。

任务板存储：
1. `.tasks/<team>/task_<id>.json`
2. `_meta.json` 维护 task id 递增。

## 6. 并发与一致性

并发策略：
1. 单 worker 线程内串行执行（`max_concurrency=1`）。
2. 多 worker 线程并行。
3. LLM 调用通过全局 semaphore 做并发闸门。

锁策略：
1. 使用目录锁（`mkdir` 原子创建）。
2. 支持 `timeout + stale reclaim`。
3. 任务板 claim 在锁内执行，防重复认领。

关键修复约束：
1. `create_team` 不再默认拉起所有 worker，避免干扰纯 claim 测试与竞态。
2. worker 在 fanout/message 等触发点按需启动。

## 7. 安全与权限

基础权限策略：
1. teammate 成员 `tool_policy` 必含 `role` 与 `tool_policy` 结构。
2. teammate 路径中 `Task` 永久禁止（denylist + 执行层双重过滤）。
3. 支持 delegate mode 下的工具调用限制（lead 只做编排）。

## 8. 运行时注入与会话恢复

运行时注入：
1. team runtime 摘要通过 system block 注入。
2. 不写入 user 轮次，不破坏历史压缩边界。

会话持久化：
1. `save_session` 导出 `teams_snapshot` 与并行工作索引。
2. `load_session` 触发 `import_state` 恢复团队状态。
3. 恢复时避免重复拉起同名 worker。
4. 恢复时会将 running work requeue 为 queued。

## 9. 测试与验收口径

MVP 验收重点：
1. Team 工具协议返回统一（success/error 形状一致）。
2. `message/broadcast` 可触发 teammate 执行。
3. `shutdown_request/response` request_id 关联可验证。
4. 并行执行有效（多 worker 并行，oneshot 兼容）。
5. claim 竞争场景无重复认领。
6. 会话恢复不重复拉起 worker。

## 10. 已知限制（MVP 保留）

1. 终端交互暂不支持完整 teammate 焦点切换 UI（键盘导航体验未复刻）。
2. in-process teammate 不是完整独立会话恢复（当前为状态恢复）。
3. shutdown 协议是可用基线，未扩展复杂拒绝/协商状态机。
4. 全量 `pytest` 仍受非 Teams 目录测试收集路径影响，需后续统一测试入口策略。

## 11. 配置项

关键环境变量：
1. `ENABLE_AGENT_TEAMS`（总开关）
2. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`（兼容开关）
3. `AGENT_TEAMS_STORE_DIR`
4. `AGENT_TASKS_STORE_DIR`
5. `TEAMMATE_MODE`（`auto|in-process|tmux`）
6. `TEAM_DELEGATE_MODE`
7. `TEAM_LLM_MAX_CONCURRENCY`

---

该文档为当前代码实现对齐版本。若后续进入非 MVP 阶段（完整交互 UI、会话级恢复、多进程隔离），需在此文档上继续版本化扩展。
