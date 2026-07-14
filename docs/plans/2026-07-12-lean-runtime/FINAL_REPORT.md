# Lean Runtime Release Evidence

Date: 2026-07-14

Status: **APPROVED under the 15,000-line C-008 policy; current evidence is in
the dated [closeout report](../2026-07-14-lean-runtime-closeout/FINAL_REPORT.md).**

## Current closeout status

The M5 and M6 evidence below is preserved as dated historical evidence; it is
not rewritten to make M5's 14,243-line failure look like a pass. M6-01 and
M6-02 completed the optional-project-memory and rendered-trace cleanup. The
subsequent closeout has repaired the enabled verification-agent bootstrap,
enforced the strict Ruff policy, proved the retained JSONL summary contract,
and removed the approved model-layer duplication.

Latest R6-01 regression evidence is `uv run pytest -q` → `580 passed, 1
deselected, 6 subtests passed`. The enabled path is covered by the network-free
`build_runtime` verifier-bootstrap regression; normal startup still constructs
no verifier or subagent. JSONL remains the only trace artifact and ends with a
`session_summary` row containing steps, `tools_used`, and accumulated token
totals; no HTML renderer, trace protocol module, or `runtime.evals` API is
restored.

The release command now reports `stable_production_python_lines=14094`, exact
seven stable tools, and exits 0 under the user-approved 15,000-line policy in
closeout [C-008](../2026-07-14-lean-runtime-closeout/DECISIONS.md#c-008-raise-the-stable-production-budget-to-15000-lines).
Only the line cap changed; roots, exclusions, tool cap, and dependency cap are
unchanged. The closeout
[FINAL_REPORT.md](../2026-07-14-lean-runtime-closeout/FINAL_REPORT.md) is the
current approval record.

## Historical M5-02 evidence (not a release approval)

This is fresh M5-02 evidence, not a release approval. At that historical
checkpoint, Q-05 remained failed until the stable-production line budget was
reduced.

## Historical M6-02 remediation update (not a release approval)

JSONL remains the only trace artifact. Its append-only event facts end in a
`session_summary` row containing steps, tools used, and accumulated token
totals. The HTML renderer and configuration, the unused trace protocol
declarations, and the product-side `runtime.evals` analysis API are deleted
rather than retained as opt-ins or compatibility layers. Trace/transcript
parity remains a direct runtime-event contract; deterministic scenario and demo
assertions inspect emitted facts without restoring an evaluator.

Fresh M6-02 evidence:

```bash
uv run pytest -q
# 548 passed, 1 deselected, 6 subtests passed
uv run ruff check .
# All checks passed!
uv run python scripts/check_release_metrics.py
# stable_production_python_lines=14243
# stable_tool_count=7
# exits 1: exceeds 14,000 by 243 lines
```

The stable tool names remain `Bash, Edit, Glob, Grep, Read, Task, TodoWrite`.
Focused trace/transcript/session-recovery and scenario coverage passed (`88
passed`); MCP coverage passed (`20 passed, 6 subtests passed`). The CI release
metrics job already runs the same enforcing command, so it remains correctly
red until a later scoped remediation reduces the final 243 lines. This update
does not grant release approval.

## Reproduce

```bash
uv sync --locked --extra dev --extra mcp
uv run pytest -q
uv run ruff check .
uv run pytest -q tests/scenarios
uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
uv lock --check
rg 'experimental\.teams|skill_evolution|Team[A-Z]' app core runtime tools extensions prompts
uv run python scripts/check_release_metrics.py
```

The final command is an enforcing gate and currently exits 0 under the 15,000
line C-008 budget. It uses the M0 baseline definition:

```bash
rg --files app core runtime tools extensions -g '*.py' |
  rg -v '^extensions/skill_evolution/' | xargs wc -l | tail -1
```

For the installed-command smoke, M5-02 created a temporary Python 3.12 venv,
ran `uv pip install --python <venv>/bin/python -e .`, initialized an unrelated
temporary Git repository, and ran that venv's `mycodeagent` command there.
The deterministic fake-runtime contract for one-shot output and selected root
is covered by `tests/test_cli_one_shot.py` and `tests/test_cli_project_root.py`.

## Baseline versus current tree

| Metric | M0 baseline | Current | Evidence |
|---|---:|---:|---|
| Stable production Python LOC | 19,320 | 14,243 | M0-compatible command above |
| Test Python LOC | 17,904 | 13,265 | `rg --files tests -g '*.py' \| xargs wc -l \| tail -1` |
| Markdown documentation LOC | 10,393 | 7,301 | `rg --files docs -g '*.md' \| xargs wc -l \| tail -1` |
| Required dependencies | 7 | 4 | `pyproject.toml` project dependencies |
| Stable model-visible tools | 12 | 7 | `scripts/check_release_metrics.py` |

Required dependencies are `pydantic`, `python-dotenv`, `prompt-toolkit`, and
`rich`. `anyio` and `mcp` are only in the `mcp` extra.

## Historical M5 acceptance evidence

| IDs | Status | Evidence |
|---|---|---|
| P-01 | PASS | Installed `mycodeagent --help` exited 0 in 1.36 seconds in an unrelated temporary Git repository. |
| P-02–P-07 | PASS | `uv run pytest -q tests/test_cli_project_root.py tests/test_cli_one_shot.py tests/test_cli_lifecycle.py tests/test_lean_defaults.py tests/runtime/test_transcript.py` → 56 passed in 0.51s. It covers default/explicit root, text and JSON one-shot, session list/resume, cancellation, transcript recovery, default startup, and seven-tool schema. |
| A-01 | PASS | The full suite includes canonical `RuntimeRunner` boundary tests; current `docs/HARNESS.md` names it as the only loop. |
| A-02–A-03 | PASS | Lean-default and trace contracts verify no default subagent, MCP process, extension network work, renderer configuration, or non-JSONL trace artifact. |
| A-04 | PASS | The stable-source `rg` command above returned no matches. |
| A-05 | PASS | Fresh transcript contracts prove transcript-only recovery and completed-versus-uncertain action handling. |
| A-06 | PASS | `uv run pytest -q tests/test_maintenance_boundaries.py::test_stable_tools_have_no_runtime_layer_imports` → 1 passed. |
| A-07 | PASS | Fresh core editable install had neither `mcp` nor `anyio`; a separately installed `.[mcp]` environment imported both. MCP-focused tests → 20 passed, 6 subtests passed. |
| T-01–T-07 | PASS | Metric output is exactly `Bash, Edit, Glob, Grep, Read, Task, TodoWrite`; full tool contracts and 23 scenarios cover confinement, conflict safety, atomic Edit, Glob/Grep, and recoverable oversized output. |
| Q-01 | PASS | `uv run pytest -q` → 548 passed, 1 deselected, 6 subtests passed in 3.43s. |
| Q-02 | PASS | `uv run ruff check .` → All checks passed. |
| Q-03 | PASS | `uv run pytest -q tests/scenarios` → 23 passed in 0.38s. |
| Q-04 | PASS | Current README/AGENT/HARNESS were checked against CLI help and defaults; documentation/packaging/maintenance focused contracts → 14 passed, then the full suite passed. |
| Q-05 | **FAIL** | `scripts/check_release_metrics.py` reports `stable_production_python_lines=14243`; this exceeds 14,000 by 243 and exits 1. |
| Q-06 | PASS | Four required dependencies and the fresh core-without-MCP/AnyIO import smoke above. |
| Q-07 | PASS | The original source worktree still has its six recorded user modifications unchanged: four Skill Evolution files, `runtime/session.py`, and `tools/builtin/bash.py`. |

## Removed scope and documentation

- Agent Teams: `551a9ca` plus `7911225` packaging repair.
- Skill Evolution: `7336ef1`.
- Snapshot persistence as recovery truth: `756556a`, `966b389`, and `a5c9466`.
- Write/MultiEdit: `16cf074`; ListFiles/search-by-name: `eff0688`.
- Obsolete compatibility layers and AskUser: `d48a38a`.

The active documentation is now README, HARNESS, the dated plan, and the
research archive. Superseded design notes, portfolio material, task breakdowns,
and trace snapshots are explicitly historical under `docs/archives/`.

## Historical outstanding remediation

At the historical M5/M6 checkpoint, Q-05 was a product release blocker, not an
external environment failure. The later closeout remediation and current
one-release exception are described above; R4-02 must collect fresh final
evidence before either report can become release approval.
