# Task Graph and Assignment Map

Each task is scoped for one implementation agent. The goal runner owns sequencing, integration, milestone gates, and conflict resolution.

## Dependency Graph

```text
M0-01 → M0-02
             ↓
       M1-01 → M1-02 → M1-03 → M1-04
             ↓
       M2-01 → M2-02
          ├────→ M2-03
          └────→ M2-04
                    ↓
       M3-01 → M3-02 → M3-03
                    ↓
       M4-01 → M4-02 ─┐
          └──→ M4-03 ─┼→ M4-04 → M4-05
                       ↓
                    M5-01 → M5-02 → M6-01 → M6-02 → R0-01
                                                        ├── R1-01 → R1-02 → R1-03 ─┐
                                                        └── R2-01 ──────────────────┤
                                                                                     ↓
                                                                R3-01 → R3-02 ─┐
                                                                     └ R3-03 ──┼→ R3-04
                                                                               ↓
                                                                      R4-01 → R4-02 → R5-01
```

## Safe Parallel Groups

- After `M2-01`, `M2-02`, `M2-03`, and `M2-04` may be implemented by separate agents, but integration must occur in that order because all touch configuration/docs.
- After `M4-01`, `M4-02` and `M4-03` may run in parallel in separate worktrees.
- Research-removal tasks and tool-consolidation tasks must not share a working tree concurrently.
- `M5-01` starts only after every functional task is integrated.

## Task Inventory

| ID | Outcome | Primary surface |
|---|---|---|
| M0-01 | Reproducible baseline and protected worktree | repository/test environment |
| M0-02 | Deterministic stable-path characterization | `tests/scenarios/` |
| M1-01 | Correct project root and `--cwd` | bootstrap/CLI/tools |
| M1-02 | One-shot and JSON output | CLI/runtime response |
| M1-03 | Installable console command | packaging |
| M1-04 | Resume/status/cancellation UX | CLI/transcript |
| M2-01 | Single config source and lean defaults | config/bootstrap |
| M2-02 | MCP optional extra and lazy startup | packaging/MCP |
| M2-03 | Teams removed from stable product | experimental/team tools |
| M2-04 | Skill Evolution removed from stable product | extension/runtime hooks |
| M3-01 | Unified event path | loop/trace/transcript |
| M3-02 | Smaller loop/host composition | runtime |
| M3-03 | Transcript-only recovery truth | persistence |
| M4-01 | Shared safe filesystem primitives | tools workspace |
| M4-02 | One Edit tool | file mutation tools |
| M4-03 | Minimal search/list tools | read-only tools |
| M4-04 | Small internal ToolResult protocol | tool base/registry |
| M4-05 | Compatibility/dead-code deletion | repository-wide narrow cleanup |
| M5-01 | Contract + scenario-centered tests | tests |
| M5-02 | Docs, CI, metrics, final release gate | docs/tooling |
| M6-01 | Optional project memory removed | memory/configuration/runtime |
| M6-02 | JSONL facts retained; renderer/evaluator removed | tracing/runtime |
| R0-01–R5-01 | Final closeout, evidence, and safe handoff | [2026-07-14 closeout plan](../2026-07-14-lean-runtime-closeout/00_START_HERE.md) |

## Post-M5 Status

`M6-01` and `M6-02` are completed remediation tasks. The R0–R5 graph is the
authoritative final closeout sequence; its safe-parallelism rules replace the
original plan's rules once `R0-01` begins. That graph reached R4-02 and R5-01.
The later user-approved 15,000-line policy is documented in closeout C-008 and
does not alter this historical graph.

## Ownership Rule

An agent owns exactly one task ID and should not opportunistically implement successors. If it discovers successor work, record it in the task report with the existing task ID rather than creating a new subsystem or backlog.
