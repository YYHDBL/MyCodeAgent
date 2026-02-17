# AgentTeams Parallel Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 AgentTeams MVP 基础上落地“真实并行分工执行”，让多个 teammate 能并发领取工作项、独立执行并回传结果，而不是仅 ACK 消息。

**Architecture:** 保留当前 `CodeAgent + ToolRegistry + TeamManager + TeammateWorker + TurnExecutor` 主体，新增“工作项协议 + worker 执行回路 + 结果聚合 API”。lead 通过 Team 工具进行 fanout 和 collect，worker 在独立线程内调用 `TurnExecutor` 执行任务并写回 `processed + result` 事件。继续使用文件化 `.teams/` 存储，不引入分布式调度与复杂事务。

**Tech Stack:** Python 3.x、现有 `pytest`、`ToolRegistry`、`HistoryManager`、`session_store`、文件锁存储。

---

## Mandatory Rules (Must Follow)

1. **TurnExecutor integration is a hard prerequisite**
   - 并行功能实现前，必须先完成 worker 与 `TurnExecutor` 的真实执行集成。
   - 未接入 `TurnExecutor` 的 worker 仅 ACK 不执行，不能视为并行能力完成。

2. **Concurrency model**
   - 每个 worker 线程内保持 `max_concurrency=1`（线程内串行，简化一致性）。
   - 多 worker 线程并行执行。
   - 必须增加全局 LLM 并发闸门（如 `Semaphore`）与 rate-limit 退避，避免 API 429/超时雪崩。

3. **Work item storage sharding**
   - 不使用单一 `work_items.jsonl` 热点文件。
   - 按 teammate 分片：`work_items/work_items_<teammate>.jsonl`（或等价结构）。
   - 保留轻量索引/聚合视图供 collect 查询，避免全量扫描成为瓶颈。

4. **Task recursion ban for teammate**
   - teammate 绝对禁止 `Task`（防递归）。
   - 在 worker 执行路径中必须二次校验：`TurnExecutor` 工具过滤 + `tool_policy` denylist 双重生效。
   - 该约束需有专门测试覆盖，防止后续回归。

---

### Task 1: 并行工作项协议扩展

**Files:**
- Modify: `core/team_engine/protocol.py`
- Test: `tests/test_team_protocol_parallel.py`

**Step 1: Write the failing test**

```python
def test_parallel_work_item_status_constants():
    assert WORK_ITEM_STATUS_QUEUED == "queued"
    assert WORK_ITEM_STATUS_RUNNING == "running"
    assert WORK_ITEM_STATUS_SUCCEEDED == "succeeded"
    assert WORK_ITEM_STATUS_FAILED == "failed"
```

```python
def test_message_types_include_work_item():
    assert EVENT_WORK_ITEM_ASSIGNED in EVENT_TYPES
    assert EVENT_WORK_ITEM_COMPLETED in EVENT_TYPES
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_protocol_parallel.py -q`  
Expected: FAIL（缺少常量与事件类型）

**Step 3: Write minimal implementation**

- 在 `protocol.py` 增加：
  - 工作项状态：`queued/running/succeeded/failed/canceled`
  - 事件类型：`work_item_assigned/work_item_started/work_item_completed/work_item_failed`
  - `work_item` 基础 schema 校验辅助函数（最小字段：`work_id`, `title`, `instruction`）

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_protocol_parallel.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/team_engine/protocol.py tests/test_team_protocol_parallel.py
git commit -m "feat(agentteams): add parallel work-item protocol constants"
```

### Task 2: TeamStore 增加工作项持久化

**Files:**
- Modify: `core/team_engine/store.py`
- Test: `tests/test_team_store_parallel.py`

**Step 1: Write the failing test**

```python
def test_create_and_update_work_item(tmp_path):
    store = TeamStore(tmp_path)
    store.create_team("demo", members=[{"name": "lead"}])
    item = store.create_work_item("demo", owner="dev1", title="t", instruction="do x")
    updated = store.update_work_item_status("demo", item["work_id"], "running")
    assert updated["status"] == "running"
```

```python
def test_work_item_lock_is_exclusive(tmp_path):
    # 并发更新同一 work_item，不出现 json 损坏
    ...
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_store_parallel.py -q`  
Expected: FAIL（store 无 work item 方法）

**Step 3: Write minimal implementation**

- 在 `.teams/<team>/work_items/` 下新增分片存储：
  - `work_items_<teammate>.jsonl`（每个 teammate 独立工作项文件）
  - `work_items_<teammate>.lock`（对应分片锁）
  - 可选：`work_items_index.json`（轻量聚合索引）
- 新增方法：
  - `create_work_item(team, owner, title, instruction, payload=None)`
  - `list_work_items(team, owner=None, status=None)`
  - `update_work_item_status(team, work_id, status, result=None, error=None)`

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_store_parallel.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/team_engine/store.py tests/test_team_store_parallel.py
git commit -m "feat(agentteams): persist parallel work items in team store"
```

