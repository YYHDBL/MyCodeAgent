# Skill Evolution — 主状态机与跨重启恢复

**文件：** `extensions/skill_evolution/state_machine.py`

---

## 1. 职责

协调所有子模块，统一入口。每个 Skill 独立维护一个 `EvolutionStateRecord` + 一个 `CandidateObserver` 实例。跨重启通过 `state.json` 恢复。

---

## 2. 接口

```python
class SkillEvolutionManager:
    def __init__(
        self,
        skill_loader: SkillLoader,
        llm: HelloAgentsLLM,
        config: EvolutionConfig,
        overlay_dir: Path,                      # memory/skill_evolution/active/
        on_skills_changed: Callable[[], None] | None = None,  # ← 回调，通知 host 刷新 prompt
    )
    def load_state(self)                        # 从 state.json 恢复跨重启状态
    def save_state(self)                        # 原子写入 state.json
    def on_run_finished(
        self,
        trace_events: list[dict],
        session_id: str,
        run_id: int,
        processed_input: str,
    )                                           # 主入口（全量 try/except 隔离）
```

**内部属性：**

```python
self._states: dict[str, EvolutionStateRecord]     # per-skill 状态
self._observers: dict[str, CandidateObserver]      # per-skill observer 实例
self._proposal_managers: dict[str, ProposalManager] # per-skill proposal 管理
self._hotfix_gen: HotfixGenerator
self._review_agent: BatchReviewAgent
self._buffer: AbnormalTrajectoryBuffer
self._store: SkillVersionStore
self._on_skills_changed = on_skills_changed        # 回调，替代 host._refresh_skills_prompt()
```

---

## 3. 核心流程 (`on_run_finished`)

以下流程中 `pm` = `self._get_proposal_manager(skill_name)`，`observer` = `self._get_observer(skill_name)`。

```
1. Adapter: trace_events → RolloutRecord
   └─ persistent_run_id = f"{session_id}:{run_id}"
   └─ input_fingerprint = SHA256(processed_input)[:12]
   └─ skills_invoked, attributing_skill

2. if attributing_skill is None → return (跳过)

3. skill_name = attributing_skill
   state = self._states.get(skill_name) or new EvolutionStateRecord(skill_name, "STABLE")

4. FeedbackRouter.route(rollout)

5. switch(route):

   ┌─ USER_HOTFIX_CANDIDATE ─────────────────────────────┐
   │  proposal = HotfixGenerator.generate(...)            │
   │  if proposal is None → return (LLM 终判拒绝)          │
   │  if state == EVALUATING → abort_candidate(skill)     │
   │  store.ensure_overlay_exists(skill)                  │
   │  store.snapshot_current(skill)                       │
   │  store.apply_patch(skill, proposal.patch)            │
   │  skill_loader.set_overlay_dir(overlay_dir)           │
   │  _notify_skills_changed()                            │  ← 回调，不直接调 host
   │  state.state = "STABLE"                              │
   │  state.lkg_version = store.get_current_version(skill) │
   │  state.current_version = state.lkg_version            │
   │  state.cooldown_tasks_remaining = 0                   │
   │  save_state()                                        │
   │  record_success(skill, rollout.summary)               │  ← 成功轨迹存证
   │  emit trace("hotfix_applied")                        │
   └──────────────────────────────────────────────────────┘

    ┌─ ABNORMAL_ROLLOUT ──────────────────────────────────┐
    │                                                      │
    │  if state.state == "EVALUATING":                     │
    │    observer = self._get_observer(skill_name)          │
    │    result = observer.observe(rollout, active_proposal)│
    │    if result == IRRELEVANT → return                  │
    │    if result == PASS:                                │
    │      if observer.is_observation_complete():          │
    │        promote(skill)                                │
    │      elif observer.is_exceeded():                    │
    │        rollback(skill, "EXPIRED")                    │
    │      return  # ← 不追加到 buffer                     │
    │    # result is TARGET_ERROR/HARD_FAILURE/            │
    │    #            HUMAN_INTERVENTION                    │
    │    rollback(skill, str(result))                      │
    │    # 回滚时不追加到 buffer，避免污染下一轮 review      │
    │    return                                            │
   │                                                      │
   │  # 只有在 STABLE/COOLDOWN 状态下才追加到 buffer       │
   │  if state.state in ("STABLE", "COOLDOWN"):           │
   │    buffer.append(rollout)                            │
   │                                                      │
   │  if state.state == "STABLE" and buffer.should_review(skill):│
   │    try:                                              │
   │      decision = review_agent.review(                 │
   │          current_skill=store.read_skill(skill),       │
   │          abnormal_rollouts=buffer.get_batch(skill),   │
   │          success_summaries=get_recent_successes(skill, 3),│
   │          rejected_proposals=pm.get_recent_rejected(5),│
   │      )                                               │
   │      if decision == NO_UPDATE:                       │
   │        buffer.mark_consumed(                         │
   │            skill,                                    │
   │            [r.persistent_run_id for r in buffer.get_batch(skill)]│
   │        )                                             │
   │      if decision == KEEP_COLLECTING:                 │
   │        pass  # buffer 保持不变，等待更多异常轨迹       │
    │      if decision == PROPOSE_PATCH:                   │
    │        if validate_proposal(decision.proposal, store.read_skill(skill)) and not pm.is_duplicate(decision.proposal):│
   │          pm.propose(proposal)                        │
   │          store.ensure_overlay_exists(skill)           │
   │          content = patcher.apply_patch(              │
   │              store.read_skill(skill), proposal.patch) │
   │          store.create_candidate(skill, content, ver)  │
   │          pm.stage(proposal.proposal_id)              │
   │          pm.evaluate(proposal.proposal_id)            │
   │          observer = self._get_observer(skill)         │
   │          observer.reset()                             │
   │          skill_loader.set_overlay_dir(overlay_dir)    │
   │          _notify_skills_changed()                     │
   │          state.state = "EVALUATING"                   │
   │          state.active_proposal_id = proposal.proposal_id│
   │          state.current_version = ver                  │
   │          emit trace("proposal_proposed")               │
   │          emit trace("candidate_evaluating")            │
   │    except Exception:                                 │
   │      logger.warning("Batch review failed for %s", skill, exc_info=True)│
   │      # buffer 保留不消费                            │
   │                                                      │
   │  save_state()                                        │
   └──────────────────────────────────────────────────────┘

    ┌─ NORMAL_ROLLOUT ────────────────────────────────────┐
    │  if state.state == "EVALUATING":                     │
    │    observer = self._get_observer(skill_name)          │
    │    result = observer.observe(rollout, active_proposal)│
    │    if result == IRRELEVANT → (跳过)                  │
    │    elif result == PASS:                              │
    │      if observer.is_observation_complete():          │
    │        promote(skill)                                │
    │      elif observer.is_exceeded():                    │
    │        rollback(skill, "EXPIRED")                    │
    │    else → rollback(skill, str(result))               │
    │                                                      │
    │  if state.cooldown_tasks_remaining > 0:              │
    │    state.cooldown_tasks_remaining -= 1               │
    │                                                      │
    │  record_success(skill_name, rollout.summary)          │  ← 成功轨迹存证
    │  save_state()                                        │
    └──────────────────────────────────────────────────────┘
```

