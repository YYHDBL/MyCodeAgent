# Closeout Progress

Append one entry per completed task using the format in
`04_EXECUTION_PROTOCOL.md`. Do not pre-mark tasks complete.

## Current State

- Current task: `R6-01` is complete. The user approved a 15,000-line stable
  production budget and authorized merge/push. Integration must happen from a
  separate clean worktree; the original worktree and its six changes remain
  protected.
- Completed commits: `docs(R0-01): capture closeout baseline`,
  `fix(R1-01): repair verification-agent bootstrap`,
  `chore(R1-02): enforce critical Ruff rules`,
  `chore(R1-03): make import ordering explicit`,
  `docs(R2-01): clarify JSONL summary contract`,
  `refactor(R3-01): data-drive provider resolution`,
  `refactor(R3-02): share model request handling`,
  `refactor(R3-03): share response normalization`,
  `docs(R3-04): record approved budget exception`,
  `docs(R4-01): reconcile lean runtime plans`, and
  `docs(R4-02): record final release verification`, and
  `docs(R5-01): prepare integration handoff`. Per original-plan D-001,
  task records use subjects rather than self-referential content-derived SHAs.
- Release approval: all gates pass under the user-approved C-008 policy; direct
  integration and publication are authorized.
- Q-06: `scripts/check_release_metrics.py` exits 0 at 14,095 stable production
  lines and seven stable tools under the 15,000-line cap. C-008 supersedes the
  temporary C-006 exception; source roots, exclusions, tool contract, and
  dependency cap are unchanged.
- Known blockers at plan creation (historical): verifier bootstrap `NameError`; production
  metric 14,243 > 14,000; original worktree contains six protected changes.

## R6-01 — complete

- Changed: raised only the stable-production line cap from 14,000 to 15,000,
  added a release-policy regression, and synchronized active plans and reports.
- RED: `uv run pytest -q tests/test_release_metrics.py` failed with
  `assert 14000 == 15000`.
- GREEN: the same command passed; `uv run python
  scripts/check_release_metrics.py` exited 0 with
  `stable_production_python_lines=14095` and `stable_tool_count=7`.
- Regression: full suite `580 passed, 1 deselected, 6 subtests passed`; normal,
  strict-critical, and stable-source E402 Ruff checks passed; scenarios passed
  23/23; MCP coverage passed 20 tests plus 6 subtests; lock check resolved 46
  packages; installed CLI help exited 0 in 1.322 seconds from an unrelated repo.
- Remaining: merge into a clean `main` integration worktree, repeat the release
  gates on the merged tree, and push without touching the original dirty
  `feature/skill-evolution` worktree.

## R5-01 — complete

- Commit: `docs(R5-01): prepare integration handoff`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: created `INTEGRATION_HANDOFF.md`; updated the final report's D-01
  and D-02 delivery evidence and this current-state record only. The handoff
  records the exact topology, all completed closeout commits, local-only branch
  state, six protected paths, four modify/delete conflicts, two modify/modify
  conflicts, three user-controlled choices, and the full R4-02 verification
  checklist.
- RED: not applicable: this task is an explicit, non-mutating documentation
  handoff after R4-02 release verification.
- GREEN: read-only topology commands returned merge-base
  `cf0d0a02aa1f5c201bbefad56849c24ca2dba1a9`, `83` branch-only commits, and no
  upstream for `lean-runtime-20260712`. The original worktree still reported
  exactly six modified paths; portable protected-diff SHA-256 was
  `655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`, matching
  R0.
- Regression: documentation consistency is covered by R4-02's fresh Q-08;
  `git diff --check` must pass before the handoff commit. No production behavior,
  dependency, metric, or tool surface changed.
- Metrics: unchanged. Q-06 remains C-006's user-approved one-release
  exception: the raw enforcing command exits 1 at 14,095 lines; it is not a
  passing metric.
- Remaining: user-controlled integration decision only; no automatic merge,
  rebase, push, checkout, reset, stash, or original-worktree mutation is
  authorized.

## R0-01 — complete

