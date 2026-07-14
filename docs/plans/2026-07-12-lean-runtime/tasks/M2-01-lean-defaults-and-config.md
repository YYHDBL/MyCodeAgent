# M2-01 Lean Defaults and Configuration Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Establish one configuration source whose defaults describe the minimal single-agent path.

**Architecture:** Resolve defaults and environment values in `Config`, apply CLI overrides once in bootstrap, and inject the resulting object.

**Tech Stack:** Python, Pydantic or dataclasses as already chosen by the codebase, argparse, pytest.

**Dependencies:** M1-04.

**Files:**

- Modify: `core/config.py`
- Modify: `app/cli.py`
- Modify: `app/bootstrap.py`
- Modify: `runtime/host.py`
- Modify: `.env.example`
- Test: `tests/test_app_bootstrap.py`
- Test: `tests/test_llm_temperature_policy.py` only if config construction changes
- Create: `tests/test_lean_defaults.py`

## Target Defaults

- MCP off.
- Verification subagent off; deterministic completion on.
- Agent Teams off pending removal.
- Skill Evolution off pending removal.
- Long-term memory off.
- Skills discover lazily; no rescan on every model call by default.
- Lightweight local tracing on, but no HTML/report generation in the hot path.

## Steps

1. Parameterize tests over config defaults, environment parsing, and CLI precedence.
2. Make `Config` the single source; remove duplicated constructor defaults in `CodeAgent` where possible.
3. Add explicit positive CLI flags for optional systems; avoid double-negative flag names.
4. Remove legacy alias environment variables unless documented user compatibility requires one release window.
5. Update `.env.example` to show only common core values; put optional flags in a short optional section.
6. Add a startup test asserting no subagent, team manager, MCP client, or long-term store is created by default.

## Acceptance

- `Config()`, `Config.from_env()`, CLI defaults, README, and tests agree.
- No optional subsystem is initialized merely because its package is installed.
- Commit: `refactor(M2-01): make minimal runtime the default`.
