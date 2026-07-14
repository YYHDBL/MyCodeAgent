# Lean Runtime Progress

## M0-01 — complete

- Commit: recorded by `git log --oneline -- docs/plans/2026-07-12-lean-runtime/`
- Changed: `BASELINE.md`, `PROGRESS.md`, `DECISIONS.md`
- Behavior: none; this task intentionally changes no runtime behavior.
- Verification: `pytest --collect-only -q` collected 861 tests; `pytest -q` passed 861 tests and 6 subtests; `main.py --help` exited 0 in 0.52s.
- Metrics: stable production 19,320 LOC; tests 17,904 LOC; Teams 4,208 LOC; Skill Evolution 2,070 LOC; docs 10,393 LOC; 12 stable tools; 7 core dependencies.
- Follow-ups: M0-02

## M0-02 — complete

- Commit: `d996b98ebf9658478e0ab37505c183fbf2a96dba` (completed implementation commit; supersedes historical `84c424242df0485ba889fa2c6f7c223ce17026b2` and `8709417917cb69dae936d6190d507185bc1dd853`)
- Changed: `docs/plans/2026-07-12-lean-runtime/PROGRESS.md`, `tests/scenarios/phase0_baselines.py`, `tests/scenarios/test_lean_runtime_characterization.py`
- Behavior: deterministic fake-model scenarios now characterize final completion, authorized and denied tool observations, non-destructive checkpoints, oversized-output artifacts, transcript facts, transcript-aware resume/continue side-effect safety, and missing/stale completion evidence through the canonical loop terminal.
- Verification: `.venv/bin/python -m pytest tests/scenarios -q` → `20 passed` twice consecutively; `.venv/bin/python -m pytest -q` → `870 passed, 6 subtests passed in 7.24s`.
- Metrics: scenario tests `11 → 20`; full tests `861 → 870`; baseline behavior failures `none`.
- Follow-ups: M1-01. Lint remains unavailable in the baseline environment: `.venv/bin/python -m ruff check ...` → `No module named ruff`; `uv run ruff check ...` → `Failed to spawn: ruff`.
- Review follow-up: task-only scenario refinements are discoverable with `git log --oneline -- tests/scenarios/ docs/plans/2026-07-12-lean-runtime/` under D-001's non-self-referential record rule.

## M0 milestone gate — complete

- Commit: recorded by `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001.
- Verification: `.venv/bin/python -m pytest tests/scenarios -q` → `20 passed`; `.venv/bin/python -m pytest -q` → `870 passed, 6 subtests passed in 7.16s`; `main.py --help` exited 0 in 0.48s.
- Metrics: deterministic scenario coverage `11 → 20`; full suite `861 → 870` tests; baseline stable production remains 19,320 LOC.
- Follow-ups: M1-01.

## M1 milestone gate — complete

- Commit: recorded by `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001.
- Verification: `uv run pytest -q` → `909 passed, 6 subtests passed in 8.25s`; `uv run ruff check .` → `All checks passed`; `uv run mycodeagent --help` exited 0.
- Metrics: full suite `870 → 909`; scenarios `20 → 22`; one-shot contracts `0 → 9`; lifecycle contracts `0 → 15`.
- Follow-ups: M2-01.

## M2 milestone gate — complete

- Commit: recorded by `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001.
- Verification: `uv run pytest -q` → `749 passed, 6 subtests passed in 4.09s`; `uv run ruff check .` → `All checks passed`; `uv lock --check` passed; `rg 'experimental\\.teams|skill_evolution|Team[A-Z]' app core runtime tools extensions prompts` returned no matches.
- Metrics: direct core dependencies `7 → 4`; Teams production Python `−4,679`; Skill Evolution production Python `−2,070`; full suite `909 → 749` after intentional research-test removal.
- Follow-ups: M3-01.

## M3-01 — complete

- Commit: `refactor(M3-01): unify runtime event sinks` (recorded under D-001).
- Changed: `runtime/events.py`, `runtime/loop.py`, `runtime/factory.py`, `runtime/host.py`, `tools/orchestrator.py`, trace protocol, focused event/runner/transcript/trace tests, and D-012.
- Behavior: the factory composes ordered trace and transcript adapters behind one synchronous runtime event sink. The runner emits run, message, transition, checkpoint, terminal, model, and completion facts through that sink; tool lifecycle and cancellation terminal facts use it too. Sink failures are logged and isolated. Existing diagnostic trace names and their frozen transition payload retain their projections, while transcript recovery retains its durable facts.
- Verification: RED `uv run pytest tests/runtime/test_events.py -q` → `5 failed` (missing `runtime.events`); wiring RED → `2 failed` (runner and tool lifecycle emitted no sink facts); cancellation RED → `1 failed`; trace-protocol RED → `1 failed`. Focused GREEN `uv run pytest tests/extensions/test_trace_protocol.py tests/runtime/test_events.py tests/runtime/test_runner.py tests/runtime/test_transcript.py tests/runtime/test_evals.py tests/extensions/test_tracing_extension.py tests/test_trace_logger.py tests/scenarios -q` → `110 passed`; `uv run pytest -q` → `757 passed, 6 subtests passed in 3.93s`; `uv run ruff check .` → `All checks passed`; `git diff --check` passed.
- Metrics: `runtime/loop.py` `1,135 → 1,063` lines; deterministic suite `749 → 757` tests; direct loop trace/transcript recorder call sites `>0 → 0`.
- Follow-ups: M3-02.

## M3-02 — complete

- Commit: `refactor(M3-02): simplify runtime composition` (recorded under D-001).
- Changed: direct runtime builders, host lifecycle wiring, shared LLM response normalization, the runtime event projection boundary, and runner/host/transcript/maintenance boundary tests.
- Behavior: `CodeAgent` directly composes context, persistence, runner, tools, and deferred subagents; the one-product `RuntimeComponentFactory` is gone. The runner remains the sole turn state machine, while `core.llm` owns provider-compatible response parsing and `runtime.events` owns event serialization. Recovery limits, transition reasons, terminal reasons, tool observation ordering, completion-gate feedback, and transcript cancellation remain observable.
- Verification: RED direct-builder boundary → `1 failed` because `build_runtime_context` did not exist; GREEN direct-builder/lean-startup/host set → `9 passed`. Focused runner/orchestrator/transcript regression → `78 passed`; Ruff on changed runtime modules passed. Required ponytail-review found and removed one unused `TerminalReason` import; no remaining applicable deletion finding. Full-suite verification is the next M3 integration gate.
- Metrics: `runtime/host.py` `691 → 482` lines; `runtime/factory.py` `166 → 135` lines; `runtime/loop.py` `1,080 → 1,018` lines; duplicate host response parsing `~145 → 0` lines; `RuntimeComponentFactory` `1 → 0`. D-013 records the measured loop-size exception without adding a second runtime loop.
- Follow-ups: M3-03 and M3 milestone gate.

## M3-03 — complete

- Commit: `refactor(M3-03): use transcript as session truth` (recorded under D-001).
- Changed: `runtime/transcript.py`, `runtime/session.py`, `runtime/session_memory.py` coverage, `runtime/host.py`, `app/cli.py`, transcript/session/context/CLI-root tests, and D-014.
- Behavior: append-only transcript facts are the only durable recovery source for new sessions. `/save` and automatic lifecycle persistence report the existing transcript rather than creating `session-latest.json`; `/load`, `--resume`, and interactive resume restore transcript facts. A valid former snapshot can be imported exactly once into an empty transcript and never overwrites existing facts. Resume rebuilds compact checkpoints and derived session memory deterministically; completed tools remain observations and started-but-unfinished actions remain uncertain.
- Verification: RED `uv run pytest -q tests/runtime/test_session.py tests/test_cli_project_root.py::test_default_session_path_uses_selected_project_root_transcript_directory tests/runtime/test_context.py::test_load_transcript_resets_previous_context_runtime` → `2 failed, 1 passed` before implementation (missing legacy import and stale snapshot path). GREEN focused persistence/context/transcript/CLI-root/session-memory suite → `45 passed`; runtime, CLI-root, and scenario suite → `206 passed`; `uv run pytest -q` → `759 passed, 6 subtests passed in 3.99s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: session snapshot write APIs `3 → 0`; new-session durable recovery stores `snapshot + transcript → transcript only`; full suite `757 → 759`; `runtime/session.py` `76 → 31` lines.
- Follow-ups: M3 milestone gate.

