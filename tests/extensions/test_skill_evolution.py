"""Skill Evolution 单元测试 — 60 个测试用例。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from extensions.skill_evolution.types import (
    BatchReviewDecision,
    EvolutionStateRecord,
    FeedbackRoute,
    ObservationResult,
    PatchOp,
    Proposal,
    ProposalStatus,
    ProposalType,
    ReviewResult,
    RolloutRecord,
)
from extensions.skill_evolution.config import EvolutionConfig
from extensions.skill_evolution.patcher import (
    append_to_end,
    apply_patch,
    insert_after_section,
    locate_section,
    replace_text,
)
from extensions.skill_evolution.validator import validate_proposal
from extensions.skill_evolution.adapter import (
    resolve_attribution,
    extract_skills_invoked,
    detect_user_feedback,
    trace_events_to_rollout,
)
from extensions.skill_evolution.feedback_router import FeedbackRouter
from extensions.skill_evolution.store import SkillVersionStore
from extensions.skill_evolution.evolution.buffer import AbnormalTrajectoryBuffer
from extensions.skill_evolution.evolution.observer import CandidateObserver
from extensions.skill_evolution.evolution.proposal_manager import ProposalManager
from extensions.skills.loader import SkillLoader


SAMPLE_SKILL = """---
name: code-review
description: Review code quality
---
# Code Review

## Review Process

1. Read the changed files
2. Run existing tests
3. Apply each checklist item
4. Report findings

## Output Format

