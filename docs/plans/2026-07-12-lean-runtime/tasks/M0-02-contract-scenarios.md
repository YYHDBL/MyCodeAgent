# M0-02 Stable-Path Characterization Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Freeze the behavior that must survive simplification with deterministic scenarios, without preserving accidental internal structure.

**Architecture:** Drive the existing canonical runtime with fake models and temporary projects, asserting observable events and state rather than source layout.

**Tech Stack:** Python, pytest, existing scenario fixtures and fake LLMs.

**Dependencies:** M0-01.

**Files:**

- Modify: `tests/scenarios/phase0_baselines.py`
- Modify: `tests/scenarios/test_phase0_baselines.py`
- Create: `tests/scenarios/test_lean_runtime_characterization.py`
- Modify only if required for deterministic fixtures: `tests/conftest.py`

## Required Scenarios

1. One user turn → model final → completion terminal.
2. Model tool call → authorized execution → ordered observation → final.
3. Permission rejection returns a normal tool observation.
4. Context threshold creates a checkpoint without deleting source history.
5. Oversized tool output persists a full artifact and sends a bounded preview.
6. Transcript records user, assistant, tool, transition, and terminal facts.
7. Resume does not replay a completed side-effecting tool.
8. Completion is blocked when required evidence is stale or missing.

## Steps

1. Replace implementation-string assertions with externally visible state/event assertions where practical.
2. Add failing characterization tests only for behavior already claimed by current docs.
3. Run each new test and determine whether a failure is a real current defect or a stale claim.
4. For real defects, record a decision and defer the fix to the owning later task; do not broaden this task.
5. Keep all scenarios free of API keys, network, real shell side effects, and wall-clock sleeps.
6. Run `pytest tests/scenarios -q` and the existing core suite.

## Acceptance

- Scenarios test contracts, not filenames or source-code substrings.
- Results are deterministic across two consecutive runs.
- Baseline failures are explicitly listed in `PROGRESS.md`.
- Commit: `test(M0-02): characterize stable runtime contracts`.
