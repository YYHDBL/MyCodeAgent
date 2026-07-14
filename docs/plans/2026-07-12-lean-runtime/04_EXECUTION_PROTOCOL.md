# Execution Protocol

Every agent implementing a task file must follow this protocol.

## Required Skills

- Before implementation: `@superpowers:test-driven-development`.
- For unexpected failures: `@superpowers:systematic-debugging`.
- Before claiming completion: `@superpowers:verification-before-completion`.
- For plan batch execution: `@superpowers:executing-plans`.
- Use an isolated worktree through `@superpowers:using-git-worktrees` when the source worktree is dirty.

## Preflight

1. Read `00_START_HERE.md`, the control documents, and the assigned task.
2. Run `git status --short` and record pre-existing changes.
3. Do not touch files outside the task's allowed scope unless a failing test proves the plan is incomplete.
4. If scope must change, write a decision entry before editing additional files.
5. Never reset, stash, discard, or fold user-owned changes into a task commit.

## Task Loop

1. Inspect current implementation and relevant tests.
2. Write one focused failing behavior or contract test.
3. Run it and confirm the expected failure.
4. Implement the smallest change that passes it.
5. Run focused tests.
6. Run the milestone regression set listed in the task.
7. Review the diff for unrelated edits and unnecessary abstractions.
8. Commit only the task's files with the task ID in the message.
9. Append a progress record.

Do not combine unrelated cleanup with feature work. Do not preserve compatibility unless the task explicitly requires a transition window.

## Task Completion Report

Append to `PROGRESS.md`:

```markdown
## <task-id> — <status>

- Commit: `<sha>`
- Changed: `<short file list>`
- Behavior: `<what is now true>`
- Verification: `<commands and results>`
- Metrics: `<relevant before → after>`
- Follow-ups: `<none or exact task IDs>`
```

## Decision Record

Append unexpected architectural decisions to `DECISIONS.md`:

```markdown
## D-<number>: <title>

- Context: <evidence that contradicted or underspecified the plan>
- Decision: <smallest chosen change>
- Alternatives rejected: <brief reasons>
- Consequences: <task/file/test impact>
```

## Milestone Verification

At every milestone gate:

```bash
.venv/bin/python -m pytest -q
```

If packaging has already migrated:

```bash
uv run pytest -q
uv run ruff check .
```

Also run the milestone's scenario commands. Do not mark a milestone complete from focused tests alone.

## Blocking Rules

Continue independently when the issue is an ordinary implementation choice covered by the goal. Pause only when:

- user-owned changes overlap destructively with required edits;
- external credentials are necessary for a required gate and no deterministic substitute exists;
- two target invariants conflict;
- satisfying the task would require a new product capability or destructive external action.

When blocked, document the exact command, output, affected task, and safest next action. Vague blockers are not acceptable.
