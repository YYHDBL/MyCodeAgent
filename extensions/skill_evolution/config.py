"""
.. function:: EvolutionConfig  —  技能演化框架可调参数

触发 & 观察 & 冷却 & 拒绝限制 & 补丁约束 & 存储保留时间。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvolutionConfig:
    enabled: bool = False

    # ---- Batch Review ----
    minimum_abnormal_traces: int = 3
    minimum_distinct_runs: int = 2
    max_proposals_per_batch: int = 1

    # ---- Candidate 观察 ----
    minimum_relevant_tasks: int = 3
    max_observation_tasks: int = 15

    # ---- 冷却期 (任务计数) ----
    tasks_after_accept: int = 3
    tasks_after_reject: int = 3

    # ---- 拒绝限制 ----
    max_consecutive_rejections: int = 2
    recent_rejected_proposals_in_prompt: int = 5


__all__ = ["EvolutionConfig"]
