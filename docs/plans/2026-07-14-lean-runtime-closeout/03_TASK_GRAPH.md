# Closeout Task Graph

Each task is the maximum scope of one implementation agent. The goal runner
owns integration, verification, conflict resolution, and progress records.

```text
R0-01
  ├── R1-01 → R1-02 → R1-03 ───────────────┐
  └── R2-01 ────────────────────────────────┤
                                             ↓
                         R3-01 → R3-02 ─┐
                              └ R3-03 ──┼→ R3-04
                                        ↓
                               R4-01 → R4-02 → R5-01
```

## Safe Parallelism

- After `R0-01`, `R2-01` may run in parallel with the R1 chain in a separate
  worktree because it owns trace tests and documentation only.
- After `R1-03` and `R2-01` are integrated, `R3-03` may run in parallel with
  `R3-01`; integrate `R3-01` first, then rebase and integrate `R3-03`.
- `R3-02` starts only after `R3-01` because both change `core/llm.py`.
- All other tasks are sequential.

## Inventory

| ID | Outcome | Primary files |
|---|---|---|
| R0-01 | Baseline and worktree protection | closeout evidence |
| R1-01 | Working verifier bootstrap | `runtime/host.py`, bootstrap tests |
| R1-02 | Critical Ruff rules enforced | `pyproject.toml`, concrete findings |
| R1-03 | Import-order and dead-code cleanup | stable imports, narrow lint config |
| R2-01 | Proven JSONL summary contract | trace tests and docs |
| R3-01 | Data-driven provider resolution | `core/llm.py`, provider tests |
| R3-02 | One request/retry implementation | `core/llm.py`, model tests |
| R3-03 | Shared response normalization | `runtime/subagents.py`, subagent tests |
| R3-04 | Unchanged release budget passes | metric evidence |
| R4-01 | Plan/docs reconciliation | active docs and dated plan |
| R4-02 | Final release verification | `FINAL_REPORT.md` |
| R5-01 | Non-mutating integration handoff | `INTEGRATION_HANDOFF.md` |
