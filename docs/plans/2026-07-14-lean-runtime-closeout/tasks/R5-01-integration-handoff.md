# R5-01 Prepare a Safe Integration Handoff

**Goal:** Give the user everything needed to integrate the release-ready branch
without touching the original dirty worktree automatically.

**Files:**

- Create: `docs/plans/2026-07-14-lean-runtime-closeout/INTEGRATION_HANDOFF.md`
- Modify: closeout `PROGRESS.md`, `FINAL_REPORT.md`

## Steps

1. Record exact branch topology:

   ```bash
   git merge-base feature/skill-evolution lean-runtime-20260712
   git rev-list --count feature/skill-evolution..lean-runtime-20260712
   git log --oneline feature/skill-evolution..lean-runtime-20260712
   git diff --name-status feature/skill-evolution...lean-runtime-20260712
   git branch -vv --list feature/skill-evolution lean-runtime-20260712
   ```

2. Read-only inspect the original worktree and list all six protected paths.
   Classify expected conflicts:

   - modified in original, deleted in lean branch;
   - modified in both branches;
   - modified in original but moved/replaced in lean branch.

3. Write three explicit user-controlled options:

   - **Preserve and port:** user first commits the six changes on a preservation
     branch; then selected behavior is manually ported onto lean runtime.
   - **Archive only:** user exports/commits the research changes for history,
     accepts their removal from the stable product, then integrates lean runtime.
   - **Abandon:** only the user may choose to discard them; do not provide this
     as an automatic default.

4. For the recommended preserve/archive route, provide non-destructive command
   sequences but do not execute them. Include a post-integration verification
   checklist identical to R4-02.

5. State clearly:

   - closeout branch is local and whether it has an upstream;
   - no push or merge occurred;
   - exact release-ready HEAD;
   - original status/diff hash remains unchanged.

6. Update final report/progress and commit:

   ```bash
   git add docs/plans/2026-07-14-lean-runtime-closeout
   git commit -m "docs(R5-01): prepare integration handoff"
   git status --short --branch
   ```

## Acceptance

- Implementation worktree is clean after the handoff commit.
- Original worktree status/hash matches R0.
- No merge, push, checkout, reset, stash, or original-worktree write occurred.
