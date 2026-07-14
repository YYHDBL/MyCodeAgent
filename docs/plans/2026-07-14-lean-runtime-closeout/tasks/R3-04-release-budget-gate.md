# R3-04 Pass the Unchanged Release Budget

**Goal:** Prove that first-principles deduplication, not feature deletion or
metric manipulation, closes Q-05.

**Files:**

- Modify: closeout `PROGRESS.md`, `DECISIONS.md`
- No production file by default

## Steps

1. Inspect metric integrity before running it:

   ```bash
   git diff feature/skill-evolution...HEAD -- scripts/check_release_metrics.py
   rg -n "MAX_STABLE_PRODUCTION_LINES|STABLE_SOURCE_ROOTS|MAX_STABLE_TOOLS" scripts/check_release_metrics.py
   ```

   Verify the threshold remains 14,000, source roots remain unchanged, and no
   new exclusion was introduced.

2. Run:

   ```bash
   uv run python scripts/check_release_metrics.py
   ```

   Required: exit 0, production lines ≤14,000, tool count 7, exact expected
   tool names.

3. If the metric still fails, stop production edits and record:

   - exact remaining excess;
   - line deltas for `core/llm.py`, `runtime/subagents.py`, and R1 cleanup;
   - why each retained large subsystem is necessary;
   - a separately scoped behavior-preserving duplicate within the already
     approved R3 surfaces.

   Do not remove a capability or change metric code. Resume only after the goal
   runner reviews the scoped proposal against `01_GOAL.md`.

4. Once metrics pass, run the R3 milestone gate:

   ```bash
   uv run ruff check .
   uv run ruff check . --select E722,F401,F541,F821,F841
   uv run ruff check app core runtime tools extensions prompts utils --select E402
   uv run pytest -q
   uv run pytest -q tests/scenarios
   uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
   uv lock --check
   git diff --check
   ```

5. Record before/after metrics and commit evidence:

   ```bash
   git commit -am "docs(R3-04): record passing release budget"
   ```

## Acceptance

- Metric command exits 0 without metric-code changes.
- Full R3 milestone gate passes.
- No retained product capability was removed for line count.
