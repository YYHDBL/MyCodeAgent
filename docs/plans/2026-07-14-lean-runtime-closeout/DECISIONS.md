# Closeout Decisions

## C-001: Use the existing JSONL session summary as the summary-metrics contract

- Context: the original goal retains lightweight JSONL tracing and summary
  metrics. `TraceLogger.finalize()` already appends a `session_summary` row with
  steps, tools, and token usage, while M6-02 removed an unused generic evaluator.
- Decision: strengthen the existing JSONL contract and correct documentation;
  do not restore `runtime.evals`, HTML reports, or a second summary subsystem.
- Consequence: retained behavior stays minimal and the earlier audit ambiguity
  is resolved with executable evidence.

## C-002: End with an integration handoff, not an automatic merge

- Context: the original worktree has six uncommitted user changes; four are in
  a feature intentionally deleted by the lean branch.
- Decision: prepare exact integration evidence and wait for explicit user choice.
- Consequence: the closeout can be release-ready without risking user work.

## C-003: Apply strict Ruff cleanup to every reported path

- Context: R1-02's required repository-wide strict Ruff command reported 50
  findings. The initial task file named the production findings but the same
  command also reported unused test/auxiliary imports and two bare fallback
  handlers.
- Decision: remove only the reported unused imports, unused assignment,
  placeholder-free f-strings, and bare `except` clauses in the exact reported
  files. Test assertions and the ordinary `Exception`/JSON fallback remain
  unchanged; replacing bare `except` with `except Exception` deliberately no
  longer catches `KeyboardInterrupt` or `SystemExit`. No global or per-file
  suppression is added.
- Consequence: the strict all-repository gate can pass honestly without
  changing product behavior or weakening lint configuration.

## C-004: Replace the deleted R1-02 focused protocol path with live coverage

- Context: R1-02's prescribed focused command names
  `tests/test_protocol_compliance.py`, which commit `08480a8`
  (`test(M5-01): center suite on contracts and scenarios`) deleted. Its model
  envelope checks moved to `tests/contracts/tool_results.py` and the existing
  tool contract tests.
- Decision: do not restore or recreate the obsolete test. Run the live task
  tests (`tests/test_todo_write_tool.py`, `tests/test_app_bootstrap.py`, and
  `tests/test_lean_defaults.py`) plus the migrated contract coverage in
  `tests/contracts/test_tool_result_contracts.py`, followed by the required
  full suite as the reproducible R1-02 focused/regression evidence.
- Consequence: R1-02 proves the current contract surface without inventing a
  duplicate compatibility test; R4-01 owns future plan-text reconciliation.

## C-005: Provider resolution uses declared names and URLs, not opaque key formats

- Context: `HelloAgentsLLM` previously inferred selected providers from opaque
  API-key prefixes, suffixes, and local-port patterns while separately loading
  `.env` values into a private cache. Those guesses are not documented user
  behavior and make provider selection and configuration precedence hard to
  reason about.
- Decision: retain explicit provider names, declared provider aliases, and
  known provider URL markers as data-driven conveniences. Remove opaque
  API-key-format and port-only inference. `auto` remains the generic
  OpenAI-compatible route using `LLM_*`; configuration precedence is explicit
  constructor/CLI values, then process environment (with `.env` filling only
  missing process values through `core.env.load_env`), then provider defaults.
- Consequence: users who relied solely on an undocumented key-shape or generic
  local-port guess must set `LLM_PROVIDER` or pass `--provider`; documented
  provider credentials, endpoint aliases, default models, Kimi temperature,
  and MiniMax request behavior are retained.

## C-006: User-approved one-release stable-LOC budget exception

- Context: the unmodified release command `uv run python
  scripts/check_release_metrics.py` on `lean-runtime-20260712` exits 1 with
  `stable_production_python_lines=14095`, 95 lines above its unchanged 14,000
  cap. Its other reported contract values remain `stable_tool_count=7` and
  `stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite`.
- Decision: the user explicitly authorizes this 14,095 stable-production-LOC
  result as an exception for this release only. This is not a change to the
  metric, its threshold, source roots, exclusions, or tool cap, and it is not a
  claim that the command itself passes. All other Q-06 requirements remain
  unwaived: the metric script must remain unchanged, the exact seven-tool
  contract must hold, and required dependencies must remain at most five
  (current `pyproject.toml` declares four: Pydantic, python-dotenv,
  prompt-toolkit, and Rich).
- Consequence: R3-04 may record its evidence as complete under this narrowly
  scoped exception, with the raw exit-1 result preserved. The final report must
  distinguish approved release acceptance from a normal metric pass; no future
  release inherits this exception, and no retained capability may be removed to
  manufacture a lower count.

## C-007: Reconcile the original plan without rewriting historical evidence

- Context: the original M5 report accurately records its then-current 14,243
  line failure. M6 subsequently removed optional project memory and rendered
  trace evaluation, and this closeout repaired verifier bootstrap, lint gates,
  trace-contract wording, and measured model duplication. Leaving the original
  milestones, graph, acceptance wording, and report unlinked would make active
  documentation contradict the current branch.
- Decision: retain the historical M5 and M6 evidence in place; add completed
  M6 remediation and the R0–R5 closeout chain to the original plan, state the
  current strict-Ruff policy and actual defaults, and point current approval
  status to the closeout report. Cross-reference C-006 exactly as an approved
  one-release acceptance exception while preserving the raw 14,095-line
  exit-1 metric fact.
- Consequence: the original final report remains **not approved** pending
  R4-02. R4-02's closeout `FINAL_REPORT.md` is the only final approval record;
  neither plan treats the metric command as passing or changes its threshold.

## C-008: Raise the stable production budget to 15,000 lines

- Context: the completed runtime contains 14,095 stable production lines. The
  former 14,000-line threshold failed by 95 lines even though all functional,
  lint, scenario, dependency, and seven-tool gates passed. The user explicitly
  stated that the line count may be relaxed and asked for the branch to be
  fixed and published.
- Decision: set `MAX_STABLE_PRODUCTION_LINES` to 15,000, retain the existing
  source roots and exclusions, and add a regression proving both the approved
  policy value and that the current release tree passes the enforcing command.
  This supersedes C-006's one-release exception with a normal, reusable gate.
- Consequence: 14,095 lines pass with 905 lines of headroom. The tool cap stays
  seven, required dependencies stay capped at five, and the metric still exits
  nonzero if stable production code exceeds 15,000 lines.
