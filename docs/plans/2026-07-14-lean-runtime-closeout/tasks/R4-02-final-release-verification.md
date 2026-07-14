# R4-02 Produce Final Release Evidence

**Goal:** Replace the closeout final-report template with fresh evidence for
every acceptance criterion.

**Files:**

- Modify: `docs/plans/2026-07-14-lean-runtime-closeout/FINAL_REPORT.md`
- Modify: `docs/plans/2026-07-14-lean-runtime-closeout/PROGRESS.md`

## Steps

1. Confirm a clean pre-verification state and record HEAD:

   ```bash
   git status --short --branch
   git log --oneline --decorate -20
   git diff --check
   ```

2. Run every deterministic gate fresh:

   ```bash
   uv sync --locked --extra dev --extra mcp
   uv run pytest -q
   uv run ruff check .
   uv run ruff check . --select E722,F401,F541,F821,F841
   uv run ruff check app core runtime tools extensions prompts utils --select E402
   uv run pytest -q tests/scenarios
   uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
   uv lock --check
   uv run python scripts/check_release_metrics.py
   rg 'experimental\.teams|skill_evolution|Team[A-Z]' app core runtime tools extensions prompts
   ```

   The final `rg` is expected to produce no matches; record its exit 1 as the
   successful “no match” result, not as a failed shell gate.

3. Re-run the verifier integration test and trace summary contract explicitly:

   ```bash
   uv run pytest -q tests/test_app_bootstrap.py -k verification
   uv run pytest -q tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary
   ```

4. Perform a fresh installed-command smoke:

   ```bash
   tmp_dir="$(mktemp -d)"
   uv venv "$tmp_dir/venv" --python 3.12
   uv pip install --python "$tmp_dir/venv/bin/python" -e .
   git -C "$tmp_dir" init -q
   (cd "$tmp_dir" && time "$tmp_dir/venv/bin/mycodeagent" --help)
   ```

   Expected: exit 0 under 3 seconds. Remove the temporary directory afterward.

5. Recompute the original protected-worktree status/diff hash using the exact
   R0 command and compare it with `BASELINE.md`. Any difference blocks approval.

6. Replace `FINAL_REPORT.md` with:

   - branch/head and commit list;
   - every acceptance ID and exact command/result;
   - baseline/final production, test, and docs lines;
   - required and optional dependencies;
   - exact seven tool names;
   - help timing;
   - removed/retained trace behavior;
   - original-worktree hash comparison;
   - any failed criterion marked FAIL with exact evidence.

7. Only when all non-integration criteria pass, change report status to
   `RELEASE-READY BRANCH — NOT YET INTEGRATED`, update progress, and commit:

   ```bash
   git add docs/plans/2026-07-14-lean-runtime-closeout
   git commit -m "docs(R4-02): publish closeout release evidence"
   ```

## Acceptance

- Every command was run during this task, not copied from older progress.
- The report has no PASS without evidence.
- Release-ready does not claim merged or pushed.
