"""反馈路由器 — 只做关键词初筛，允许假阳性。

真正语义判断在 HotfixGenerator 的 LLM 终判中完成。
"""

from __future__ import annotations

from extensions.skill_evolution.types import FeedbackRoute, RolloutRecord


class FeedbackRouter:
    def route(self, rollout: RolloutRecord) -> FeedbackRoute:
        if rollout.is_long_term_instruction:
            return FeedbackRoute.USER_HOTFIX_CANDIDATE

        if rollout.attributing_skill is None:
            return FeedbackRoute.NORMAL_ROLLOUT

        if not rollout.task_success or rollout.hard_error or rollout.human_intervention:
            return FeedbackRoute.ABNORMAL_ROLLOUT

        return FeedbackRoute.NORMAL_ROLLOUT


__all__ = ["FeedbackRouter"]