### M3-03 review repair

- Commit: recorded under D-001.
- Changed: transcript checkpoint recovery, session-memory lifecycle keys, and compact-model-view/cross-run uncertainty regressions.
- Behavior: the one-way legacy-import checkpoint contributes only its runtime-state fact and cannot activate compact projection or inject a phantom summary. Session-memory lifecycle state is keyed by the `(run_id, tool_call_id)` identity in rebuild and incremental paths, so a completed later-run call with a reused ID cannot erase a prior started-only uncertain action.
- Verification: RED `uv run pytest -q tests/runtime/test_context.py::test_legacy_snapshot_import_does_not_create_a_compact_model_summary tests/runtime/test_session_memory.py::test_session_memory_keeps_cross_run_duplicate_started_action_uncertain` → `2 failed` (legacy checkpoint activated compact projection; duplicate ID erased derived uncertainty). GREEN focused recovery/runner/completion/CLI/scenario suite → `113 passed`; `uv run pytest -q` → `762 passed, 6 subtests passed in 3.99s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: full suite `759 → 762`; legacy imported compact projections `1 → 0`; cross-run duplicate-ID uncertainty regressions `0 → 2` (rebuild and incremental derivation).

### M3-03 quality repair

- Commit: recorded under D-001.
- Changed: `runtime/host.py`, `runtime/factory.py`, and partial-host context coverage.
- Behavior: system messages always derive from the canonical context builder. The former `_system_messages_override` snapshot-restoration field is absent from host composition and no partial host needs it.
- Verification: RED `uv run pytest -q tests/runtime/test_context.py::test_system_messages_are_always_derived_from_context_builder tests/runtime/test_context.py::test_load_transcript_resets_previous_context_runtime` → `1 failed, 1 passed` (partial host raised `AttributeError` for the removed-state contract). GREEN focused M3 recovery/runner/completion/CLI/scenario suite → `104 passed`; `uv run pytest -q` → `763 passed, 6 subtests passed in 4.15s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: snapshot-only host fields `1 → 0`; full suite `762 → 763`.

### M3-02 review repair

- Commit: recorded under D-001.
- Changed: `core.llm.serialize_response`, direct runner-to-orchestrator invocation, and behavior-boundary regressions.
- Behavior: every `model_output.raw_response` is JSON-compatible before trace projection; object-shaped provider responses, including a provider whose `model_dump()` raises, retain a deterministic raw fallback rather than silently dropping the trace event or crashing the turn. `ToolOrchestrator.run` is now the required runtime contract with no serial fallback; host composition tests assert constructed dependencies instead of source strings.
- Verification: RED object-shaped response through a real JSONL `TraceLogger` → missing `model_output` and `Object of type _Response is not JSON serializable`; follow-up RED with raising `model_dump()` → turn raised `RuntimeError`; focused GREEN trace set → `14 passed`; final full-suite verification follows before the repair commit.
- Metrics: source-string host composition checks `2 → 0`; direct runner tool-execution paths `run + fallback → run`.

## M1-01 — complete

- Commit: `a3ccae7d4fd5d43d0c705b52218f60b740457122`
- Changed: `app/bootstrap.py`, `app/cli.py`, `tests/test_app_bootstrap.py`, `tests/test_cli_project_root.py`
- Behavior: the invocation directory is the selected project by default; `--cwd` accepts an absolute or invocation-relative existing directory; invalid roots exit 2 before config, model, registry, or agent initialization. Sessions, chat history, code-law checks, runtime tools, transcripts, memory, and output artifacts receive that selected root rather than the source checkout.
- Verification: initial RED: `.venv/bin/python -m pytest tests/test_app_bootstrap.py tests/test_cli_project_root.py -q` → `6 failed, 4 passed` before implementation. Repair RED: `.venv/bin/python -m pytest tests/test_cli_project_root.py::test_explicit_project_root_keeps_trace_and_transcript_artifacts_under_target -q` → failed because the trace path was `memory/traces/...` under the invocation directory. Scenario RED: with the prior zero-argument trace-factory call temporarily reinstated, `.venv/bin/python -m pytest tests/scenarios/test_project_root_cli.py -q` → `1 failed, 1 passed`; the explicit-`--cwd` Git-repository case had an artifact outside its target. Quality RED: unrelated-target bootstrap had empty built-in L1/tool-contract messages, while external `TRACE_DIR`/`TOOL_OUTPUT_DIR` caused an external write and `relative_to()` crash (`4 failed`). GREEN: trace/transcript target-root test plus host regression → `8 passed`; the new Git-repository scenario → `2 passed` twice; M1 focused regression set → `244 passed`; `.venv/bin/python -m pytest tests/scenarios -q` → `22 passed` twice; `.venv/bin/python -m pytest -q` → `883 passed, 6 subtests passed`; `main.py --cwd /definitely/not/a/project` → concise error and exit `2`; `git diff --check` and `.venv/bin/python -m compileall -q app/bootstrap.py runtime/host.py runtime/factory.py runtime/prompt_builder.py extensions/tracing/logger.py tools/observation_store.py` passed. Lint remains unavailable in this baseline environment: `.venv/bin/python -m ruff check ...` → `No module named ruff`.
- Metrics: deterministic full-suite count `870 → 883`; scenario count `20 → 22`; focused root/confinement coverage adds default, absolute/relative override, invalid-root-before-dependency, target session-path, CLI exit-code, target trace/transcript artifact, unrelated Git-repository artifact, package-resource prompt, and external artifact-override contracts.
- Repair: `f2bcc04f374166600f6202a54ab39278ff50a904` injects the selected root into trace creation; `34377ef1e2676dae7ec5677a82b7df20e61e6e2b` adds the unrelated Git-repository scenario; `70128ad0d7bdc4644f58a429c341a9b5468f754a` separates package resources and confines artifact overrides; D-002 and D-003 record the boundary decisions.
- Follow-ups: M1-02. The subsequent record-only commit follows D-001; locate it with `git log --oneline -- docs/plans/2026-07-12-lean-runtime/`.

## M1-02 — complete