### Task 3: TeamManager 增加 fanout/collect 编排 API

**Files:**
- Modify: `core/team_engine/manager.py`
- Test: `tests/test_team_manager_parallel.py`

**Step 1: Write the failing test**

```python
def test_fanout_creates_work_items_and_assign_events(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    manager.create_team("demo", members=[{"name": "lead"}])
    manager.spawn_teammate("demo", "dev1")
    manager.spawn_teammate("demo", "dev2")
    result = manager.fanout_work(
        "demo",
        tasks=[
            {"owner": "dev1", "title": "impl", "instruction": "do impl"},
            {"owner": "dev2", "title": "test", "instruction": "do test"},
        ],
    )
    assert len(result["work_items"]) == 2
```

```python
def test_collect_work_returns_done_and_pending(tmp_path):
    ...
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_manager_parallel.py -q`  
Expected: FAIL（manager 无 fanout/collect）

**Step 3: Write minimal implementation**

- 在 `TeamManager` 增加：
  - `fanout_work(team_name, tasks)`：批量创建工作项并写 `assigned` 事件
  - `collect_work(team_name, work_ids=None)`：返回 `pending/running/succeeded/failed` 分组
  - `retry_failed_work(team_name, work_id)`（可选，MVP 最小重试）
- 保持所有异常映射到 `TeamManagerError(code, message)`

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_manager_parallel.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/team_engine/manager.py tests/test_team_manager_parallel.py
git commit -m "feat(agentteams): add fanout and collect orchestration APIs"
```

### Task 4: Worker 真正执行工作项（并发 data plane）

**Files:**
- Modify: `core/team_engine/worker.py`
- Modify: `core/team_engine/manager.py`
- Modify: `core/team_engine/turn_executor.py`
- Test: `tests/test_team_worker_parallel_execution.py`

**Step 1: Write the failing test**

```python
def test_worker_executes_assigned_work_item(tmp_path):
    manager = TeamManager(project_root=tmp_path)
    # 准备 team + worker + work_item
    # 断言 work_item 最终进入 succeeded，并有 result 字段
```

```python
def test_two_workers_run_tasks_in_parallel(tmp_path):
    # 构造 dev1/dev2 各自 sleep 任务
    # 断言总耗时显著小于串行总和（例如 < 1.5s 而不是 ~2.0s）
```

```python
def test_worker_uses_turn_executor_not_ack_only(tmp_path):
    # 若未调用 TurnExecutor，则测试失败（防止仅做 processed 标记）
```

```python
def test_teammate_cannot_call_task_in_worker_path(tmp_path):
    # worker 执行时 Task 调用被拒绝（双重过滤）
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_worker_parallel_execution.py -q`  
Expected: FAIL（worker 尚未执行 work item）

**Step 3: Write minimal implementation**

- worker 每轮：
  - 拉取 owner=自身 且 status=queued 的 work item
  - 原子更新为 `running`
  - 调用 `TurnExecutor` 执行（禁止 `Task`）
  - 写回 `succeeded/failed` 与 `result/error`
  - 发 `completed/failed` 事件
- 增加每 worker 的 `max_concurrency=1`（线程内串行，跨 worker 并行）
- 增加全局 LLM 并发闸门（例如 TeamManager 级 `Semaphore`）：
  - worker 调用 LLM 前 acquire，完成后 release
  - 对 429/限流错误执行指数退避并上报事件

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_worker_parallel_execution.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/team_engine/worker.py core/team_engine/manager.py core/team_engine/turn_executor.py tests/test_team_worker_parallel_execution.py
git commit -m "feat(agentteams): execute work items in teammate worker loop"
```

### Task 5: 新增 TeamFanout / TeamCollect 工具

**Files:**
- Create: `tools/builtin/team_fanout.py`
- Create: `tools/builtin/team_collect.py`
- Create: `prompts/tools_prompts/team_fanout_prompt.py`
- Create: `prompts/tools_prompts/team_collect_prompt.py`
- Modify: `agents/codeAgent.py`
- Test: `tests/test_team_parallel_tools.py`

**Step 1: Write the failing test**

```python
def test_team_fanout_tool_protocol(tmp_path):
    # 返回 success + work_items 列表
```

```python
def test_team_collect_tool_protocol(tmp_path):
    # 返回 pending/running/succeeded/failed 聚合结果
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_tools.py -q`  
Expected: FAIL（工具不存在）

**Step 3: Write minimal implementation**

