# M1-02 One-Shot and JSON Output Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Add scriptable one-shot text and JSON modes without creating a second runtime path.

**Architecture:** Reuse the same runtime builder and agent call for interactive and one-shot modes, with rendering isolated at the output boundary.

**Tech Stack:** Python, argparse, Rich, JSON, pytest subprocess tests.

**Dependencies:** M1-01.

**Files:**

- Modify: `app/cli.py`
- Modify: `app/bootstrap.py` only for injectable runtime construction
- Create: `app/output.py` if rendering cannot remain small in `cli.py`
- Create: `tests/test_cli_one_shot.py`
- Modify: `tests/test_ui_components.py` only for shared rendering behavior

## CLI Contract

```text
mycodeagent -p "task"
mycodeagent --print "task"
mycodeagent -p "task" --json
```

- Text mode writes the final answer to stdout; progress goes to stderr or is suppressed.
- JSON mode writes exactly one JSON object with `status`, `response`, `session_id`, `terminal_reason`, and usage/verification fields when available.
- Success exits 0; invalid configuration/input exits 2; runtime failure exits 1; interrupted exits 130.
- Interactive and one-shot call the same `build_runtime()` and `agent.run()` path.

## Steps

1. Write parser and output tests with a fake runtime/agent; do not require credentials.
2. Separate output rendering from runtime behavior only as much as tests require.
3. Ensure Rich banners/spinners never pollute JSON stdout.
4. Implement exit-code mapping from structured runtime outcome; if only strings exist, add the smallest backward-compatible outcome adapter.
5. Add a subprocess smoke test for `python main.py -p ... --json` with injected fake dependencies.
6. Run CLI, bootstrap, UI, and scenario tests.

## Acceptance

- JSON output parses with `json.loads(stdout)`.
- No duplicate agent loop or one-shot-only tool path exists.
- Commit: `feat(M1-02): add one-shot and json CLI modes`.
