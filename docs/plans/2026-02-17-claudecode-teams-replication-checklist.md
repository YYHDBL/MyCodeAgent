# Claude Code Teams 复刻清单（基于 v7/v8/v9）

> 参考来源：
> 1. 官方 Agent Teams 说明（你贴的文档）
> 2. `docs/learn-claude-code/agents/v7_background_agent.py`
> 3. `docs/learn-claude-code/agents/v8a_team_foundation.py`
> 4. `docs/learn-claude-code/agents/v8b_messaging.py`
> 5. `docs/learn-claude-code/agents/v8c_coordination.py`
> 6. `docs/learn-claude-code/agents/v9_autonomous_agent.py`

## 0. 目标定义（什么叫“复刻 Claude Teams”）

要达到“接近 Claude Code Teams”的标准，至少要具备 4 个支柱：
1. 持久 teammate + 点对点/广播消息 + 有状态 shutdown/approval 协议
2. 共享任务看板（任务依赖、claim、防并发冲突、状态推进）
3. 自治 teammate（idle 轮询、自动认领、被动唤醒）
4. lead 编排能力（任务分发、审批、汇总、清理）

当前仓库已经实现了并行 data plane，但还没形成完整“团队协作 control plane”。

---

## 1. 当前实现对照（现状）

### 1.1 已具备（可复用）

1. Team 基础工具：`TeamCreate/SendMessage/TeamStatus/TeamDelete`
2. 并行工作项：`TeamFanout/TeamCollect` + worker 实际执行 + `TurnExecutor`
3. ACK 三态：`pending/delivered/processed`
4. teammate 禁止 Task 递归（policy + denied_tools 双保险）
5. runtime 事件通过 system block 注入
6. 会话恢复避免重复拉起同名 worker
7. work item 分片存储 + 文件锁 + stale reclaim

### 1.2 与 Claude Teams 的核心差距

1. 缺少 `broadcast` 消息类型
2. 缺少 `shutdown_response` + `request_id` 的完整关闭协议
3. 缺少 `plan_approval_response` 工作流（审批前禁止执行）
4. 缺少共享任务看板（TaskCreate/Get/Update/List + 依赖解除）
5. 缺少 teammate 自治循环（idle + auto-claim）
6. 缺少 lead 的“纯委派模式”
7. 缺少 teammateMode（in-process/tmux/split-pane）体验层

---

## 2. 需要“重构”的部分（不是简单新增）

## R1. TeamManager 职责拆分（高优先级）

**现状问题**
- `core/team_engine/manager.py` 同时处理：消息、worker 生命周期、work item 编排、执行细节，职责过重。

**重构目标**
1. `MessageRouter`：message/broadcast/ack/shutdown 协议
2. `TaskBoardService`：任务看板 CRUD + 依赖 + claim
3. `WorkerSupervisor`：spawn/heartbeat/idle/shutdown/recover
4. `ApprovalService`：plan approval 状态机
5. `ExecutionService`：work item 执行（调用 `TurnExecutor`）

**改动文件**
- 重构：`core/team_engine/manager.py`
- 新增：
  - `core/team_engine/message_router.py`
  - `core/team_engine/task_board.py`
  - `core/team_engine/approval.py`
  - `core/team_engine/supervisor.py`

## R2. SendMessage 协议扩展（高优先级）

**现状问题**
- 仅支持点对点 `to_member`，协议字段不足。

**重构目标**
1. `type=message|broadcast|shutdown_request|shutdown_response|plan_approval_response`
2. 增加 `summary`（message/broadcast 必填）
3. 增加 `request_id`（shutdown/approval 关联）

**改动文件**
- 重构：`tools/builtin/send_message.py`
- 重构：`core/team_engine/protocol.py`
- 重构：`core/team_engine/manager.py`
- 重构：`prompts/tools_prompts/send_message_prompt.py`

## R3. TeamDelete 语义调整（中高优先级）

**现状问题**
- 当前 `TeamDelete` 偏“强制删队”，与 Claude cleanup 的“先关成员，再清理，否则失败”不一致。

**重构目标**
1. 新增 `TeamCleanup`（或给 TeamDelete 加 strict 模式）
2. 检查 active teammate，未全部 shutdown 则返回 `CONFLICT`
3. 支持 graceful close 超时与诊断信息

**改动文件**
- 重构：`tools/builtin/team_delete.py`
- 新增：`tools/builtin/team_cleanup.py`（推荐）
- 重构：`core/team_engine/manager.py`

## R4. TaskTool 语义分层（中优先级）

**现状问题**
- `TaskTool` 同时承载 oneshot/persistent/parallel，未来再加 approval/role 将持续膨胀。

**重构目标**
1. 保留 `Task`（兼容）
2. 新增 `TeamSpawn`（显式 teammate 生命周期管理）
3. `Task(parallel)` 只做 dispatch shortcut，不再承载团队治理语义

**改动文件**
- 重构：`tools/builtin/task.py`
- 新增：`tools/builtin/team_spawn.py`
- 重构：`agents/codeAgent.py`

