"""HotfixGenerator — LLM 终判用户长期指令。

只做语义判断：一次性指令 → NO_HOTFIX，长期规则 → APPLY_HOTFIX。
"""

from __future__ import annotations

import json
import logging
import re

from extensions.skill_evolution.types import PatchOp, Proposal, ProposalType, RolloutRecord

logger = logging.getLogger(__name__)

HOTFIX_GENERATOR_SYSTEM_PROMPT = """\
You are reviewing a user instruction to decide whether it should become a permanent rule in a skill file.

## Rules

1. If the instruction is SPECIFIC TO THE CURRENT TASK and would NOT apply to future tasks,
   return {"action": "NO_HOTFIX", "reason": "..."}.

2. If the instruction is a GENERAL RULE that should apply to ALL FUTURE similar tasks,
   return {"action": "APPLY_HOTFIX", ...}.

3. If you are UNSURE whether the rule should generalize, return {"action": "ASK_USER", "question": "..."}.

## Patch Guidelines

- Prefer replace over append.
- target_section must be the exact heading text from the current skill (e.g., "## Review Process" -> "Review Process").
- old_text must match the original text exactly (for replace patches).
- NEVER rewrite the entire skill. Modify at most 1-2 sections.

## Output Format

Return ONLY a JSON object. No markdown, no explanation outside the JSON.
"""


class HotfixGenerator:
    def __init__(self, llm):
        self._llm = llm

    def generate(
        self,
        current_skill_content: str,
        user_instruction: str,
        rollout: RolloutRecord,
    ) -> Proposal | None:
        prompt = self._build_prompt(current_skill_content, user_instruction, rollout)
        try:
            response = self._llm.invoke([
                {"role": "system", "content": HOTFIX_GENERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
        except Exception:
            logger.warning("HotfixGenerator LLM invoke failed", exc_info=True)
            return None

        parsed = self._parse_response(response)
        if parsed is None:
            return None

        action = parsed.get("action", "")
        if action == "NO_HOTFIX":
            return None
        if action == "ASK_USER":
            # V1 降级：返回 None 并记录日志
            logger.info("HotfixGenerator ASK_USER downgraded to no-op: %s", parsed.get("question"))
            return None
        if action != "APPLY_HOTFIX":
            return None

        patch = PatchOp(
            patch_type=parsed.get("patch_type", "append"),
            target_section=parsed.get("target_section", ""),
            old_text=parsed.get("old_text", ""),
            new_text=parsed.get("new_text", ""),
        )

        proposal = Proposal(
            proposal_id="",
            proposal_type=ProposalType.USER_DIRECTED_HOTFIX,
            target_skill=rollout.attributing_skill or "",
            base_version="v0",
            source_trace_ids=[rollout.persistent_run_id],
            problem=f"User requested: {user_instruction}",
            reason=parsed.get("reason", "User explicit instruction"),
            target_section=parsed.get("target_section", ""),
            patch=patch,
            expected_behavior=parsed.get("expected_behavior", ""),
            error_signature=f"HOTFIX_{rollout.persistent_run_id}",
            risk_level="low",
            user_instruction=user_instruction,
        )
        return proposal

    def _build_prompt(self, skill_content: str, user_instruction: str, rollout: RolloutRecord) -> str:
        return f"""## Current Skill

{skill_content}

## User Instruction

{user_instruction}

## Current Task Context

{rollout.summary}

Determine whether this instruction should become a permanent rule.
Return ONLY a JSON object as specified in the system instructions."""

    def _parse_response(self, response: str) -> dict | None:
        try:
            text = response.strip()
            match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            logger.warning("HotfixGenerator failed to parse LLM response")
            return None


__all__ = ["HotfixGenerator"]
