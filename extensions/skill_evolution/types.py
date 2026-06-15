""":enum EvolutionState    技能演化主状态机状态
:enum ProposalStatus    提案生命周期状态
:enum ProposalType      USER_DIRECTED_HOTFIX vs AGENT_INFERRED
:enum SkillState        单个 Skill 版本状态
:enum FeedbackRoute     反馈路由结果
:enum BatchReviewDecision 批量审查决策
:enum ObservationResult Candidate 观察结果

:class RolloutRecord      从 Trace 聚合的任务执行摘要
:class PatchOp            局部补丁操作
:class Proposal           Skill 修改提案
:class SkillVersionMeta   版本元数据
:class ReviewResult       Batch Review 结果
:class EvolutionStateRecord per-Skill 持久化演化状态
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EvolutionState(str, Enum):
    STABLE = "stable"
    EVALUATING = "evaluating"
    COOLDOWN = "cooldown"
    PAUSED = "paused"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    STAGED = "staged"
    EVALUATING = "evaluating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ProposalType(str, Enum):
    USER_DIRECTED_HOTFIX = "user_directed_hotfix"
    AGENT_INFERRED = "agent_inferred"


class FeedbackRoute(str, Enum):
    USER_HOTFIX_CANDIDATE = "user_hotfix_candidate"
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
    IRRELEVANT = "irrelevant"


# ---------------------------------------------------------------------------
# Core Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RolloutRecord:
    trace_id: str
    persistent_run_id: str
    input_fingerprint: str
    skills_invoked: list[str]
    attributing_skill: str | None
    skill_version: str
    task_success: bool
    hard_error: bool
    human_intervention: bool
    user_feedback_text: str | None = None
    is_explicit_correction: bool = False
    is_long_term_instruction: bool = False
    error_signatures: list[str] = field(default_factory=list)
    summary: str = ""
    feedback_route: str = ""


@dataclass
class PatchOp:
    patch_type: str
    target_section: str
    old_text: str = ""
    new_text: str = ""


@dataclass
class Proposal:
    proposal_id: str
    proposal_type: ProposalType
    target_skill: str
    base_version: str
    source_trace_ids: list[str]
    problem: str
    reason: str
    target_section: str
    patch: PatchOp
    expected_behavior: str
    error_signature: str
    risk_level: str = "medium"
    status: ProposalStatus = ProposalStatus.PROPOSED
    user_instruction: str | None = None
    rejection_reason: str | None = None
    failure_trace_ids: list[str] = field(default_factory=list)


@dataclass
class SkillVersionMeta:
    skill_id: str
    version: str
    parent_version: str | None
    state: str
    proposal_id: str | None = None
    source_type: str | None = None


@dataclass
class ReviewResult:
    decision: BatchReviewDecision
    proposal: Proposal | None = None
    reasoning: str = ""


@dataclass
class EvolutionStateRecord:
    skill_id: str
    state: str = "stable"
    active_proposal_id: str | None = None
    lkg_version: str = ""
    current_version: str = ""
    observer_relevant_pass_count: int = 0
    observer_total_relevant_count: int = 0
    cooldown_tasks_remaining: int = 0
    consecutive_rejections: int = 0
    overlay_active: bool = False


__all__ = [
    "EvolutionState",
    "ProposalStatus",
    "ProposalType",
    "FeedbackRoute",
    "BatchReviewDecision",
    "ObservationResult",
    "RolloutRecord",
    "PatchOp",
    "Proposal",
    "SkillVersionMeta",
    "ReviewResult",
    "EvolutionStateRecord",
]
