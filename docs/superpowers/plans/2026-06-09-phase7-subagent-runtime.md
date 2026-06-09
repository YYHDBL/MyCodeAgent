# Phase 7 Subagent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Task-specific loop with isolated Explore and Verification agents that reuse `RuntimeRunner`.

**Architecture:** Add immutable runtime profiles and a `SubagentLauncher` that constructs an isolated runtime host with its own history, context engine, transcript, memory, registry, trace, state, and budgets. `TaskTool` becomes an Explore-only adapter. Completion verification composes the deterministic verifier with an optional Verification profile and never permits the model verifier to override deterministic failure.

**Tech Stack:** Python, pytest, existing RuntimeRunner, ContextEngine, Permission Core, Transcript, Session Memory, Trace/Eval harness.

---

### Task 1: Runtime profiles and result contracts

**Files:**
- Create: `runtime/subagents.py`
- Test: `tests/runtime/test_subagents.py`

- [ ] Write failing tests for profile invariants, result verdicts, tool allowlists, and recursion policy.
- [ ] Run `pytest tests/runtime/test_subagents.py -q` and confirm missing interfaces fail.
- [ ] Implement immutable Explore and Verification profiles plus structured request/result types.
- [ ] Re-run the targeted tests.

### Task 2: Isolated launcher on RuntimeRunner

**Files:**
- Modify: `runtime/subagents.py`
- Modify: `runtime/host.py`
- Test: `tests/runtime/test_subagents.py`

- [ ] Write failing tests proving `RuntimeRunner.run()` is used and parent history/context are untouched.
- [ ] Implement the isolated host, filtered registry, readonly permission context, child transcript/memory, and child trace.
- [ ] Record parent lifecycle events with parent/child IDs, budgets, usage, verdict, terminal reason, and elapsed time.
- [ ] Re-run launcher and permission tests.

### Task 3: Rewrite TaskTool

**Files:**
- Replace: `tools/builtin/task.py`
- Modify: `runtime/host.py`
- Replace: `tests/test_task_tool.py`

- [ ] Write failing tests for Explore-only validation, structured parent result, failure containment, and teams-independent registration.
- [ ] Remove `SubagentRunner`, general/plan/summary modes, and persistent/parallel Teams routing.
- [ ] Register Task independently from `enable_agent_teams`.
- [ ] Re-run Task and runtime host tests.

### Task 4: Verification agent completion integration

**Files:**
- Modify: `runtime/completion.py`
- Modify: `runtime/host.py`
- Modify: `core/config.py`
- Test: `tests/runtime/test_completion.py`
- Test: `tests/runtime/test_subagents.py`

- [ ] Write failing tests for PASS/FAIL/PARTIAL/UNVERIFIED, deterministic short-circuit, exception mapping, and readonly verification.
- [ ] Implement a deterministic-first composite verifier backed by the Verification profile.
- [ ] Enable it by configuration only when completion requirements request verification.
- [ ] Re-run completion tests.

### Task 5: Trace, eval, scenarios, and documentation

**Files:**
- Modify: `runtime/evals.py`
- Modify: `extensions/tracing/protocol.py`
- Create: `tests/scenarios/test_phase7_subagents.py`
- Modify: `docs/HARNESS.md`
- Modify: `docs/HARNESS_ROADMAP.md`
- Modify: `docs/HARNESS_TRACE_PROTOCOL.md`

- [ ] Add failing metric tests for child invocation/tool/token/failure counts and verification verdict.
- [ ] Implement metric aggregation and two deterministic Phase 7 scenarios.
- [ ] Update architecture, trace, and roadmap documentation.
- [ ] Run targeted, runtime, tools, scenario, and all non-experimental tests.
- [ ] Run source scans, `git diff --check`, verify no ` 2.py` files, and commit once with the requested message.
