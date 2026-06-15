# Skill Evolution — Batch Review Agent

**文件：** `extensions/skill_evolution/evolution/review_agent.py`, `extensions/skill_evolution/templates/review_prompt.py`

---

## 1. 职责

使用 LLM 分析多条异常轨迹，判断是否需要对 Skill 进行局部修改。默认输出 `NO_UPDATE`。

---

## 2. 接口

```python
class BatchReviewAgent:
    def __init__(self, llm: HelloAgentsLLM):
        """复用主 Agent 的 LLM。"""

    def review(
        self,
        current_skill: str,                      # 完整 Skill Markdown
        abnormal_rollouts: list[RolloutRecord],  # 异常轨迹摘要
        success_summaries: list[str],            # 最近 2-3 条成功轨迹摘要
        rejected_proposals: list[Proposal],      # 最近 5 条被拒绝的 Proposal
    ) -> ReviewResult:
        """
        返回 ReviewResult。如果 PROPOSE_PATCH，result.proposal 包含完整的 Proposal 对象。
        如果 LLM 调用异常，返回 ReviewResult(decision=NO_UPDATE, reasoning=str(error))。
        """
```

---

## 3. 输入构成

```
System Prompt: templates/review_prompt.py

User Message：
  1. ## Current Skill（完整 Markdown 内容）
  2. ## Abnormal Trajectories（每条一个精简摘要：terminal reason + error signature + skills invoked）
  3. ## Recent Successes（最近 2-3 条正常轨迹的简要描述）
  4. ## Rejected Proposals（最近 5 条被拒绝的 Proposal，含拒绝原因）
```

**成功轨迹来源：** 从 `memory/skill_evolution/active/<skill_name>/.evolution/successes.jsonl` 读取最近 N 条。该文件由 `state_machine` 在每次 NORMAL_ROLLOUT 或 Hotfix 成功后写入。每个 Skill 独立维护，重启后自然保留。

---

## 4. LLM 输出解析

期望 LLM 返回纯 JSON（不含 markdown 包裹）：

```json
// 情况 A: 无问题
{"decision": "NO_UPDATE", "reasoning": "All failures are isolated environment issues."}

// 情况 B: 有共性但证据不足
{"decision": "KEEP_COLLECTING", "reasoning": "Similar pattern emerging but only 2 distinct tasks."}

// 情况 C: 建议修改
{
  "decision": "PROPOSE_PATCH",
  "problem": "Agent repeatedly reused a failed tool argument without re-reading environment.",
  "reason": "Current skill defines retry but does not require refreshing state.",
  "target_section": "Failure Recovery",
  "patch_type": "replace",
  "old_text": "Retry the tool call when it fails.",
  "new_text": "Before retrying a failed tool call, refresh the environment state.",
  "expected_behavior": "Agent refreshes state before retrying.",
  "error_signature": "RETRY_WITHOUT_STATE_REFRESH",
  "risk_level": "medium"
}
```

---

## 5. templates/review_prompt.py — System Prompt

```python
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
```

---

## 6. 异常处理

```python
def review(self, ...) -> ReviewResult:
    try:
        response = self.llm.invoke(...)
        parsed = json.loads(response)
        decision = BatchReviewDecision(parsed["decision"])
        if decision == BatchReviewDecision.PROPOSE_PATCH:
            proposal = Proposal(
                proposal_type=ProposalType.AGENT_INFERRED,
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
        return ReviewResult(decision=BatchReviewDecision.NO_UPDATE, reasoning=str(e))
```

**要点：** Review LLM 调用在任何情况下都不应抛出未捕获异常。上层 state_machine 也额外包裹 try/except。
