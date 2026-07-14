# Closeout Execution Protocol

## Required Skills

The goal runner and implementation agents must use the applicable local skills:

- `executing-plans` for task sequencing;
- `subagent-driven-development` when dispatching one agent per task;
- `test-driven-development` for behavior changes;
- `systematic-debugging` for unexpected failures;
- `verification-before-completion` before every commit and milestone claim;
- `requesting-code-review` for R1 and R3 milestone diffs.

## Task Lifecycle

1. Read all control files and the assigned task file.
2. Confirm `git status --short --branch` and current task ownership.
3. Run the task's pre-change characterization or failing test.
4. Make only the files listed by the task. If another file is necessary, record
   the reason in `DECISIONS.md` before changing it.
5. Run focused verification.
6. Run the task's milestone-required regression command.
7. Review `git diff --check`, `git diff --stat`, and the actual diff.
8. Update `PROGRESS.md` with exact output, not a summary claim.
9. Commit only the task with its task ID.
10. The goal runner independently inspects the commit and reruns its gate.

## Commit Format

```text
fix(R1-01): repair verification-agent bootstrap
chore(R1-02): enforce critical Ruff rules
refactor(R3-01): data-drive provider resolution
docs(R4-01): reconcile closeout documentation
```

## Hard Prohibitions

- Do not modify `MAX_STABLE_PRODUCTION_LINES`, `STABLE_SOURCE_ROOTS`, metric
  exclusions, the seven-tool cap, or dependency counting.
- Do not delete retained capabilities to make the metric pass.
- Do not add a framework or dependency for a table/refactor problem.
- Do not restore HTML tracing, `runtime.evals`, or compatibility wrappers.
- Do not split the main loop for line-count aesthetics.
- Do not change the original dirty worktree, merge into it, or push.
- Do not batch unrelated cleanup into a task commit.

## Decision Rule

Ordinary implementation details may be decided autonomously. Record a decision
before any behavior change involving provider inference, environment precedence,
public CLI flags, stable tool schemas, persistence facts, or trace event names.
If an acceptance requirement can only be met by weakening another invariant,
stop and mark the exact blocker; do not silently trade it away.

## Progress Entry Format

```markdown
## R1-01 — complete

- Commit: `<sha> <subject>`
- Changed: exact files and behavior.
- RED: command and failure.
- GREEN: command and result.
- Regression: command and result.
- Metrics: before → after.
- Remaining: next task IDs.
```
