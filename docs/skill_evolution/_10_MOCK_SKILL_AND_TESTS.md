# Skill Evolution — Mock Skill 与测试清单

---

## 1. Mock Skill

**文件：** `skills/code-review/SKILL.md`

```markdown
---
name: code-review
description: Review code quality and risks using a structured checklist
---
# Code Review

Use this checklist when reviewing code:

1. **Security** - Check for hardcoded secrets, SQL injection, unsafe deserialization
2. **Error Handling** - Verify exceptions are caught and handled properly
3. **Naming** - Ensure variables and functions have clear, descriptive names
4. **Duplication** - Look for repeated logic that could be extracted
5. **Testing** - Confirm edge cases have test coverage

## Review Process

1. Read the changed files using the Read tool
2. Run existing tests to verify the baseline
3. Apply each checklist item
4. Report findings with file paths and line numbers

## Output Format

Provide findings as a numbered list with severity: HIGH / MEDIUM / LOW
```

---

## 2. 测试用例清单

**文件：** `tests/extensions/test_skill_evolution.py`

### 2.1 Patcher（5 个）

| 用例 | 输入 | 期望 |
|------|------|------|
| `test_patcher_replace_exact` | 替换 `## Review Process` 段内的文本 | 返回修改后内容，old_text 已替换 |
| `test_patcher_insert_after_section` | 在 `## Review Process` 后插入一段 | 插入在段落末尾之后 |
| `test_patcher_append` | 追加到文件末尾 | 末尾追加，有空行分隔 |
| `test_patcher_section_not_found` | 标题不存在 | 返回 None |
| `test_patcher_multiple_headings` | 多级 `##`/`###` 标题 | 正确定位到目标段落边界 |

### 2.2 Store（6 个）

| 用例 | 验证点 |
|------|--------|
| `test_store_ensure_overlay_creates_dir` | 首次开启时从源码复制到 overlay |
| `test_store_snapshot_and_restore` | 快照保存到 `versions/` + 从快照恢复 |
| `test_store_version_naming` | v1 → v2 → v3-candidate 版本号自增 |
| `test_store_apply_patch` | 补丁应用 + 版本号更新（写入 overlay，不污染源码）|
| `test_store_list_versions` | 按版本号排序返回 |
| `test_store_source_skill_never_modified` | 全程不修改 `skills/code-review/SKILL.md` 源码 |

### 2.3 SkillLoader overlay（2 个）

| 用例 | 验证点 |
|------|--------|
| `test_loader_overlay_priority` | overlay 存在同名 Skill → 以 overlay 为准 |
| `test_loader_no_overlay_falls_back_to_source` | 未设置 overlay → 正常读源码 |

### 2.4 FeedbackRouter（6 个）

| 用例 | 验证点 |
|------|--------|
| `test_router_hotfix_long_term_keyword` | 含"以后都" → USER_HOTFIX_CANDIDATE |
| `test_router_abnormal_failure` | task_success=False → ABNORMAL |
| `test_router_abnormal_hard_error` | hard_error=True → ABNORMAL |
| `test_router_normal` | 正常任务 → NORMAL |
| `test_router_no_skill_attribution` | attributing_skill=None → NORMAL (跳过) |
| `test_router_multi_skill_attribution` | skills_invoked≥2 → attributing_skill=None → 跳过 |

### 2.5 HotfixGenerator（3 个，均 mock LLM）

| 用例 | 验证点 |
|------|--------|
| `test_hotfix_llm_returns_no_hotfix` | LLM 返回 NO_HOTFIX → 返回 None |
| `test_hotfix_llm_returns_apply` | LLM 返回 APPLY_HOTFIX → 返回 Proposal |
| `test_hotfix_llm_returns_ask_user` | LLM 返回 ASK_USER → 降级为 None |

### 2.6 Buffer（5 个）

