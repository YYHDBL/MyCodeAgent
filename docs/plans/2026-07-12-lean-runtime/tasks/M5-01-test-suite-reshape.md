# M5-01 Test Suite Reshape Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Make tests measure behavior and architecture contracts with less duplication and stronger end-to-end evidence.

**Architecture:** Organize tests into focused units, reusable contracts, and deterministic user-visible scenarios; keep credentialed evals separate.

**Tech Stack:** Python, pytest fixtures/parametrization, fake LLMs, temporary projects.

**Dependencies:** M4-05 and M4 milestone gate.

**Files:**

- Reorganize/modify: `tests/tools/`
- Reorganize/modify: `tests/runtime/`
- Reorganize/modify: `tests/scenarios/`
- Modify: root `tests/test_*.py` where duplicates remain
- Create: `tests/contracts/` if it reduces duplication
- Modify: `pyproject.toml` pytest/Ruff configuration

## Target Test Pyramid

- Unit tests for pure parsing, policy, state transitions, and compact algorithms.
- Parameterized contract tests shared by all tools/sinks.
- Deterministic scenario tests for user-visible lifecycle.
- Optional credentialed evals clearly separated and never required for core CI.

Required scenarios: CLI target root, one-shot JSON, permission deny, edit + verification, context compact, oversized output, interruption, transcript resume, completion evidence, optional MCP missing, restricted subagent.

## Steps

1. Inventory duplicate test names/assertion patterns and source-string architecture tests.
2. Introduce shared contract fixtures before deleting duplicates.
3. Convert architecture assertions to import/dependency/behavior checks.
4. Add missing required scenarios, using fake LLMs and temporary projects.
5. Remove duplicate per-tool response-shape tests covered by the contract suite.
6. Run tests twice, check collection count intentionally, and measure duration.

## Acceptance

- Lower test LOC is desirable but not mandatory; stronger deterministic coverage is mandatory.
- Two consecutive full runs have identical outcomes.
- Commit: `test(M5-01): center suite on contracts and scenarios`.
