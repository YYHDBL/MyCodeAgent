"""Batch Review Agent — LLM 批量分析异常轨迹，判断是否需要对 Skill 进行局部修改。

默认输出 NO_UPDATE。任何 LLM 异常都降级为 NO_UPDATE。
"""

from __future__ import annotations

import json
import logging
import re

from extensions.skill_evolution.types import (
    BatchReviewDecision,
    PatchOp,
    Proposal,
    ProposalType,
    ReviewResult,
    RolloutRecord,
)
from extensions.skill_evolution.templates.review_prompt import REVIEW_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class BatchReviewAgent:
    def __init__(self, llm):
        self._llm = llm

    def review(
        self,
        current_skill: str,
        abnormal_rollouts: list[RolloutRecord],
        success_summaries: list[str],
        rejected_proposals: list[Proposal],
    ) -> ReviewResult:
        try:
            prompt = self._build_prompt(current_skill, abnormal_rollouts, success_summaries, rejected_proposals)
            response = self._llm.invoke([
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            parsed = self._parse_response(response)
            raw_decision = str(parsed.get("decision", "")).lower().strip()
            valid_decisions = {d.value for d in BatchReviewDecision}
            if raw_decision not in valid_decisions:
                logger.warning(
                    "BatchReviewAgent received unexpected decision '%s', falling back to NO_UPDATE. "
                    "Raw LLM output: %.200s",
                    raw_decision, response[:200],
                )
                return ReviewResult(
                    decision=BatchReviewDecision.NO_UPDATE,
                    reasoning=f"Unexpected decision value: {parsed.get('decision', '')!r}",
                )
            decision = BatchReviewDecision(raw_decision)
            if decision == BatchReviewDecision.PROPOSE_PATCH:
                proposal = Proposal(
                    proposal_id="",
                    proposal_type=ProposalType.AGENT_INFERRED,
                    target_skill="",
                    base_version="v0",
                    source_trace_ids=[r.persistent_run_id for r in abnormal_rollouts],
                    problem=parsed["problem"],
                    reason=parsed["reason"],
                    target_section=parsed["target_section"],
                    patch=PatchOp(
                        patch_type=parsed["patch_type"],
                        target_section=parsed["target_section"],
                        old_text=parsed.get("old_text", ""),
                        new_text=parsed["new_text"],
                    ),
                    expected_behavior=parsed["expected_behavior"],
                    error_signature=parsed["error_signature"],
                    risk_level=parsed.get("risk_level", "medium"),
                )
                return ReviewResult(decision=decision, proposal=proposal)
            return ReviewResult(decision=decision, reasoning=parsed.get("reasoning", ""))
        except Exception as e:
            logger.warning("BatchReviewAgent review failed", exc_info=True)
            return ReviewResult(decision=BatchReviewDecision.NO_UPDATE, reasoning=str(e))

    def _build_prompt(
        self,
        current_skill: str,
        abnormal_rollouts: list[RolloutRecord],
        success_summaries: list[str],
        rejected_proposals: list[Proposal],
    ) -> str:
        parts: list[str] = []
        parts.append("## Current Skill\n")
        parts.append(current_skill)

        parts.append("\n## Abnormal Trajectories\n")
        for r in abnormal_rollouts:
            parts.append(f"- [{r.persistent_run_id}] {r.summary} (attributing: {r.attributing_skill})")

        parts.append("\n## Recent Successes\n")
        for s in success_summaries:
            parts.append(f"- {s}")

        parts.append("\n## Rejected Proposals\n")
        if rejected_proposals:
            for p in rejected_proposals:
                parts.append(f"- [{p.proposal_id}] {p.problem} (rejected: {p.rejection_reason})")
        else:
            parts.append("- (none)")

        return "\n".join(parts)

    def _parse_response(self, response: str) -> dict:
        text = response.strip()
        match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        return json.loads(text)


__all__ = ["BatchReviewAgent"]