- Commit: `0644b7a150113e9159a7d1e514cdecdd6db0237b`
- Changed: `app/cli.py`, `tests/test_cli_one_shot.py`
- Behavior: `-p`/`--print` executes exactly one prompt through the canonical `build_runtime()` then `agent.run()` path and emits only the final text on stdout. `--json` emits exactly one JSON object containing status, response, session ID, terminal reason, and available usage/completion-verification metadata; runtime, interruption, and invalid-configuration exits map to 1, 130, and 2 respectively.
- Verification: RED `.venv/bin/python -m pytest tests/test_cli_one_shot.py -q` → `6 failed` before implementation (missing flags/entrypoint); metadata-lifetime RED → `1 failed` before outcome capture moved before `agent.close()`. GREEN `.venv/bin/python -m pytest tests/test_cli_one_shot.py tests/test_app_bootstrap.py tests/test_cli_project_root.py tests/test_ui_components.py tests/scenarios -q` → `80 passed`; `.venv/bin/python -m pytest -q` → `892 passed, 6 subtests passed`; `git diff --check`, `.venv/bin/python -m compileall -q app/cli.py`, and `.venv/bin/python main.py --help` passed. The suite includes an injected `main.py -p task --json` subprocess smoke test whose stdout parses as the single expected JSON object. Lint remains unavailable in the baseline environment: `.venv/bin/python -m ruff check app/cli.py tests/test_cli_one_shot.py` → `No module named ruff`.
- Metrics: deterministic full suite `883 → 892`; M1 one-shot contract tests `0 → 9`; scenario tests remain `22`.
- Follow-ups: M1-03.

## M1-03 — complete

- Commit: `6620f4c65c4d7dee04bd854105a3c464949fa381` (`build(M1-03): package mycodeagent console command`)
- Changed: PEP 621 `pyproject.toml`, generated `uv.lock`, generated compatibility `requirements.txt` and `requirements-dev.txt`, README Quick Start, packaging smoke coverage, and the legacy requirements-boundary assertion.
- Behavior: `mycodeagent = app.cli:main` is an installable console script; `pyproject.toml` is the sole dependency authority, while requirements files are generated `uv export` compatibility artifacts. The current M1 package discovery includes all current CLI import roots and prompts; MCP remains core until M2-02 moves it to an optional extra.
- Verification: initial RED `.venv/bin/python -m pytest tests/test_packaging_smoke.py -q` → `2 failed` because `pyproject.toml` was absent; package-import RED `uv run pytest tests/test_packaging_smoke.py -q` → `1 failed, 1 passed` because `experimental*` was absent from the explicit package discovery. GREEN `uv run pytest tests/test_packaging_smoke.py -q` → `2 passed`; `uv sync --extra dev`, `uv run mycodeagent --help`, and an isolated `uv venv` + `uv pip install --python <venv>/bin/python -e .` + `<venv>/bin/mycodeagent --help` all exited 0. Final `uv run pytest -q` → `894 passed, 6 subtests passed in 8.35s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: deterministic full suite `892 → 894`; one dependency source `requirements*.txt → pyproject.toml`; lockfile `absent → uv.lock`; development tooling now includes pytest and Ruff via the `dev` extra. Current compatibility milestone retains seven core dependencies, with MCP/AnyIO scheduled for M2-02.
- Follow-ups: M1-04. Ruff begins as a reproducible legacy-safe gate; M5 tightens its rule policy after the planned runtime and research-system removals.
- Repair: `76141ccf1cd1e7c692dd7eb6fc0ff1cd93b35d8a` replaces direct `tomllib` test imports with the standard Python 3.10 `tomli` fallback and declares `tomli>=2.0.0; python_version < '3.11'` in the authoritative `dev` extra. RED: an isolated Python 3.10 editable install collected both tests with `ModuleNotFoundError: tomllib`; the new metadata assertion failed before the dependency was added. GREEN: `uv sync --locked --extra dev` passed; isolated Python 3.10 packaging/maintenance tests → `11 passed in 1.23s`; final normal suite → `894 passed, 6 subtests passed in 8.40s`; Ruff and diff check passed.

## M1-04 — complete

- Commit: `5d2e4a74631e22552f9eb105eb70a678ab493dea`
- Changed: `app/cli.py`, `runtime/host.py`, `runtime/transcript.py`, `tests/test_cli_lifecycle.py`, `tests/runtime/test_transcript.py`
- Behavior: `--resume [id]`, `/status`, `/sessions`, and `/resume [id]` use transcript-backed lifecycle methods. Status reports the selected project, model/provider, session ID, permission mode, enabled extensions, and context usage. Ctrl-C during a turn records an `interrupted` transcript terminal and returns to the prompt; a tool that started but did not complete remains an uncertain action on resume.
- Verification: RED `uv run pytest tests/test_cli_lifecycle.py tests/runtime/test_transcript.py -q` → `6 failed, 14 passed` before implementation (missing parser/control/session APIs). GREEN focused lifecycle/transcript tests → `21 passed`; M1 lifecycle regression set (CLI one-shot/root/bootstrap, session, and scenarios) → `67 passed`; `uv run pytest -q` → `901 passed, 6 subtests passed in 8.12s`; `uv run ruff check .` and `git diff --check` passed; `uv run mycodeagent --help` exited 0 and listed `--resume [RESUME]`.
- Metrics: full suite `894 → 901`; lifecycle contract coverage `0 → 7`; transcript recovery continues to use the append-only JSONL fact stream rather than session snapshots.
- Follow-ups: M1 milestone gate.

### M1-04 P1 repair

- Commit: `2e36bdfec4022c685290c5747a36b972cac72e91`
- Changed: `runtime/transcript.py`, `runtime/host.py`, `tests/runtime/test_transcript.py`
- Behavior: interactive resume now rebuilds every append-ordered run in a transcript session while explicit `load_transcript(..., run_id=...)` retains its one-run inspection semantics. A started-but-unfinished tool call now receives a synthetic `INTERRUPTED_UNCERTAIN` tool observation during recovery, so the restored assistant tool-call message has a valid paired response and the side effect remains uncertain rather than replayed.
- Verification: RED `uv run pytest tests/runtime/test_transcript.py -q` → `2 failed, 17 passed` (missing session loader); focused transcript/context/CLI/scenario regression → `77 passed`; `uv run pytest -q` → `903 passed, 6 subtests passed in 7.83s`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: full suite `901 → 903`; transcript recovery coverage adds all-runs ordering, explicit-run compatibility, and interrupted tool-call pairing.
- Follow-ups: M1 milestone gate.

### M1-04 P1 mixed-tool repair

- Commit: `0cc2ad26eb37b4e2228e62b8b76e422049fff24f`
- Changed: `runtime/transcript.py`, `tests/runtime/test_transcript.py`
- Behavior: recovery now pairs every assistant tool call even when interruption occurs after one tool lifecycle completes but before the runtime records its normal tool messages. Completed lifecycle results are restored as observations, failed/pending/unknown lifecycle states get synthetic error observations, and only a started-without-completion call is marked `INTERRUPTED_UNCERTAIN`.
- Verification: RED `uv run pytest tests/runtime/test_transcript.py -q` → `1 failed, 19 passed` (the completed call lacked its paired observation); focused transcript/context/CLI/scenario regression → `78 passed`; `uv run pytest -q` → `904 passed, 6 subtests passed in 7.99s`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: full suite `903 → 904`; mixed completed-plus-interrupted multi-tool transcript pairing is covered.
- Follow-ups: M1 milestone gate.

### M1-04 P1 recovery ordering repair

- Commit: `7a3f4f9dc476e60a7ed974bb60f708a5413e7b35`
- Changed: `runtime/transcript.py`, `runtime/host.py`, `tests/runtime/test_transcript.py`
- Behavior: recovered tool observations retain persisted transcript order before synthetic observations. Lifecycle facts are scoped by transcript run plus tool-call ID, so a duplicate ID in a later run cannot inherit an earlier completed result. Repeated cancellation writes at most one interrupted terminal and returns a non-cancelled result afterward.
- Verification: RED `uv run pytest tests/runtime/test_transcript.py -q` → `3 failed, 20 passed` (ordering, duplicate-ID scoping, and duplicate terminal failures); focused transcript/context/CLI/scenario regression → `81 passed`; `uv run pytest -q` → `907 passed, 6 subtests passed in 8.07s`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: full suite `904 → 907`; recovery coverage adds persisted/synthetic ordering, duplicate-ID run isolation, and cancellation idempotence.
- Follow-ups: M1 milestone gate.

### M1-04 P1 stale-cancel repair

- Commit: `177e4c21dd6b0267bef8f56f391bb762a10883b1`
- Changed: `runtime/host.py`, `tests/runtime/test_transcript.py`
- Behavior: after cancelling an active turn, a repeat cancellation returns non-cancelled without falling back to and terminalizing an older incomplete transcript run.
- Verification: RED `uv run pytest tests/runtime/test_transcript.py -q` → `1 failed, 23 passed` (second cancellation terminalized `run-old`); GREEN transcript tests → `24 passed`; `uv run pytest -q` → `908 passed, 6 subtests passed in 8.36s`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: full suite `907 → 908`; cancellation fallback isolation has a deterministic regression.
- Follow-ups: M1 milestone gate.

### M1-04 P1 per-turn cancellation reset

- Commit: `e462e3ab027fc1a1fe70855a3195bc0f87d3b1ca`
- Changed: `runtime/loop.py`, `tests/runtime/test_runner.py`
- Behavior: `RuntimeRunner` resets the host cancellation marker at the start of every new turn, so a prior post-loop cancellation guard cannot suppress a later interrupted turn.
- Verification: RED `uv run pytest tests/runtime/test_runner.py::test_runtime_runner_resets_cancel_marker_for_each_new_turn -q` → `1 failed`; focused runner/transcript tests → `25 passed`; `uv run pytest -q` → `909 passed, 6 subtests passed in 8.65s`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: full suite `908 → 909`; sequential-turn cancellation reset has a deterministic runner contract.
- Follow-ups: M1 milestone gate.

## M2-01 — complete

- Commit: `refactor(M2-01): make minimal runtime the default` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: `core/config.py`, `app/cli.py`, `app/bootstrap.py`, `runtime/host.py`, `tools/builtin/skill.py`, `extensions/tracing/logger.py`, `.env.example`, lean-default and legacy-alias tests, and decision/progress records.
- Behavior: Config is the canonical source for optional-capability defaults and environment values. Default startup keeps MCP, verification subagents, Teams, Skill Evolution, and long-term memory off; deterministic completion remains the runtime fallback. MCP, verification, long-term memory, Teams, and Skill Evolution use explicit positive CLI opt-ins. Skills retain lazy local discovery without a default per-call refresh. Lightweight traces remain JSONL-only by default; HTML traces require `TRACE_HTML_ENABLED=true`.
- Verification: RED `uv run pytest -q tests/test_lean_defaults.py` → `4 failed` before Config/CLI/host changes; follow-up RED → `4 failed` before Config HTML, SkillTool refresh injection, and JSONL-only trace behavior. Focused GREEN `uv run pytest -q tests/test_lean_defaults.py tests/test_trace_logger.py tests/extensions/test_skills_extension.py tests/extensions/test_tracing_extension.py tests/runtime/test_host.py tests/test_app_bootstrap.py tests/extensions/test_mcp_extension.py tests/experimental/test_agent_teams_config.py` → `52 passed`; final `uv run pytest -q` → `915 passed, 6 subtests passed in 8.04s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: full suite `909 → 915`; lean-default contracts `0 → 6`; default trace outputs `JSONL + HTML → JSONL only`.
- Follow-ups: M2-02, M2-03, M2-04. D-007 and D-008 document the two minimal scope extensions required to make Config ownership and lightweight tracing real.

