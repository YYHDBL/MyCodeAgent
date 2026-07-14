# Closeout Acceptance Criteria

Every row requires fresh evidence. A passing unit test does not substitute for
the listed integration or release command.

## Safety

| ID | Criterion | Evidence |
|---|---|---|
| S-01 | Correct implementation branch/worktree | `git status --short --branch` names `lean-runtime-20260712`. |
| S-02 | Original user work is untouched | Before/after status and blob/diff hashes for all six protected paths match. |
| S-03 | Task history is reviewable | One scoped commit per task; implementation worktree clean at final handoff. |

## Functional Correctness

| ID | Criterion | Evidence |
|---|---|---|
| F-01 | Enabled verifier bootstraps | Network-free `build_runtime` test with `enable_verification_agent=True` constructs a `SubagentCompletionVerifier`. |
| F-02 | Default remains lean | Existing default bootstrap test proves no verifier or subagent is created. |
| F-03 | Verifier behavior remains correct | Focused subagent/completion scenario tests pass. |

## Static Quality

| ID | Criterion | Evidence |
|---|---|---|
| L-01 | Undefined names cannot be hidden globally | `F821` absent from global Ruff ignores; `uv run ruff check . --select F821` passes. |
| L-02 | Basic dead-code rules pass | `uv run ruff check . --select E722,F401,F541,F841` passes without global ignores. |
| L-03 | Stable imports are ordered | `uv run ruff check app core runtime tools extensions prompts utils --select E402` passes. |
| L-04 | Normal project lint passes | `uv run ruff check .` exits 0. |

## Trace Contract

| ID | Criterion | Evidence |
|---|---|---|
| T-01 | JSONL is the only trace artifact | Focused trace test finds JSONL and no HTML/report artifact. |
| T-02 | Lightweight summary metrics remain | Final JSONL row is `session_summary` with steps, tools used, and token totals. |
| T-03 | Removed trace systems stay removed | Stable scan finds no renderer flag, trace protocol module, or `runtime.evals` import. |

## Architecture and Simplicity

| ID | Criterion | Evidence |
|---|---|---|
| A-01 | Provider metadata is data-driven | Provider behavior tests pass and code review finds no repeated credentials/default-model `if/elif` ladders. |
| A-02 | Environment loading has one owner | `HelloAgentsLLM` has no private dotenv cache/loader; precedence test proves explicit args > process env > `.env` > defaults. |
| A-03 | Request/retry logic has one implementation | Streaming/non-streaming/raw tests pass through shared request construction; no duplicate retry loops remain. |
| A-04 | Response normalization has one owner | Main runtime and subagent tests use `core.llm` extraction behavior. |
| A-05 | No new dependency or abstraction tax | Required dependencies remain at most five; no new single-caller framework layer. |

## Release

| ID | Criterion | Evidence |
|---|---|---|
| Q-01 | Full deterministic suite passes | `uv run pytest -q`. |
| Q-02 | Scenario suite passes | `uv run pytest -q tests/scenarios`. |
| Q-03 | MCP optional suite passes | Existing three-file MCP command passes. |
| Q-04 | Lock is current | `uv lock --check`. |
| Q-05 | Installed CLI starts promptly | Fresh editable install in a temporary venv; unrelated-repo `mycodeagent --help` exits 0 under 3 seconds. |
| Q-06 | Release metrics pass | `uv run python scripts/check_release_metrics.py` exits 0 with production lines ≤15,000 and exactly seven tools. |
| Q-07 | Research systems remain absent | Stable-source Teams/Skill Evolution scan returns no matches. |
| Q-08 | Docs and behavior agree | README, HARNESS, CLI help, original plan, and final report describe actual defaults and retained trace summary. |

## Delivery

| ID | Criterion | Evidence |
|---|---|---|
| D-01 | Release approval is evidence-backed | `FINAL_REPORT.md` maps every ID above to a command/result. |
| D-02 | Integration is safe and explicit | `INTEGRATION_HANDOFF.md` documents commits, dirty paths, conflicts, and user choices without performing the merge. |
