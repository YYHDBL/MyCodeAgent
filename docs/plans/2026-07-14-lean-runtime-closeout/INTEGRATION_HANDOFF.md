# Lean Runtime Integration Handoff

Date: 2026-07-14 CST (+0800)

Status: **PUBLICATION AUTHORIZED — CLEAN INTEGRATION PENDING**

This handoff records the safe route from the local closeout branch to `main`.
The user subsequently authorized direct merge and push under C-008. Integration
must use a separate clean worktree and must not write to the original worktree.

## Exact Topology

- Release-ready runtime HEAD before this documentation-only handoff:
  `2a803d3 docs(R4-02): record final release verification`.
- Merge base: `cf0d0a02aa1f5c201bbefad56849c24ca2dba1a9`.
- `feature/skill-evolution..lean-runtime-20260712` contains `83` commits.
- `lean-runtime-20260712` is local only: `git branch -vv` shows no upstream.
  `feature/skill-evolution` remains at `cf0d0a0`, tracking
  `origin/feature/skill-evolution` and ahead by one.
- The reproducible topology commands are:

  ```bash
  git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
    merge-base feature/skill-evolution lean-runtime-20260712
  git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
    rev-list --count feature/skill-evolution..lean-runtime-20260712
  git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
    log --oneline feature/skill-evolution..lean-runtime-20260712
  git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
    diff --name-status feature/skill-evolution...lean-runtime-20260712
  git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
    branch -vv --list feature/skill-evolution lean-runtime-20260712
  ```

## Closeout Commits

The completed closeout task commits, in dependency order, are:

1. `e41f5f6 docs(R0-01): capture closeout baseline`
2. `76af052 fix(R1-01): repair verification-agent bootstrap`
3. `51c1fd5 chore(R1-02): enforce critical Ruff rules`
4. `73cc80f chore(R1-03): make import ordering explicit`
5. `f27cf38 docs(R2-01): clarify JSONL summary contract`
6. `e2c1706 refactor(R3-01): data-drive provider resolution`
7. `888a88a refactor(R3-02): share model request handling`
8. `1d1ad97 refactor(R3-03): share response normalization`
9. `0051bf2 docs(R3-04): record approved budget exception`
10. `acc9305 docs(R4-01): reconcile lean runtime plans`
11. `2a803d3 docs(R4-02): record final release verification`

This R5-01 handoff is committed separately under the task's required subject;
as required by original-plan D-001, this content does not self-reference its
content-derived commit SHA. Locate it with:

```bash
git -C /Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712 \
  log --oneline -- docs/plans/2026-07-14-lean-runtime-closeout/
```

## Protected Original Worktree and Conflicts

The original worktree is
`/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent` on
`feature/skill-evolution`. It remains ahead of origin by one commit with
exactly these six user-owned modifications:

| Original path | Lean branch relation | Integration treatment |
|---|---|---|
| `extensions/skill_evolution/adapter.py` | Modified in original; deleted in lean | Preserve/archive first; no stable destination exists. |
| `extensions/skill_evolution/evolution/buffer.py` | Modified in original; deleted in lean | Preserve/archive first; no stable destination exists. |
| `extensions/skill_evolution/evolution/observer.py` | Modified in original; deleted in lean | Preserve/archive first; no stable destination exists. |
| `extensions/skill_evolution/evolution/success_store.py` | Modified in original; deleted in lean | Preserve/archive first; no stable destination exists. |
| `runtime/session.py` | Modified in both branches | Manual, line-by-line conflict resolution is required. |
| `tools/builtin/bash.py` | Modified in both branches | Manual, line-by-line conflict resolution is required. |

There is no sixth-path case of “modified in original but moved/replaced” in
the name-status evidence: the four research files are deleted, not renamed or
moved, by lean runtime. Their removal is deliberate (Q-07), so their behavior
must not be restored without a separately reviewed product decision.

Read-only preservation check:

```bash
git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent status --short --branch
LC_ALL=C LANG=C git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent \
  diff --binary -- \
  extensions/skill_evolution/adapter.py \
  extensions/skill_evolution/evolution/buffer.py \
  extensions/skill_evolution/evolution/observer.py \
  extensions/skill_evolution/evolution/success_store.py \
  runtime/session.py \
  tools/builtin/bash.py | LC_ALL=C LANG=C shasum -a 256
```

At handoff, that hash is
`655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`,
unchanged from R0. The original worktree has not been modified by closeout.

## User-Controlled Choices

### 1. Preserve and port (recommended)