---

## 4. Review 决策的完整动作语义

| 决策 | 动作 | buffer 变化 |
|------|------|-----------|
| `NO_UPDATE` | `buffer.mark_consumed(skill, all_run_ids)` | 本批次全部标记 consumed=true，不再参与后续 review |
| `KEEP_COLLECTING` | 无操作 | buffer 保持不变，下一次 `should_review()` 时同一批轨迹仍在 |
| `PROPOSE_PATCH` | 生成 Candidate，进入 EVALUATING | buffer 不消费 — Candidate 晋升后消费，回滚后清除问题轨迹 |

> Candidate 晋升后，应调用 `buffer.mark_consumed()` 消费促成此 Proposal 的异常轨迹。回滚后也应消费（已被此 REJECTED Proposal 引用，不应再次触发同一 review）。

---

## 5. 晋升与回滚

```python
def promote(self, skill_name: str):
    state = self._states[skill_name]
    pm = self._get_proposal_manager(skill_name)
    self._store.apply_candidate_as_stable(skill_name, state.current_version)
    pm.accept(state.active_proposal_id)
    proposal = pm.load(state.active_proposal_id)
    self._buffer.mark_consumed(skill_name, proposal.source_trace_ids)
    state.state = "STABLE"
    state.lkg_version = state.current_version
    state.active_proposal_id = None
    state.cooldown_tasks_remaining = self._config.tasks_after_accept
    state.consecutive_rejections = 0
    self._skill_loader.set_overlay_dir(self._overlay_dir)
    self._notify_skills_changed()
    self.save_state()


def rollback(self, skill_name: str, reason: str, failure_trace_id: str | None = None):
    state = self._states[skill_name]
    pm = self._get_proposal_manager(skill_name)
    self._store.restore_version(skill_name, state.lkg_version)
    pm.reject(state.active_proposal_id, reason,
              failure_trace_ids=[failure_trace_id] if failure_trace_id else [])
    proposal = pm.load(state.active_proposal_id)
    self._buffer.mark_consumed(skill_name, proposal.source_trace_ids)
    state.state = "STABLE"
    state.current_version = state.lkg_version
    state.active_proposal_id = None
    state.cooldown_tasks_remaining = self._config.tasks_after_reject
    state.consecutive_rejections += 1
    if state.consecutive_rejections >= self._config.max_consecutive_rejections:
        state.state = "PAUSED"
    self._skill_loader.set_overlay_dir(self._overlay_dir)
    self._notify_skills_changed()
    self.save_state()


def abort_candidate(self, skill_name: str):
    """Hotfix 打断 Candidate 观察。"""
    state = self._states[skill_name]
    pm = self._get_proposal_manager(skill_name)
    self._store.restore_version(skill_name, state.lkg_version)
    pm.supersede(state.active_proposal_id)
    state.state = "STABLE"
    state.current_version = state.lkg_version
    state.active_proposal_id = None
    observer = self._get_observer(skill_name)
    observer.reset()
    self.save_state()
```

