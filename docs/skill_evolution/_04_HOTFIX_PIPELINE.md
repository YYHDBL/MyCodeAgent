# Skill Evolution — Hotfix 管道

**文件：** `extensions/skill_evolution/hotfix/generator.py`

---

## 1. 职责

将用户**明确**长期指令转化为局部 Skill Patch。FeedbackRouter 只做关键词初筛，HotfixGenerator 的 LLM 做语义终判。

---

## 2. 接口

```python
class HotfixGenerator:
    def __init__(self, llm: HelloAgentsLLM):
        """复用主 Agent 的 LLM。"""

    def generate(
        self,
        current_skill_content: str,     # 当前 overlay Skill 的完整 Markdown
        user_instruction: str,          # 用户原始指令文本
        rollout: RolloutRecord,         # 当前任务摘要
    ) -> Proposal | None:
        """
        返回 Proposal 表示 LLM 判定为长期规则。
        返回 None 表示 LLM 判定为一次性指令或不确定。
        """
```

---

## 3. 处理流程

```
1. 构建 prompt：
   - 当前 Skill 完整内容
   - 用户原始指令（原文引用）
   - 当前任务上下文（rollout.summary）
   - 判据：区分一次性任务要求 vs 可泛化的长期规则

2. LLM 返回结构化 JSON，三选一：

   A. {"action": "NO_HOTFIX", "reason": "This instruction is specific to the current task..."}
      → 返回 None，不更新

   B. {"action": "ASK_USER", "question": "Should this rule apply to all future..."}
      → V1 降级为返回 None，记录日志

   C. {"action": "APPLY_HOTFIX",
        "patch_type": "insert_after|replace|append",
        "target_section": "Review Process",
        "old_text": "...",             # replace 时填写
        "new_text": "...",
        "reason": "...",
        "scope": "task_class|all_tasks"}

3. 校验：
   - target_section 必须存在于 current_skill_content 中
   - patch_type 必须是合法值
   - 如果 section 不存在 → 降级为 append

4. 构造 Proposal：
   proposal_type = USER_DIRECTED_HOTFIX
   user_instruction = 原始指令（原文保留）
   source_trace_ids = [rollout.trace_id]
```

---

## 4. Prompt 约束

```python
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
- Target_section must be the exact heading text from the current skill (e.g., "## Review Process" → "Review Process").
- old_text must match the original text exactly (for replace patches).
- NEVER rewrite the entire skill. Modify at most 1-2 sections.

## Output Format

Return ONLY a JSON object. No markdown, no explanation outside the JSON.
"""
```

---

## 5. 约束

- Hotfix 不进入 Candidate 观察期（立即生效）
- Hotfix 保留用户原始指令在 `Proposal.user_instruction` 字段
- 如果 LLM 返回的 target_section 不存在，降级为 append
- Hotfix 写入 overlay，不修改源码 `skills/`
- LLM 超时或返回不可解析的输出 → 返回 None（安全降级）
