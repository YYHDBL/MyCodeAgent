# M1-03 Packaging and Entrypoint Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Make MyCodeAgent installable and runnable as `mycodeagent` with one authoritative dependency definition.

**Architecture:** Use PEP 621 metadata and one console-script entrypoint; keep dependency truth in `pyproject.toml` and generate the lock mechanically.

**Tech Stack:** Python packaging, uv, pyproject.toml, pytest, Ruff.

**Dependencies:** M1-02.

**Files:**

- Create: `pyproject.toml`
- Create/update mechanically: `uv.lock`
- Modify: `requirements.txt` and `requirements-dev.txt` to become compatibility exports or remove them with documented migration
- Modify: `README.md` quick-start only
- Create: `tests/test_packaging_smoke.py`

## Packaging Contract

- Project metadata declares Python version, core dependencies, dev dependencies, and console entrypoint.
- `mycodeagent = app.cli:main` or an equivalent thin entrypoint.
- One file is authoritative for dependencies; do not manually maintain two divergent lists.
- Editable install and `uv run mycodeagent --help` work from a fresh environment.

## Steps

1. Write a packaging smoke test that parses `pyproject.toml` and verifies the console script.
2. Add the smallest PEP 621 configuration that packages the existing modules and prompts.
3. Define `dev` extras/tool group for pytest and Ruff; do not add a build framework beyond the chosen backend.
4. Generate the lock file using uv.
5. Test `uv sync --extra dev`, `uv run mycodeagent --help`, and an editable install in a temporary venv.
6. Update only the README installation/launch commands in this task.

## Acceptance

- A clean checkout can be installed without first creating requirements files manually.
- No package import depends on the checkout directory name.
- Commit: `build(M1-03): package mycodeagent console command`.
