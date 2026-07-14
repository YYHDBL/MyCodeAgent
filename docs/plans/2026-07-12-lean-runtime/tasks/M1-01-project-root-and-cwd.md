# M1-01 Project Root and CWD Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Make the invocation directory the default target project and add an explicit `--cwd` override.

**Architecture:** Separate package resource location from the injected target-project root, resolving the latter once at the CLI/bootstrap boundary.

**Tech Stack:** Python, argparse, pathlib, pytest.

**Dependencies:** M0-02.

**Files:**

- Modify: `app/cli.py`
- Modify: `app/bootstrap.py`
- Modify: `runtime/host.py` only if root propagation is incomplete
- Test: `tests/test_app_bootstrap.py`
- Create: `tests/test_cli_project_root.py`

## Behavior Contract

- Resource/package root and target project root are different concepts.
- `mycodeagent` invoked from `/tmp/project-a` targets `/tmp/project-a`.
- `--cwd /tmp/project-b` targets the resolved `/tmp/project-b`.
- Missing/non-directory roots fail before model or extension initialization.
- Tool paths, transcripts, memory, project rules, and output artifacts use the target root.

## Steps

1. Write failing parser/bootstrap tests for default CWD, explicit CWD, relative CWD, and invalid CWD.
2. Introduce a resource-root constant only where built-in package assets require it; remove `PROJECT_ROOT` use as a target default.
3. Resolve and validate the target root once in bootstrap, then inject it.
4. Audit `app/`, `runtime/`, and `tools/` for hidden source-root assumptions.
5. Add a scenario that starts from an unrelated temporary repository and asserts all writes remain there.
6. Run focused tests, scenarios, and the full core suite.

## Acceptance

- No product path silently falls back to the MyCodeAgent source checkout.
- Root traversal/security tests still pass.
- Commit: `feat(M1-01): target current or explicit project root`.
