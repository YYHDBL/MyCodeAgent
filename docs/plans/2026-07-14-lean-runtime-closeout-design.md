# Lean Runtime Closeout Design

## Context

The lean-runtime implementation is functionally close to its target, but it is
not release-ready. Fresh audit evidence found one enabled-path startup crash,
an overly broad Ruff ignore list that concealed the crash, a 243-line release
budget failure, duplicated model/provider logic, stale plan metadata, and an
unsafe integration boundary around six user-owned changes in the original
worktree.

This closeout is deliberately narrower than another architecture phase. It
must repair the broken capability and quality gate, simplify existing code
without deleting retained behavior, prove the already-present lightweight
trace summary contract, and leave a release-ready local branch plus a safe
integration handoff.

## Considered Approaches

### A. Patch only the startup crash

Import `SubagentCompletionVerifier`, add one test, and leave the rest alone.
This is low risk but does not fix the lint gate, release metric, duplicated
provider logic, or delivery state. It cannot satisfy the existing goal.

### B. Targeted closeout through simplification — selected

Fix correctness first, make static checks capable of detecting the same class
of bug, preserve JSONL trace summaries as a tested contract, and recover the
remaining line budget from duplicated provider/request/response-normalization
logic. This preserves product behavior while aligning implementation with the
data-driven target architecture.

### C. Merge immediately and clean up in the original worktree

This would collide with six user-owned modifications, including files deleted
by the lean branch. It is unsafe and is explicitly rejected. The closeout ends
with an integration handoff; it does not mutate, stash, commit, or discard the
original worktree.

## Design

The work proceeds through four product layers and one delivery layer:

1. **Correctness and gates.** Cover enabled verification-agent bootstrap, fix
   the undefined symbol, remove broad suppression of correctness rules, and
   clean the concrete findings exposed by strict Ruff runs.
2. **Trace contract reconciliation.** Keep JSONL as the sole trace artifact.
   Treat the existing `session_summary` JSONL event as the required lightweight
   summary metrics contract; do not restore the deleted HTML renderer,
   protocol module, or generic `runtime.evals` API.
3. **Measured simplification.** Replace repeated provider branches with one
   data table, remove heuristic or duplicated configuration paths that are not
   part of the user promise, share request/retry construction, and make
   subagents use the canonical response-normalization helpers in `core.llm`.
4. **Release proof.** Run the complete deterministic, scenario, MCP, lint,
   packaging, and metrics gates. The 15,000-line definition, source roots,
   exclusions, dependency cap, and tool cap must not be weakened.
5. **Safe delivery.** Record the exact commits and commands needed to integrate
   the closeout branch. Do not perform the merge while the original worktree
   contains unresolved user changes.

## Non-Goals

- No new tools, UI modes, provider framework, plugin system, memory system, or
  tracing renderer.
- No removal of transcript recovery, JSONL tracing, Task, Skills, MCP, the
  seven-tool contract, or deterministic completion behavior.
- No artificial metric pass by changing the threshold, exclusions, source
  roots, or counting implementation.
- No splitting `RuntimeRunner` merely to satisfy its advisory line target.
- No push, merge, rebase, stash, reset, or mutation of the original dirty
  worktree.

## Verification Strategy

Every behavior change uses a failing regression first. Pure refactors run the
relevant characterization tests before and after, with a diff review proving
that public behavior and configuration precedence remain intentional. Each
task is one commit. Milestone gates run the full suite, strict lint commands,
and the release metric. Final release approval requires every criterion in the
closeout acceptance matrix to pass with fresh command output.
