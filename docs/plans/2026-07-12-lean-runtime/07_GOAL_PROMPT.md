# Codex Goal Prompt

The official Goal workflow recommends one durable objective, a verifiable stopping condition, required source files, checkpoint evidence, and a progress log. Paste the following prompt into Codex from the MyCodeAgent repository.

```text
/goal Refactor MyCodeAgent into the lean, usable single-agent coding harness specified in docs/plans/2026-07-12-lean-runtime, without stopping until every applicable acceptance criterion in 06_ACCEPTANCE_CRITERIA.md passes and FINAL_REPORT.md contains reproducible proof.

Before changing code, read these files in order:
1. docs/plans/2026-07-12-lean-runtime/00_START_HERE.md
2. docs/plans/2026-07-12-lean-runtime/01_GOAL.md
3. docs/plans/2026-07-12-lean-runtime/02_TARGET_ARCHITECTURE.md
4. docs/plans/2026-07-12-lean-runtime/03_MILESTONES.md
5. docs/plans/2026-07-12-lean-runtime/04_EXECUTION_PROTOCOL.md
6. docs/plans/2026-07-12-lean-runtime/05_TASK_GRAPH.md
7. docs/plans/2026-07-12-lean-runtime/06_ACCEPTANCE_CRITERIA.md

Then execute every task file under docs/plans/2026-07-12-lean-runtime/tasks in dependency order. Treat one task file as the maximum scope for one implementation agent. Use parallel agents only for the safe parallel groups explicitly listed in 05_TASK_GRAPH.md, integrate in the documented order, and run the milestone gate after every milestone.

Preserve all pre-existing user changes. If the source worktree is dirty, do not reset, discard, stash, overwrite, or commit those changes; create an isolated worktree from the committed base and perform the refactor there. Use test-driven development for behavior changes, systematic debugging for unexpected failures, and verification-before-completion before each task and milestone is marked complete. Commit each completed task separately with its task ID.

Keep PROGRESS.md and DECISIONS.md current. At each checkpoint report only: current milestone/task, commits completed, verification evidence, metrics changed, remaining tasks, and exact blockers. Do not add features outside 01_GOAL.md, do not preserve removed research systems through no-op compatibility layers, and do not optimize only for line count at the cost of behavior or safety.

Continue independently through ordinary implementation choices. Pause only for the blocking conditions defined in 04_EXECUTION_PROTOCOL.md. The goal is complete only after the installed CLI works on an unrelated repository, default startup is lean, Teams and Skill Evolution are absent from the stable product, MCP is optional, transcript resume works, the stable tool surface is seven or fewer, all deterministic tests/lint pass, stable production Python is at most 15,000 lines, required dependencies are at most five, docs match behavior, and docs/plans/2026-07-12-lean-runtime/FINAL_REPORT.md records the exact commands and results.
```

If `/goal` is not available, enable it with:

```bash
codex features enable goals
```

Or set:

```toml
[features]
goals = true
```

Official reference: <https://learn.chatgpt.com/use-cases/follow-goals>