The user first creates a preservation branch and commits the six changes in
the original worktree. Then, in a separate review branch based on lean runtime,
the user manually ports only selected behavior; do not revive Skill Evolution
as an implicit conflict resolution.

The following are commands for the user to run later, not commands run by this
closeout:

```bash
ORIGINAL=/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent
git -C "$ORIGINAL" switch -c preserve/skill-evolution-research-20260714
git -C "$ORIGINAL" add \
  extensions/skill_evolution/adapter.py \
  extensions/skill_evolution/evolution/buffer.py \
  extensions/skill_evolution/evolution/observer.py \
  extensions/skill_evolution/evolution/success_store.py \
  runtime/session.py tools/builtin/bash.py
git -C "$ORIGINAL" commit -m "preserve: skill evolution research changes"

LEAN=/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712
git -C "$LEAN" switch -c port/preserved-behavior-review
git -C "$LEAN" diff --no-index /dev/null "$ORIGINAL/runtime/session.py"
git -C "$LEAN" diff --no-index /dev/null "$ORIGINAL/tools/builtin/bash.py"
```

The final two commands are inspection aids only. Apply any approved change as
a new reviewed edit with tests; do not merge the preservation branch wholesale.

### 2. Archive only

The user exports or commits the research changes for history, accepts their
removal from the stable product, and then makes an explicit integration choice.

```bash
ORIGINAL=/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent
git -C "$ORIGINAL" diff --binary -- \
  extensions/skill_evolution/adapter.py \
  extensions/skill_evolution/evolution/buffer.py \
  extensions/skill_evolution/evolution/observer.py \
  extensions/skill_evolution/evolution/success_store.py \
  runtime/session.py tools/builtin/bash.py > ~/skill-evolution-research-20260714.patch
git -C "$ORIGINAL" switch -c archive/skill-evolution-research-20260714
git -C "$ORIGINAL" add \
  extensions/skill_evolution/adapter.py \
  extensions/skill_evolution/evolution/buffer.py \
  extensions/skill_evolution/evolution/observer.py \
  extensions/skill_evolution/evolution/success_store.py \
  runtime/session.py tools/builtin/bash.py
git -C "$ORIGINAL" commit -m "archive: skill evolution research changes"
```

No integration command is prescribed here: the user must choose the target and
review the branch comparison before any merge.

### 3. Abandon

Only the user may choose to discard these six changes. This is never the
default and this handoff intentionally supplies no discard command.

## Post-Integration Verification Checklist

After a user-controlled integration or a separately reviewed manual port, run
the full R4-02 acceptance evidence again from the resulting implementation
worktree. Q-06 must pass normally under the 15,000-line C-008 policy.

```bash
git status --short --branch
uv run pytest -q tests/test_app_bootstrap.py -k verification
uv run pytest -q tests/test_lean_defaults.py::test_default_host_startup_creates_no_optional_runtime_services
uv run pytest -q tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py
uv run ruff check . --select E722,F401,F541,F821,F841
uv run ruff check app core runtime tools extensions prompts utils --select E402
uv run ruff check .
uv run pytest -q tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary tests/test_lean_defaults.py::test_trace_logger_writes_only_jsonl
test ! -e runtime/evals.py
test ! -e extensions/tracing/protocol.py
! rg -n 'trace_html_enabled|runtime\\.evals|summarize_trace' app core runtime tools extensions prompts
uv run pytest -q tests/test_llm_provider_resolution.py tests/test_llm_temperature_policy.py tests/test_llm_requests.py tests/runtime/test_model_errors.py tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py tests/test_core_without_mcp.py
uv run pytest -q
uv run pytest -q tests/scenarios
uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
uv lock --check
uv run python scripts/check_release_metrics.py
! rg -n 'experimental\\.teams|skill_evolution|Team[A-Z]' app core runtime tools extensions prompts
uv run pytest -q tests/test_tool_surface_docs.py tests/test_maintenance_boundaries.py tests/test_cli_one_shot.py tests/test_lean_defaults.py
```

Also repeat the fresh Python 3.12 editable-install / unrelated-repository
`mycodeagent --help` check, verify required dependencies remain at most five
(currently four), and record a fresh `FINAL_REPORT.md` mapping every
acceptance ID. The metrics command must report exactly seven stable tools and
exit 0 under the 15,000-line budget.

## Authorized Integration

No merge, rebase, push, checkout, reset, stash, or original-worktree write
occurred while creating the original R5-01 handoff. The user has now selected
direct publication: merge the release branch into a clean `main` worktree,
repeat the full release gates, and push normally. The original dirty worktree
and its six changes remain outside the integration path.
