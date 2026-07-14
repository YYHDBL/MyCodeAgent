# M5-02 Documentation, CI, and Release Gate Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:verification-before-completion`.

**Goal:** Align public documentation and automated quality gates with the lean runtime, then prove the final goal state.

**Architecture:** Treat README/HARNESS/AGENT as the current documentation surface and CI as the executable form of the final acceptance matrix.

**Tech Stack:** Markdown, GitHub Actions, uv, pytest, Ruff, shell metrics.

**Dependencies:** M5-01.

**Files:**

- Rewrite: `README.md`
- Rewrite: `AGENT.md`
- Rewrite: `docs/HARNESS.md`
- Update/delete/archive labels for stale `docs/HARNESS_*`, tool design docs, portfolio docs, and old roadmap/task breakdown
- Create: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Create: `docs/plans/2026-07-12-lean-runtime/FINAL_REPORT.md`
- Modify: `docs/plans/2026-07-12-lean-runtime/PROGRESS.md`

## Documentation Contract

- README answers: what it is, why it exists, install, interactive use, one-shot use, resume, permissions, extensions, tests, non-goals.
- HARNESS explains the current execution flow and boundaries in one concise document.
- AGENT contains only durable contributor instructions and exact verification commands.
- Historical documents are removed or clearly labeled historical; they must not compete with current docs.
- No test-count or feature claim is written without a reproducible command.

## CI Contract

- Supported Python versions are explicit.
- Core job: install core/dev, Ruff, full deterministic core tests.
- Optional MCP job: install MCP extra and run MCP tests.
- A metrics check reports stable production LOC and tool count; it fails only on the agreed budgets.

## Steps

1. Run every acceptance command in `06_ACCEPTANCE_CRITERIA.md` and fix only defects within the approved goal.
2. Write CI and run its commands locally.
3. Rewrite docs from current behavior, not from old roadmap language.
4. Produce `FINAL_REPORT.md` with baseline/final metrics, removed scope, dependency/tool counts, test evidence, and known limitations.
5. Run link/path checks, `uv run ruff check .`, `uv run pytest -q`, CLI smoke tests, and metrics gates.
6. Review the final diff for user-owned changes and unrelated files.

## Acceptance

- Every acceptance row is PASS or contains an exact external blocker approved by the user.
- Stable production Python is ≤14,000 lines and required dependencies ≤5.
- Commit: `docs(M5-02): publish lean runtime release evidence`.
