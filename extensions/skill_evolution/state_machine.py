"""Skill Evolution 主状态机。

协调所有子模块，每个 Skill 独立维护状态 + observer + proposal_manager。
跨重启通过 state.json 恢复。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from extensions.skill_evolution.config import EvolutionConfig
from extensions.skill_evolution.types import (
    EvolutionStateRecord,
    FeedbackRoute,
    ObservationResult,
    Proposal,
    ProposalStatus,
    ProposalType,
    RolloutRecord,
)
from extensions.skill_evolution.adapter import trace_events_to_rollout
from extensions.skill_evolution.feedback_router import FeedbackRouter
from extensions.skill_evolution.store import SkillVersionStore
from extensions.skill_evolution.validator import validate_proposal
from extensions.skill_evolution.patcher import apply_patch
from extensions.skill_evolution.evolution.buffer import AbnormalTrajectoryBuffer
from extensions.skill_evolution.evolution.observer import CandidateObserver
from extensions.skill_evolution.evolution.proposal_manager import ProposalManager
from extensions.skill_evolution.evolution.success_store import RecentSuccessStore
from extensions.skill_evolution.hotfix.generator import HotfixGenerator
from extensions.skill_evolution.evolution.review_agent import BatchReviewAgent

logger = logging.getLogger(__name__)


class SkillEvolutionManager:
    def __init__(
        self,
        skill_loader,
        llm,
        config: EvolutionConfig,
        overlay_dir: Path,
        on_skills_changed: Callable[[], None] | None = None,
        trace_logger=None,
    ):
        self._skill_loader = skill_loader
        self._llm = llm
        self._config = config
        self._overlay_dir = Path(overlay_dir)
        self._on_skills_changed = on_skills_changed
        self._trace_logger = trace_logger

        self._states: dict[str, EvolutionStateRecord] = {}
        self._observers: dict[str, CandidateObserver] = {}
        self._proposal_managers: dict[str, ProposalManager] = {}
        self._success_stores: dict[str, RecentSuccessStore] = {}

        self._hotfix_gen = HotfixGenerator(llm)
        self._review_agent = BatchReviewAgent(llm)
        self._buffer = AbnormalTrajectoryBuffer(self._overlay_dir)
        self._router = FeedbackRouter()

        project_root = getattr(skill_loader, "_project_root", Path("."))
        source_dir = Path(str(project_root)) / "skills"
        self._store = SkillVersionStore(
            source_skills_dir=source_dir,
            overlay_dir=self._overlay_dir,
        )

    # ------------------------------------------------------------------
    # 跨重启恢复
    # ------------------------------------------------------------------

    def load_state(self):
        path = self._overlay_dir / "state.json"
        if not path.exists():
            self._states = {}
            return

        data = json.loads(path.read_text())
        for skill_name, raw in data.get("skills", {}).items():
            record = EvolutionStateRecord(**raw)

            overlay_skill = self._overlay_dir / skill_name / "SKILL.md"
            if record.state == "EVALUATING" and not overlay_skill.exists():
                record.state = "stable"
                record.active_proposal_id = None

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

    def save_state(self):
        path = self._overlay_dir / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        skills_data: dict[str, dict] = {}
        for name, record in self._states.items():
            skills_data[name] = {
                "skill_id": record.skill_id,
                "state": record.state,
                "active_proposal_id": record.active_proposal_id,
                "lkg_version": record.lkg_version,
                "current_version": record.current_version,
                "observer_relevant_pass_count": record.observer_relevant_pass_count,
                "observer_total_relevant_count": record.observer_total_relevant_count,
                "cooldown_tasks_remaining": record.cooldown_tasks_remaining,
                "consecutive_rejections": record.consecutive_rejections,
                "overlay_active": record.overlay_active,
            }

        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({"skills": skills_data}, ensure_ascii=False, indent=2))
        tmp_path.replace(path)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def on_run_finished(
        self,
        trace_events: list[dict],
        session_id: str,
        run_id: int,
        processed_input: str,
    ):
        if not self._config.enabled:
            return
        try:
            self._on_run_finished_impl(trace_events, session_id, run_id, processed_input)
        except Exception:
            logger.warning("Skill Evolution on_run_finished failed", exc_info=True)

    def _on_run_finished_impl(
        self,
        trace_events: list[dict],
        session_id: str,
        run_id: int,
        processed_input: str,
    ):
        rollout = trace_events_to_rollout(trace_events, session_id, run_id, processed_input)
        if rollout.attributing_skill is None:
            return

        skill_name = rollout.attributing_skill
        state = self._states.get(skill_name)
        if state is None:
            state = EvolutionStateRecord(skill_id=skill_name, state="stable")
            self._states[skill_name] = state

        route = self._router.route(rollout)

        if route == FeedbackRoute.USER_HOTFIX_CANDIDATE:
            self._handle_hotfix_candidate(rollout, skill_name, state)
        elif route == FeedbackRoute.ABNORMAL_ROLLOUT:
            self._handle_abnormal(rollout, skill_name, state)
        else:
            self._handle_normal(rollout, skill_name, state)

        self.save_state()

    # ------------------------------------------------------------------
    # Hotfix
    # ------------------------------------------------------------------

    def _handle_hotfix_candidate(self, rollout: RolloutRecord, skill_name: str, state: EvolutionStateRecord):
        user_text = rollout.user_feedback_text or ""
        current_skill = self._store.read_skill(skill_name)
        proposal = self._hotfix_gen.generate(current_skill, user_text, rollout)
        if proposal is None:
            return

        if state.state == "EVALUATING":
            self._abort_candidate(skill_name)

        self._store.ensure_overlay_exists(skill_name)
        self._store.snapshot_current(skill_name)
        ver = self._store.apply_patch(skill_name, proposal.patch)

        pm = self._get_proposal_manager(skill_name)
        proposal.proposal_id = ""
        proposal.target_skill = skill_name
        proposal.base_version = self._store.get_current_version(skill_name)
        pm.propose(proposal)
        pm.accept(proposal.proposal_id)

        self._skill_loader.set_overlay_dir(self._overlay_dir)
        self._notify_skills_changed()

        state.state = "stable"
        state.lkg_version = ver
        state.current_version = ver
        state.cooldown_tasks_remaining = 0
        self._record_success(skill_name, rollout.persistent_run_id, rollout.summary)
        self.save_state()

        self._emit_trace("hotfix_applied", skill_name, {"proposal_id": proposal.proposal_id})

    # ------------------------------------------------------------------
    # Abnormal
    # ------------------------------------------------------------------

    def _handle_abnormal(self, rollout: RolloutRecord, skill_name: str, state: EvolutionStateRecord):
        if state.state == "EVALUATING":
            observer = self._get_observer(skill_name)
            pm = self._get_proposal_manager(skill_name)
            active_proposal = pm.get_active()
            if active_proposal:
                result = observer.observe(rollout, active_proposal)
                state.observer_relevant_pass_count = observer.relevant_pass_count
                state.observer_total_relevant_count = observer.total_relevant_count
                if result == ObservationResult.IRRELEVANT:
                    return
                if result == ObservationResult.PASS:
                    if observer.is_observation_complete():
                        self._promote(skill_name)
                    elif observer.is_exceeded():
                        self._rollback(skill_name, "EXPIRED")
                    return
                self._rollback(skill_name, str(result.value), rollout.persistent_run_id)
                return

        if state.state in ("stable", "cooldown"):
            self._buffer.append(rollout)

        if state.state == "stable" and self._buffer.should_review(
            skill_name,
            min_traces=self._config.minimum_abnormal_traces,
            min_runs=self._config.minimum_distinct_runs,
        ):
            self._trigger_review(skill_name, state)

        self.save_state()

    def _trigger_review(self, skill_name: str, state: EvolutionStateRecord):
        try:
            batch = self._buffer.get_batch(skill_name)
            success_sums = self._get_success_store(skill_name).get_recent(3)
            pm = self._get_proposal_manager(skill_name)
            rejected = pm.get_recent_rejected(self._config.recent_rejected_proposals_in_prompt)

            current_skill = self._store.read_skill(skill_name)
            decision = self._review_agent.review(current_skill, batch, success_sums, rejected)

            if decision.decision.value == "no_update":
                run_ids = [r.persistent_run_id for r in batch]
                self._buffer.mark_consumed(skill_name, run_ids)

            elif decision.decision.value == "propose_patch" and decision.proposal:
                proposal = decision.proposal
                if validate_proposal(proposal, current_skill) and not pm.is_duplicate(proposal):
                    proposal.target_skill = skill_name
                    pm.propose(proposal)

                    self._store.ensure_overlay_exists(skill_name)
                    new_content = apply_patch(current_skill, proposal.patch)
                    if new_content is None:
                        return
                    self._store.snapshot_current(skill_name)
                    ver = f"{self._store.get_current_version(skill_name)}-candidate"
                    self._store.create_candidate(skill_name, new_content, ver)

                    pm.stage(proposal.proposal_id)
                    pm.evaluate(proposal.proposal_id)

                    observer = self._get_observer(skill_name)
                    observer.reset()

                    self._skill_loader.set_overlay_dir(self._overlay_dir)
                    self._notify_skills_changed()

                    state.state = "EVALUATING"
                    state.active_proposal_id = proposal.proposal_id
                    state.current_version = ver

                    self._emit_trace("proposal_proposed", skill_name, {"proposal_id": proposal.proposal_id})
                    self._emit_trace("candidate_evaluating", skill_name, {"version": ver})

        except Exception:
            logger.warning("Batch review failed for %s", skill_name, exc_info=True)

    # ------------------------------------------------------------------
    # Normal
    # ------------------------------------------------------------------

    def _handle_normal(self, rollout: RolloutRecord, skill_name: str, state: EvolutionStateRecord):
        if state.state == "EVALUATING":
            observer = self._get_observer(skill_name)
            pm = self._get_proposal_manager(skill_name)
            active_proposal = pm.get_active()
            if active_proposal:
                result = observer.observe(rollout, active_proposal)
                state.observer_relevant_pass_count = observer.relevant_pass_count
                state.observer_total_relevant_count = observer.total_relevant_count
                if result == ObservationResult.IRRELEVANT:
                    pass
                elif result == ObservationResult.PASS:
                    if observer.is_observation_complete():
                        self._promote(skill_name)
                    elif observer.is_exceeded():
                        self._rollback(skill_name, "EXPIRED")
                else:
                    self._rollback(skill_name, str(result.value), rollout.persistent_run_id)

        if state.cooldown_tasks_remaining > 0:
            state.cooldown_tasks_remaining -= 1

        self._record_success(skill_name, rollout.persistent_run_id, rollout.summary)
        self.save_state()

    # ------------------------------------------------------------------
    # 晋升 / 回滚 / 打断 Candidate
    # ------------------------------------------------------------------

    def _promote(self, skill_name: str):
        state = self._states[skill_name]
        pm = self._get_proposal_manager(skill_name)
        ver = self._store.apply_candidate_as_stable(skill_name, state.current_version)
        pm.accept(state.active_proposal_id)

        proposal = pm.load(state.active_proposal_id)
        if proposal and proposal.source_trace_ids:
            self._buffer.mark_consumed(skill_name, proposal.source_trace_ids)

        state.state = "stable"
        state.lkg_version = ver if ver else state.current_version
        state.active_proposal_id = None
        state.cooldown_tasks_remaining = self._config.tasks_after_accept
        state.consecutive_rejections = 0

        self._skill_loader.set_overlay_dir(self._overlay_dir)
        self._notify_skills_changed()
        self.save_state()

        self._emit_trace("candidate_promoted", skill_name, {"version": ver})

    def _rollback(self, skill_name: str, reason: str, failure_run_id: str | None = None):
        state = self._states[skill_name]
        pm = self._get_proposal_manager(skill_name)
        self._store.restore_version(skill_name, state.lkg_version)

        failure_ids: list[str] = []
        if failure_run_id and reason not in ("EXPIRED",):
            failure_ids = [failure_run_id]

        pm.reject(state.active_proposal_id, reason, failure_trace_ids=failure_ids)

        proposal = pm.load(state.active_proposal_id)
        if proposal and proposal.source_trace_ids:
            self._buffer.mark_consumed(skill_name, proposal.source_trace_ids)

        state.state = "stable"
        state.current_version = state.lkg_version
        state.active_proposal_id = None
        state.cooldown_tasks_remaining = self._config.tasks_after_reject
        state.consecutive_rejections += 1

        if state.consecutive_rejections >= self._config.max_consecutive_rejections:
            state.state = "PAUSED"

        self._skill_loader.set_overlay_dir(self._overlay_dir)
        self._notify_skills_changed()
        self.save_state()

        self._emit_trace("candidate_rolled_back", skill_name, {"reason": reason})

    def _abort_candidate(self, skill_name: str):
        state = self._states[skill_name]
        pm = self._get_proposal_manager(skill_name)
        self._store.restore_version(skill_name, state.lkg_version)
        pm.supersede(state.active_proposal_id)

        state.state = "stable"
        state.current_version = state.lkg_version
        state.active_proposal_id = None

        observer = self._get_observer(skill_name)
        observer.reset()
        self.save_state()

    # ------------------------------------------------------------------
    # per-Skill 子模块映射
    # ------------------------------------------------------------------

    def _get_observer(self, skill_name: str) -> CandidateObserver:
        if skill_name not in self._observers:
            self._observers[skill_name] = CandidateObserver(self._config)
        return self._observers[skill_name]

    def _get_proposal_manager(self, skill_name: str) -> ProposalManager:
        if skill_name not in self._proposal_managers:
            proposals_dir = self._overlay_dir / skill_name / ".evolution" / "proposals"
            self._proposal_managers[skill_name] = ProposalManager(proposals_dir)
        return self._proposal_managers[skill_name]

    def _get_success_store(self, skill_name: str) -> RecentSuccessStore:
        if skill_name not in self._success_stores:
            path = self._overlay_dir / skill_name / ".evolution" / "successes.jsonl"
            self._success_stores[skill_name] = RecentSuccessStore(path)
        return self._success_stores[skill_name]

    def _record_success(self, skill_name: str, persistent_run_id: str, summary: str):
        self._get_success_store(skill_name).record(persistent_run_id, summary)

    # ------------------------------------------------------------------
    # 回调 & Trace
    # ------------------------------------------------------------------

    def _notify_skills_changed(self):
        if self._on_skills_changed:
            try:
                self._on_skills_changed()
            except Exception:
                logger.warning("on_skills_changed callback failed", exc_info=True)

    def _emit_trace(self, event_type: str, skill_id: str, details: dict):
        try:
            if self._trace_logger and hasattr(self._trace_logger, "log_event"):
                self._trace_logger.log_event("skill_evolution_event", {
                    "event_type": event_type,
                    "skill_id": skill_id,
                    "details": details,
                })
            logger.info("skill_evolution: %s skill=%s %s", event_type, skill_id, json.dumps(details, ensure_ascii=False))
        except Exception:
            pass


__all__ = ["SkillEvolutionManager"]