- Commit: `docs(R0-01): capture closeout baseline`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; the final report and integration
  handoff record closeout commit SHA(s). Locate this record with
  `git log --oneline -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: created `BASELINE.md` and recorded this progress entry only; no
  product file changed.
- RED: exact network-free here-doc under
  [`BASELINE.md`'s verifier reproduction](BASELINE.md#network-free-enabled-verifier-reproduction)
  runs `uv run python -`; it exited 1 with
  `NameError: name 'SubagentCompletionVerifier' is not defined` at
  `runtime/host.py:122`. Exact strict command
  `uv run ruff check . --select E402,E722,F401,F541,F821,F841` exited 1:
  `Found 100 errors`; reproducible JSON count was
  `E402:49, E722:2, F401:45, F541:2, F821:1, F841:1`.
- GREEN: `uv run pytest -q` → `548 passed, 1 deselected, 6 subtests passed in
  3.45s` (exit 0); `uv run pytest -q tests/scenarios` → `23 passed in 0.44s`
  (exit 0); `uv run pytest -q tests/extensions/test_mcp_extension.py
  tests/test_core_without_mcp.py tests/test_mcp_protocol.py` → `20 passed,
  6 subtests passed in 0.54s` (exit 0); `uv run ruff check .` → `All checks
  passed!` (exit 0); `uv lock --check` → `Resolved 46 packages in 2ms`
  (exit 0). Exact fresh-editable-install and unrelated-repository command is
  recorded in [`BASELINE.md`'s installed CLI section](BASELINE.md#installed-cli-help-from-an-unrelated-repository):
  `mycodeagent --help` → exit 0 in `1.266s`.
- Regression: `uv run python scripts/check_release_metrics.py` → exit 1:
  `release metric failure: stable production Python exceeds 14000: 14243`,
  `stable_production_python_lines=14243`, `stable_tool_count=7`, and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`.
- Metrics: stable production Python `14,243` (target `≤14,000`); stable tools
  `7`; protected original-worktree binary diff SHA-256
  `655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`.
- Remaining: goal-runner review; `R1-01` and `R2-01` have not started and may
  begin only under the graph's permitted separate-worktree parallelism.

## R1-01 — complete

- Commit: `fix(R1-01): repair verification-agent bootstrap`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; the final report and integration
  handoff record closeout commit SHA(s). Locate this record with
  `git log --oneline -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: `runtime/host.py` now imports and constructs
  `SubagentCompletionVerifier` only inside the enabled verification-agent
  branch; `tests/test_app_bootstrap.py` adds a network-free enabled-bootstrap
  regression; this progress record only.
- RED: `uv run pytest -q
  tests/test_app_bootstrap.py::test_enabled_verification_agent_bootstraps_without_network`
  → `1 failed in 0.22s` (exit 1), with `NameError: name
  'SubagentCompletionVerifier' is not defined` at `runtime/host.py:122` after
  `build_runtime` constructed `CodeAgent` with verification enabled.
- GREEN: the same command → `1 passed in 0.11s` (exit 0). Focused command
  `uv run pytest -q tests/test_app_bootstrap.py tests/test_lean_defaults.py
  tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py`
  → `38 passed in 0.24s` (exit 0); `uv run ruff check runtime/host.py
  tests/test_app_bootstrap.py` → `All checks passed!` (exit 0).
- Regression: `uv run pytest -q` → `549 passed, 1 deselected, 6 subtests
  passed in 4.13s` (exit 0). Existing
  `test_default_host_startup_creates_no_optional_runtime_services` is included
  in the focused command and still asserts no `completion_verifier` exists on
  default startup.
- Metrics: stable production Python `14,243` → `14,245` (the two-line lazy
  import; target remains `≤14,000`); stable tools `7` → `7`. Fresh
  `uv run python scripts/check_release_metrics.py` exited 1 only for the
  existing production-line cap: `stable_production_python_lines=14245`,
  `stable_tool_count=7`.
- Remaining: goal-runner review; `R1-02`, `R1-03`, and `R2-01` have not
  started.

## R1-02 — complete

- Commit: `chore(R1-02): enforce critical Ruff rules`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: `pyproject.toml`; the task's listed production findings in
  `core/env.py`, `prompts/agents_prompts/subagent_summary_prompt.py`,
  `runtime/completion.py`, `runtime/host.py`, `tools/builtin/bash.py`,
  `tools/builtin/read_file.py`, `tools/builtin/todo_write.py`, and
  `tools/registry.py`; exact strict-Ruff-reported auxiliary/test files
  `utils/ui_components.py`, `tests/runtime/test_host.py`,
  `tests/runtime/test_prompt_assembly_trace.py`,
  `tests/runtime/test_subagents.py`, `tests/runtime/test_transcript.py`,
  `tests/scenarios/test_phase7_subagents.py`, `tests/test_bash_tool.py`,
  `tests/test_cli_project_root.py`, `tests/test_core_without_mcp.py`,
  `tests/test_read_tool.py`, `tests/test_todo_write_tool.py`,
  `tests/test_trace_logger.py`, `tests/tools/test_edit_contract.py`,
  `tests/tools/test_permissions.py`, `tests/tools/test_result_contract.py`,
  `tests/utils/protocol_validator.py`, and `tests/utils/test_helpers.py`; and
  this progress record plus [C-003](DECISIONS.md#c-003-apply-strict-ruff-cleanup-to-every-reported-path)
  and [C-004](DECISIONS.md#c-004-replace-the-deleted-r1-02-focused-protocol-path-with-live-coverage).
  The edits remove only unused imports/assignment, placeholder-free f-string
  markers, and bare `except` clauses; the prompt re-export is explicitly
  retained with `__all__`; test assertions and ordinary Exception/JSON
  fallback handling are unchanged, while `KeyboardInterrupt` and `SystemExit`
  are intentionally no longer caught by the former bare handlers.
- RED: `uv run ruff check . --select E722,F401,F541,F821,F841` exited 1 with
  `Found 50 errors` (`E722:2`, `F401:45`, `F541:2`, `F841:1`). The first
  focused command from the task then exited 4 before collection because
  `tests/test_protocol_compliance.py` does not exist. Root cause: commit
  `08480a8 test(M5-01): center suite on contracts and scenarios` deleted that
  path and moved its envelope assertion to `tests/contracts/tool_results.py`.
- GREEN: `uv run ruff check . --select E722,F401,F541,F821,F841` → `All checks
  passed!` (exit 0); `uv run ruff check .` → `All checks passed!` (exit 0).
  Config scan printed `global_ignore=['E402']` and
  `critical_global_ignores=[]` (exit 0), so `E722`, `F401`, `F541`, `F821`, and
  `F841` have no global suppression.
- Regression: per C-004, the live replacement command `uv run pytest -q
  tests/test_todo_write_tool.py tests/test_app_bootstrap.py
  tests/test_lean_defaults.py tests/contracts/test_tool_result_contracts.py`
  → `75 passed in 0.37s` (exit 0); `uv run pytest -q` → `549 passed, 1
  deselected, 6 subtests passed in 3.97s` (exit 0).
  `git diff --check` exited 0.
- Metrics: stable production Python `14,245` → `14,238`; stable tools `7` →
  `7`. Fresh `uv run python scripts/check_release_metrics.py` exited 1 only
  for the existing production-line cap: `stable_production_python_lines=14238`,
  `stable_tool_count=7`, and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`.
