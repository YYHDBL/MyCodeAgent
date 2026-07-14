# Lean Runtime Closeout Execution Hub

> **For GPT/Codex:** Read every control document in the order below before
> changing code. Use `MASTER_IMPLEMENTATION_PLAN.md` and the assigned task file
> together; neither is optional.

## Objective

Turn branch `lean-runtime-20260712` from a nearly complete refactor into a
release-ready branch without weakening product behavior, safety, or metrics.

The closeout is complete only when every row in `05_ACCEPTANCE_CRITERIA.md`
passes and `FINAL_REPORT.md` contains fresh reproducible evidence.

## Required Worktree

Perform implementation only in:

```text
/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712
```

Expected branch at start:

```text
lean-runtime-20260712
```

Never change the original worktree at:

```text
/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent
```

It contains six user-owned modifications. Do not reset, stash, commit, copy
over, delete, or otherwise resolve them. Integration is a handoff task, not an
automatic merge task.

## Read Order

1. `00_START_HERE.md`
2. `01_GOAL.md`
3. `02_MILESTONES.md`
4. `03_TASK_GRAPH.md`
5. `04_EXECUTION_PROTOCOL.md`
6. `05_ACCEPTANCE_CRITERIA.md`
7. `../2026-07-14-lean-runtime-closeout-design.md`
8. `MASTER_IMPLEMENTATION_PLAN.md`
9. The assigned file under `tasks/`
10. The original lean-runtime goal and decisions under
   `../2026-07-12-lean-runtime/`

## First Action

Run the read-only checks from `tasks/R0-01-baseline-and-safety.md`. Do not make
any product change until the branch, worktree cleanliness, ancestor relation,
and six protected original-worktree paths have been recorded in `BASELINE.md`.
