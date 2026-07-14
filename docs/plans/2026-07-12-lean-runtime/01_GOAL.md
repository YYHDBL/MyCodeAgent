# MyCodeAgent Lean Runtime Goal

## Product Definition

MyCodeAgent is a local-first Python coding-agent harness that can be installed once and run against any project directory. It demonstrates the minimum reliable machinery around an LLM: one agent loop, bounded tool execution, project-root permissions, context projection, durable resume, deterministic completion checks, and inspectable traces.

It is not an enterprise platform, autonomous team framework, self-modifying skill laboratory, IDE, web application, or Claude Code clone.

## User Promise

A user can install MyCodeAgent, enter any repository, run an interactive or one-shot task, understand what the agent is doing, interrupt safely, resume later, and verify whether work was actually completed.

## First-Principles Invariants

1. **One loop:** `RuntimeRunner` remains the only stable agent loop.
2. **One project boundary:** every filesystem and shell action is resolved against the selected working project.
3. **One execution gate:** the model requests actions; the runtime authorizes and executes them.
4. **One recovery source:** an append-only transcript is the authoritative session recovery record.
5. **One model projection:** the model receives a bounded view; complete facts are not destructively compacted.
6. **Lean default:** starting the CLI does not launch MCP servers, verification agents, teams, or skill evolution.
7. **Optional means isolated:** optional systems do not affect imports, dependencies, startup, or tests of the core path.
8. **Evidence over claims:** completion requires commands, scenarios, or artifacts that prove the stated behavior.

## Capabilities to Keep

- OpenAI-compatible model adapter.
- Interactive CLI and one-shot CLI.
- `Read`, unified `Edit`, `Bash`, `Glob`, and `Grep`; `Todo` and restricted `Task` only if they still justify their cost.
- Input-level permission decisions and project-root enforcement.
- Tool-result budgeting and full-output persistence.
- Context budget, checkpoint compaction, and model view.
- Transcript-based resume.
- Lightweight, append-only JSONL tracing, including a final
  `session_summary` row with steps, tools used, and accumulated token totals.
- Deterministic completion gate.
- Skills and MCP as explicit optional extensions.

## Systems to Remove from the Stable Product

- Agent Teams, mailbox, task board, tmux orchestration, team approval tools, team UI.
- Skill Evolution runtime, hotfix pipeline, proposal state machine, candidate observation, promotion and rollback.
- Duplicate session snapshot state once transcript resume has parity.
- Compatibility re-export modules and single-implementation abstractions without a real boundary.
- Per-tool copies of filesystem validation and oversized response-building boilerplate.
- HTML trace renderer/configuration, unused trace protocol declarations, and
  the generic product-side `runtime.evals` analysis API. These removed
  evaluator/reporting surfaces are distinct from the retained JSONL
  `session_summary` metrics above.

Git history is the archive for removed research implementations. A short document may point to the last commit that contained them; do not keep thousands of inactive Python lines in the stable tree merely as reference.

## Non-Goals

- No web dashboard, IDE bridge, voice, cron, remote worker, plugin marketplace, billing, telemetry platform, vector memory, automatic model router, or OS-grade sandbox.
- No new framework dependency unless it deletes more complexity than it introduces.
- No broad rewrite. Refactor through characterization tests and milestone checkpoints.
- No change whose only justification is aesthetics or line-count reduction.

## Verifiable End State

The goal is complete only when:

- `mycodeagent --help` returns promptly.
- From an unrelated temporary repository, `mycodeagent --cwd <repo> -p <task>` targets that repository and can emit text or JSON.
- Interactive sessions can be interrupted, listed, and resumed from transcript data.
- Default startup launches no optional external server or subagent.
- Stable tools are seven or fewer and redundant file/search tools are removed.
- Agent Teams and Skill Evolution have no stable runtime imports or shipped code.
- MCP dependencies are optional installation extras.
- The formal non-research production code is at most 15,000 Python lines, measured consistently.
- The deterministic scenario suite and full core test suite pass.
- README, architecture docs, CLI help, and actual defaults agree.