- Remaining: goal-runner review; `R1-03` then `R2-01` remain.

## R1-03 — complete

- Commit: `chore(R1-03): make import ordering explicit`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: `app/cli.py` now imports required Rich and prompt-toolkit modules at
  module top level without an import-time `try`/`sys.exit` path; its existing
  `main()` initialization error handling remains the CLI error boundary.
  `runtime/host.py` no longer imports or calls redundant module-level
  `load_env()` because bootstrap/configuration owns environment loading.
  `tests/runtime/test_context_compaction.py` and
  `tests/runtime/test_context_engine.py` move their module imports to the top.
  `pyproject.toml` removes the global E402 ignore and documents the only narrow
  E402 exceptions: `tests/conftest.py` and the standalone
  `demo/harness_portfolio.py`, each of which must prepend the repository root
  before local imports.
- RED: `uv run ruff check . --select E402 --output-format concise` exited 1
  with `Found 48 errors`: `app/cli.py` (4), `runtime/host.py` (19), the two
  test modules (10), `tests/conftest.py` (1), and the standalone demo (14).
  The task text's historical 49-finding count did not match the fresh
  `51c1fd5` checkout. The focused characterization command `uv run pytest -q
  tests/test_cli_one_shot.py tests/test_cli_project_root.py
  tests/runtime/test_context_compaction.py tests/runtime/test_context_engine.py
  tests/scenarios/test_phase9_portfolio_demos.py` → `44 passed in 0.57s`
  before the edit.
- GREEN: `uv run ruff check . --select E402 --output-format concise` → `All
  checks passed!`; `uv run ruff check app core runtime tools extensions prompts
  utils --select E402` → `All checks passed!`; `uv run ruff check .` → `All
  checks passed!`. The focused command above → `44 passed in 0.55s`; `uv run
  mycodeagent --help` exited 0 and printed the normal CLI usage.
- Regression: `uv run pytest -q` → `549 passed, 1 deselected, 6 subtests
  passed in 3.40s` (exit 0); `git diff --check` exited 0. A first GREEN lint
  attempt found one missed duplicate module-level `Config` import at
  `tests/runtime/test_context_engine.py:246` (`E402` plus `F811`); its root
  cause was the pre-existing second import. Removing only that duplicate made
  the recorded gates pass.
