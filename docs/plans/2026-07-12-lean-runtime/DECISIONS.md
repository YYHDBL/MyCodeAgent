# Lean Runtime Decisions

## D-001: Record task commits without self-referential hashes

- Context: Embedding a commit's exact hash in a file changes that commit's content and therefore changes its hash. Repeated amendments to make a progress record self-reference the resulting commit cannot converge.
- Decision: Progress records name the completed implementation commit. Later record-only revisions are located with `git log --oneline -- docs/plans/2026-07-12-lean-runtime/` rather than embedded as self-references.
- Alternatives rejected: Repeatedly amend a record with its new hash, because each amendment produces another hash; leave the implementation commit ambiguous, because the task record must identify it.
- Consequences: M0-02 names implementation commit `d996b98ebf9658478e0ab37505c183fbf2a96dba`; this decision documents any later docs-only record correction without changing product behavior.

## D-002: Inject the selected project root into trace creation

- Context: M1-01 review found that `RuntimeComponentFactory.initialize_persistence()` calls the zero-argument trace factory. Its `memory/traces` default is relative to the invocation directory, while transcript creation correctly uses `host.project_root`, leaking trace artifacts outside an explicit `--cwd` target.
- Decision: Pass the selected `host.project_root / "memory" / "traces"` path at the factory boundary when tracing is enabled.
- Alternatives rejected: Change the process working directory, because it would globally alter CLI and tool behavior; make trace configuration globally infer a project, because it has no selected-project dependency; leave the trace path relative, because it violates the single project boundary.
- Consequences: M1-01 adds a deterministic target-root artifact regression and changes only trace-factory argument propagation; environment `TRACE_DIR` override behavior remains owned by the tracing extension.

## D-003: Separate package resources and confine artifact-directory overrides

- Context: The selected target project is intentionally unrelated to the installed package, so built-in L1 and tool-contract resources cannot be read from the target. Separately, absolute `TRACE_DIR` and `TOOL_OUTPUT_DIR` environment values can direct runtime artifacts outside that target.
- Decision: Inject a package resource root only for built-in prompt resources, keep project rules at the selected target root, and normalize artifact-directory overrides beneath the selected target before any write.
- Alternatives rejected: Reuse the source checkout as the target root, because that recreates M1-01's boundary defect; silently honor external absolute artifact paths, because that bypasses project confinement; remove environment overrides entirely, because scoped relative overrides remain useful configuration.
- Consequences: M1-01 changes only prompt-resource lookup and trace/tool-output path resolution, adds explicit external-path rejection coverage, and preserves target-root propagation for tools, transcripts, memory, and project rules.

## D-004: Make PEP 621 metadata the only dependency authority

- Context: Hand-maintained runtime and development requirement files could diverge and did not define an installable console command.
- Decision: Define project metadata, runtime dependencies, the `dev` extra, and `mycodeagent = app.cli:main` in `pyproject.toml`; resolve `uv.lock` mechanically; retain `requirements*.txt` only as `uv export` compatibility artifacts.
- Alternatives rejected: Continue hand-editing two requirements files, because it leaves two dependency truths; remove compatibility artifacts without a migration path, because downstream pip-oriented users may still consume them.
- Consequences: Normal installation is `uv sync --extra dev` or `pip install -e ".[dev]"`; package changes require regenerating the lock and exports. M2-02 will split MCP/AnyIO into an optional extra.

## D-005: Package all current CLI import roots until research removal

- Context: M1's explicit package discovery initially omitted `experimental`, but the current CLI/UI import graph still reaches its Teams modules. The installed console command consequently failed before argument handling.
- Decision: Include `experimental*` in the M1 package discovery so the packaged behavior matches the current source tree.
- Alternatives rejected: Add a packaging-only compatibility stub, because it would preserve a no-op research layer; silently omit current CLI behavior, because editable installs must be usable.
- Consequences: M2-03 must remove the Teams imports and then remove `experimental*` from package discovery in the same task; it is not a stable-product commitment.

## D-006: Keep packaging tests compatible with the declared Python floor