---

## 3. 需要“新增”的核心能力（Claude Teams parity）

## A1. 消息协议全量复刻（必须）

**新增能力**
1. `broadcast` 一对多消息
2. `shutdown_request/shutdown_response`（带 request_id）
3. `plan_approval_response`（approve/reject + feedback）

**新增测试**
- `tests/test_team_message_protocol.py`
- `tests/test_team_broadcast.py`
- `tests/test_team_shutdown_protocol.py`
- `tests/test_team_plan_approval_messages.py`

## A2. 共享任务看板（必须）

**新增能力**
1. Task board 数据结构：`id/subject/description/status/owner/blocked_by/blocks`
2. 工具：`TaskCreate/TaskGet/TaskUpdate/TaskList`（teams 域）
3. claim 原子性（多 worker 并发 claim 无重复）
4. 依赖解除：上游任务完成后自动解锁下游

**新增文件**
- `core/team_engine/task_board_store.py`
- `tools/builtin/team_task_create.py`
- `tools/builtin/team_task_get.py`
- `tools/builtin/team_task_update.py`
- `tools/builtin/team_task_list.py`

**新增测试**
- `tests/test_team_task_board.py`
- `tests/test_team_task_dependencies.py`
- `tests/test_team_task_claim_race.py`

## A3. teammate 自治循环（必须）

**新增能力**
1. idle 状态轮询（inbox + task board）
2. auto-claim unclaimed tasks
3. 被消息唤醒恢复工作
4. idle 超时策略 + reason 可观测

**新增/重构文件**
- 重构：`core/team_engine/worker.py`
- 重构：`core/team_engine/manager.py`

**新增测试**
- `tests/test_team_worker_idle_wakeup.py`
- `tests/test_team_worker_auto_claim.py`

## A4. plan approval 执行闸门（必须）

**新增能力**
1. teammate 可进入 `plan_only` 模式
2. 未批准前禁止写操作（或禁止 execution）
3. lead 审批消息回传后解锁执行

**新增/重构文件**
- 新增：`core/team_engine/approval.py`
- 重构：`core/team_engine/worker.py`
- 新增：`tools/builtin/team_approve_plan.py`（可选，或走 SendMessage type）

**新增测试**
- `tests/test_team_plan_approval_gate.py`

## A5. 通知总线优化（高优先级）

**新增能力**
1. 从“轮询 drain_events”升级为“事件队列 + 去重 + 限流摘要”
2. runtime block 注入增加：idle teammates、待审批计划、阻塞任务数

**新增测试**
- `tests/test_team_runtime_summary_advanced.py`

---

## 4. 体验层（可选但建议，接近官方）

## U1. teammateMode

**新增能力**
1. `teammateMode=auto|in-process|tmux`
2. CLI flag `--teammate-mode`
3. 不支持时回退 in-process + 告警

**改动文件**
- `core/config.py`
- `scripts/chat_test_agent.py`
- 新增 `core/team_engine/display_mode.py`

## U2. 直接与队友交互

**新增能力**
1. 主界面选择队友发送 direct message
2. 最小化实现可先做 `/team msg <name> ...` 命令

---

## 5. 配置与兼容（建议）

## C1. 环境变量兼容

1. 兼容 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`（映射到 `ENABLE_AGENT_TEAMS`）
2. 保持现有变量不破坏

## C2. 存储路径策略

1. 支持 `~/.claude/teams` 与项目内 `.teams` 双模式（配置切换）
2. 默认继续项目内，降低风险

---

## 6. 推荐实施顺序（按价值/风险）

### Phase 1（必须）
1. A1 消息协议全量复刻
2. A2 共享任务看板
3. A3 teammate 自治循环

### Phase 2（必须）
1. A4 plan approval 闸门
2. R3 TeamDelete/cleanup 语义

### Phase 3（建议）
1. R1 TeamManager 职责拆分
2. A5 通知总线增强
3. C1 环境变量兼容

### Phase 4（体验）
1. U1 teammateMode
2. U2 direct teammate 交互

---

## 7. 验收基线（你可以用来判定“复刻完成”）

满足以下 10 条即可认为“Claude Teams 核心复刻完成”：
1. 支持 message + broadcast
2. shutdown request/response 带 request_id
3. plan approval 可阻塞执行
4. 共享任务看板 CRUD 完整
5. 任务依赖可阻塞/解锁
6. 多 teammate 并发 claim 无重复领取
7. teammate 空闲后可自动认领新任务
8. runtime 能显示任务/消息/审批摘要
9. cleanup 遵循“先关闭成员再清理”
10. `/save` `/load` 后团队状态可继续推进，不重复拉起 worker

---

## 8. 对当前仓库的明确结论

当前版本是：
- **并行执行 MVP：已达标**
- **Claude Teams 完整复刻：未达标**

距离“完整复刻”最关键的缺口：
1. **共享任务看板 + 自动认领（A2/A3）**
2. **消息协议全量（A1）**
3. **审批闸门（A4）**

优先把这三块补齐，再做 tmux/display mode 这类体验层。