- Metrics: stable production Python `14,238` → `14,232`; stable tools `7` →
  `7`. Fresh `uv run python scripts/check_release_metrics.py` exited 1 only for
  the existing production-line cap: `stable_production_python_lines=14232`,
  `stable_tool_count=7`, and `stable_tools=Bash, Edit, Glob, Grep, Read, Task,
  TodoWrite`.
- Remaining: goal-runner review; then `R2-01` and the dependent R3 work.

## R2-01 — complete

- Commit: `docs(R2-01): clarify JSONL summary contract`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: the original goal and historical final report now distinguish
  retained append-only JSONL facts and final `session_summary` metrics (steps,
  tools used, accumulated token totals) from the removed HTML
  renderer/configuration, trace protocol declarations, and generic
  `runtime.evals` analysis API. `tests/test_trace_logger.py` was inspected but
  not changed because its existing contract already asserts every required
  field; README and HARNESS wording was already unambiguous and remains
  unchanged.
- RED: not applicable: this task changes documentation only after the existing
  executable contract characterized the retained behavior.
- GREEN: `uv run pytest -q
  tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary`
  → `1 passed in 0.31s` (exit 0); the final JSONL row is asserted as
  `session_summary` with `steps == 2`, `tools_used == 1`, and accumulated
  `total_tokens == 30` plus zero prompt/completion totals.
- Regression: `uv run pytest -q
  tests/test_lean_defaults.py::test_trace_logger_writes_only_jsonl
  tests/extensions/test_tracing_extension.py
  tests/runtime/test_prompt_assembly_trace.py` → `4 passed in 0.13s` (exit 0).
  Step 5 regression `uv run pytest -q tests/test_trace_logger.py
  tests/extensions/test_tracing_extension.py tests/runtime/test_transcript.py
  tests/scenarios` → `61 passed in 0.52s` (exit 0); `uv run ruff check .` →
  `All checks passed!` (exit 0); `git diff --check` exited 0.
  `test ! -e runtime/evals.py`; `test ! -e
  extensions/tracing/protocol.py`; and the stable-source scan for
  `trace_html_enabled|runtime.evals|summarize_trace` all passed with no
  matches.
- Metrics: no production, tool, or dependency files changed.
- Remaining: goal-runner review; then dependent R3 work.

## R3-01 — complete

