# Skill Evolution — 数据类型与配置

**文件：** `extensions/skill_evolution/types.py`, `extensions/skill_evolution/config.py`

---

## 1. types.py

### 1.1 Enums

```python
class EvolutionState(str, Enum):
    STABLE = "stable"
    EVALUATING = "evaluating"
    COOLDOWN = "cooldown"
    PAUSED = "paused"

class ProposalStatus(str, Enum):
    PROPOSED = "proposed"        # 刚生成，尚未校验
    STAGED = "staged"            # 校验通过，Candidate 已创建
    EVALUATING = "evaluating"    # Candidate 观察中
    ACCEPTED = "accepted"        # 观察通过，已晋升
    REJECTED = "rejected"        # 观察失败，已回滚
    SUPERSEDED = "superseded"    # 被 Hotfix 覆盖

class ProposalType(str, Enum):
    USER_DIRECTED_HOTFIX = "user_directed_hotfix"
    AGENT_INFERRED = "agent_inferred"

class SkillState(str, Enum):
    STABLE = "stable"
    CANDIDATE = "candidate"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"

class FeedbackRoute(str, Enum):
    USER_HOTFIX_CANDIDATE = "user_hotfix_candidate"  # 关键词初筛通过，待 LLM 终判
    ABNORMAL_ROLLOUT = "abnormal_rollout"
    NORMAL_ROLLOUT = "normal_rollout"

class BatchReviewDecision(str, Enum):
    NO_UPDATE = "no_update"
    KEEP_COLLECTING = "keep_collecting"
    PROPOSE_PATCH = "propose_patch"

class ObservationResult(str, Enum):
    PASS = "pass"
    TARGET_ERROR = "target_error"
    HARD_FAILURE = "hard_failure"
    HUMAN_INTERVENTION = "human_intervention"
    IRRELEVANT = "irrelevant"    # 归属的 Skill 不匹配，跳过
```

### 1.2 Core Dataclasses

```python
@dataclass
class RolloutRecord:
    """从 Trace 聚合的任务执行摘要"""
    trace_id: str
    persistent_run_id: str        # f"{session_id}:{run_id}"，跨进程持久去重
    input_fingerprint: str        # SHA256(processed_input)[:12]
    skills_invoked: list[str]     # 本 run 调用的 Skill 名称列表
    attributing_skill: str | None # 归属 Skill（仅当恰好调用 1 个时）
    skill_version: str
    task_success: bool
    hard_error: bool              # model_error / tool_error_unrecoverable / token_budget
    human_intervention: bool      # AskUser 被调用且用户给了非空回复
    user_feedback_text: str | None = None
    is_explicit_correction: bool = False
    is_long_term_instruction: bool = False
    error_signatures: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class PatchOp:
    """局部补丁操作"""
    patch_type: str          # "replace" | "insert_after" | "append"
    target_section: str      # Markdown 标题文本（用于定位段落）
    old_text: str = ""       # replace 时匹配的原文本
    new_text: str = ""       # 新内容


@dataclass
class Proposal:
    """Skill 修改提案"""
    proposal_id: str                      # 格式: "HF-00001" 或 "P-00001"
    proposal_type: ProposalType
    target_skill: str                     # Skill 名称
    base_version: str                     # 修改基于的版本
    source_trace_ids: list[str]           # 来源轨迹
    problem: str                          # 发生了什么
    reason: str                           # 为什么 Skill 不足
    target_section: str                   # 修改的目标段落标题
    patch: PatchOp                        # 具体补丁
    expected_behavior: str                # 修改后应发生什么
    error_signature: str                  # 目标问题的标识 key（去重用）
    risk_level: str = "medium"
    status: ProposalStatus = ProposalStatus.PROPOSED
    user_instruction: str | None = None   # Hotfix 时填写用户原始指令
    rejection_reason: str | None = None
    failure_trace_ids: list[str] = field(default_factory=list)


@dataclass
class SkillVersionMeta:
    skill_id: str
    version: str                          # "v1", "v2", "v3-candidate", "v3"
    parent_version: str | None
    state: SkillState
    proposal_id: str | None = None
    source_type: str | None = None        # "user_directed_hotfix" | "agent_inferred"


@dataclass
class ReviewResult:
    decision: BatchReviewDecision
    proposal: Proposal | None = None
    reasoning: str = ""


@dataclass
class EvolutionStateRecord:
    """per-Skill 持久化演化状态，跨重启恢复"""
    skill_id: str
    state: str                     # EvolutionState 的值
    active_proposal_id: str | None
    lkg_version: str               # Last Known Good version
    current_version: str           # 当前 overlay 版本
    observer_relevant_pass_count: int = 0
    observer_total_relevant_count: int = 0
    cooldown_tasks_remaining: int = 0
    consecutive_rejections: int = 0
    overlay_active: bool = False
```

---

## 2. config.py

```python
@dataclass
class EvolutionConfig:
    enabled: bool = False

    # ---- Batch Review 阈值 ----
    minimum_abnormal_traces: int = 3
    minimum_distinct_runs: int = 2
    max_proposals_per_batch: int = 1

    # ---- Candidate 观察 ----
    minimum_relevant_tasks: int = 3     # ≥N 次相关 PASS → 晋升
    max_observation_tasks: int = 15     # ≥N 次相关但不够 PASS → EXPIRE
    lock_during_evaluation: bool = True # 观察期间禁止叠加新 Proposal

    # ---- 冷却期（任务计数）----
    tasks_after_accept: int = 3
    tasks_after_reject: int = 3

    # ---- 拒绝限制 ----
    max_consecutive_rejections: int = 2    # 连续 N 次 → PAUSED
    recent_rejected_proposals_in_prompt: int = 5

    # ---- Patch 约束 ----
    max_sections: int = 2
    allow_full_rewrite: bool = False

    # ---- 存储 ----
    rollout_retention_days: int = 30
    version_retention_count: int = 20
```
