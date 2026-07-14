# M1-04 Resume, Status, and Cancellation UX Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Complete the basic interactive lifecycle: inspect status, list/resume sessions, and cancel one turn without exiting the CLI.

**Architecture:** Expose small lifecycle operations from the runtime/transcript boundary and keep command parsing/rendering in the CLI.

**Tech Stack:** Python, prompt_toolkit, transcript JSONL, pytest.

**Dependencies:** M1-03.

**Files:**

- Modify: `app/cli.py`
- Modify: `runtime/transcript.py`
- Modify: `runtime/host.py` only for public lifecycle methods
- Modify: `runtime/session.py` only for transition compatibility
- Create: `tests/test_cli_lifecycle.py`
- Modify: `tests/runtime/test_transcript.py`

## UX Contract

- `/status` shows target root, model/provider, session ID, permission mode, enabled optional extensions, and context usage.
- `/sessions` lists recent transcript sessions for the target root.
- `/resume <id>` restores from transcript facts and reports uncertain actions.
- `--resume [id]` supports one-shot or interactive startup.
- `Ctrl+C` during a running turn cancels that turn, records an interrupted terminal/event, and returns to the prompt. A second interrupt at an idle prompt may exit.

## Steps

1. Write transcript listing/resolution tests using temporary directories.
2. Write CLI command tests with fake host state and simulated `KeyboardInterrupt`.
3. Expose small public status/resume/cancel methods; do not let CLI inspect private trace internals.
4. Ensure interrupted side effects become `uncertain` only when they actually started without completion.
5. Add deterministic resume and cancellation scenarios.
6. Run lifecycle, transcript, session, CLI, and scenario tests.

## Acceptance

- Resume is transcript-backed, even if legacy snapshots still exist temporarily.
- Cancellation never corrupts assistant/tool message pairing.
- Commit: `feat(M1-04): add session lifecycle CLI controls`.
