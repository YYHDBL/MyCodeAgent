# Milestones and Gates

Milestones are sequential. Tasks inside a milestone may run in parallel only as permitted by `05_TASK_GRAPH.md`.

## M0 — Baseline and Safety Net

**Purpose:** establish reproducible evidence before changing architecture.

Tasks:

- `M0-01` Capture baseline, isolate worktree, and repair test execution if environment-specific.
- `M0-02` Add/normalize deterministic characterization scenarios for the current stable path.

Gate:

- Baseline commands, counts, startup behavior, and known failures are recorded.
- Core tests can run reproducibly, or a precisely diagnosed external blocker is documented.
- No user-owned dirty changes were altered.

## M1 — A CLI That Works on Real Projects

**Purpose:** fix the most important product gap before internal refactoring.

Tasks:

- `M1-01` Current-directory and `--cwd` project-root semantics.
- `M1-02` One-shot text and JSON modes.
- `M1-03` Packaging and `mycodeagent` console entrypoint.
- `M1-04` Session list/resume/status and per-turn cancellation.

Gate:

- An installed command operates on an unrelated temporary repository.
- Interactive and one-shot modes share the same runtime path.
- CLI errors are concise and return meaningful exit codes.

## M2 — Lean Defaults and Research Removal

**Purpose:** make the default path genuinely small and isolate optional capability cost.

Tasks:

- `M2-01` Normalize configuration and lean defaults.
- `M2-02` Make MCP lazy and an optional dependency extra.
- `M2-03` Remove Agent Teams from the stable tree.
- `M2-04` Remove Skill Evolution from the stable tree.

Gate:

- Default startup launches no external servers or subagents.
- Core install does not install MCP/AnyIO.
- Stable code has no Teams or Skill Evolution imports, flags, prompts, docs claims, or tests.

## M3 — One Runtime, One Event Path, One Recovery Source

**Purpose:** shrink orchestration without changing behavior.

Tasks:

- `M3-01` Introduce one structured event sink interface.
- `M3-02` shrink RuntimeRunner/Host and remove single-product wiring abstractions.
- `M3-03` consolidate resume on transcripts and retire session snapshot duplication.

Gate:

- Runtime flow remains traceable and resumable.
- Loop and host meet complexity budgets or have a documented reason not to.
- Transcript recovery scenarios prove no completed side effect is replayed.

## M4 — Small Tool Harness

**Purpose:** remove the largest stable-code duplication while preserving safety.

Tasks:

- `M4-01` Central `FileWorkspace` primitives.
- `M4-02` Merge Write/MultiEdit into Edit.
- `M4-03` Merge ListFiles/SearchFilesByName into Glob/Grep.
- `M4-04` Simplify internal ToolResult and serialization.
- `M4-05` Delete compatibility wrappers and dead abstractions.

Gate:

- Stable tool schema exposes at most seven tools.
- File writes preserve atomicity, root confinement, binary checks, and conflict detection.
- Tool contract tests and file-operation scenarios pass.

## M5 — Quality, Documentation, and Release Gate

**Purpose:** prove the smaller system is more usable and maintainable.

Tasks:

- `M5-01` Reshape tests around contracts and end-to-end scenarios.
- `M5-02` Rewrite current docs, add CI/quality gates, and produce final metrics.

Gate:

- All criteria in `06_ACCEPTANCE_CRITERIA.md` pass.
- Docs and CLI defaults agree.
- Final report compares baseline to result and lists intentionally removed features.

## M6 — Narrow Post-M5 Remediation — completed

**Purpose:** remove two optional or unused surfaces identified by the M5
release evidence without weakening transcript recovery, the seven-tool
contract, JSONL tracing, Skills, Task, or MCP.

Tasks:

- `M6-01` Remove optional cross-session project memory; transcript facts and
  derived session memory remain the recovery path.
- `M6-02` Retain append-only JSONL facts and remove the unused HTML renderer,
  trace protocol declarations, and product-side `runtime.evals` API.

Gate:

- M6 reduced the stable metric from 15,411 to 14,243 lines, but did not make
  the original M5 release gate pass.
- The final `session_summary` JSONL row still contains steps, `tools_used`, and
  accumulated token totals; it is not a replacement evaluator.
- The next release work is governed by the dated
  [closeout plan](../2026-07-14-lean-runtime-closeout/00_START_HERE.md), not by
  a rewrite of this historical M5 evidence.

## R0–R5 — Lean Runtime Closeout — complete

**Purpose:** repair the enabled verifier path, make the Ruff gates honest,
prove the retained JSONL summary contract, remove measured duplicate model
logic, and collect final release evidence without mutating the original dirty
worktree.

The authoritative dependency graph and acceptance matrix are in the dated
[closeout execution hub](../2026-07-14-lean-runtime-closeout/00_START_HERE.md).
R0 through R5 are recorded there. The user subsequently approved a 15,000-line
stable-production budget in closeout
[C-008](../2026-07-14-lean-runtime-closeout/DECISIONS.md#c-008-raise-the-stable-production-budget-to-15000-lines),
under which the current 14,094-line tree passes the enforcing metric normally.