Provide findings as a numbered list.
"""


def _make_rollout(
    persistent_run_id="s-abc:1",
    attributing_skill="code-review",
    task_success=True,
    hard_error=False,
    human_intervention=False,
    is_long_term=False,
    skills_invoked=None,
    error_signatures=None,
    summary="test task",
    **kwargs,
) -> RolloutRecord:
    return RolloutRecord(
        trace_id="t-xxx",
        persistent_run_id=persistent_run_id,
        input_fingerprint="fp1234567890",
        skills_invoked=skills_invoked if skills_invoked is not None else [attributing_skill] if attributing_skill else [],
        attributing_skill=attributing_skill,
        skill_version="v0",
        task_success=task_success,
        hard_error=hard_error,
        human_intervention=human_intervention,
        is_long_term_instruction=is_long_term,
        error_signatures=error_signatures or [],
        summary=summary,
        **kwargs,
    )


def _make_proposal(
    proposal_id="P-00001",
    target_skill="code-review",
    patch_type="replace",
    target_section="Review Process",
    old_text="1. Read the changed files",
    new_text="1. Read the changed files thoroughly",
    error_signature="TEST_ERR",
    **kwargs,
) -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        proposal_type=ProposalType.AGENT_INFERRED,
        target_skill=target_skill,
        base_version="v0",
        source_trace_ids=["s-abc:1"],
        problem="Test problem",
        reason="Test reason",
        target_section=target_section,
        patch=PatchOp(
            patch_type=patch_type,
            target_section=target_section,
            old_text=old_text,
            new_text=new_text,
        ),
        expected_behavior="Test expected",
        error_signature=error_signature,
        **kwargs,
    )


# ============================================================================
# 2.1 Patcher tests
# ============================================================================

class TestPatcher:
    def test_patcher_replace_exact(self):
        result = replace_text(SAMPLE_SKILL, "1. Read the changed files", "1. Carefully read the changed files")
        assert result is not None
        assert "Carefully read" in result
        assert "1. Read the changed files" not in result

    def test_patcher_insert_after_section(self):
        result = insert_after_section(SAMPLE_SKILL, "Review Process", "5. Verify dependencies")
        assert result is not None
        assert "5. Verify dependencies" in result
        idx_review = result.index("## Review Process")
        idx_insert = result.index("5. Verify dependencies")
        assert idx_insert > idx_review

    def test_patcher_append(self):
        result = append_to_end(SAMPLE_SKILL, "\n\n## Notes\nExtra info\n")
        assert result is not None
        assert "## Notes" in result

    def test_patcher_section_not_found(self):
        result = replace_text(SAMPLE_SKILL, "NON_EXISTENT", "x")
        assert result is None

    def test_patcher_multiple_headings(self):
        section = locate_section(SAMPLE_SKILL, "Review Process")
        assert section is not None
        start, end = section
        assert end > start


# ============================================================================
# 2.2 Store tests
# ============================================================================

class TestStore:
    def test_store_ensure_overlay_creates_dir(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        target = store.ensure_overlay_exists("code-review")
        assert target.exists()
        assert target.read_text() == SAMPLE_SKILL

    def test_store_snapshot_and_restore(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        store.ensure_overlay_exists("code-review")
        ver = store.snapshot_current("code-review")
        assert ver.startswith("v")
        versions_dir = overlay / "code-review" / ".evolution" / "versions"
        assert (versions_dir / f"{ver}.md").exists()

    def test_store_version_naming(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        store.ensure_overlay_exists("code-review")
        v1 = store.snapshot_current("code-review")
        assert v1 == "v1"

    def test_store_apply_patch(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        store.ensure_overlay_exists("code-review")
        patch = PatchOp(patch_type="replace", target_section="Review Process",
                         old_text="1. Read the changed files", new_text="1. Read carefully")
        ver = store.apply_patch("code-review", patch)
        assert ver.startswith("v")
        updated = store.read_skill("code-review")
        assert "Read carefully" in updated

    def test_store_list_versions(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        store.ensure_overlay_exists("code-review")
        store.snapshot_current("code-review")
        versions = store.list_versions("code-review")
        assert isinstance(versions, list)

    def test_store_source_skill_never_modified(self):
        source = Path(tempfile.mkdtemp())
        overlay = Path(tempfile.mkdtemp())
        skill_dir = source / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

        store = SkillVersionStore(source_skills_dir=source, overlay_dir=overlay)
        store.ensure_overlay_exists("code-review")
        patch = PatchOp(patch_type="replace", target_section="Review Process",
                         old_text="1. Read the changed files", new_text="1. Read carefully")
        store.apply_patch("code-review", patch)
        assert (skill_dir / "SKILL.md").read_text() == SAMPLE_SKILL


# ============================================================================
# 2.3 SkillLoader overlay tests
# ============================================================================

class TestLoaderOverlay:
    def test_loader_overlay_priority(self, temp_project):
        temp_project.create_file("skills/code-review/SKILL.md", SAMPLE_SKILL)

        overlay_dir = Path(tempfile.mkdtemp())
        overlay_skill = overlay_dir / "code-review"
        overlay_skill.mkdir(parents=True)
        (overlay_skill / "SKILL.md").write_text(
            SAMPLE_SKILL.replace("Review code quality", "REVIEW OVERRIDE DESCRIPTION")
        )

        loader = SkillLoader(str(temp_project.root))
        loader.set_overlay_dir(overlay_dir)
        skills = loader.scan()
        assert any("OVERRIDE" in s.description for s in skills)

    def test_loader_no_overlay_falls_back_to_source(self, temp_project):
        temp_project.create_file("skills/code-review/SKILL.md", SAMPLE_SKILL)
        loader = SkillLoader(str(temp_project.root))
        skills = loader.scan()
        assert any(s.name == "code-review" for s in skills)


# ============================================================================
# 2.4 FeedbackRouter tests
# ============================================================================

class TestFeedbackRouter:
    def test_router_hotfix_long_term_keyword(self):
        r = FeedbackRouter()
        rollout = _make_rollout(is_long_term=True)
        assert r.route(rollout) == FeedbackRoute.USER_HOTFIX_CANDIDATE

    def test_router_abnormal_failure(self):
        r = FeedbackRouter()
        rollout = _make_rollout(task_success=False)
        assert r.route(rollout) == FeedbackRoute.ABNORMAL_ROLLOUT

    def test_router_abnormal_hard_error(self):
        r = FeedbackRouter()
        rollout = _make_rollout(hard_error=True)
        assert r.route(rollout) == FeedbackRoute.ABNORMAL_ROLLOUT

    def test_router_normal(self):
        r = FeedbackRouter()
        rollout = _make_rollout(task_success=True)
        assert r.route(rollout) == FeedbackRoute.NORMAL_ROLLOUT

    def test_router_no_skill_attribution(self):
        r = FeedbackRouter()
        rollout = _make_rollout(attributing_skill=None)
        assert r.route(rollout) == FeedbackRoute.NORMAL_ROLLOUT

    def test_router_multi_skill_attribution(self):
        r = FeedbackRouter()
        rollout = _make_rollout(attributing_skill=None, skills_invoked=["a", "b"])
        assert r.route(rollout) == FeedbackRoute.NORMAL_ROLLOUT


# ============================================================================
# 2.5 HotfixGenerator tests
# ============================================================================

class TestHotfixGenerator:
    def test_hotfix_llm_returns_no_hotfix(self):
        from extensions.skill_evolution.hotfix.generator import HotfixGenerator
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = '{"action": "NO_HOTFIX", "reason": "one-time task"}'
        gen = HotfixGenerator(mock_llm)
        rollout = _make_rollout()
        result = gen.generate(SAMPLE_SKILL, "以后都这么做", rollout)
        assert result is None

    def test_hotfix_llm_returns_apply(self):
        from extensions.skill_evolution.hotfix.generator import HotfixGenerator
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = json.dumps({
            "action": "APPLY_HOTFIX",
            "patch_type": "replace",
            "target_section": "Review Process",
            "old_text": "1. Read the changed files",
            "new_text": "1. Read carefully",
            "reason": "long-term rule",
        })
        gen = HotfixGenerator(mock_llm)
        rollout = _make_rollout()
        result = gen.generate(SAMPLE_SKILL, "以后都这么做", rollout)
        assert result is not None
        assert result.proposal_type == ProposalType.USER_DIRECTED_HOTFIX

    def test_hotfix_llm_returns_ask_user(self):
        from extensions.skill_evolution.hotfix.generator import HotfixGenerator
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = '{"action": "ASK_USER", "question": "Should this be a rule?"}'
        gen = HotfixGenerator(mock_llm)
        rollout = _make_rollout()
        result = gen.generate(SAMPLE_SKILL, "以后都这么做", rollout)
        assert result is None


# ============================================================================
# 2.6 Buffer tests
# ============================================================================

class TestBuffer:
    def test_buffer_threshold_reached(self):
        b = AbnormalTrajectoryBuffer(Path(tempfile.mkdtemp()))
        b.append(_make_rollout("s-a:1"))
        b.append(_make_rollout("s-a:2"))
        b.append(_make_rollout("s-b:1"))
        assert b.should_review("code-review", min_traces=3, min_runs=2)

    def test_buffer_below_threshold(self):
        b = AbnormalTrajectoryBuffer(Path(tempfile.mkdtemp()))
        b.append(_make_rollout("s-a:1"))
        b.append(_make_rollout("s-a:2"))
        assert not b.should_review("code-review", min_traces=3, min_runs=2)

    def test_buffer_distinct_runs(self):
        b = AbnormalTrajectoryBuffer(Path(tempfile.mkdtemp()))
        b.append(_make_rollout("s-a:1"))
        b.append(_make_rollout("s-a:2"))
        b.append(_make_rollout("s-b:1"))
        assert b.count_distinct_runs("code-review") == 3

    def test_buffer_persistent_key_unique(self):
        b = AbnormalTrajectoryBuffer(Path(tempfile.mkdtemp()))
        b.append(_make_rollout("s-aaa:1"))
        b.append(_make_rollout("s-bbb:1"))
        batch = b.get_batch("code-review")
        assert len(batch) == 2

    def test_buffer_mark_consumed(self):
        b = AbnormalTrajectoryBuffer(Path(tempfile.mkdtemp()))
        b.append(_make_rollout("s-a:1"))
        b.append(_make_rollout("s-a:2"))
        b.append(_make_rollout("s-b:1"))
        b.mark_consumed("code-review", ["s-a:1", "s-a:2"])
        assert not b.should_review("code-review", min_traces=3, min_runs=2)


# ============================================================================
# 2.7 ProposalManager tests
# ============================================================================

class TestProposalManager:
    def test_proposal_lifecycle(self):
        d = Path(tempfile.mkdtemp())
        pm = ProposalManager(d)
        p = _make_proposal(proposal_id="")
        pm.propose(p)
        assert p.proposal_id
        pm.stage(p.proposal_id)
        pm.evaluate(p.proposal_id)
        pm.accept(p.proposal_id)
        loaded = pm.load(p.proposal_id)
        assert loaded.status == ProposalStatus.ACCEPTED

    def test_proposal_reject(self):
        d = Path(tempfile.mkdtemp())
        pm = ProposalManager(d)
        p = _make_proposal(proposal_id="")
        pm.propose(p)
        pm.reject(p.proposal_id, "bad patch", [])
        loaded = pm.load(p.proposal_id)
        assert loaded.status == ProposalStatus.REJECTED

    def test_proposal_supersede(self):
        d = Path(tempfile.mkdtemp())
        pm = ProposalManager(d)
        p = _make_proposal()
        pm.propose(p)
        pm.supersede(p.proposal_id)
        loaded = pm.load(p.proposal_id)
        assert loaded.status == ProposalStatus.SUPERSEDED

    def test_proposal_duplicate_same_fingerprint(self):
        d = Path(tempfile.mkdtemp())
        pm = ProposalManager(d)
        p1 = _make_proposal(proposal_id="")
        pm.propose(p1)
        pm.reject(p1.proposal_id, "dup", [])
        p2 = _make_proposal(proposal_id="", error_signature="TEST_ERR")
        assert pm.is_duplicate(p2)

    def test_proposal_duplicate_different_fingerprint(self):
        d = Path(tempfile.mkdtemp())
        pm = ProposalManager(d)
        p1 = _make_proposal(proposal_id="")
        pm.propose(p1)
        pm.reject(p1.proposal_id, "dup", [])
        p2 = _make_proposal(proposal_id="", error_signature="OTHER_ERR")
        assert not pm.is_duplicate(p2)


# ============================================================================
# 2.8 Observer tests
# ============================================================================

class TestObserver:
    def test_observer_relevant_pass(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        rollout = _make_rollout()
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.PASS
        assert obs.relevant_pass_count == 1

    def test_observer_irrelevant_passes(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        rollout = _make_rollout(skills_invoked=["other-skill"], attributing_skill="other-skill")
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.IRRELEVANT
        assert obs.relevant_pass_count == 0

    def test_observer_irrelevant_no_rollback(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        rollout = _make_rollout(skills_invoked=["other-skill"], attributing_skill="other-skill", hard_error=True)
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.IRRELEVANT

    def test_observer_promotes_after_relevant_tasks(self):
        config = EvolutionConfig(minimum_relevant_tasks=3)
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        for i in range(3):
            obs.observe(_make_rollout(persistent_run_id=f"s-xx:{i}"), proposal)
        assert obs.is_observation_complete()

    def test_observer_expires_after_max_no_enough_pass(self):
        config = EvolutionConfig(minimum_relevant_tasks=3, max_observation_tasks=5)
        obs = CandidateObserver(config)

        class FailObser(CandidateObserver):
            def observe(self, rollout, proposal):
                self._total_relevant_count += 1
                return ObservationResult.IRRELEVANT

        fail_obs = FailObser(config)
        for i in range(5):
            fail_obs.observe(_make_rollout(persistent_run_id=f"s-xx:{i}"), _make_proposal())
        assert fail_obs.is_exceeded()

    def test_observer_target_error(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review", error_signature="TEST_ERR")
        rollout = _make_rollout(error_signatures=["TEST_ERR"])
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.TARGET_ERROR

    def test_observer_hard_failure(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        rollout = _make_rollout(hard_error=True)
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.HARD_FAILURE

    def test_observer_human_intervention(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        proposal = _make_proposal(target_skill="code-review")
        rollout = _make_rollout(human_intervention=True)
        result = obs.observe(rollout, proposal)
        assert result == ObservationResult.HUMAN_INTERVENTION

    def test_observer_restore_across_restart(self):
        config = EvolutionConfig()
        obs = CandidateObserver(config)
        obs.restore(2, 5)
        assert obs.relevant_pass_count == 2
        assert obs.total_relevant_count == 5


# ============================================================================
# 2.9 StateMachine tests
# ============================================================================

class TestStateMachine:
    def _make_manager(self, overlay_dir=None, llm=None):
        from extensions.skill_evolution.state_machine import SkillEvolutionManager
        mock_loader = MagicMock()
        mock_loader._project_root = Path(tempfile.mkdtemp())
        return SkillEvolutionManager(
            skill_loader=mock_loader,
            llm=llm or MagicMock(),
            config=EvolutionConfig(enabled=True),
            overlay_dir=Path(overlay_dir or tempfile.mkdtemp()),
        )

    def test_config_disabled(self):
        mgr = self._make_manager()
        mgr._config.enabled = False
        mgr.on_run_finished([], "s", 1, "input")

    def test_no_skill_attribution_skips(self):
        events = [{"event": "tool_call", "payload": {"tool": "Bash", "args": {}}}]
        mgr = self._make_manager()
        mgr.on_run_finished(events, "s-abc", 1, "input")

    def test_multi_skill_attribution_skips(self):
        events = [
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "other"}}},
        ]
        mgr = self._make_manager()
        mgr.on_run_finished(events, "s-abc", 1, "input")

    def test_cross_restart_state_recovery(self):
        overlay = Path(tempfile.mkdtemp())
        state_path = overlay / "state.json"
        overlay.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "skills": {
                "code-review": {
                    "skill_id": "code-review",
                    "state": "stable",
                    "active_proposal_id": None,
                    "lkg_version": "v1",
                    "current_version": "v1",
                    "observer_relevant_pass_count": 0,
                    "observer_total_relevant_count": 0,
                    "cooldown_tasks_remaining": 0,
                    "consecutive_rejections": 0,
                    "overlay_active": False,
                }
            }
        }))
        mgr = self._make_manager(overlay_dir=overlay)
        mgr.load_state()
        assert "code-review" in mgr._states
        assert mgr._states["code-review"].state == "stable"

    def test_cross_restart_overlay_inconsistent(self):
        overlay = Path(tempfile.mkdtemp())
        state_path = overlay / "state.json"
        overlay.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "skills": {
                "code-review": {
                    "skill_id": "code-review",
                    "state": "EVALUATING",
                    "active_proposal_id": "P-00001",
                    "lkg_version": "v1",
                    "current_version": "v2-candidate",
                    "observer_relevant_pass_count": 2,
                    "observer_total_relevant_count": 5,
                    "cooldown_tasks_remaining": 0,
                    "consecutive_rejections": 0,
                    "overlay_active": True,
                }
            }
        }))
        mgr = self._make_manager(overlay_dir=overlay)
        mgr.load_state()
        assert mgr._states["code-review"].state == "stable"

    def test_per_skill_independent_state(self):
        overlay = Path(tempfile.mkdtemp())
        mgr = self._make_manager(overlay_dir=overlay)
        mgr._states["skill-a"] = EvolutionStateRecord(skill_id="skill-a", state="PAUSED")
        mgr._states["skill-b"] = EvolutionStateRecord(skill_id="skill-b", state="stable")
        mgr.save_state()
        assert mgr._states["skill-a"].state == "PAUSED"
        assert mgr._states["skill-b"].state == "stable"

    def test_rollback_missing_lkg_restores_source_v0(self):
        from extensions.skill_evolution.state_machine import SkillEvolutionManager

        root = Path(tempfile.mkdtemp())
        skill_dir = root / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL, encoding="utf-8")

        overlay = root / "memory" / "skill_evolution" / "active"
        overlay_skill = overlay / "code-review" / "SKILL.md"
        overlay_skill.parent.mkdir(parents=True)
        overlay_skill.write_text(SAMPLE_SKILL.replace("Report findings", "BROKEN CANDIDATE"), encoding="utf-8")

        mock_loader = MagicMock()
        mock_loader._project_root = root
        mock_loader.set_overlay_dir = MagicMock()
        mgr = SkillEvolutionManager(
            skill_loader=mock_loader,
            llm=MagicMock(),
            config=EvolutionConfig(enabled=True),
            overlay_dir=overlay,
        )
        mgr._states["code-review"] = EvolutionStateRecord(
            skill_id="code-review",
            state="evaluating",
            active_proposal_id="P-missing",
            lkg_version="missing",
            current_version="missing-candidate",
        )

        mgr._rollback("code-review", "HARD_FAILURE")

        assert overlay_skill.read_text(encoding="utf-8") == SAMPLE_SKILL
        assert mgr._states["code-review"].current_version == "v0"

    def test_review_llm_exception_isolated(self):
        overlay = Path(tempfile.mkdtemp())
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM boom")
        mgr = self._make_manager(overlay_dir=overlay, llm=mock_llm)

        events = [
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
            {"event": "terminal", "payload": {"reason": "model_error"}},
        ]
        for i in range(3):
            mgr.on_run_finished(events, f"s-{chr(97+i)}", i, f"input-{i}")
        # should not raise


# ============================================================================
# 2.10 NullTraceLogger tests
# ============================================================================

class TestNullTraceLogger:
    def test_null_tracer_returns_empty_events(self):
        from extensions.tracing import NullTraceLogger
        t = NullTraceLogger()
        assert t.get_current_run_events() == []

    def test_null_tracer_clear_noop(self):
        from extensions.tracing import NullTraceLogger
        t = NullTraceLogger()
        t.clear_current_run_events()

    def test_evolution_with_tracing_disabled(self):
        overlay = Path(tempfile.mkdtemp())
        from extensions.tracing import NullTraceLogger
        mock_llm = MagicMock()
        mgr = MagicMock()
        mgr._config = MagicMock()
        mgr._config.enabled = True
        mgr.on_run_finished = lambda e, s, r, i: None
        mgr.on_run_finished([], "s", 1, "input")


# ============================================================================
# Adapter unit tests
# ============================================================================

class TestAdapter:
    def test_extract_skills_invoked_single(self):
        events = [
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
        ]
        assert extract_skills_invoked(events) == ["code-review"]

    def test_extract_skills_invoked_multiple(self):
        events = [
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "other-skill"}}},
        ]
        assert sorted(extract_skills_invoked(events)) == ["code-review", "other-skill"]

    def test_resolve_attribution_single(self):
        assert resolve_attribution(["code-review"]) == "code-review"

    def test_resolve_attribution_none(self):
        assert resolve_attribution([]) is None

    def test_resolve_attribution_multi(self):
        assert resolve_attribution(["a", "b"]) is None

    def test_detect_user_feedback_long_term(self):
        events = [{"event": "user_input", "payload": {"text": "以后都这样做"}}]
        result = detect_user_feedback(events)
        assert result["is_long_term"]

    def test_detect_user_feedback_correction(self):
        events = [{"event": "user_input", "payload": {"text": "这样不对，应该是xxx"}}]
        result = detect_user_feedback(events)
        assert result["is_explicit_correction"]

    def test_trace_events_to_rollout_success(self):
        events = [
            {"event": "tool_call", "payload": {"tool": "Skill", "args": {"name": "code-review"}}},
            {"event": "terminal", "payload": {"reason": "completed"}},
        ]
        rollout = trace_events_to_rollout(events, "s-abc", 1, "review this code")
        assert rollout.attributing_skill == "code-review"
        assert rollout.task_success


# ============================================================================
# Validator tests
# ============================================================================

class TestValidator:
    def test_validate_proposal_valid_replace(self):
        p = _make_proposal()
        assert validate_proposal(p, SAMPLE_SKILL)

    def test_validate_proposal_invalid_patch_type(self):
        p = _make_proposal(patch_type="invalid")
        assert not validate_proposal(p, SAMPLE_SKILL)

    def test_validate_proposal_section_not_found(self):
        p = _make_proposal(target_section="NonExistentSection")
        assert not validate_proposal(p, SAMPLE_SKILL)

    def test_validate_proposal_empty_new_text(self):
        p = _make_proposal(new_text="")
        assert not validate_proposal(p, SAMPLE_SKILL)

    def test_validate_proposal_append_no_section_needed(self):
        p = _make_proposal(patch_type="append", old_text="")
        assert validate_proposal(p, SAMPLE_SKILL)