- Commit: `refactor(R3-01): data-drive provider resolution`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: `core/llm.py` now owns immutable provider profiles for credential
  environment names, defaults, URL markers, and model defaults; it has no
  private dotenv cache or loader. Explicit provider aliases and declared URL
  markers remain, while unsupported key-shape and port-only guesses are
  removed per [C-005](DECISIONS.md#c-005-provider-resolution-uses-declared-names-and-urls-not-opaque-key-formats).
  Provider tests cover every retained explicit profile, generic `auto`, alias
  and base-URL normalization, and a subprocess boundary proving constructor
  values > process environment > `.env`-filled missing values > defaults.
- RED: `uv run pytest -q tests/test_llm_provider_resolution.py` → `14 passed,
  1 failed in 0.20s` (exit 1). The new precedence regression demonstrated the
  old private cache selected `.env` `deepseek|dotenv-key|https://dotenv.example/v1|dotenv-model`
  over process `openai|process-key|https://process.example/v1|process-model`.
- GREEN: `uv run pytest -q tests/test_llm_provider_resolution.py
  tests/test_llm_temperature_policy.py tests/test_app_bootstrap.py
  tests/test_core_without_mcp.py` → `33 passed in 0.77s` (exit 0); `uv run
  ruff check core/llm.py tests/test_llm_provider_resolution.py` → `All checks
  passed!` (exit 0). The immediate post-refactor first run found three old
  tests directly relying on the deliberately deleted private dotenv loader;
  their root cause was isolated and they now exercise parameter/process
  behavior, while the subprocess owns the application `core.config`/`core.env`
  boundary.
- Regression: `uv run pytest -q` → `561 passed, 1 deselected, 6 subtests
  passed in 3.50s` (exit 0); `git diff --check` exited 0.
- Metrics: stable production Python `14,232` → `14,170`; stable tools `7` →
  `7`. Fresh `uv run python scripts/check_release_metrics.py` exited 1 only
  for the remaining unchanged-cap failure:
  `stable_production_python_lines=14170`, `stable_tool_count=7`, and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`.
- Remaining: goal-runner review; `R3-02` remains dependent on this
  `core/llm.py` commit, and R3-03/R3-04 follow the task graph.

### R3-01 review repair

- Changed: parameterized the provider-alias regression to cover the retained
  case-normalized `SiliconFlow` input plus both declared aliases,
  `silicon-flow` and `silicon_flow`.
- Verification: `uv run pytest -q tests/test_llm_provider_resolution.py` →
  `17 passed in 0.24s` (exit 0); `uv run ruff check
  tests/test_llm_provider_resolution.py` → `All checks passed!` (exit 0);
  `git diff --check` exited 0.

## R3-02 — complete

- Commit: `refactor(R3-02): share model request handling`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: `core/llm.py` now has one `_build_request` owner for message
  normalization, temperature resolution, `None` omission, streaming, and
  MiniMax compatibility, plus one `_invoke_with_retries` loop for non-streaming
  calls. `invoke_raw` returns that helper's raw client result and `invoke`
  projects its existing message content; `think` keeps its non-retrying stream
  behavior through the same builder. `tests/test_llm_requests.py` characterizes
  raw/content projection, retry count/backoff/final wrapping, `None` omission,
  MiniMax handling, and streamed text chunks. Existing
  `tests/test_llm_temperature_policy.py` retains Kimi temperature coverage.
- RED / characterization: before the refactor, `uv run pytest -q
  tests/test_llm_requests.py tests/test_llm_temperature_policy.py
  tests/test_llm_provider_resolution.py tests/runtime/test_model_errors.py` →
  `32 passed in 0.28s` (exit 0). These are behavior-preserving
  characterization tests; no missing contract was discovered.
- GREEN: after the refactor, the same focused command → `32 passed in 0.29s`
  (exit 0); `uv run ruff check core/llm.py tests/test_llm_requests.py` → `All
  checks passed!` (exit 0).
- Regression: `uv run pytest -q` → `569 passed, 1 deselected, 6 subtests
  passed in 3.65s` (exit 0); `git diff --check` exited 0. Source review finds
  one non-streaming retry loop and one request builder; the streaming dispatch
  remains intentionally separate and has no retry loop.
- Metrics: `core/llm.py` `617 → 599` lines; stable production Python
  `14,170 → 14,152` (target `≤14,000`); stable tools remain `7`
  (`Bash, Edit, Glob, Grep, Read, Task, TodoWrite`); required dependencies
  remain `4`. Fresh `uv run python scripts/check_release_metrics.py` exited 1
  only for the remaining production-line cap: `stable_production_python_lines=14152`.
- Remaining: goal-runner review; R3-03 and then R3-04 remain. This task does
  not start either task.

### R3-02 review repair

- Root cause: the first refactor projected `response.choices[0].message.content`
  after `_invoke_with_retries` returned. A malformed but client-successful
  response with empty `choices` therefore raised a bare `IndexError` outside
  the configured retry and error-wrapping boundary.
- RED: `uv run pytest -q
  tests/test_llm_requests.py::test_invoke_retries_empty_choices_before_wrapping_the_final_failure`
  → `1 failed in 0.04s` (exit 1), with `IndexError: list index out of range`
  at `core/llm.py:587`; the client was called only once rather than the
  configured two attempts.
- GREEN: `_invoke_with_retries` now performs an optional response projection
  inside its existing `try` block. `invoke` supplies its unchanged content
  projection; `invoke_raw` supplies none and still returns the raw response.
  The RED command → `1 passed`; `uv run pytest -q tests/test_llm_requests.py
  tests/test_llm_temperature_policy.py tests/test_llm_provider_resolution.py
  tests/runtime/test_model_errors.py` → `33 passed in 0.34s` (exit 0);
  `uv run ruff check core/llm.py tests/test_llm_requests.py` → `All checks
  passed!` (exit 0).
- Regression: `uv run pytest -q` → `570 passed, 1 deselected, 6 subtests
  passed in 3.45s` (exit 0); `git diff --check` exited 0. The one retry loop
  remains the only non-streaming retry implementation.
- Metrics: final R3-02 `core/llm.py` is `604` lines (`617 → 604` from R3-01);
  fresh release metrics remain red only for the cap at
  `stable_production_python_lines=14157`, with seven stable tools.

## R3-03 — complete

- Commit: `refactor(R3-03): share response normalization`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: deleted the unused `_SubagentRuntimeHost` JSON-input and response
  extraction adapters, together with their private `_attr` and
  `_response_message` helpers. `RuntimeRunner` retains direct imports of the
  canonical `core.llm` response helpers and `ToolOrchestrator` retains direct
  `parse_tool_input` use; no forwarding wrapper was added. The subagent test
  now proves the legacy host adapter is absent and that dictionary and SDK-style
  standard responses normalize identically through the canonical helpers.
- RED: `uv run pytest -q
  tests/runtime/test_subagents.py::test_subagent_response_normalization_uses_canonical_dict_and_sdk_contracts`
  → `1 failed in 0.15s` (exit 1), exclusively because `_SubagentRuntimeHost`
  still defined `_ensure_json_input`. Initial full characterization before the
  edit, `uv run pytest -q tests/runtime/test_host.py tests/runtime/test_runner.py
  tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py`,
  → `56 passed in 0.31s` (exit 0).
- GREEN: the new regression → `1 passed in 0.16s` (exit 0); `uv run pytest -q
  tests/runtime/test_host.py tests/runtime/test_runner.py tests/runtime/test_subagents.py
  tests/scenarios/test_phase7_subagents.py tests/scenarios/test_lean_runtime_characterization.py`
  → `67 passed in 0.19s` (exit 0); `uv run ruff check runtime/subagents.py` →
  `All checks passed!` (exit 0). The final source scan has no legacy host
  adapter/helper definitions, while `runtime/loop.py` and
  `tools/orchestrator.py` import canonical `core.llm` helpers directly.
- Regression: `uv run pytest -q` → `571 passed, 1 deselected, 6 subtests
  passed in 3.55s` (exit 0); `git diff --check` exited 0.
- Metrics: `runtime/subagents.py` `797 → 735` lines; stable production Python
  `14,157 → 14,095`; stable tools `7 → 7`; required dependencies remain `4`.
  Fresh `uv run python scripts/check_release_metrics.py` exited 1 only for the
  remaining production-line cap: `stable_production_python_lines=14095`,
  `stable_tool_count=7`, and `stable_tools=Bash, Edit, Glob, Grep, Read, Task,
  TodoWrite`.
- Remaining: goal-runner review and R3 milestone review; then R3-04.

### R3-03 review repair

- Changed: parameterized the absence regression across all seven deleted host
  adapters (`_ensure_json_input`, `_extract_content`,
  `_extract_reasoning_content`, `_extract_tool_calls`, `_extract_usage`,
  `_extract_response_meta`, and `_extract_raw_response`). Added a real
  `_SubagentRuntimeHost` → `RuntimeRunner` execution with a one-response LLM
  stub for both dictionary and SDK-shaped responses; it compares the final
  structured child text and the emitted `model_output` facts, including usage,
  metadata, raw-response serialization, and tool calls. No production file
  remains changed by this review repair.
- RED: after adding the parameterized absence regression, temporarily restored
  only `_ensure_json_input` in the worktree and ran `uv run pytest -q
  'tests/runtime/test_subagents.py::test_subagent_runtime_host_has_no_legacy_response_adapters[_ensure_json_input]'`
  → `1 failed in 0.12s` (exit 1), because the restored method made `hasattr`
  true. The temporary method was removed immediately with no production diff.
  The runner equivalence regression is behavior-preserving and cannot become
  red from these dead, uncalled host members; deliberately breaking the
  canonical runner to manufacture a RED case would violate task scope.
- GREEN: `uv run pytest -q
  tests/runtime/test_subagents.py::test_child_host_runner_normalizes_dict_and_sdk_responses_equivalently
  tests/runtime/test_subagents.py::test_subagent_runtime_host_has_no_legacy_response_adapters`
  → `8 passed in 0.14s` (exit 0) before the temporary RED proof; final task
  gate `uv run pytest -q tests/runtime/test_host.py tests/runtime/test_runner.py
  tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py
  tests/scenarios/test_lean_runtime_characterization.py` → `75 passed in
  0.32s` (exit 0); `uv run ruff check runtime/subagents.py
  tests/runtime/test_subagents.py` → `All checks passed!` (exit 0); `uv run
  pytest -q` → `579 passed, 1 deselected, 6 subtests passed in 3.60s` (exit
  0); and `git diff --check` exited 0.

## R3-04 — complete under approved one-release budget exception; no product changes made

- Commit: `docs(R3-04): record approved budget exception`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Metric-integrity inspection: `git diff feature/skill-evolution...HEAD --
  scripts/check_release_metrics.py` shows the committed script was introduced
  on this branch; its reviewed constants remain
  `STABLE_SOURCE_ROOTS = ("app", "core", "runtime", "tools", "extensions")`,
  `MAX_STABLE_PRODUCTION_LINES = 14_000`, and `MAX_STABLE_TOOLS = 7`.
  No task-local change was made to the script, its roots, exclusions, or caps.
- Release metric: fresh `uv run python scripts/check_release_metrics.py` →
  exit 1: `stable_production_python_lines=14095`,
  `stable_tool_count=7`, and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`; stderr:
  `stable production Python exceeds 14000: 14095`. The exact remaining excess
  is therefore **95 lines**. This is the sole failed R3 gate.
- Approved exception: after the metric evidence was recorded, the user
  explicitly approved `14,095` stable production lines as a **one-release
  exception only**. [C-006](DECISIONS.md#c-006-user-approved-one-release-stable-loc-budget-exception)
  preserves the raw exit-1 fact: this is approved release acceptance, not a
  metric pass. The metric script remains unchanged; its exact seven-tool
  output remains required, and required dependencies remain four (≤5).
- Required line deltas: R1 strict cleanup reduced the stable metric from
  `14,245` after R1-01 to `14,232` after R1-03 (`-13`: R1-02 `-7`, R1-03
  `-6`). R3 changed `core/llm.py` from `679` lines before R3-01 to `617`
  after R3-01 and `604` after R3-02 (`-75`); it is still `604` at HEAD.
  R3-03 changed `runtime/subagents.py` from `797` to `735` (`-62`). Across
  those two approved R3 surfaces the Git diff is `218 insertions, 355
  deletions` (`-137` net), and stable production changed from `14,232` before
  R3 to `14,095` at HEAD (`-137`).
- Retained-subsystem review: `core/llm.py` is still the canonical owner of
  dict/SDK response extraction, immutable provider profiles and declared
  credential/default resolution, provider compatibility, request construction,
  retry/error wrapping, and the retained `think`/`invoke`/`invoke_raw`/
  `stream_invoke` public paths. `runtime/subagents.py` still supplies the
  opt-in verifier contract: typed request/result persistence, child-runtime
  composition, tool-registry construction, parent/child trace projection,
  completion evaluation, structured-result parsing, and child metrics. These
  are required by the R3/R1 acceptance contracts; deleting them to recover the
  95 lines would violate `01_GOAL.md`.
- Candidate-scope review: no further behavior-preserving duplicate was
  established. Fresh `uv run ruff check core/llm.py runtime/subagents.py
  --select E722,F401,F541,F821,F841` → `All checks passed!`; the R3 diffs
  already leave one non-stream retry loop, one request builder, and canonical
  response extraction. The only permissible future investigation area is a
  newly demonstrated duplicate or strict-lint-exposed dead code confined to
  `core/llm.py` or `runtime/subagents.py`; none is authorized by this task and
  none may remove a retained capability or alter the metric. Goal-runner review
  against `01_GOAL.md` is required before any such new task is created.
- R3 milestone verification after the failed metric: `uv run ruff check .` →
  `All checks passed!`; `uv run ruff check . --select
  E722,F401,F541,F821,F841` → `All checks passed!`; `uv run ruff check app core
  runtime tools extensions prompts utils --select E402` → `All checks passed!`;
  `uv run pytest -q` → `579 passed, 1 deselected, 6 subtests passed in 3.62s`;
  `uv run pytest -q tests/scenarios` → `23 passed in 0.51s`; `uv run pytest -q
  tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py
  tests/test_mcp_protocol.py` → `20 passed, 6 subtests passed in 0.64s`;
  `uv lock --check` → `Resolved 46 packages in 25ms`; and `git diff --check`
  exited 0 before this evidence-only update.
- Remaining: R3-04 is complete only under C-006's narrow release exception.
  Do not start R4 from this task. No production capability, metric definition,
  tool count, dependency, or original-worktree file was changed by R3-04.

## R4-01 — complete

- Commit: `docs(R4-01): reconcile lean runtime plans`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; locate it with `git log --oneline
  -- docs/plans/2026-07-14-lean-runtime-closeout/`.
- Changed: added completed M6-01/M6-02 and the R0–R5 closeout chain to the
  original milestones/task graph; reconciled original acceptance wording with
  normal and strict Ruff coverage; marked the original final report as
  historical evidence and linked it to the pending closeout final report.
  README and HARNESS now state the actual default/opt-in boundaries, retained
  `session_summary` fields, and removed renderer/evaluator surfaces. C-007
  records why the historical M5 failure remains historical rather than being
  rewritten. All current references state that C-006 is an approved one-release
  acceptance exception for the raw 14,095-line exit-1 result, never a metric
  pass or a threshold change.
- Characterization: before the documentation edit, `uv run pytest -q
  tests/test_tool_surface_docs.py tests/test_maintenance_boundaries.py
  tests/test_cli_one_shot.py tests/test_lean_defaults.py` → `33 passed in
  0.52s` (exit 0); `uv run mycodeagent --help` exited 0 and listed
  `--enable-mcp` and `--enable-verification-agent` as explicit options.
- GREEN: after the edit, the same documentation/maintenance/CLI/default command
  → `33 passed in 0.56s` (exit 0); `uv run pytest -q tests/test_app_bootstrap.py
  -k verification` → `1 passed, 8 deselected in 0.07s` (exit 0); and `uv run
  pytest -q tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary`
  → `1 passed in 0.02s` (exit 0). `uv run mycodeagent --help` exited 0 and
  showed the expected opt-in flags.
- Regression: `uv run ruff check .` → `All checks passed!`; `uv run ruff check
  . --select E722,F401,F541,F821,F841` → `All checks passed!`; `uv run ruff
  check app core runtime tools extensions prompts utils --select E402` → `All
  checks passed!`; `uv run pytest -q` → `579 passed, 1 deselected, 6 subtests
  passed in 3.44s`; `git diff --check` exited 0. The required
  `verification|summary|JSONL|runtime.evals|HTML|14,000|Ruff|F821|M6` scan
  confirms the active docs distinguish retained JSONL summary metrics from the
  removed HTML/evaluator surfaces and name the strict-lint policy.
- Metrics: fresh `uv run python scripts/check_release_metrics.py` → exit 1:
  `stable_production_python_lines=14095`, `stable_tool_count=7`, and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`; stderr reports
  the unchanged 14,000-line cap. C-006 is the sole one-release acceptance
  exception; no metric definition, product source, tool count, dependency, or
  original-worktree path changed in this task.
- Remaining: goal-runner review, then R4-02 final release verification and
  R5-01 safe integration handoff. `FINAL_REPORT.md` remains not approved until
  R4-02 has fresh evidence.

## R4-02 — complete

- Commit: `docs(R4-02): record final release verification`. Per original-plan
  [D-001](../../2026-07-12-lean-runtime/DECISIONS.md), this task record does
  not self-reference its content-derived SHA; use `git log --oneline --
  docs/plans/2026-07-14-lean-runtime-closeout/` to locate it.
- Changed: replaced the closeout final-report template with the 2026-07-14 CST
  acceptance matrix and this progress entry only; no product or metric file
  changed.
- Fresh gates: `uv sync --locked --extra dev --extra mcp` resolved 46 and
  audited 41 packages; full tests → `579 passed, 1 deselected, 6 subtests
  passed in 3.74s`; scenarios → `23 passed in 0.32s`; MCP → `20 passed, 6
  subtests passed in 0.48s`; verifier bootstrap → `1 passed, 8 deselected in
  0.13s`; default lean startup → `1 passed in 0.08s`; focused subagent
  behavior → `26 passed in 0.10s`.
- Static/trace/architecture: normal Ruff, strict
  `E722,F401,F541,F821,F841`, and stable-package E402 each returned `All
  checks passed!`; global ignores and critical global ignores are both empty.
  Trace contracts → `2 passed in 0.07s`; the renderer/evaluator scan found no
  matches. Provider/request/response architecture coverage → `63 passed in
  0.73s`; scans found one canonical request/retry owner and no subagent legacy
  adapters. Required dependencies remain four.
- Docs reconciliation: active docs/default/CLI coverage → `33 passed in
  0.50s`; a separate key-term scan across README, HARNESS, original-plan, and
  closeout docs confirmed the documented opt-ins, retained JSONL summary, and
  removed renderer/evaluator surfaces. Closeout `01_GOAL.md` and
  `05_ACCEPTANCE_CRITERIA.md` deliberately retain their original ≤14,000
  exit-0 requirement; C-006 records the narrow one-release override of the
  raw exit-1 result rather than rewriting that requirement or claiming a pass.
- Release/safety: `uv lock --check` → `Resolved 46 packages in 4ms`; fresh
  Python 3.12 editable install from an unrelated Git repository ran
  `mycodeagent --help` with exit 0 in `0.961s`; Teams/Skill Evolution scan had
  no matches; docs/default consistency suite → `33 passed in 0.45s`. Original
  status and numstat match R0 exactly and the portable binary-diff SHA-256 is
  still `655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`.
- Q-06: the unchanged metric intentionally remains raw exit 1:
  `stable_production_python_lines=14095`, seven exact tools, and the unchanged
  14,000 cap. C-006 is the explicit user-approved one-release exception; it
  does not recast this command as passing. All other release gates pass.
- Delivery: `FINAL_REPORT.md` status is `RELEASE-READY BRANCH — NOT YET
  INTEGRATED`. D-02 remains deliberately pending R5-01, which alone may create
  the non-mutating integration handoff. The implementation tree was clean
  before this evidence-only edit.
- Remaining: goal-runner review, then R5-01 only. Do not merge, rebase, push,
  reset, stash, or modify the original worktree.
