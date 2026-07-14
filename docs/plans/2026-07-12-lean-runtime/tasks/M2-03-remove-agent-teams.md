# M2-03 Remove Agent Teams from Stable Product Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Remove Agent Teams and all stable-runtime integration while preserving the research implementation through Git history documentation.

**Architecture:** Delete the research subsystem and its integration points from the stable dependency graph; preserve discoverability with a commit reference only.

**Tech Stack:** Python, Git history, pytest, ripgrep boundary checks.

**Dependencies:** M2-01. Integrate after M2-02.

**Files:**

- Delete: `experimental/teams/`
- Delete: `tests/experimental/`
- Delete: all `tools/builtin/team_*.py` and `tools/builtin/send_message.py`
- Delete: matching team/send-message prompt files
- Modify: `app/cli.py`
- Modify: `core/config.py`
- Modify: `runtime/host.py`
- Modify: `runtime/loop.py`
- Modify: `runtime/subagents.py` only to remove team compatibility state
- Modify: `README.md`, `AGENT.md`, `docs/HARNESS.md`
- Create: `docs/research-archive.md` if not already present

## Steps

1. Add a boundary test asserting stable packages contain no Teams imports, flags, tool registrations, CLI commands, or prompt names.
2. Record the exact pre-removal commit in `docs/research-archive.md`; Git history is the archive.
3. Remove CLI team commands, display hooks, config fields, host initialization, loop runtime blocks, tools, prompts, code, and tests.
4. Do not introduce empty compatibility tools or deprecated no-op flags.
5. Ensure formal `Task` Explore/Verification subagents continue to work independently.
6. Run CLI, config, runtime, subagent, protocol, scenario, and full tests.
7. Measure production/test/doc LOC reduction.

## Acceptance

- Acceptance gate A-04 passes for Teams symbols.
- No user-facing help or README text promises Teams.
- Explore/Verification subagent scenarios still pass.
- Commit: `refactor(M2-03): remove agent teams research runtime`.