- Context: M1-03 declares `requires-python = ">=3.10"`, but its new metadata tests imported the Python 3.11-only `tomllib` module directly.
- Decision: Use the standard `try: import tomllib` / `except ImportError: import tomli as tomllib` test import and declare `tomli>=2.0.0; python_version < '3.11'` in the authoritative `dev` extra.
- Alternatives rejected: Raise the supported Python floor without a product requirement, because it would contradict the current documented contract; rely on pytest's transitive `tomli` dependency, because transitive availability is not an explicit test-environment contract.
- Consequences: The lock/export records the conditional dependency and M1-03 has an isolated Python 3.10 test proof. The runtime itself does not require `tomli`.

## D-007: Inject skill refresh policy instead of reading it per tool call

- Context: `Config.skills_refresh_on_call` establishes the M2-01 default as false, but `tools/builtin/skill.py` separately reads `SKILLS_REFRESH_ON_CALL` with a true default for every invocation. This bypasses the canonical configuration boundary and rescans project skills on every Skill-tool call.
- Decision: Add a single injected `refresh_on_call` policy to `SkillTool` and pass the resolved Config value from `CodeAgent`; default standalone construction to false.
- Alternatives rejected: Keep the duplicate environment lookup, because it contradicts both Config ownership and the lean default; disable skills entirely, because local skills remain a supported lazy capability.
- Consequences: M2-01 minimally expands to `tools/builtin/skill.py` and a lean-defaults behavior regression; explicit opt-in retains refresh behavior.

## D-008: Keep default traces JSONL-only

- Context: the enabled default trace logger opens and writes an HTML audit report for every event. That report generation is not required for transcript recovery or lightweight local tracing and violates the M2-01 hot-path budget.
- Decision: Make HTML trace output an explicit Config-backed opt-in while retaining JSONL traces as the enabled core default.
- Alternatives rejected: Disable tracing by default, because inspectable lightweight JSONL traces are a retained core capability; retain unconditional HTML output, because it adds a second hot-path renderer without serving the default runtime.
- Consequences: M2-01 minimally expands Config/host trace wiring and `extensions/tracing/logger.py`; direct trace construction defaults to JSONL-only and explicit callers can still request HTML output.

## D-009: Defer subagent and skills construction until their explicit tool paths

- Context: M2-01's initial lean-default implementation still imported and constructed `SubagentLauncher` at every `CodeAgent` startup, and an enabled no-skill project imported the skills extension, constructed a loader, scanned it, and registered `SkillTool`. Both actions contradict the minimal default path even though the optional Task and Skill capabilities were never used.
- Decision: Keep `TaskTool` available, but construct `SubagentLauncher` only when Task actually delegates. Do not import the skills extension, build its loader, scan project skills, or register `SkillTool` unless an explicit skills capability is enabled or discovered.
- Alternatives rejected: Eager construction behind an unused tool because it leaves optional work on the startup path; removing Task or skills because both remain supported capabilities; a no-op compatibility layer because it would preserve removed startup work without user value.
- Consequences: M2-01 expands narrowly into runtime factory/host wiring and regression coverage. Future Task delegation retains its current behavior after first use, while no-skill projects keep the default startup import and registration surface lean.

## D-010: Use a standard-library OpenAI-compatible transport in the core runtime

- Context: After moving direct `mcp` and `anyio` requirements into an `mcp` extra, `uv sync --extra dev` still installed `anyio==4.14.1`. `uv tree --no-dev` traced it to the required `openai==2.45.0` SDK (and its `httpx` dependency). Isolated dry runs for OpenAI SDK versions `1.0.0`, `1.10.0`, `1.30.0`, and `1.55.3` each also resolved AnyIO, contradicting M2's literal core-install gate.
- Decision: Replace the core's official SDK dependency with a minimal standard-library transport that preserves the existing OpenAI-compatible chat-completions request, response, streaming, and error boundary. Keep the MCP SDK and AnyIO exclusively in `mycodeagent[mcp]`.
- Alternatives rejected: Treat transitive AnyIO as an acceptance exception, because M2 explicitly requires a core install without it; pin an older OpenAI SDK, because tested v1 releases still require AnyIO; retain the SDK and shadow imports in tests, because it would not prove the install invariant.
- Consequences: M2-02 expands into `core/llm.py` and focused transport tests. The core dependency list falls from five to four; the optional MCP extra remains the only route that installs MCP/AnyIO.

## D-011: Archive Agent Teams at the removal parent