### M2-01 P1 lean-startup repair

- Commit: `refactor(M2-01): defer optional startup services` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: `runtime/factory.py`, `runtime/host.py`, `tests/test_lean_defaults.py`, `README.md`, and decision/progress records.
- Behavior: a default `CodeAgent` does not construct `SubagentLauncher`; the Task tool holds a deferred launcher protocol and creates the launcher only for a valid Task delegation. A selected project with no `skills/**/SKILL.md` does not import `extensions.skills`, construct or scan a loader, or register `SkillTool`. Projects containing a local skill retain the existing loader, prompt, and Skill-tool path. README now states these defaults and does not advertise Skill Evolution as a stable capability; MCP remains a current core dependency, disabled by default at runtime pending M2-02.
- Verification: RED `uv run pytest tests/test_lean_defaults.py::test_default_host_defers_subagent_launcher_until_task_is_used tests/test_lean_defaults.py::test_default_no_skill_project_avoids_skills_extension_and_skill_tool -q` → `2 failed` (eager launcher construction and skills import). GREEN lean-default suite → `10 passed`, including first-valid-Task launcher construction and discovered-skill registration; focused runtime/task/skills suite → `34 passed`; final `uv run pytest -q` → `919 passed, 6 subtests passed in 9.23s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed; `uv run mycodeagent --help` exited 0.
- Metrics: full suite `915 → 919`; lean-default contracts `6 → 10`; default no-skill startup now has zero skills-extension imports, loaders, scans, and Skill-tool registrations; default launcher instances `1 → 0`.
- Follow-ups: M2-02, M2-03, M2-04.

## M2-03 — complete

- Commit: `551a9ca22cfc4b1e1b4007200c26da3a711cfc57` (Teams-runtime removal); repair `7911225` (experimental packaging/archive boundary repair), recorded under D-001.
- Changed: Teams implementation, tools, prompts, integration tests, stable-boundary tests, package discovery, `experimental/__init__.py`, archive documentation, README, AGENT, and code-law documentation.
- Behavior: Agent Teams has no stable runtime imports, flags, commands, prompts, tools, tests, namespace package, or shipped wheel content. The final pre-removal state remains reproducibly inspectable from the M2-03 parent commit; formal Explore/Verification subagents remain covered by the standard subagent scenario tests.
- Verification: RED `uv run pytest -q tests/test_packaging_smoke.py tests/test_maintenance_boundaries.py` → `2 failed` before removing `experimental*` and correcting the archive parent. GREEN focused `uv run pytest -q tests/test_packaging_smoke.py tests/test_maintenance_boundaries.py tests/test_lean_defaults.py tests/runtime/test_subagents.py tests/test_protocol_compliance.py tests/scenarios` → `93 passed`; `uv build --wheel --out-dir <temp>` followed by `unzip -l` found no `experimental/` entries; `uv run pytest -q` → `816 passed, 6 subtests passed in 3.99s`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: package discovery entries `8 → 7`; shipped experimental namespace marker `1 → 0`; focused test count `93`; full suite `816` tests plus `6` subtests.
- Follow-ups: M2-04 and the M2 milestone gate.

## M2-02 — complete (integrated completion record)

- Commit: `f497b172c9bce8279d9a26eb69273e25db7392cf` (`refactor(M2-02): make MCP an opt-in extra`), recorded under D-001.
- Changed: MCP lazy adapter boundary, standard-library OpenAI-compatible core transport, `pyproject.toml`, `uv.lock`, MCP example configuration, and focused core-without-MCP/transport/extension tests.
- Behavior: the core package requires only `pydantic`, `python-dotenv`, `prompt-toolkit`, and `rich`; `anyio` and `mcp` are installed only by `mycodeagent[mcp]`. Core startup is importable with the MCP SDK blocked, while explicit MCP enablement gives the install-extra guidance.
- Verification: integrated focused command `uv run pytest -q tests/test_packaging_smoke.py tests/test_core_without_mcp.py tests/test_openai_compat_transport.py tests/extensions/test_mcp_extension.py tests/test_maintenance_boundaries.py tests/test_research_boundaries.py tests/extensions/test_skills_extension.py tests/extensions/test_tracing_extension.py tests/runtime/test_host.py tests/runtime/test_runner.py tests/scenarios` → `94 passed in 1.02s`; `rg -n '^from mcp|^import anyio' app core runtime tools` → no matches; a fresh Python 3.11 venv installed from `requirements.txt` plus `--no-deps .`, then imported `app.cli` with neither `mcp` nor `anyio` and ran `mycodeagent --help` successfully; a separate fresh `.[mcp]` install imported both `anyio` and `mcp`; locked core and dev compatibility exports were regenerated with `uv export --locked --format requirements-txt --no-hashes --no-dev --no-emit-project -o requirements.txt` and `uv export --locked --format requirements-txt --no-hashes --extra dev --no-emit-project -o requirements-dev.txt`.
- Metrics: required runtime dependencies `7 → 4`; core compatibility export `137 → 29` lines; core/dev compatibility exports contain zero MCP or AnyIO distributions.
- Follow-ups: M2-03, M2-04, and the M2 milestone gate (all successor implementation commits are integrated; gate remains).

## M2-03 — complete (integrated completion record)

- Commit: `551a9ca22cfc4b1e1b4007200c26da3a711cfc57` (`refactor(M2-03): remove agent teams research runtime`) and `7911225580fd48bce7f82f4f039a230a093710cf` (`fix(M2-03): remove experimental packaging remnants`), recorded under D-001.
- Changed: removed Teams runtime/tools/prompts/tests and the shipped `experimental*` namespace; archive and packaging boundary records point to the actual pre-removal parent.
- Behavior: stable packages, CLI/config, environment example, docs, prompts, and wheel discovery expose no Agent Teams surface; the research implementation is discoverable only through the Git-history archive.
- Verification: integrated focused command above → `94 passed in 1.02s`; `rg -n --glob '!docs/plans/**' --glob '!docs/research-archive.md' --glob '!docs/skill*' 'skill[_ -]?evolution|Skill Evolution|ENABLE_AGENT_TEAMS|agent[_ -]?teams|Agent Teams' app core runtime tools extensions prompts README.md AGENT.md .env.example docs` → no stable-product matches.
- Metrics: task diff removed `6,901` lines; package-discovery entries `8 → 7`; stable Teams symbol matches `0`.
- Follow-ups: M2-04 and the M2 milestone gate (M2-04 is integrated; gate remains).

## M2-04 — complete (integrated completion record)

- Commit: `7336ef14c00164490c8d9458d1641a3665643180` (`refactor(M2-04): remove skill evolution research`), recorded under D-001.
- Changed: removed Skill Evolution implementation, lifecycle hooks, tests, and research docs while retaining ordinary read-only skills loading and normal JSONL tracing.
- Behavior: stable runtime has no self-modifying skill overlay, flags, buffers, events, or imports; ordinary local Skills behavior remains available through its explicit/lazy extension path.
- Verification: integrated focused command above → `94 passed in 1.02s`; `uv run pytest -q` → `749 passed, 6 subtests passed in 4.04s`; `uv run ruff check .` → `All checks passed!`; the stable-product boundary search in the preceding entry returned no Skill Evolution matches; `uv run pytest -q tests/test_packaging_smoke.py::test_compatibility_exports_and_install_docs_keep_mcp_optional` → `1 passed in 0.01s` after the generated-export and documentation correction.
- Metrics: task diff removed `6,363` lines; stable Skill Evolution symbol matches `0`; compatibility export lines after the M2 dependency split are core `29`, dev `50`.
- Follow-ups: M2 milestone gate.

## M3 — complete

- Commit: milestone verification record pending commit under D-001.
- Changed: unified runtime events, direct runtime composition, and transcript-only recovery across M3-01 through M3-03.
- Behavior: one `RuntimeRunner` emits structured facts to trace/transcript projections; direct builders replace the single-product factory; transcripts are the only durable recovery source, including legacy import, compact recovery, and uncertain-action preservation without completed-tool replay.
- Verification: M3 gate `uv run pytest -q tests/runtime/test_events.py tests/extensions/test_trace_protocol.py tests/runtime/test_runner.py tests/runtime/test_host.py tests/runtime/test_transcript.py tests/runtime/test_session.py tests/runtime/test_session_memory.py tests/runtime/test_context.py tests/runtime/test_subagents.py tests/scenarios` → `131 passed`; `uv run pytest -q` → `763 passed, 6 subtests passed`; `uv run ruff check .` and `git diff --check` passed. The scenario and recovery suites cover completed-vs-uncertain tool semantics, compact checkpoints, legacy import, and duplicate IDs across runs.
- Metrics: full suite `749 → 763`; `runtime/host.py` `691 → 462`; `runtime/factory.py` `166 → 134`; `runtime/loop.py` `1,080 → 1,009`, with D-013 documenting the measured single-runner exception.
- Follow-ups: M4-01.

## M4-01 — complete

- Commit: `refactor(M4-01): centralize safe file workspace operations` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: added `tools/workspace.py` and independent workspace contracts; refactored `ReadTool` and `EditTool` to use the shared project-confined path, text, snapshot, and atomic-write primitives without changing their public response schema.
- Behavior: all workspace paths must be non-empty relative paths under the selected project. Traversal, absolute paths, and symlinks escaping the root are rejected; missing files, directories, and null-byte binary files have one checked path. Text reads use declared UTF-8 replacement fallback. Edit performs its existing caller-facing millisecond/size lock check plus an exact post-read snapshot check immediately before an atomic same-directory replacement; replacement cleans failed temporaries and preserves existing file modes.
- Verification: RED `uv run pytest -q tests/tools/test_workspace.py` → collection failed because `tools.workspace` did not exist; RED permission-preservation contract → `1 failed` before mode copying. GREEN workspace contracts → `12 passed`; focused workspace/Read/Edit/permission/protocol command → `147 passed`; final `uv run pytest -q` → `775 passed, 6 subtests passed in 4.10s`; `uv run ruff check .` and `git diff --check` passed. The focused contracts cover normalization, absolute/traversal/symlink escape, missing/directory/binary rejection, UTF-8 fallback, matching/mismatching snapshots, atomic replacement failure cleanup, and permission preservation.
- Metrics: duplicated Read/Edit path-validation, binary-check, and temporary-replacement implementations `2 → 1`; deterministic full suite `763 → 775`; `ReadTool` lines `407 → 407` (presentation retained), `EditTool` lines `549 → 549` (diff presentation retained), shared workspace `126` lines.
- Follow-ups: M4-02 and M4-03 safe parallel group, then M4-04 and M4-05.

### M4-01 review repair

- Commit: `fix(M4-01): preserve workspace error protocol context` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: `FileWorkspace.resolve`, Read/Edit workspace error projection, and focused workspace contracts.
- Behavior: a symlink-resolution loop is normalized to a `WorkspaceError`, so both tools return their normal protocol errors rather than raising. For missing, directory, and binary errors whose requested path already resolved safely under the project, Read and Edit retain `context.path_resolved`; resolution failures and escapes do not receive an untrusted path context.
- Verification: RED workspace regressions → `5 failed` (uncaught `RuntimeError` and missing context); GREEN workspace contracts → `17 passed`; final focused/full verification is recorded with this repair commit.

### M4-01 quality repair

- Commit: `fix(M4-01): reject non-regular workspace files` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: regular-file validation at the workspace stat boundary and FIFO Read/Edit contracts.
- Behavior: workspace inspection obtains metadata and rejects every non-regular entry, including FIFOs, before the binary probe opens it. Read and Edit convert this into their normal `INVALID_PARAM` protocol errors with the already safe `path_resolved` context, rather than potentially blocking on a FIFO.
- Verification: RED FIFO regressions → `2 failed` because the binary probe was invoked; GREEN workspace contracts → `19 passed`; final focused/full verification is recorded with this repair commit.

## M4-02 — complete

- Commit: `refactor(M4-02): unify file mutation in Edit` (recorded under D-001 after commit).
- Changed: replaced the separate Write, Edit, and MultiEdit implementations, prompts, host registrations, permission/completion/replay classifications, legacy unit suites, and scenario fixtures with one `EditTool` contract. `FileWorkspace` now also owns race-safe atomic new-file creation.
- Behavior: `Edit` accepts exactly one of ordered `edits` or `create_content`. Existing-file edits require a Read snapshot and validate every original-content anchor for uniqueness and overlap before one atomic replacement. `create_content` atomically creates a new file or fully replaces an existing file after the same snapshot check; dry runs never write. Write and MultiEdit have no source module, prompt, registration, schema alias, or runtime classification.
- Verification: RED `uv run python -m pytest -q tests/tools/test_edit_contract.py` → `9 failed` before the unified API/registration existed; RED existing empty-file full replacement → `1 failed` before snapshot-guarded `create_content` replacement. GREEN `uv run python -m pytest -q tests/tools/test_edit_contract.py tests/tools/test_workspace.py` → `30 passed`; focused migration command → `97 passed`; final `uv run python -m pytest -q` → `664 passed, 6 subtests passed`; `uv run ruff check .` and `git diff --check` passed. Default host schema inspection reports `Edit` and no Write/MultiEdit, with properties `path`, `edits`, `create_content`, `expected_mtime_ms`, `expected_size_bytes`, and `dry_run`.
- Metrics: file-mutation production implementations `3 → 1`; file-mutation prompt modules `3 → 1`; legacy mutation unit-test lines `2,802 → 0` replaced by `252` contract-test lines; `EditTool` `549 → 413` lines; full deterministic suite `775 → 664` tests while adding the nine required unified safety behaviors. The temporary M4 schema remains nine tools until the parallel M4-03 integration removes its redundant search/list tools.
- Follow-ups: M4-03 integration, then M4-04 and M4-05. M5 will complete the remaining release-documentation work.

### M4-02 spec repair

- Commit: `fix(M4-02): align active tool surface docs` (recorded under D-001 after commit).
- Changed: removed the obsolete Write and MultiEdit design documents; rewrote the active Edit design document; corrected active harness, portfolio, trace, README, task-policy, and UI icon references; and added an active-surface regression scan.
- Behavior: active product documentation and UI expose `Edit` as the sole file-mutation tool. Historical plans and the explicit research archive remain excluded from the active-surface scan.
- Verification: RED `uv run python -m pytest -q tests/test_tool_surface_docs.py` exposed legacy Write/MultiEdit names in active docs and UI; GREEN `uv run python -m pytest -q tests/test_tool_surface_docs.py tests/scenarios/test_phase9_portfolio_demos.py tests/test_ui_components.py` plus JSON validation → `40 passed`; final `uv run python -m pytest -q` → `665 passed, 6 subtests passed`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: active legacy file-mutation design documents `2 -> 0`; active UI file-mutation aliases `3 -> 1`; active-surface regression contracts `0 -> 1`.
- Follow-ups: M4-03 integration, then M4-04 and M4-05.

## M4-03 — complete

- Commit: `refactor(M4-03): consolidate file discovery and search` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: replaced `ListFiles` and `SearchFilesByNameTool` with one `GlobTool`; reduced `GrepTool` to the `pattern`, `path`, `glob`, `case_sensitive`, and `limit` schema; migrated registration, prompts, subagent restrictions, permission/concurrency policy, and protocol coverage; retired the separate legacy list/glob/grep suites.
- Behavior: Glob lists an immediate directory when pattern is omitted and otherwise recursively returns matching file paths. Both tools resolve their search root through `FileWorkspace`, exclude hidden/build/dependency paths by default, enforce bounded deterministic output, and reject project escapes. Grep pre-validates regular text candidates before its ripgrep primary path, skips binary files consistently, and reports its sole Python fallback as partial.
- Verification: RED `uv run pytest -q tests/tools/test_search_contract.py` → expected `ModuleNotFoundError: tools.builtin.glob`; first GREEN run → `8 passed, 1 failed` and identified that ripgrep emits text before a NUL byte in an explicit binary candidate; after workspace candidate validation → `9 passed`; fallback protocol RED → `1 failed` because a Python fallback reported success; final search/protocol contracts → `38 passed`; focused migration suite → `122 passed`; `uv run pytest -q` → `734 passed, 6 subtests passed`; `uv run ruff check .` and `git diff --check` passed. Stable source/prompt scan for `ListFiles`, `SearchFilesByNameTool`, `search_files_by_name`, `list_files`, and `LS` returned no matches.
- Metrics: stable discovery/search tools `3 → 2`; legacy discovery/search test modules `3 → 1`; discovery/search implementation lines `1,609 → 481` including the shared path policy; deterministic full suite `775 → 734` after retiring redundant compatibility tests.
- Follow-ups: integrate M4-02, then M4-04 and M4-05.

## M4 — complete

- Commit: milestone verification record pending commit under D-001.
- Changed: M4-01 centralizes safe workspace operations; M4-02 reduces mutation to Edit; M4-03 reduces discovery/search to Glob/Grep; M4-04 makes results typed until one serializer; M4-05 deletes obsolete compatibility layers and AskUser.
- Behavior: the default stable schema is exactly `Bash, Edit, Glob, Grep, Read, Task, TodoWrite`. File operations preserve root confinement, symlink/non-regular rejection, snapshots, atomic writes, and conflict safety. Search and result observations are bounded with full-output artifacts.
- Verification: M4 gate `uv run pytest -q tests/tools/test_workspace.py tests/tools/test_edit_contract.py tests/tools/test_search_contract.py tests/tools/test_result_contract.py tests/tools/test_orchestrator.py tests/tools/test_permissions.py tests/test_protocol_compliance.py tests/test_lean_defaults.py tests/test_maintenance_boundaries.py tests/scenarios` → `136 passed`; `uv run pytest -q` → `595 passed, 6 subtests passed`; `uv run ruff check .` and `git diff --check` passed. M4-05 review independently confirms the exact seven-tool schema and reproducible cleanup evidence.
- Metrics: stable tool schemas `12 → 7`; mutation tools `3 → 1`; discovery/search tools `3 → 2`; M4-05 compatibility/dead modules deleted `4`; AskUser stable-surface files `2` deleted.
- Follow-ups: M5-01.

### M4-03 P1 spec repair

- Commit: `fix(M4-03): bound search output and align fallback` (see `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` under D-001).
- Changed: Grep matching-line budget and truncation metadata, ripgrep unsupported-pattern fallback, search contracts, and Glob/Grep prompt contracts.
- Behavior: every returned Grep line is bounded to 2,000 characters; line-size and match-count truncation set `data.truncated`, enumerate `data.truncation_reasons`, and return `partial`. Python compilation remains the user-facing regex validity boundary. A Python-valid expression unsupported by ripgrep (for example look-ahead) now follows the normal Python fallback path rather than becoming an invalid-input error. Prompts no longer advertise removed timeout/count-abort fields and match their actual parameter and output limits.
- Verification: RED search contracts → `2 failed` (an oversized match was returned as success and an rg-unsupported Python expression was returned as error); GREEN `uv run pytest -q tests/tools/test_search_contract.py tests/test_protocol_compliance.py` → `40 passed`; final focused/full verification is recorded with this repair commit.

## M4-04 — complete

- Commit: `refactor(M4-04): simplify tool result protocol` (recorded under D-001 after commit).
- Changed: replaced per-tool JSON response construction with typed `ToolResult` values across all built-ins, registry, executor, orchestrator lifecycle/budgeting, and observation truncation. History now receives the single model-ready serialization; duplicated protocol and truncation assertions were consolidated into typed contract suites.
- Behavior: each built-in returns `ToolResult`; permission, circuit-breaker, parse, execution, partial, and truncation outcomes remain structured until `serialize_tool_result` produces the model-facing envelope. Full-output artifacts, visible error code/message, transcript lifecycle payloads, and aggregate budget metadata retain their prior behavior without JSON parse/re-encode loops.
- Verification: RED `uv run pytest -q tests/tools/test_result_contract.py` → `ImportError: ToolResult`; RED typed truncation contract → missing `force_truncate_result`; GREEN result/protocol contracts → `18 passed`; final `uv run pytest -q` → `594 passed, 6 subtests passed`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed. The final-diff ponytail review found no removable abstraction (`Lean already. Ship.`).
- Metrics: `tests/test_protocol_compliance.py` `516 → 34` lines; `tests/test_observation_truncator.py` `327 → 45` lines; `tools/registry.py` `551 → 456` lines; per-tool result JSON parsing in the registry/orchestrator/truncation path `3 → 0`; task diff `669 additions / 1,526 deletions` before this record.
- Follow-ups: M4-05, then M4 milestone gate.

### M4-04 spec repair

- Commit: `fix(M4-04): apply typed observation truncation` (recorded under D-001 after commit).
- Changed: routed each normalized `ToolObservation` through the existing typed line/byte observation limit before the single-tool and aggregate byte-budget force-compression paths; added an end-to-end 3,000-line orchestration regression.
- Behavior: a result that exceeds `TOOL_OUTPUT_MAX_LINES` is a structured partial result with its full-output artifact and truncation metadata even when both byte budgets are high. Byte-budget handling still receives the original typed result and can apply its stricter forced compression afterward.
- Verification: RED `uv run pytest -q tests/tools/test_orchestrator.py::test_run_applies_typed_line_limit_before_result_budget` → `1 failed` (status was `success`); GREEN same command → `1 passed`; focused `uv run pytest -q tests/tools/test_orchestrator.py` → `17 passed`; final `uv run pytest -q` → `595 passed, 6 subtests passed`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: end-to-end normal observation-limit orchestration contracts `0 → 1`; remaining M4-04 JSON parse/re-encode loops `0`.
- Follow-ups: M4-05, then M4 milestone gate.

### M4-04 quality repair

- Commit: `fix(M4-04): type registered demo callbacks` (recorded under D-001 after commit).
- Changed: updated `ToolRegistry.register_function` and `get_function` type contracts/documentation to require `ToolResult`; migrated the deterministic tool-harness demo callbacks to produce typed Read/Grep results; added registered-function and demo-observation regressions.
- Behavior: registered functions are documented and typed as internal `ToolResult` producers. The tool-harness demo now demonstrates successful concurrent Read/Grep results and the unchanged Edit permission denial, rather than exposing internal errors caused by legacy string callbacks.
- Verification: RED `uv run pytest -q tests/tools/test_executor.py::test_tool_executor_accepts_typed_registered_function_results tests/scenarios/test_phase9_portfolio_demos.py::test_tool_harness_demo_shows_batching_order_and_permission_denial` → `1 failed, 1 passed` (demo Read was `error`); GREEN same command → `2 passed`; focused `uv run pytest -q tests/tools/test_executor.py tests/scenarios/test_phase9_portfolio_demos.py` → `16 passed`; final `uv run pytest -q` → `595 passed, 6 subtests passed`; `uv run ruff check .` → `All checks passed!`; `git diff --check` passed.
- Metrics: deterministic registered-function typed-success contract `0 → 1`; deterministic demo typed Read/Grep observation assertions `0 → 4`; remaining demo registered-function string producers `2 → 0`.
- Follow-ups: M4-05, then M4 milestone gate.

## M4-05 — complete

- Commit: `refactor(M4-05): remove obsolete compatibility layers` (recorded under D-001 after commit).
- Changed: deleted the unused `core.agent` base protocol, runtime/tool
  observation re-export modules, an empty serialization module, and the
  unneeded AskUser tool/prompt surface. Direct imports now point at the typed
  tools boundary; CodeAgent directly owns its identity/config initialization
  and preserves its previous string representation. Active docs now identify
  the actual observation owner and no longer advertise AskUser's error code.
  `CLEANUP_REPORT.md` records every deletion, call-site evidence, retained
  migration boundary, and deletion-focused review.
- Behavior: default startup exposes exactly seven stable schemas: Bash, Edit,
  Glob, Grep, Read, Task, and TodoWrite. AskUser has no model schema, source
  module, prompt, error code, permission branch, or no-op alias. The legacy
  snapshot parser remains a read-only transcript-migration exception under
  D-014, not a second persistence path.
- Verification: RED `uv run pytest -q
  tests/test_lean_defaults.py::test_default_host_exposes_the_bounded_seven_tool_stable_schema`
  → `1 failed` because default startup exposed AskUser as an eighth schema.
  GREEN focused cleanup suite → `92 passed`; full `uv run pytest -q` →
  `595 passed, 6 subtests passed`; `uv run ruff check .`, `git diff
  --check`, import smoke, and `uv run mycodeagent --help` passed. The
  stable-source `rg` scan recorded in `CLEANUP_REPORT.md` returned no
  obsolete-layer or AskUser matches.
- Metrics: default stable tool schemas `8 → 7`; deleted standalone
  compatibility/dead modules `4`; deleted AskUser implementation/prompt
  lines `90`; committed M4-05 diff `184 additions / 189 deletions`.
  `CLEANUP_REPORT.md` records the exact `git show --numstat` filters for
  the report-excluded `113 / 189` and production-plus-tests `60 / 185`
  subsets.
- Follow-ups: M4 milestone gate. Active old LS/ListFiles design documents are
  recorded for the planned M5-02 documentation reconciliation, rather than
  silently broadened into this cleanup task.

## M5-01 — complete

- Commit: `test(M5-01): center suite on contracts and scenarios` (recorded under D-001 after commit).
- Changed: one shared stable-tool envelope contract, a deterministic Edit → Bash-verification → completion scenario, explicit credentialed-eval separation, and deletion of duplicate/source-string architecture tests.
- Behavior: all seven default tools are exercised through one typed/model-envelope contract; a real runtime scenario proves mutation followed by fresh test evidence can complete; credentialed provider probes require the explicit `credentialed` marker and never run in deterministic core CI.
- Verification: RED `uv run pytest -q tests/contracts/test_credentialed_eval_boundary.py` → `1 failed` before the marker was configured; RED scenario collection → missing `VerifiedEditScenarioHost`; GREEN focused command `uv run pytest -q tests/contracts tests/scenarios/test_lean_runtime_characterization.py tests/test_app_bootstrap.py tests/runtime/test_messages.py tests/runtime/test_prompt.py tests/tools/test_executor.py tests/runtime/test_subagents.py tests/test_maintenance_boundaries.py tests/test_lean_defaults.py` → `78 passed`; consecutive full runs `uv run pytest -q --durations=10` → `584 passed, 1 deselected, 6 subtests passed` in `3.84s` and `3.94s`; `uv run pytest -q -m credentialed` → `1 skipped, 584 deselected`; collection confirms core `584/585` and credentialed `1/585`; `uv run ruff check .` and `git diff --check` passed.
- Metrics: collected deterministic tests `595 → 584` plus `1` explicitly opt-in live-provider test; current test Python LOC `14,248` (`rg --files tests -g '*.py' | xargs wc -l | tail -1`); duplicate six-case envelope suite and nine-case internal-type matrix `→` one seven-tool behavior contract; source-string ownership checks removed `5`.
- Follow-ups: M5-02 and the M5/release gate.

## M5-02 — evidence recorded; release gate blocked by Q-05

- Commit: `docs(M5-02): publish lean runtime release evidence` (recorded under
  D-001 after commit).
- Changed: current README, contributor guide, and harness architecture;
  explicit archive labels for superseded HARNESS/tool/portfolio/roadmap
  material; core/MCP/metrics CI jobs; reproducible metrics command; and
  `FINAL_REPORT.md`.
- Verification: `uv run pytest -q` → `584 passed, 1 deselected, 6 subtests
  passed in 3.68s`; `uv run ruff check .` → `All checks passed`; MCP-focused
  command → `20 passed, 6 subtests passed`; scenarios → `23 passed`; installed
  help in an unrelated temporary Git repository exited 0 in `1.36s`; core
  editable install had neither `mcp` nor `anyio`, while `.[mcp]` imported both.
- Metrics: exact seven-tool schema and four core dependencies pass. Stable
  production Python is `15,411`, not the required `≤14,000`; the metrics
  command exits 1 with the exact Q-05 failure.
- Exact blocker: Q-05 is a product release blocker, not an external blocker.
  A net 1,411-line reduction under the M0 metric remains. `FINAL_REPORT.md`
  identifies the long-term-memory, verification-subagent, and HTML-trace
  call-site candidates for the immediate post-task remediation.

## M6-01 — complete

- Commit: `refactor(M6-01): remove optional project memory` (recorded under
  D-001 after commit).
- Changed: deleted the cross-session project-memory store, Memory tool and
  prompt, configuration and CLI opt-in, model-view injection, trace branches,
  permission branch, and dedicated tests. The portfolio recovery demo now
  demonstrates transcript-derived session memory rather than a second store.
- Behavior: transcript facts, compact checkpoints, and derived session memory
  remain the only recovery path. There is no project-memory schema, flag,
  store, prompt, injection, trace event, permission exception, or alias.
- Verification: RED `uv run pytest -q
  tests/test_lean_defaults.py::test_runtime_exposes_no_optional_project_memory_capability`
  → `1 failed` because `Config.model_fields` still exposed
  `long_term_memory_enabled`; GREEN focused recovery/trace/Task/MCP/scenario
  command → `81 passed, 6 subtests passed`; full `uv run pytest -q` → `555
  passed, 1 deselected, 6 subtests passed`; `uv run ruff check .` → `All
  checks passed!`; `uv run mycodeagent --help` and `git diff --check` passed.
- Metrics: stable production Python `15,411 → 15,130`; stable schemas remain
  exactly `Bash, Edit, Glob, Grep, Read, Task, TodoWrite`. Q-05 remains a
  product blocker by 1,130 lines pending the next scoped remediation.

## M6-02 — complete; release gate remains blocked

- Commit: `refactor(M6-02): keep JSONL tracing only` (recorded under D-001
  after commit).
- Changed: removed the trace HTML renderer/configuration path, trace protocol
  declarations, and unused `runtime.evals` API with their dedicated tests.
  JSONL logger facts, sanitizer, and trace/transcript sink remain. Scenario
  and portfolio assertions now inspect direct event facts; the active scenario
  guide describes those facts rather than a product-side evaluator. D-023
  records the deletion boundary.
- Behavior: default tracing creates JSONL only. There is no trace renderer
  configuration, report output, protocol export, or generic trace-summary API.
  The runtime event sink still projects one message fact to both trace and
  transcript stores, and compact/session recovery stays covered.
- Verification: RED `uv run pytest -q
  tests/test_lean_defaults.py::test_trace_logger_writes_jsonl_without_an_html_configuration`
  → `1 failed` because `Config.model_fields` contained
  `trace_html_enabled`; scenario dependency RED → collection error after
  removing `summarize_trace`; demo RED → `NameError` after removing the final
  production evaluator import. GREEN focused trace/transcript/session/scenario
  command → `88 passed`; MCP regression command → `20 passed, 6 subtests
  passed`; scenarios → `23 passed`; full `uv run pytest -q` → `548 passed, 1
  deselected, 6 subtests passed`; `uv run ruff check .` → `All checks passed`.
  Direct scans found no production caller before deletion and no remaining
  removed renderer/config/evaluation/protocol symbol afterward.
- Metrics: stable production Python `15,130 → 14,243`; test Python `14,248
  → 13,265`; stable schema remains seven tools. `uv run python
  scripts/check_release_metrics.py` correctly still exits 1: 243 lines above
  the `14,000` Q-05 cap.
- Exact blocker: Q-05 remains a product release blocker by 243 stable
  production Python lines. No external blocker exists; the next scoped
  remediation must reduce that budget without weakening JSONL tracing,
  transcript recovery, Task/Explore, MCP, or Skills behavior.
