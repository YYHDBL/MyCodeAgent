# R1-03 Make Import Ordering Explicit

**Goal:** Remove the final global E402 suppression while preserving executable
and test bootstrap behavior.

**Files:**

- Modify: `app/cli.py:14-37`
- Modify: `runtime/host.py:1-43`
- Modify: `tests/conftest.py`
- Modify: `tests/runtime/test_context_compaction.py`
- Modify: `tests/runtime/test_context_engine.py`
- Modify: `pyproject.toml`
- Inspect/possibly narrowly configure: `demo/harness_portfolio.py`
- Modify: closeout `PROGRESS.md`

## Steps

1. Capture the 49-finding E402 baseline:

   ```bash
   uv run ruff check . --select E402 --output-format concise
   ```

2. In `runtime/host.py`, remove its redundant module-level `load_env()` call
   and import; configuration/bootstrap already owns environment loading. Move
   all remaining imports to a normal top-level block.

3. In `app/cli.py`, treat Rich and prompt-toolkit as required installed
   dependencies. Remove the import-time try/exit wrapper and keep imports at the
   top. Preserve concise CLI error handling in `main`, not during module import.

4. Move mid-file test imports to the top of their modules. For
   `tests/conftest.py` and the standalone demo bootstrap, prefer a package-safe
   import. If path injection is structurally unavoidable, use a narrow
   `per-file-ignores` entry with a comment; never ignore E402 globally or for
   stable packages.

5. Remove E402 from the global ignore and run:

   ```bash
   uv run ruff check app core runtime tools extensions prompts utils --select E402
   uv run ruff check .
   uv run pytest -q tests/test_cli_one_shot.py tests/test_cli_project_root.py \
     tests/runtime/test_context_compaction.py tests/runtime/test_context_engine.py \
     tests/scenarios/test_phase9_portfolio_demos.py
   uv run pytest -q
   git diff --check
   ```

6. Update progress and commit:

   ```bash
   git commit -am "chore(R1-03): make import ordering explicit"
   ```

## Acceptance

- Stable packages have zero E402 findings.
- No broad lint ignore remains.
- CLI import/help, context tests, demo scenarios, and full tests pass.
