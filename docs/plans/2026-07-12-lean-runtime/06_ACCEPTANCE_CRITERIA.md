# Acceptance Criteria

The goal runner must produce evidence for every row. `PASS` requires the listed command or an equivalent deterministic check. This is the original-plan
matrix; final branch status is governed by the dated
[closeout acceptance matrix](../2026-07-14-lean-runtime-closeout/05_ACCEPTANCE_CRITERIA.md).
The user-approved C-008 policy sets the stable-production cap to 15,000 lines;
the enforcing metric command must exit 0 normally.

## Product Gates

| ID | Criterion | Evidence |
|---|---|---|
| P-01 | CLI help starts promptly | `mycodeagent --help` exits 0 in under 3 seconds on the reference machine. |
| P-02 | Current directory is the default project | Run from a temporary git repo and assert reported/project root equals that repo. |
| P-03 | Explicit root override works | `mycodeagent --cwd <tmp> ...` confines file actions to `<tmp>`. |
| P-04 | One-shot text works | `mycodeagent -p "..."` returns a final response and a meaningful exit code. |
| P-05 | JSON mode is machine-readable | Output parses as one documented JSON object without Rich decoration. |
| P-06 | Sessions are discoverable/resumable | Create, list, resume, and continue a deterministic mock session. |
| P-07 | Turn cancellation is safe | Interrupt an active mock turn; CLI remains usable and transcript is valid. |

## Architecture Gates

| ID | Criterion | Evidence |
|---|---|---|
| A-01 | One canonical loop | Boundary test and architecture doc identify only `RuntimeRunner`. |
| A-02 | Default is single-agent | No subagent is created unless explicitly configured. |
| A-03 | No optional startup work | Default startup creates no MCP child process and makes no extension network call. |
| A-04 | Research systems are absent | `rg 'experimental\.teams|skill_evolution|Team[A-Z]' app core runtime tools extensions prompts` returns no stable references. |
| A-05 | Transcript is recovery truth | Resume tests rebuild state from transcript without requiring a session snapshot. |
| A-06 | Tools do not import runtime | Automated boundary test passes. |
| A-07 | Optional MCP dependency | Core environment imports/runs without `mcp` and `anyio`; `mycodeagent[mcp]` tests pass separately. |

## Tool Gates

| ID | Criterion | Evidence |
|---|---|---|
| T-01 | Seven or fewer stable tools | Schema snapshot count. |
| T-02 | One mutation tool | No `Write` or `MultiEdit` in the final tool schema. |
| T-03 | Root confinement | Parameterized traversal/symlink/absolute-path tests. |
| T-04 | Conflict safety | Snapshot mismatch blocks mutation. |
| T-05 | Atomic multi-edit | All edits apply or the file remains unchanged. |
| T-06 | Search uses a minimal implementation | Glob/Grep cover listing and filename/content search scenarios. |
| T-07 | Oversized results remain recoverable | Full output is persisted and bounded preview points to it. |

## Quality Gates

| ID | Criterion | Evidence |
|---|---|---|
| Q-01 | Full core suite passes | `uv run pytest -q` or documented equivalent. |
| Q-02 | Lint passes | `uv run ruff check .`; the current closeout also runs `uv run ruff check . --select E722,F401,F541,F821,F841` and stable-package `E402`. `F821`, `E722`, `F401`, `F541`, and `F841` are not globally ignored. This is lint coverage, not a claim of type checking or broader static analysis. |
| Q-03 | Deterministic scenarios pass | Scenario suite includes CLI, tool, compaction, permission, resume, cancellation, completion. |
| Q-04 | Docs match behavior | Documentation consistency tests and manual spot check. |
| Q-05 | Stable production code ≤15k lines | Checked by the repository metrics command excluding tests/docs/research; the command must exit 0. |
| Q-06 | Required dependencies ≤5 | Core dependency list and import smoke test. |
| Q-07 | No user changes lost | Original dirty-worktree files remain recoverable and were never reset/discarded. |

## Final Report

`M5-02` must write a final report containing:

- baseline vs final production/test/doc line counts;
- required vs optional dependencies;
- stable tool count;
- startup behavior;
- test/scenario results;
- removed features and the Git commit where they remain recoverable;
- any acceptance criterion not passed, with exact blocker evidence.
