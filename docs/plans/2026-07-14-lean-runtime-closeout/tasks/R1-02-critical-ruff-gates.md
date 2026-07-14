# R1-02 Enforce Critical Ruff Gates

**Goal:** Ensure undefined names and basic dead code cannot pass CI through a
global ignore.

**Files:**

- Modify: `pyproject.toml:49-52`
- Modify as findings require: `core/env.py`,
  `prompts/agents_prompts/subagent_summary_prompt.py`, `runtime/completion.py`,
  `runtime/host.py`, `tools/builtin/bash.py`, `tools/builtin/read_file.py`,
  `tools/builtin/todo_write.py`, `tools/registry.py`
- Modify: closeout `PROGRESS.md`

## Steps

1. Remove `E722`, `F401`, `F541`, `F821`, and `F841` from the global ignore.
   Leave E402 for R1-03 only.

2. Run the focused rules and capture RED:

   ```bash
   uv run ruff check . --select E722,F401,F541,F821,F841
   ```

3. Make mechanical, behavior-neutral fixes:

   - delete unused imports and the unused `todo_id` assignment;
   - make the prompt re-export explicit with `__all__` or import-as-self;
   - replace placeholder-free f-strings with string literals;
   - retain imports only when they express an actual public export.

4. Run:

   ```bash
   uv run ruff check . --select E722,F401,F541,F821,F841
   uv run ruff check .
   uv run pytest -q tests/test_todo_write_tool.py tests/test_protocol_compliance.py \
     tests/test_app_bootstrap.py tests/test_lean_defaults.py
   uv run pytest -q
   git diff --check
   ```

5. Confirm the Ruff configuration contains no global suppression for these
   five rules. Update progress and commit:

   ```bash
   git commit -am "chore(R1-02): enforce critical Ruff rules"
   ```

## Acceptance

- Both focused and normal Ruff commands exit 0.
- No behavior assertion changes merely to accommodate cleanup.
- `F821` remains enforced in CI through the normal Ruff command.