- Context: `docs/research-archive.md` identified the earlier M2-01 commit `eb5986608593e810d82a57109d57570f69900f78` as the exact pre-removal state, but the M2-03 removal commit's actual parent is `f497b172c9bce8279d9a26eb69273e25db7392cf`.
- Decision: Point the research archive at the M2-03 parent and protect that exact reference with a deterministic maintenance-boundary assertion.
- Alternatives rejected: Retain the older M2-01 commit, because it omits the subsequent optional-MCP state that existed immediately before removal; preserve an in-tree experimental namespace, because the research archive is Git history rather than a shipped compatibility surface.
- Consequences: M2-03 removes `experimental/__init__.py` and `experimental*` package discovery, while `docs/research-archive.md` provides the reproducible historical inspection command.

## D-012: Route tool lifecycle through the runtime event boundary

- Context: M3-01's task contract requires tool lifecycle facts to share the unified event path, but `tools/orchestrator.py` directly calls `TranscriptRecorder.record_tool_lifecycle` outside the task file's initially listed files.
- Decision: Add the narrow event-sink dependency to `ToolOrchestrator` and emit its existing requested, started, completed, and failed lifecycle facts through the host's runtime event sink.
- Alternatives rejected: Leave lifecycle recording direct because it would preserve a second persistence path; move tool execution into the loop because it would violate the existing execution boundary and broaden M3-01.
- Consequences: M3-01 additionally changes `tools/orchestrator.py` and its focused behavior coverage; trace event names and transcript lifecycle payloads remain stable projections of the same fact.

## D-013: Keep the canonical runner's recovery and completion stages co-located

- Context: M3-02 removes the one-product composition factory, host-owned response parsing, and runner-owned event projection. The measured `runtime/host.py` falls from 691 to 482 lines, while `runtime/loop.py` falls from 1,080 to 1,018 lines after moving transition/checkpoint/prompt-schema projection into `runtime/events.py`. The remaining runner lines are the only state machine and retain model recovery budgets, transcript-visible transition and terminal reasons, tool-result history ordering, and deterministic completion-gate feedback.
- Decision: Accept the measured loop-size exception for M3-02 rather than split recovery, tool execution, or completion-gate control flow into a second runner or a one-caller stage abstraction. Retain one `RuntimeRunner` and direct composition builders; keep pure response parsing in `core.llm` and event serialization in `runtime.events`.
- Alternatives rejected: Force the 650-line target through a second runtime loop or stage-object graph, because it would obscure the required visible turn state machine; leave host parsing and a class factory in place, because they are duplicate composition/adapter layers; remove recovery or terminal facts, because they are observable resume and safety behavior.
- Consequences: M3-03 may remove the remaining legacy snapshot path, but must preserve this single-runner ownership. The exact measured exception and retained responsibilities are reviewable with `wc -l runtime/loop.py runtime/host.py` and the focused runner, transcript, completion, and scenario suites.

## D-014: Permit a one-way legacy snapshot import without retaining snapshot persistence

- Context: pre-M3-03 local sessions may contain `session-latest.json`, which duplicates transcript history and runtime cache state. Removing its reader outright would strand those sessions, while retaining its writer would violate transcript-only recovery.
- Decision: new sessions write no snapshot. A selected empty transcript may import one valid legacy snapshot into append-only message and checkpoint facts; once facts exist, the transcript wins and a snapshot cannot overwrite it. The compatibility parser is read-only and contains no snapshot save/build API.
- Alternatives rejected: keep `/save` writing a snapshot, because that leaves two durable truths; silently ignore legacy snapshots, because an inexpensive deterministic conversion preserves local continuity; merge a snapshot into a nonempty transcript, because it can overwrite or duplicate later durable work.
- Consequences: `/save` and automatic lifecycle messages report the existing durable transcript path, `/load` accepts a transcript or performs this one-time import, and legacy read-cache data is carried only as a transcript checkpoint runtime-state fact. Session memory is rebuilt from events on every resume.

## D-015: Share concrete project-confined file primitives before tool consolidation