- `TeamFanout`：参数校验 + `manager.fanout_work` + 协议封装
- `TeamCollect`：参数校验 + `manager.collect_work` + 协议封装
- 在 `CodeAgent._register_agent_teams_tools` 注册新工具（受开关控制）

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_tools.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add tools/builtin/team_fanout.py tools/builtin/team_collect.py prompts/tools_prompts/team_fanout_prompt.py prompts/tools_prompts/team_collect_prompt.py agents/codeAgent.py tests/test_team_parallel_tools.py
git commit -m "feat(agentteams): add fanout and collect tools for parallel teamwork"
```

### Task 6: TaskTool 增加并行分工快捷入口

**Files:**
- Modify: `tools/builtin/task.py`
- Modify: `prompts/tools_prompts/task_prompt.py`
- Test: `tests/test_task_tool_parallel_mode.py`

**Step 1: Write the failing test**

```python
def test_task_parallel_mode_dispatches_fanout(tmp_path):
    # mode=parallel 时调用 team_manager.fanout_work
```

```python
def test_task_parallel_mode_param_validation(tmp_path):
    # 缺少 team_name/tasks 时返回 INVALID_PARAM
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_task_tool_parallel_mode.py -q`  
Expected: FAIL

**Step 3: Write minimal implementation**

- 扩展 `Task.mode`：`oneshot|persistent|parallel`
- `parallel` 分支仅做“任务分发”，不阻塞等待完成
- 返回 `dispatch_id/work_items`，由 `TeamCollect` 轮询收集

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_task_tool_parallel_mode.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add tools/builtin/task.py prompts/tools_prompts/task_prompt.py tests/test_task_tool_parallel_mode.py
git commit -m "feat(agentteams): add task parallel dispatch mode"
```

### Task 7: Runtime 注入与状态可观测增强

**Files:**
- Modify: `agents/codeAgent.py`
- Modify: `core/context_engine/context_builder.py`
- Test: `tests/test_team_parallel_runtime_injection.py`

**Step 1: Write the failing test**

```python
def test_parallel_runtime_block_summarizes_progress():
    # system block 包含 running/succeeded/failed 摘要
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_runtime_injection.py -q`  
Expected: FAIL

**Step 3: Write minimal implementation**

- runtime block 每轮注入：
  - `work_item` 状态摘要（计数 + 最近失败）
  - 限流（最多 N 行）
- 保持 system 注入，不写 user/history

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_runtime_injection.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add agents/codeAgent.py core/context_engine/context_builder.py tests/test_team_parallel_runtime_injection.py
git commit -m "feat(agentteams): enrich runtime system block with parallel progress"
```

### Task 8: Session 恢复与并行集成验收

**Files:**
- Modify: `core/session_store.py`
- Modify: `core/team_engine/manager.py`
- Create: `tests/test_team_parallel_session_restore.py`
- Create: `tests/test_agent_teams_parallel_integration.py`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_restore_requeues_running_work_items(tmp_path):
    # 会话恢复后 running 项可恢复为 queued 或继续执行策略
```

```python
def test_parallel_end_to_end_flow(tmp_path):
    # fanout -> workers 并行执行 -> collect 全部 succeeded -> team delete
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_session_restore.py tests/test_agent_teams_parallel_integration.py -q`  
Expected: FAIL

**Step 3: Write minimal implementation**

- snapshot 增加并行 work items 索引（不嵌入大结果）
- load 时避免重复 worker；对 `running` 项做恢复策略（建议回退 queued）
- 文档补充并行分工示例与故障排查

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_team_parallel_session_restore.py tests/test_agent_teams_parallel_integration.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/session_store.py core/team_engine/manager.py tests/test_team_parallel_session_restore.py tests/test_agent_teams_parallel_integration.py README.md
git commit -m "feat(agentteams): finalize parallel execution restore and integration"
```

---

## Verification Matrix (Before Merge)

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_llm_temperature_policy.py \
  tests/test_task_tool.py \
  tests/test_turn_executor.py \
  tests/test_team_store.py \
  tests/test_team_manager.py \
  tests/test_team_worker.py \
  tests/test_team_worker_parallel_execution.py \
  tests/test_team_store_parallel.py \
  tests/test_team_manager_parallel.py \
  tests/test_team_tools.py \
  tests/test_team_parallel_tools.py \
  tests/test_task_tool_parallel_mode.py \
  tests/test_team_parallel_runtime_injection.py \
  tests/test_team_parallel_session_restore.py \
  tests/test_agent_teams_parallel_integration.py -q
```

Expected: 全绿；无协议破坏；oneshot/persistent 回归通过。

## Rollout / Rollback

1. 灰度开启：`ENABLE_AGENT_TEAMS=true` 且仅在测试环境启用并行工具。
2. 观察项：worker 并发数、失败率、平均完成时长、锁冲突率。
3. 快速回滚：`ENABLE_AGENT_TEAMS=false`，并行入口立即关闭，主链路保持不变。
