"""CandidateObserver — 监控单个 Skill 的 Candidate 版本在后继任务中的表现。

无关任务永不改变 Candidate 的命运。
"""

from __future__ import annotations

from extensions.skill_evolution.types import ObservationResult, Proposal, RolloutRecord


class CandidateObserver:
    def __init__(self, config):
        self._config = config
        self._relevant_pass_count: int = 0
        self._total_relevant_count: int = 0

    def observe(self, rollout: RolloutRecord, proposal: Proposal) -> ObservationResult:
        if proposal.target_skill not in rollout.skills_invoked:
            return ObservationResult.IRRELEVANT

        self._total_relevant_count += 1

        from extensions.skill_evolution.adapter import detect_error_signature
        if detect_error_signature(rollout, proposal):
            return ObservationResult.TARGET_ERROR

        if rollout.hard_error:
            return ObservationResult.HARD_FAILURE

        if rollout.human_intervention:
            return ObservationResult.HUMAN_INTERVENTION

        self._relevant_pass_count += 1
        return ObservationResult.PASS

    def is_observation_complete(self) -> bool:
        return self._relevant_pass_count >= self._config.minimum_relevant_tasks

    def is_exceeded(self) -> bool:
        return self._total_relevant_count >= self._config.max_observation_tasks

    def reset(self):
        self._relevant_pass_count = 0
        self._total_relevant_count = 0

    def restore(self, relevant_pass: int, total_relevant: int):
        self._relevant_pass_count = relevant_pass
        self._total_relevant_count = total_relevant

    @property
    def relevant_pass_count(self) -> int:
        return self._relevant_pass_count

    @property
    def total_relevant_count(self) -> int:
        return self._total_relevant_count


__all__ = ["CandidateObserver"]