| 用例 | 验证点 |
|------|--------|
| `test_buffer_threshold_reached` | 3 条消费=false、2 个 distinct run → should_review=True |
| `test_buffer_below_threshold` | 2 条 → should_review=False |
| `test_buffer_distinct_runs` | persistent_run_id 去重计数正确 |
| `test_buffer_persistent_key_unique` | 不同 session_id 不冲突 |
| `test_buffer_mark_consumed` | 标记后 consumed=true，不计入 should_review |

### 2.7 ProposalManager（5 个）

| 用例 | 验证点 |
|------|--------|
| `test_proposal_lifecycle` | PROPOSED → STAGED → EVALUATING → ACCEPTED |
| `test_proposal_reject` | REJECTED + 追加到 rejected.jsonl |
| `test_proposal_supersede` | Hotfix 覆盖 → SUPERSEDED |
| `test_proposal_duplicate_same_fingerprint` | 相同 (error_signature, section, patch_type) → is_duplicate=True |
| `test_proposal_duplicate_different_fingerprint` | 不同指纹 → is_duplicate=False |

### 2.8 Observer（9 个）

| 用例 | 验证点 |
|------|--------|
| `test_observer_relevant_pass` | 命中目标 Skill + PASS → relevant_count++ |
| `test_observer_irrelevant_passes` | 未命中 → IRRELEVANT, 不计入任何计数 |
| `test_observer_irrelevant_no_rollback` | 无关任务出现 hard_error → 不回滚 Candidate |
| `test_observer_promotes_after_relevant_tasks` | 3 次相关 PASS → is_observation_complete=True |
| `test_observer_expires_after_max_no_enough_pass` | ≥15 次相关但 <3 次 PASS → is_exceeded=True |
| `test_observer_target_error` | 相关任务中目标错误 → TARGET_ERROR |
| `test_observer_hard_failure` | 相关任务中 hard_error → HARD_FAILURE |
| `test_observer_human_intervention` | 相关任务中 human_intervention → HUMAN_INTERVENTION |
| `test_observer_restore_across_restart` | restore() 恢复计数后继续工作 |

### 2.9 StateMachine（16 个，均 mock LLM）

| 用例 | 验证点 |
|------|--------|
| `test_hotfix_flow` | 完整流程：路由→LLM 终判→overlay 写入→STABLE |
| `test_hotfix_one_time_instruction_rejected` | 一次性指令 → LLM 返回 NO_HOTFIX → 不更新 |
| `test_evolution_flow` | 异常→Buffer→Review→Candidate→3 PASS→Promote |
| `test_evolution_rollback_target_error` | Candidate 出现目标错误 → 回滚+REJECTED |
| `test_evolution_rollback_hard_failure` | 回滚 |
| `test_hotfix_interrupts_candidate` | 观察期间 Hotfix → Candidate SUPERSEDED |
| `test_consecutive_rejections_pause` | 连续 2 次 REJECTED → PAUSED |
| `test_cooldown_after_promote` | 晋升后 3 个任务冷却 → should_review=False |
| `test_cooldown_after_reject` | 回滚后冷却 |
| `test_config_disabled` | enable=False → _on_run_finished 是 no-op |
| `test_cross_restart_state_recovery` | load_state() 恢复 EVALUATING + observer 计数 |
| `test_cross_restart_overlay_inconsistent` | overlay 缺失 → 降级为 STABLE |
| `test_no_skill_attribution_skips` | 0 个 Skill → 跳过 |
| `test_multi_skill_attribution_skips` | 2 个 Skill → 歧义 → 跳过 |
| `test_per_skill_independent_state` | Skill A PAUSED 不影响 Skill B STABLE |
| `test_review_llm_exception_isolated` | Review LLM 异常 → buffer 保留，主任务不受影响 |

### 2.10 NullTraceLogger（3 个）

| 用例 | 验证点 |
|------|--------|
| `test_null_tracer_returns_empty_events` | get_current_run_events() 返回 [] |
| `test_null_tracer_clear_noop` | clear_current_run_events() 不崩溃 |
| `test_evolution_with_tracing_disabled` | tracing 关闭 + evolution 开启 → 降级跳过 |

---

**总计：60 个单元测试**
