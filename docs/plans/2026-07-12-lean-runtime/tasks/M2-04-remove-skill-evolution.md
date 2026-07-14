# M2-04 Remove Skill Evolution from Stable Product Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Remove the self-modifying Skill Evolution research system and all lifecycle hooks from the stable runtime.

**Architecture:** Detach evolution-specific hooks, overlays, events, and configuration while retaining the ordinary read-only Skills extension.

**Tech Stack:** Python, Git history, pytest, ripgrep boundary checks.

**Dependencies:** M2-01. Integrate after M2-03.

**Files:**

- Delete: `extensions/skill_evolution/`
- Delete: `tests/extensions/test_skill_evolution.py`
- Delete: `docs/skill_evolution/`
- Delete: `docs/SKILL_EVOLUTION_DESIGN.md`
- Modify: `extensions/skills/loader.py` only to remove evolution overlay behavior while retaining normal skills
- Modify: `app/cli.py`
- Modify: `app/bootstrap.py`
- Modify: `core/config.py`
- Modify: `runtime/factory.py`
- Modify: `runtime/host.py`
- Modify: `runtime/loop.py`
- Modify: tracing protocol/logger only to remove evolution-only events/buffers
- Modify: `README.md`, `AGENT.md`, `docs/HARNESS.md`, `docs/research-archive.md`

## Safety Note

The source worktree had user changes under Skill Evolution when this plan was written. Execute in an isolated worktree and never delete or alter the user's source-worktree copies.

## Steps

1. Add a boundary test asserting no stable package contains Skill Evolution flags, imports, hooks, events, or overlay configuration.
2. Record the last containing commit in `docs/research-archive.md`.
3. Remove the CLI/config/bootstrap/factory/host/loop lifecycle integration first and keep normal Skills tests green.
4. Remove evolution-specific trace buffering without weakening normal JSONL tracing.
5. Delete implementation, tests, and detailed research docs; do not move them to a new in-tree Python package.
6. Run skills, tracing, host, loop, bootstrap, scenario, and full tests.
7. Measure LOC and prompt/config reduction.

## Acceptance

- Normal skill discovery/loading still works.
- Acceptance gate A-04 passes for Skill Evolution symbols.
- Stable runtime has no self-modifying skill behavior.
- Commit: `refactor(M2-04): remove skill evolution research system`.
