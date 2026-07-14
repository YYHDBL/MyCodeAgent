# Closeout Milestones

## R0 — Baseline and Protection

Task: `R0-01`

Gate:

- Implementation worktree and branch are correct and clean.
- Original six modified paths are recorded and unchanged.
- Full tests, scenarios, MCP tests, Ruff, strict ignored-rule scan, CLI help,
  and release metrics have fresh baseline output.
- Verification-agent bootstrap failure is reproduced without network access.

## R1 — Correctness and Honest Static Gates

Tasks: `R1-01`, `R1-02`, `R1-03`

Gate:

- Enabled verification-agent bootstrap succeeds.
- Default bootstrap still creates no verifier.
- `F821`, `E722`, `F401`, `F541`, and `F841` are not globally ignored.
- Stable packages pass `E402`; any unavoidable script/test exception is narrow,
  documented, and never applies to product packages.
- Full deterministic tests pass.

## R2 — Trace Summary Contract

Task: `R2-01`

Gate:

- JSONL remains the only trace output.
- Existing `session_summary` metrics are covered by a focused contract.
- Documentation no longer implies that all trace summaries were removed.
- No HTML renderer, trace protocol compatibility module, or `runtime.evals`
  API is restored.

## R3 — First-Principles Simplification

Tasks: `R3-01`, `R3-02`, `R3-03`, `R3-04`

Gate:

- Provider aliases/defaults/credential keys are data, not repeated branches.
- Environment loading has one owner and documented precedence.
- Model request construction and retry behavior have one implementation.
- Main agent and subagents share canonical response normalization.
- Release metrics pass without changing their definition.

## R4 — Release Evidence

Tasks: `R4-01`, `R4-02`

Gate:

- Original plan graph, decisions, progress, README/HARNESS, and final report
  agree with actual behavior.
- Every acceptance command has been run fresh and passed.
- Implementation worktree is clean after the final evidence commit.

## R5 — Safe Integration Handoff

Task: `R5-01`

Gate:

- Integration base, closeout head, commit list, original dirty paths, expected
  delete/modify conflicts, and exact user choices are documented.
- No merge, push, reset, stash, or original-worktree mutation occurred.
