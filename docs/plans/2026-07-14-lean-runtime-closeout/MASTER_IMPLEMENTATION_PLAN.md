# Lean Runtime Closeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this
> plan task-by-task. When using one agent per task, also use
> `subagent-driven-development` and independently verify every agent commit.

**Goal:** Make the existing lean-runtime branch release-ready by repairing the
broken verifier path, enforcing honest static checks, reconciling the JSONL
summary contract, removing measured model-layer duplication, and producing a
safe integration handoff.

**Architecture:** Preserve the single loop, transcript recovery, JSONL trace,
seven-tool surface, and optional extension boundaries. Recover the remaining
complexity budget by making provider configuration data-driven, sharing request
and response normalization, and deleting dead code rather than deleting useful
capabilities.

**Tech Stack:** Python 3.10+, Pydantic 2, pytest, Ruff, uv, standard-library
OpenAI-compatible HTTP transport, Git worktrees.

---

## Task Sequence

### Task 1: R0-01 Baseline and Safety Lock

**Files:** Create `BASELINE.md`; update `PROGRESS.md`.

1. Record both worktrees, branches, heads, status, and protected-file hashes.
2. Run all baseline commands from `tasks/R0-01-baseline-and-safety.md`.
3. Reproduce the enabled-verifier `NameError` without making a network call.
4. Commit only baseline evidence.

### Task 2: R1-01 Verification Bootstrap

**Files:** Modify `runtime/host.py`; test `tests/test_app_bootstrap.py`.

1. Write the enabled-bootstrap regression.
2. Run it and confirm `NameError`.
3. Add the minimal lazy import inside the enabled branch.
4. Run focused verifier/default tests, then full tests.
5. Commit `fix(R1-01): repair verification-agent bootstrap`.

### Task 3: R1-02 Critical Ruff Gates

**Files:** Modify `pyproject.toml` and the concrete F-rule findings listed in
the task file.

1. Remove global suppression for correctness/dead-code rules.
2. Run strict rules and use the output as the failing checklist.
3. Fix findings without behavior changes.
4. Run strict and normal Ruff plus full tests.
5. Commit `chore(R1-02): enforce critical Ruff rules`.

### Task 4: R1-03 Import Order and Environment Startup

**Files:** Modify `app/cli.py`, `runtime/host.py`, selected tests/demo lint
configuration, and `pyproject.toml`.

1. Capture the current E402 list.
2. Remove stable-package import-time ordering violations.
3. Move test imports to the top; use only narrow, documented per-file handling
   for an executable bootstrap script if structurally required.
4. Remove global E402 suppression and run its focused gate.
5. Commit `chore(R1-03): make import ordering explicit`.

### Task 5: R2-01 JSONL Summary Contract

**Files:** Test `tests/test_trace_logger.py`; modify active trace/plan docs.

1. Run the existing summary test as characterization.
2. Strengthen the assertion around steps, tool count, and token totals if any
   field is not already covered.
3. Update wording to distinguish retained `session_summary` metrics from the
   removed generic evaluator.
4. Prove no renderer/evaluator compatibility surface returned.
5. Commit `docs(R2-01): clarify JSONL summary contract`.

### Task 6: R3-01 Data-Driven Provider Resolution

**Files:** Modify `core/llm.py`, provider tests, `.env.example`, and README only
when behavior documentation changes.

1. Add characterization tests for all retained provider profiles and explicit
   configuration precedence.
2. Replace credentials/default-model branch ladders with immutable provider
   metadata.
3. Replace private dotenv caching with the canonical environment loader.
4. Preserve generic OpenAI-compatible `auto` behavior; remove only unsupported
   guessing that has no product contract and record that decision.
5. Run provider, bootstrap, CLI, and core-without-MCP tests.
6. Commit `refactor(R3-01): data-drive provider resolution`.

### Task 7: R3-02 Shared Model Request Path

**Files:** Modify `core/llm.py` and model request tests.

1. Characterize streaming, text, raw, retry, MiniMax, Kimi, and omission of
   `None` parameters.
2. Introduce one request builder and one retry helper.
3. Keep public `think`, `invoke`, `invoke_raw`, and `stream_invoke` behavior.
4. Run model and full regression tests.
5. Commit `refactor(R3-02): share model request handling`.

### Task 8: R3-03 Canonical Subagent Response Normalization

**Files:** Modify `runtime/subagents.py`; test runtime/subagent and phase-7
scenarios.

1. Add equivalence tests using both dict-shaped and SDK-shaped responses.
2. Delegate subagent extraction to `core.llm` helpers.
3. Delete local duplicate attribute/message helpers.
4. Run subagent, runner, completion, and scenario tests.
5. Commit `refactor(R3-03): share response normalization`.

### Task 9: R3-04 Release Budget Gate

**Files:** Evidence only unless a separately recorded, behavior-preserving
duplicate remains.

1. Run the unchanged release metric.
2. If it passes, record exact values and stop changing production code.
3. If it fails, do not alter the metric or remove capabilities; document the
   exact excess and perform a scoped review before authorizing another edit.
4. Run full milestone verification.
5. Commit `docs(R3-04): record passing release budget` only after a pass.

### Task 10: R4-01 Documentation Reconciliation

**Files:** Original dated plan control files, README/HARNESS, closeout progress
and decisions.

1. Add M6 and closeout status to the old task graph/milestones.
2. Reconcile trace summary wording and strict lint policy.
3. Run docs/CLI consistency tests and scans.
4. Commit `docs(R4-01): reconcile lean runtime plans`.

### Task 11: R4-02 Final Release Verification

**Files:** Replace closeout `FINAL_REPORT.md` template.

1. Run every command in `05_ACCEPTANCE_CRITERIA.md` fresh.
2. Map every acceptance ID to exact output.
3. Recheck protected original-worktree hashes.
4. Commit final evidence only if all non-integration gates pass.

### Task 12: R5-01 Integration Handoff

**Files:** Create `INTEGRATION_HANDOFF.md`; finalize `PROGRESS.md`.

1. Record base/head/commit range and likely conflicts.
2. Give the user explicit preserve/archive/drop choices for the six dirty paths.
3. Provide commands only; perform no merge, push, stash, reset, or checkout.
4. Commit the handoff and verify the implementation worktree is clean.

## Execution Handoff

The intended execution mode is a new long-running Goal session started from the
dedicated implementation worktree. Paste the prompt in `06_GOAL_PROMPT.md`.
