# R2-01 Reconcile the JSONL Summary Contract

**Goal:** Prove that lightweight summary metrics remain in JSONL and make the
documentation distinguish them from the deleted evaluator/reporting system.

**Files:**

- Test/modify only if coverage is incomplete: `tests/test_trace_logger.py`
- Modify: `docs/plans/2026-07-12-lean-runtime/01_GOAL.md`
- Modify: `docs/plans/2026-07-12-lean-runtime/FINAL_REPORT.md`
- Modify: `docs/HARNESS.md` and/or README only if their wording is ambiguous
- Modify: closeout `PROGRESS.md`

## Steps

1. Run the existing contract:

   ```bash
   uv run pytest -q tests/test_trace_logger.py::TestTraceLoggerEnabled::test_finalize_writes_session_summary
   ```

   It must prove the final JSONL row is `session_summary` and contains `steps`,
   `tools_used`, and accumulated token totals. If all fields are already
   asserted, do not add a duplicate test.

2. Run the JSONL-only contract:

   ```bash
   uv run pytest -q tests/test_lean_defaults.py::test_trace_logger_writes_only_jsonl \
     tests/extensions/test_tracing_extension.py tests/runtime/test_prompt_assembly_trace.py
   ```

3. Update documentation with this precise distinction:

   - retained: append-only JSONL facts plus the final `session_summary` metrics;
   - removed: HTML renderer/config, unused trace protocol declarations, and the
     generic product-side `runtime.evals` analysis API.

4. Prove the removed surface remains absent:

   ```bash
   test ! -e runtime/evals.py
   test ! -e extensions/tracing/protocol.py
   rg -n "trace_html_enabled|runtime\.evals|summarize_trace" app core runtime tools extensions prompts
   ```

   Expected: files absent and stable-source scan empty.

5. Run trace/scenario regression, diff check, update progress, and commit:

   ```bash
   uv run pytest -q tests/test_trace_logger.py tests/extensions/test_tracing_extension.py \
     tests/runtime/test_transcript.py tests/scenarios
   uv run ruff check .
   git diff --check
   git commit -am "docs(R2-01): clarify JSONL summary contract"
   ```

## Acceptance

- No new production summary subsystem is added.
- JSONL summary metrics are executable, documented behavior.
- Removed renderer/evaluator APIs remain removed.
