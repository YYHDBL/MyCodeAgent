# MyCodeAgent Lean Runtime Execution Hub

> **For GPT/Codex:** Read this file first, then execute the task graph. Do not implement from memory or from the old roadmap.

This directory is the source of truth for the MyCodeAgent simplification program.

## Objective

Turn MyCodeAgent into a small, clean, genuinely usable local coding-agent harness whose default path is single-agent, deterministic where possible, and free of research-platform bloat.

The program is complete only when all acceptance gates in `06_ACCEPTANCE_CRITERIA.md` pass. Finishing a subset of tasks or merely reducing line count is not completion.

## Read Order

1. `01_GOAL.md` — product goal, invariants, non-goals, stopping condition.
2. `02_TARGET_ARCHITECTURE.md` — intended boundaries and dependency direction.
3. `03_MILESTONES.md` — checkpoint sequence and milestone gates.
4. `04_EXECUTION_PROTOCOL.md` — rules every implementation agent must follow.
5. `05_TASK_GRAPH.md` — task dependencies and safe parallel groups.
6. `06_ACCEPTANCE_CRITERIA.md` — final proof required.
7. The assigned file under `tasks/` — exact task scope.

## Current Repository Warning

At plan creation time the source worktree contained user-owned modifications in:

- `extensions/skill_evolution/adapter.py`
- `extensions/skill_evolution/evolution/buffer.py`
- `extensions/skill_evolution/evolution/observer.py`
- `extensions/skill_evolution/evolution/success_store.py`
- `runtime/session.py`
- `tools/builtin/bash.py`

Never reset, discard, overwrite, stash, or commit those changes as part of this program. Execution should happen in an isolated worktree created from the committed base unless the user has resolved the dirty state first.

## Operating Model

- One task file is the maximum scope for one implementation agent.
- A task may be split further if it cannot be completed and verified in one focused session.
- Parallel work is allowed only where `05_TASK_GRAPH.md` explicitly says it is safe.
- Each task uses tests first, makes the smallest behavior-preserving change, runs focused verification, and commits only its own files.
- Each milestone ends with a full-suite checkpoint and a short progress entry in `PROGRESS.md`.
- If code reality contradicts this plan, record the evidence in `DECISIONS.md`; do not silently broaden scope.

## First Action for the Goal Runner

1. Read all seven control documents.
2. Inspect `git status` without changing it.
3. Create or select an isolated implementation worktree.
4. Create `PROGRESS.md` and `DECISIONS.md` from the templates in `04_EXECUTION_PROTOCOL.md`.
5. Begin with `tasks/M0-01-baseline-and-safety-net.md`.
