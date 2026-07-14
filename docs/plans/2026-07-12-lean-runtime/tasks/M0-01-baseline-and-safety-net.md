# M0-01 Baseline and Safety Net Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:using-git-worktrees`, then `superpowers:verification-before-completion`.

**Goal:** Establish a reproducible, isolated baseline without changing runtime behavior or user-owned files.

**Architecture:** Measure the committed system from an isolated worktree and store reproducible evidence in planning artifacts; make no runtime changes.

**Tech Stack:** Git worktrees, zsh, Python, pytest, ripgrep, wc.

**Dependencies:** None.

**Files:**

- Create: `docs/plans/2026-07-12-lean-runtime/BASELINE.md`
- Create in implementation worktree: `docs/plans/2026-07-12-lean-runtime/PROGRESS.md`
- Create in implementation worktree: `docs/plans/2026-07-12-lean-runtime/DECISIONS.md`
- Do not modify product code.

## Steps

1. Run `git status --short`, `git rev-parse HEAD`, and record the source worktree state.
2. If the source is dirty, create an isolated worktree/branch from committed `HEAD`; do not stash or reset the source.
3. Record Python/uv versions and dependency files.
4. Measure tracked Python LOC for stable production, tests, Teams, Skill Evolution, and docs using reproducible `rg --files ... | xargs wc -l` commands.
5. Record stable tool schema inventory and all default-enabled flags from code.
6. Run `.venv/bin/python -m pytest --collect-only -q` and `.venv/bin/python -m pytest -q`.
7. If imports stall, use import timing and focused imports to identify the exact package/path. Repair only the isolated environment if possible; do not edit product code in this task.
8. Run `.venv/bin/python main.py --help` with a reasonable timeout and record duration/result.
9. Write `BASELINE.md` with commands, outputs, known blockers, and measurement definitions.
10. Commit only the three planning/status files.

## Acceptance

- The source worktree's original changes are untouched.
- Every future metric has a documented baseline command.
- Test/startup failures are evidence-backed, not described as “hangs sometimes.”
- Commit: `docs(M0-01): capture lean-runtime baseline`.
