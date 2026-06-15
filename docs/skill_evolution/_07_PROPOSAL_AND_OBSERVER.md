# Skill Evolution — Proposal 管理与 Candidate 观察

**文件：** `extensions/skill_evolution/evolution/proposal_manager.py`, `extensions/skill_evolution/evolution/observer.py`

---

## 1. ProposalManager

### 1.1 职责

管理 **单个 Skill** 的 Proposal 完整生命周期。每个 Skill 独立一个 `ProposalManager` 实例，`SkillEvolutionManager` 内部维护 `dict[str, ProposalManager]` 映射。每个 Proposal 保存为独立 JSON 文件，被拒绝的 Proposal 追加到 rejected.jsonl。

### 1.2 接口

```python
class ProposalManager:
    def __init__(self, proposals_dir: Path):
        """
        proposals_dir: memory/skill_evolution/active/<skill_name>/.evolution/proposals/
        """

    def propose(self, proposal: Proposal):
        """保存为 proposals/<proposal_id>.json，状态 PROPOSED。"""

    def stage(self, proposal_id: str):
        """→ STAGED。"""

    def evaluate(self, proposal_id: str):
        """→ EVALUATING。"""

    def accept(self, proposal_id: str):
        """→ ACCEPTED。"""

    def reject(self, proposal_id: str, reason: str, failure_trace_ids: list[str]):
        """→ REJECTED，追加到 ../rejected.jsonl。"""

    def supersede(self, proposal_id: str):
        """→ SUPERSEDED（被 Hotfix 覆盖）。"""

    def get_active(self) -> Proposal | None:
        """返回当前状态为 EVALUATING 的 Proposal。"""

    def load(self, proposal_id: str) -> Proposal | None:
        """从 proposals/<proposal_id>.json 反序列化加载。用于跨重启恢复。"""

    def get_recent_rejected(self, n: int) -> list[Proposal]:
        """从 ../rejected.jsonl 读取最近 N 条。"""

    def is_duplicate(self, proposal: Proposal) -> bool:
        """指纹匹配：(error_signature, target_section, patch_type)。"""
```

### 1.3 load() 实现

```python
def load(self, proposal_id: str) -> Proposal | None:
    file_path = self._proposals_dir / f"{proposal_id}.json"
    if not file_path.exists():
        return None
    data = json.loads(file_path.read_text())
    # 反序列化嵌套 PatchOp
    data["patch"] = PatchOp(**data["patch"])
    data["proposal_type"] = ProposalType(data["proposal_type"])
    data["status"] = ProposalStatus(data["status"])
    return Proposal(**data)
```

### 1.4 去重逻辑

```python
def is_duplicate(self, proposal: Proposal) -> bool:
    fingerprint = (proposal.error_signature, proposal.target_section, proposal.patch.patch_type)
    for rejected in self.get_recent_rejected(n=10):
        rf = (rejected.error_signature, rejected.target_section, rejected.patch.patch_type)
        if fingerprint == rf:
            return True
    return False
```

### 1.4 Proposal ID 格式

```
HF-00001  → User-Directed Hotfix
HF-00002  → User-Directed Hotfix (第2次)
P-00001   → Agent-Inferred Proposal
P-00002   → Agent-Inferred Proposal (第2次)
```

从 `proposals/` 目录中扫描已有文件确定下一个序号。

---

## 2. CandidateObserver

### 2.1 职责

监控 **单个** Skill 的 Candidate 版本在后继任务中的表现。与 `ProposalManager` 一样，每个 Skill 独立一个 `CandidateObserver` 实例。`SkillEvolutionManager` 内部维护 `dict[str, CandidateObserver]` 映射。

### 2.2 接口

```python
class CandidateObserver:
    def __init__(self, config: EvolutionConfig):
        self._relevant_pass_count: int = 0
        self._total_relevant_count: int = 0

    def observe(
        self, rollout: RolloutRecord, proposal: Proposal
    ) -> ObservationResult:
        """
        观察单次任务结果：
        
        1. 不相关检查（优先于一切）：
           proposal.target_skill not in rollout.skills_invoked
           → IRRELEVANT（跳过，不计入任何计数）
        
        2. 相关任务才做错误检查：
           self._total_relevant_count += 1
           detect_error_signature(rollout, proposal) → TARGET_ERROR
           rollout.hard_error → HARD_FAILURE
           rollout.human_intervention → HUMAN_INTERVENTION
           否则 → PASS (self._relevant_pass_count += 1)
        """

    def is_observation_complete(self) -> bool:
        """≥ minimum_relevant_tasks(3) 次相关 PASS → True（晋升）"""
        return self._relevant_pass_count >= self.config.minimum_relevant_tasks

    def is_exceeded(self) -> bool:
        """≥ max_observation_tasks(15) 次相关但不够 PASS → True（过期回滚）"""
        return self._total_relevant_count >= self.config.max_observation_tasks

    def reset(self):
        self._relevant_pass_count = 0
        self._total_relevant_count = 0

    def restore(self, relevant_pass: int, total_relevant: int):
        """跨重启恢复计数。"""
        self._relevant_pass_count = relevant_pass
        self._total_relevant_count = total_relevant
```

### 2.3 裁决表

| 条件 | 结果 | 后续动作 |
|------|------|---------|
| ≥3 次相关 PASS | 观察完成 | **PROMOTE** Candidate → Stable, Proposal ACCEPTED |
| 某次相关任务 TARGET_ERROR | 观察失败 | **ROLLBACK**, Proposal REJECTED |
| 某次相关任务 HARD_FAILURE | 观察失败 | **ROLLBACK**, Proposal REJECTED |
| 某次相关任务 HUMAN_INTERVENTION | 观察失败 | **ROLLBACK**, Proposal REJECTED |
| 累计 15 次相关但 <3 次 PASS | 观察过期 | **EXPIRE** 回滚到 LKG, Proposal SUPERSEDED（不是 REJECTED）|
| 不相关任务 | 跳过 | 不计入任何计数 |

### 2.4 设计原理

```
                 ┌──────────────────────┐
                 │  rollout 到达         │
                 └──────────┬───────────┘
                            │
                  target_skill in skills_invoked?
                   ┌────────┴────────┐
                   NO               YES
                   │                 │
                   ▼                 ▼
              IRRELEVANT       total_relevant++
              (跳过)              │
                        ┌────────┼────────┐
                    error?              PASS
                        │                 │
                 ┌──────┴──────┐    relevant_pass++
            TARGET_ERROR   HARD_FAILURE    │
            HUMAN_INTERVENTION            │
                 │                        │
                 ▼                        ▼
             ROLLBACK             is_observation_complete()?
             (立即)                     ┌──┴──┐
                                      YES    NO
                                       │      │
                                       ▼      ▼
                                   PROMOTE  继续观察
                                                 │
                                     is_exceeded()?
                                          ┌──┴──┐
                                         YES    NO
                                          │      │
                                          ▼      ▼
                                       EXPIRE  继续等待
```

无关任务**永不改变** Candidate 的命运——既不会让它被错误晋升，也不会让它被别人的错误拖累回滚。
