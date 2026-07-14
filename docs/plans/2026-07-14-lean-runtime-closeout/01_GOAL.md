# Lean Runtime Closeout Goal

## Product Outcome

Produce a clean, release-ready local branch whose advertised optional paths
start correctly, whose quality gates detect undefined names, whose retained
JSONL trace includes lightweight summary metrics, and whose stable production
code satisfies the 15,000-line cap without deleting useful behavior.

## Invariants

1. `RuntimeRunner` remains the only stable agent loop.
2. Transcript remains the recovery source of truth.
3. JSONL remains the only trace artifact and retains `session_summary` metrics.
4. Default startup remains single-agent and launches no MCP or verifier.
5. Verification subagent remains opt-in and must work when enabled.
6. Stable tool schema remains exactly `Bash, Edit, Glob, Grep, Read, Task,
   TodoWrite` unless a failing safety contract proves otherwise.
7. MCP and AnyIO remain optional extras.
8. Teams and Skill Evolution remain absent from stable source.
9. The release metric keeps fixed source roots and a user-approved 15,000-line cap.
10. Original user modifications remain untouched.

## Simplification Target

Recover the remaining production-code budget from actual duplication:

- provider metadata and credential/default resolution in `core/llm.py`;
- repeated request construction and retry loops in `core/llm.py`;
- duplicate response normalization in `runtime/subagents.py`;
- dead imports, unused values, and ineffective broad lint suppressions.

Do not recover the budget by removing tracing, completion, resume, Skills, MCP,
Task, safety checks, tests, or documentation evidence.

## Stopping Condition

Stop only when all closeout acceptance criteria pass, the implementation
worktree is clean, the final report names every closeout commit, and an
integration handoff explains how the user can reconcile the original dirty
worktree. Do not perform the final merge or push without separate user
authorization.