- Context: Read and Edit each independently resolved project-relative paths, inspected binary files, compared file metadata, and wrote replacements. Maintaining those duplicate checks makes later tool consolidation risk diverging path-confinement and optimistic-write behavior.
- Decision: Introduce one small concrete `FileWorkspace`, not a filesystem service or backend interface. It rejects absolute, traversal, and symlink escapes; validates text files; captures `mtime_ns` and size snapshots; uses UTF-8 replacement fallback; and atomically replaces only a still-matching snapshot with a same-directory temporary file while preserving mode bits. Read and Edit retain their own response wording, pagination, diff, and parameter semantics.
- Alternatives rejected: Merge the file tools in M4-01, because the task graph reserves public-tool consolidation for later tasks; retain duplicated helpers, because that leaves the security boundary split; introduce a generic storage abstraction, because no second implementation or caller requires one.
- Consequences: M4-01 centralizes only the two selected consumers. Subsequent file-tool tasks can use the same tested boundary without inheriting tool-specific presentation code.

## D-016: Let Edit's create-content mode also perform full replacement

- Context: a one-tool mutation surface must replace a pre-existing empty file as well as create a new file. Requiring a non-empty unique anchor for every replacement would leave empty files dependent on the removed Write tool.
- Decision: `Edit.create_content` creates when the path is absent and fully replaces when it exists. The existing-file path requires the same Read mtime/size pair and exact pre-write snapshot as ordered edits; absent-path creation uses `FileWorkspace.atomic_create`, which links a fully fsynced same-directory temporary file without overwriting a concurrent creator.
- Alternatives rejected: Require full-content replacement through an `edits` anchor, because an empty file has no non-empty anchor; retain Write as an alias, because it would leave two model-visible mutation concepts; use `os.replace` for creation, because a concurrent creator could be silently overwritten.
- Consequences: `Edit` remains the only file-mutation schema. Creation, full replacement, ordered edit, conflict, dry-run, CRLF, overlap, duplicate-match, and rollback contracts are deterministic and independently covered.

## D-017: Remove obsolete mutation-tool documentation from the active surface

- Context: after M4-02 removed Write and MultiEdit from the product, active design documents, harness traces, portfolio records, and the UI icon table still advertised the deleted names.
- Decision: delete the standalone Write and MultiEdit design documents and update active documentation, generated traces, demo help, and UI aliases to the single `Edit` contract. Protect the boundary with a deterministic scan of active docs and UI, while excluding dated plans and the explicit research archive.
- Alternatives rejected: retain no-op names in the UI or docs, because they make removed product concepts appear supported; rewrite historical plan records, because they are evidence of the migration rather than active product documentation.
- Consequences: current users see only the unified mutation surface. Historical task plans remain available as dated migration evidence without participating in stable-product checks.

## D-018: Use Glob and Grep as the only stable discovery surface

- Context: `LS`, `ListFiles`, and `SearchFilesByNameTool` overlap with the retained Glob/Grep capabilities, but each carries a separate schema, prompt, registration path, and safety policy. The old Grep `include` option also describes the same candidate-path filter less directly than a glob field.
- Decision: `Glob` owns both immediate directory listing (no pattern) and recursive file discovery (a pattern). `Grep` owns text search with one optional `glob` candidate filter. Both resolve roots through `FileWorkspace`, return deterministically ordered bounded results, and omit hidden/build/dependency paths by default. Grep validates text candidates before passing explicit paths to ripgrep, then uses one Python fallback that is reported as a partial result.
- Alternatives rejected: Retain `LS`, old class/module imports, or parameter aliases, because aliases preserve an expanded stable surface without new behavior; let ripgrep decide binary handling, because it can emit text preceding a NUL byte for an explicitly passed file; keep separate traversal policies, because that risks drift at the project boundary.
- Consequences: `ListFiles`, `SearchFilesByNameTool`, their prompts/tests, and all stable registrations are deleted. Common listing, filename discovery, and content search remain available without Bash through `Glob` and `Grep` only.

## D-019: Keep tool results typed until the model boundary

- Context: every built-in tool encoded a nearly identical JSON envelope, then the registry, executor, orchestrator, and truncation path parsed or normalized that text before encoding it again for model history.
- Decision: use one frozen `ToolResult` transport for status, text, data, errors, stats, and context. Built-ins, the registry, executor, lifecycle trace projection, and observation budgeting exchange that object; `serialize_tool_result` is the sole model-envelope serializer. Truncation replaces a typed result and history accepts the already serialized observation.
- Alternatives rejected: retain JSON-string compatibility in the internal path, because it preserves the parse/normalize/re-encode loop; create abstract result interfaces, because one concrete transport has every current caller; move truncation back into history, because that reintroduces a second model-boundary path.
- Consequences: function registrations and test fixtures must return `ToolResult`; model-visible envelopes, error clarity, full-output artifacts, and budget metadata remain unchanged. Obsolete protocol and truncation test duplication is replaced by compact typed-contract coverage.

