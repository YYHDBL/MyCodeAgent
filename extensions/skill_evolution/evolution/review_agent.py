"""Batch Review Agent — LLM 批量分析异常轨迹，判断是否需要对 Skill 进行局部修改。

默认输出 NO_UPDATE。任何 LLM 异常都降级为 NO_UPDATE。
"""

from __future__ import annotations

import json
import logging

from extensions.skill_evolution.types import (
    BatchReviewDecision,
    PatchOp,
    Proposal,
    ProposalType,
    ReviewResult,
    RolloutRecord,
)

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are reviewing multiple execution trajectories to decide whether a skill requires a localized update.

## Default Decision

The default decision is NO_UPDATE. Do NOT create a patch merely because a batch is available.
A valid review result is often NO_UPDATE.

## Do NOT create a patch for:

- Isolated failures (only one task affected).
- Temporary environment issues (network, disk, API rate limits).
- Task-specific identifiers (file names, URLs, user names).
- Stylistic improvements with no behavioral impact.
- Behavior already clearly covered by the current skill.
- Issues that should be fixed in tool implementations or runtime code, not skills.

## A patch MAY be proposed when:

- Multiple DISTINCT runs (different inputs, different tasks) exhibit the same problem.
- The current skill LACKS relevant guidance for the observed failure.
- The proposed rule can GENERALIZE across future similar tasks.
- The expected behavior CAN BE OBSERVED in later rollouts.

## Patch Constraints

- Modify at most ONE or TWO local sections.
- Prefer REPLACE over APPEND. Do not rewrite the full skill.
- Include: problem, reason, target_section, old_text (for replace), new_text, expected_behavior, error_signature.
- error_signature should be a short snake_case identifier for the target problem (e.g., RETRY_WITHOUT_STATE_REFRESH).
- Do NOT repeat previously rejected proposal directions (see Rejected Proposals section).

## Output Format

Return EXACTLY a JSON object with NO markdown wrappers, NO explanatory text outside the JSON.

For NO_UPDATE:   {"decision": "NO_UPDATE", "reasoning": "..."}
For KEEP_COLLECTING: {"decision": "KEEP_COLLECTING", "reasoning": "..."}
For PROPOSE_PATCH: {"decision": "PROPOSE_PATCH", "problem": "...", "reason": "...", "target_section": "...", "patch_type": "replace|insert_after|append", "old_text": "...", "new_text": "...", "expected_behavior": "...", "error_signature": "...", "risk_level": "low|medium|high"}
"""


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
            response = self._llm.invoke(prompt)
            parsed = self._parse_response(response)
            decision = BatchReviewDecision(parsed["decision"])
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
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
        return json.loads(text)


__all__ = ["BatchReviewAgent"]
