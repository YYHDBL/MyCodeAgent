# Lean Runtime Closeout Final Report

Date: 2026-07-14 CST (+0800)

Status: **RELEASE-READY — PUBLICATION AUTHORIZED**

This report includes fresh R6-01 evidence from the dedicated implementation worktree
`/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712`.
Q-06 now passes normally at 14,095 lines under the user-approved 15,000-line
[C-008](DECISIONS.md#c-008-raise-the-stable-production-budget-to-15000-lines).
C-008 supersedes C-006 without changing the metric's roots, exclusions,
seven-tool cap, or dependency cap.

## Branch and Closeout History

- Pre-evidence HEAD: `acc930573351322207534af8b1e4a6e8120408b1`
  (`docs(R4-01): reconcile lean runtime plans`).
- Branch: `lean-runtime-20260712`; `feature/skill-evolution` remains an
  ancestor (`git merge-base --is-ancestor feature/skill-evolution
  lean-runtime-20260712` exited 0).
- R0–R4-01 commits, in order: `e41f5f6`, `76af052`, `51c1fd5`, `73cc80f`,
  `f27cf38`, `e2c1706`, `888a88a`, `1d1ad97`, `0051bf2`, and `acc9305`.
  The R4-02 evidence commit is recorded in Git history rather than
  self-referencing its content-derived SHA, per original-plan D-001.
- No merge, rebase, push, reset, stash, or original-worktree mutation occurred.

## Acceptance Matrix

| ID | Result | Fresh command and exact result |
|---|---|---|
| S-01 | PASS | `git status --short --branch` → `## lean-runtime-20260712`; HEAD before evidence `acc930573351322207534af8b1e4a6e8120408b1`. |
| S-02 | PASS | `git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent status --short --branch` reported exactly the same six modified paths as R0. The portable binary diff hash command returned `655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`, equal to R0. |
| S-03 | PASS | `git log --reverse --format='%H %s' 8f165ed..HEAD` contains one scoped commit for each completed task R0-01 through R5-01, and `git status --short --branch` reports `## lean-runtime-20260712` with no worktree paths. Per original-plan D-001, the R5-01 handoff is committed separately rather than self-referencing its content-derived SHA; the same log command locates it. |
| F-01 | PASS | `uv run pytest -q tests/test_app_bootstrap.py -k verification` → `1 passed, 8 deselected in 0.13s`; it exercises network-free enabled `build_runtime` construction. |
| F-02 | PASS | `uv run pytest -q tests/test_lean_defaults.py::test_default_host_startup_creates_no_optional_runtime_services` → `1 passed in 0.08s`. |
| F-03 | PASS | `uv run pytest -q tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py` → `26 passed in 0.10s`. |
| L-01 | PASS | `uv run ruff check . --select F821` is included in `uv run ruff check . --select E722,F401,F541,F821,F841` → `All checks passed!`; configuration scan printed `global_ignore=[]`, `critical_global_ignores=[]`. |
| L-02 | PASS | `uv run ruff check . --select E722,F401,F541,F821,F841` → `All checks passed!`. |
| L-03 | PASS | `uv run ruff check app core runtime tools extensions prompts utils --select E402` → `All checks passed!`. |
| L-04 | PASS | `uv run ruff check .` → `All checks passed!`. |
| T-01 | PASS | `uv run pytest -q tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary tests/test_lean_defaults.py::test_trace_logger_writes_only_jsonl` → `2 passed in 0.07s`. |
| T-02 | PASS | The same focused summary contract asserts the final JSONL `session_summary` with steps, `tools_used`, and accumulated token totals; it passed as above. |
| T-03 | PASS | `test ! -e runtime/evals.py`; `test ! -e extensions/tracing/protocol.py`; and stable scan `! rg -n 'trace_html_enabled\|runtime\\.evals\|summarize_trace' app core runtime tools extensions prompts` → no matches. |
| A-01 | PASS | `uv run pytest -q tests/test_llm_provider_resolution.py tests/test_llm_temperature_policy.py tests/test_llm_requests.py tests/runtime/test_model_errors.py tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py tests/test_core_without_mcp.py` → `63 passed in 0.73s`; provider credential/default ladder scan returned no matches. |
| A-02 | PASS | The same 63-test command includes provider precedence coverage; `! rg -n 'load_dotenv\|dotenv_values\|_env_cache\|_load_env' core/llm.py` → no private LLM environment loader. |
| A-03 | PASS | The same 63-test command covers stream, raw, retries, MiniMax, Kimi, and omitted `None`; source inspection found exactly `def _build_request` and `def _invoke_with_retries` in `core/llm.py`. |
| A-04 | PASS | The same 63-test command covers dict/SDK-shaped subagent responses; legacy adapter scan in `runtime/subagents.py` returned no matches, while canonical `core.llm` extractors are present. |
| A-05 | PASS | `pyproject.toml` scan printed four required dependencies: Pydantic, python-dotenv, prompt-toolkit, and Rich (`required_dependency_count=4`). No framework/dependency was added. |
| Q-01 | PASS | `uv run pytest -q` → `580 passed, 1 deselected, 6 subtests passed in 3.91s`. |
| Q-02 | PASS | `uv run pytest -q tests/scenarios` → `23 passed`. |
| Q-03 | PASS | `uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py` → `20 passed, 6 subtests passed`. |
| Q-04 | PASS | `uv lock --check` → `Resolved 46 packages`. |
| Q-05 | PASS | Fresh Python 3.12 venv editable install in a new unrelated Git repository: installed `mycodeagent --help` exited 0 in `1.322s` (<3s); the temporary directory was removed. |
| Q-06 | PASS | `uv run python scripts/check_release_metrics.py` → exit 0, `stable_production_python_lines=14095`, `stable_tool_count=7`, `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`. C-008 sets the cap to `15_000`; roots `(app, core, runtime, tools, extensions)`, exclusions, tool cap `7`, and four required dependencies are unchanged. |
| Q-07 | PASS | `rg 'experimental\\.teams\|skill_evolution\|Team[A-Z]' app core runtime tools extensions prompts` returned no matches (rg exit 1, expected); `experimental/teams` and `extensions/skill_evolution` are absent. |
| Q-08 | PASS | `uv run pytest -q tests/test_release_metrics.py tests/test_tool_surface_docs.py tests/test_maintenance_boundaries.py tests/test_cli_one_shot.py tests/test_lean_defaults.py` → `34 passed`; active documentation and the regression agree on the 15,000-line policy and normal exit-0 release gate. |
| D-01 | PASS | This report and `INTEGRATION_HANDOFF.md` map every acceptance ID to fresh, reproducible evidence; no release exception remains. |
| D-02 | PASS | R5-01 added `INTEGRATION_HANDOFF.md` with the exact base (`cf0d0a02aa1f5c201bbefad56849c24ca2dba1a9`), release-ready runtime head (`2a803d3`), 83-commit range command, all completed closeout commits, six protected paths, conflict treatment, three user-controlled choices, and the complete R4-02 post-integration verification checklist. It records that no merge, rebase, push, checkout, reset, stash, or original-worktree write occurred. |

## Metrics and Product Boundary

| Metric | Program baseline | Final fresh count |
|---|---:|---:|
| Stable production Python | 19,320 | 14,095 |
| Stable production Python (R0 closeout baseline) | 14,243 | 14,095 |
| Test Python | 17,904 | 13,692 |
| Markdown documentation | 10,393 | 10,015 |
| Required dependencies | 7 | 4 |
| Stable model-visible tools | 12 | 7 |

The final stable tools are exactly `Bash, Edit, Glob, Grep, Read, Task,
TodoWrite`. JSONL remains the sole trace artifact and retains final summary
metrics; HTML renderer/configuration, trace protocol declarations, and
`runtime.evals` remain absent. The default creates no verifier/subagent; MCP
and verification are explicit opt-ins.

The four required dependencies counted toward A-05 and Q-06 are `pydantic`,
`python-dotenv`, `prompt-toolkit`, and `rich`. They are distinct from optional
extras: `mcp` contains `anyio` and `mcp`; `dev` contains `pytest`, `ruff`, and
`tomli` only for Python <3.11. Optional extras do not count toward the required
dependency cap.

## Protected Original Worktree

The original worktree remains on `feature/skill-evolution` ahead of origin by
one commit, with exactly these user-owned modifications: four
`extensions/skill_evolution` files, `runtime/session.py`, and
`tools/builtin/bash.py`. Its fresh per-file numstat matches R0 (`0/1`, `3/1`,
`1/1`, `3/1`, `3/1`, and `16/0` respectively) and its portable SHA-256 is
unchanged. It has not been stashed, reset, committed, copied over, deleted,
or otherwise modified by this closeout.

The portable, read-only reproduction command is:

```bash
LC_ALL=C LANG=C git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent \
  diff --binary -- \
  extensions/skill_evolution/adapter.py \
  extensions/skill_evolution/evolution/buffer.py \
  extensions/skill_evolution/evolution/observer.py \
  extensions/skill_evolution/evolution/success_store.py \
  runtime/session.py \
  tools/builtin/bash.py \
  | LC_ALL=C LANG=C shasum -a 256
```

It produced the R0-matching
`655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`.

## Integration State

The user has authorized direct merge and push after relaxing the stable
production budget. Integration will be performed from a separate clean
`main` worktree, followed by the full acceptance verification on the merged
tree. The original dirty `feature/skill-evolution` worktree and its six
user-owned changes must remain untouched. Q-06 is now a normal passing gate
under C-008; C-006 is superseded.