## D-020: Remove AskUser rather than retain an eighth stable tool

- Context: M4 quality review found that the default OpenAI schema exposed eight
  stable tools: `AskUser`, Bash, Edit, Glob, Grep, Read, Task, and TodoWrite.
  The goal limits the stable surface to seven or fewer, and an interactive
  question tool is not necessary for the retained single-agent coding harness.
- Decision: delete AskUser's implementation, prompt, registration, error code,
  permission special case, and tests. Keep the seven directly useful tool
  schemas without an alias or no-op compatibility path.
- Alternatives rejected: hide AskUser behind a default-off flag, because that
  would preserve an unnecessary stable implementation; retain it as an alias,
  because an alias still expands model-visible schema and product concepts;
  remove a retained file, search, execution, delegation, or planning tool,
  because each has an active single-agent harness role.
- Consequences: the default schema is deterministically Bash, Edit, Glob,
  Grep, Read, Task, and TodoWrite. Historical plans and baseline reports retain
  their dated references as migration evidence only.

## D-021: Exclude credentialed provider probes from deterministic pytest by default

- Context: M5 requires live-provider evaluations to remain separate from the deterministic contract and scenario suite. The project had no registered marker or default selection boundary, so a future credentialed test could silently become a core-CI dependency.
- Decision: register `credentialed` in pytest and set the default test selection to `not credentialed`. The one live-provider smoke test remains discoverable with `-m credentialed`, requires `RUN_CREDENTIALLED_EVALS=1`, and fails clearly if its explicit provider credentials are absent.
- Alternatives rejected: rely on documentation alone, because it does not prevent accidental collection in core CI; silently skip a live test with missing credentials after explicitly selecting it, because that can hide a misconfigured credentialed run; remove live-eval coverage entirely, because the separate opt-in path is useful release evidence.
- Consequences: ordinary `uv run pytest -q` remains deterministic and credentials-free, while release operators can intentionally run `uv run pytest -q -m credentialed` after setting the documented opt-in environment.

## D-022: Remove optional project memory rather than retain a dormant store

- Context: the release metric remained above the stable 14,000-line budget and
  the optional cross-session project-memory store duplicated durable concepts
  already represented by transcript facts and derived session memory.
- Decision: delete the store, tool, prompt, CLI/config flags, model-view
  injection, trace events, permission policy, and feature-specific tests
  without a compatibility alias. Keep only transcript recovery, compact
  checkpoints, and derived session memory.
- Alternatives rejected: retain it behind a default-off flag, because dormant
  production code still exceeds the budget and expands the product surface;
  convert it to a no-op alias, because that keeps an unsupported API visible;
  remove session memory too, because it remains a transcript-derived recovery
  aid with deterministic resume coverage.
- Consequences: default schema remains seven tools, JSONL traces have no
  project-memory branches, and resume/uncertain-action behavior continues to
  come solely from transcripts and checkpoints.

## D-023: Keep JSONL facts and remove rendered trace evaluation

- Context: the retained trace boundary already writes append-only JSONL facts
  and the runtime event sink already proves trace/transcript projection. The
  optional rendered trace path, configuration flag, frozen trace-protocol
  constants, and generic trace-summary API had no stable product consumer.
- Decision: retain the small JSONL logger and sanitizer only. Delete the
  renderer/configuration path, `runtime.evals`, and tracing protocol module;
  scenario and demo assertions read their own emitted facts directly.
- Alternatives rejected: retain an opt-in renderer or compatibility argument,
  because it preserves a removed product surface; retain an evaluation helper
  as a public runtime API, because no production caller needs it; delete JSONL
  tracing, because transcript/trace parity and inspectable diagnostics remain
  required behavior.
- Consequences: tracing remains on by default, creates one JSONL artifact per
  session, and has no renderer flag or report. Runtime-event parity tests own
  the durable behavior rather than a duplicate protocol declaration.
