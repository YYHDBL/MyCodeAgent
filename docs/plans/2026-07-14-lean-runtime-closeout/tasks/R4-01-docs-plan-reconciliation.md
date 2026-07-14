# R4-01 Reconcile Plans and Active Documentation

**Goal:** Make the original lean-runtime plan, closeout plan, active docs, and
actual runtime behavior tell one consistent story.

**Files:**

- Modify: `docs/plans/2026-07-12-lean-runtime/03_MILESTONES.md`
- Modify: `docs/plans/2026-07-12-lean-runtime/05_TASK_GRAPH.md`
- Modify: `docs/plans/2026-07-12-lean-runtime/06_ACCEPTANCE_CRITERIA.md`
- Modify: `docs/plans/2026-07-12-lean-runtime/FINAL_REPORT.md`
- Modify as needed: `README.md`, `docs/HARNESS.md`
- Modify: closeout `PROGRESS.md`, `DECISIONS.md`

## Steps

1. Compare active behavior and docs:

   ```bash
   uv run mycodeagent --help
   rg -n "verification|summary|JSONL|runtime\.evals|HTML|14,000|Ruff|F821|M6" \
     README.md docs/HARNESS.md docs/plans/2026-07-12-lean-runtime \
     docs/plans/2026-07-14-lean-runtime-closeout
   ```

2. Add M6-01 and M6-02 to the original milestones/task graph as completed
   remediation steps. Point from that plan to this closeout plan for the final
   unresolved work instead of rewriting historical task evidence.

3. Correct trace wording everywhere:

   - JSONL and `session_summary` metrics are retained;
   - renderer, generic evaluator, and compatibility protocol are removed.

4. Correct lint wording: normal Ruff now enforces undefined names and basic
   dead-code rules. Do not claim type checking or broader static guarantees that
   are not configured.

5. Update the original final report with current test counts, code lines,
   verifier status, and a link to the closeout final report. It must remain
   “not approved” until R4-02 passes.

6. Run:

   ```bash
   uv run pytest -q tests/test_tool_surface_docs.py tests/test_maintenance_boundaries.py \
     tests/test_cli_one_shot.py tests/test_lean_defaults.py
   uv run mycodeagent --help
   uv run ruff check .
   git diff --check
   ```

7. Review for active/historical ambiguity, update progress, and commit:

   ```bash
   git commit -am "docs(R4-01): reconcile lean runtime plans"
   ```

## Acceptance

- M6 and closeout are represented in the source-of-truth plan chain.
- Trace, verifier, lint, defaults, metrics, and removed scope match behavior.
- No historical document is rewritten to pretend an earlier failure passed.