---

## 6. 成功轨迹存储

### 6.1 设计

每个 Skill 维护一个近期成功轨迹摘要的环形缓存。

**文件：** `memory/skill_evolution/active/<skill_name>/.evolution/successes.jsonl`

**格式：**
```json
{"persistent_run_id": "s-xxx:5", "summary": "Successfully reviewed code...", "timestamp": "2026-06-15T10:00:00Z"}
```

### 6.2 接口

```python
class RecentSuccessStore:
    """per-skill 近期成功轨迹缓存，FIFO，最多保留 max_entries 条。"""
    
    def __init__(self, store_path: Path, max_entries: int = 5)
    def record(self, persistent_run_id: str, summary: str)
    def get_recent(self, n: int) -> list[str]    # 最近 n 条 summary
    def clear(self)
```

### 6.3 在 state_machine 中的集成

```python
class SkillEvolutionManager:
    def __init__(self, ...):
        self._success_stores: dict[str, RecentSuccessStore] = {}

    def _get_success_store(self, skill_name: str) -> RecentSuccessStore:
        if skill_name not in self._success_stores:
            path = self.overlay_dir / skill_name / ".evolution" / "successes.jsonl"
            self._success_stores[skill_name] = RecentSuccessStore(path)
        return self._success_stores[skill_name]

    def record_success(self, skill_name: str, summary: str):
        """NORMAL_ROLLOUT 或 Hotfix 成功后调用。"""
        self._get_success_store(skill_name).record(...)
    # 重启后 successes.jsonl 自然保留，无需单独恢复
```

---

## 7. per-Skill 子模块映射

```python
class SkillEvolutionManager:
    def __init__(self, ...):
        self._observers: dict[str, CandidateObserver] = {}
        self._proposal_managers: dict[str, ProposalManager] = {}

    def _get_observer(self, skill_name: str) -> CandidateObserver:
        if skill_name not in self._observers:
            self._observers[skill_name] = CandidateObserver(self._config)
        return self._observers[skill_name]

    def _get_proposal_manager(self, skill_name: str) -> ProposalManager:
        if skill_name not in self._proposal_managers:
            proposals_dir = self._overlay_dir / skill_name / ".evolution" / "proposals"
            self._proposal_managers[skill_name] = ProposalManager(proposals_dir)
        return self._proposal_managers[skill_name]
```

这样 Skill A 在 EVALUATING 期间，Skill B 可以并行进入 EVALUATING，各自的 observer 和 proposal_manager 互不干扰。

---

## 8. 跨重启恢复

### 8.1 load_state()

```python
def load_state(self):
    path = self.overlay_dir / "state.json"
    if not path.exists():
        self._states = {}
        return

    data = json.loads(path.read_text())
    for skill_name, raw in data.get("skills", {}).items():
        record = EvolutionStateRecord(**raw)

        # 一致性校验
        overlay_skill = self.overlay_dir / skill_name / "SKILL.md"
        if record.state == "EVALUATING" and not overlay_skill.exists():
            record.state = "STABLE"
            record.active_proposal_id = None

        # 恢复 observer 计数
        if record.state == "EVALUATING" and record.active_proposal_id:
            pm = self._get_proposal_manager(skill_name)
            proposal = pm.load(record.active_proposal_id)
            if proposal:
                observer = self._get_observer(skill_name)
                observer.restore(
                    record.observer_relevant_pass_count,
                    record.observer_total_relevant_count,
                )

        self._states[skill_name] = record
```

### 8.2 ProposalManager 存储结构

每个 skill 的 proposals 目录独立：
```
.evolution/proposals/
├── HF-00001.json
├── P-00001.json
└── P-00002.json
```

`ProposalManager.load()` 方法定义见 `_07_PROPOSAL_AND_OBSERVER.md` 第 1.3 节。

---

## 9. host 回调而非直接依赖

```python
# __init__ 中
self._on_skills_changed = on_skills_changed

def _notify_skills_changed(self):
    """通知 host 刷新 prompt 缓存。替代直接调用 host._refresh_skills_prompt()。"""
    if self._on_skills_changed:
        self._on_skills_changed()
```

对应的 `runtime/factory.py` 初始化：
```python
host._skill_evolution_manager = SkillEvolutionManager(
    ...,
    on_skills_changed=lambda: host._refresh_skills_prompt(),
)
```

---

## 10. Exception 隔离

```python
def on_run_finished(self, ...):
    try:
        self._on_run_finished_impl(...)
    except Exception:
        logger.warning("Skill Evolution on_run_finished failed", exc_info=True)
        # 绝不向上抛出
```

- 外层 try/except：确保主任务结果不受影响
- 内层 Review LLM try/except：Review 异常时 buffer 保留，下次重试

---

## 11. PAUSED 状态

- 触发：连续 `max_consecutive_rejections`（默认 2）次 Proposal 被 REJECTED
- 行为：Batch Review 不触发（`should_review` 前检查 state != PAUSED）
- User Hotfix 仍可用
- 退出：手动删除 state.json 中该 Skill 记录，或未来版本增加 API
