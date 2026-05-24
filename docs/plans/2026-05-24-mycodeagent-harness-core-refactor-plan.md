# MyCodeAgent Harness-Core Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## Implementation Status

Completed on branch `refactor/harness-core`.

Final repository structure now follows:

```text
main.py -> app/ -> runtime/ -> tools/
                         -> extensions/
                         -> experimental/ (explicit opt-in only)
```

Important final decisions:

- `agents/` compatibility wrappers were removed instead of retained
- old `core/context_engine`, `core/session_store`, `core/message`, and `core/team_engine` wrappers were removed
- MCP moved from `tools/mcp` to `extensions/mcp`
- skills moved from `core/skills` to `extensions/skills`
- tracing moved from `core/context_engine` to `extensions/tracing`
- `scripts/chat_test_agent.py` is only a historical launcher, not the product entrypoint

The sections below document the migration plan and source locations used during the refactor; they are not the current architecture map.

**Goal:** Refactor `MyCodeAgent` from an accreted experimental agent framework into a smaller, cleaner, learning-oriented code-agent harness with a clear runtime core and explicitly separated optional/experimental capabilities.

**Architecture:** The refactor keeps one canonical single-agent runtime path and moves non-core mechanisms behind explicit boundaries. The project should read as `app -> runtime -> tools -> extensions/experimental`, where the core loop remains compact and optional systems no longer define the main narrative.

**Tech Stack:** Python, OpenAI-compatible LLM client, Pydantic config, Rich/prompt_toolkit CLI, pytest, optional MCP integrations.

---

## Target Outcome

After this refactor, the repository should communicate one simple story:

- the canonical product is a single-agent coding harness
- the canonical runtime is small and obvious
- tools, context management, session persistence, and permission checks are first-class
- MCP, skills, tracing, and teams are additive, not foundational
- the repository remains extensible without forcing every extension through the main runtime constructor

## Architectural Blueprint

### Layer Model

The target architecture should converge on five layers:

1. `app/`
   - CLI entrypoints
   - runtime bootstrap and wiring
   - user-facing command parsing
2. `runtime/`
   - agent turn loop
   - message/history model
   - context assembly and compaction policy
   - permission gates
   - session persistence
   - runtime error/recovery handling
3. `tools/`
   - tool abstraction
   - tool registry
   - tool execution adapter
   - builtin tool implementations
4. `extensions/`
   - MCP loading
   - skill loading
   - trace logging / observability
5. `experimental/`
   - team runtime
   - parallel task coordination
   - advanced delegation surfaces

### Target Directory Shape

```text
MyCodeAgent/
  app/
    cli.py
    bootstrap.py
  runtime/
    runner.py
    messages.py
    context.py
    prompt.py
    permissions.py
    session.py
    model_client.py
    errors.py
  tools/
    base.py
    registry.py
    executor.py
    builtin/
      bash.py
      read.py
      write.py
      edit.py
      multi_edit.py
      glob.py
      grep.py
      todo.py
      ask_user.py
  extensions/
    mcp/
    skills/
    tracing/
  experimental/
    teams/
  tests/
    runtime/
    tools/
    extensions/
    experimental/
```

This target shape is not meant to be achieved in one atomic rewrite. The migration should happen incrementally, while preserving working behavior.

## What Is Core vs Optional vs Experimental

### Core

These capabilities define the canonical harness and must remain easy to understand:

- single-agent turn loop
- OpenAI-compatible model client
- message/history accumulation
- context building and compaction policy
- tool dispatch and execution
- file/shell/todo/ask-user builtin tools
- session snapshot persistence
- permission and safety checks

### Optional Extensions

These are useful and can remain in the repo, but must not dominate the baseline:

- MCP tool loading
- skill discovery/loading
- trace logging and observability helpers
- richer prompt packs and system-prompt assembly helpers

### Experimental

These should remain available, but clearly outside the canonical runtime:

- `core/team_engine/*`
- team-specific tools in `tools/builtin/team_*`
- `TaskTool` if it remains tightly coupled to multi-agent delegation
- tmux orchestration, task boards, approval routing, worker/task parallelism

## Current-To-Target Mapping

### Canonical Runtime Inputs

- `scripts/chat_test_agent.py`
  - target: split into `app/cli.py` and `app/bootstrap.py`
  - reason: current script mixes UI, config, bootstrap, and runtime instantiation

- `agents/codeAgent.py`
  - target: split into `runtime/runner.py`, `runtime/context.py`, `runtime/session.py`, `tools/executor.py`
  - reason: current `CodeAgent` is the main gravity well and carries too many responsibilities

### Runtime / Context

- `core/context_engine/context_builder.py`
  - target: `runtime/prompt.py` plus `runtime/context.py`
- `core/context_engine/history_manager.py`
  - target: `runtime/messages.py` or `runtime/context.py`
- `core/context_engine/input_preprocessor.py`
  - target: `runtime/context.py`
- `core/context_engine/summary_compressor.py`
  - target: `runtime/context.py`
- `core/context_engine/observation_truncator.py`
  - target: `runtime/context.py`

### Model / Config / Session

- `core/llm.py`
  - target: `runtime/model_client.py`
- `core/config.py`
  - target: keep temporarily, later split into `app/bootstrap.py` + `runtime/config` concerns if needed
- `core/session_store.py`
  - target: `runtime/session.py`
- `core/message.py`
  - target: `runtime/messages.py`
- `core/exceptions.py`
  - target: `runtime/errors.py`

### Tools

- `tools/base.py`
  - target: keep in `tools/base.py`
- `tools/registry.py`
  - target: keep in `tools/registry.py`, but narrow it to registration/schema/dispatch support
- builtin file/shell tools
  - target: keep, possibly rename for consistency
- `tools/mcp/*`
  - target: move under `extensions/mcp/` or keep a compatibility wrapper while decoupling bootstrap from default runtime

### Skills / Tracing / Teams

- `core/skills/skill_loader.py`
  - target: `extensions/skills/loader.py`
- `core/context_engine/trace_logger.py`
  - target: `extensions/tracing/logger.py`
- `core/team_engine/*`
  - target: `experimental/teams/*`

## Dependency Rules

These rules should guide the refactor and be enforced socially, then by tests/import checks if useful:

- `app/` may depend on `runtime/`, `tools/`, `extensions/`, `experimental/`
- `runtime/` may depend on `tools/` and selected extension interfaces, but not on `experimental/`
- `tools/` must not depend on `app/`
- `extensions/` may depend on `runtime/` and `tools/`
- `experimental/` may depend on `runtime/`, `tools/`, and `extensions/`
- the canonical single-agent bootstrap path must not require `experimental/`

## Migration Strategy

The safest path is a staged refactor with compatibility shims, not a rewrite.

### Stage 0: Freeze the Current Canonical Behavior

Objective:

- define the baseline runtime behavior before moving modules

Required outcomes:

- identify the current canonical CLI path
- identify the tests that protect single-agent runtime behavior
- document which tests are team-only and which are core runtime

Likely files:

- `scripts/chat_test_agent.py`
- `agents/codeAgent.py`
- `tests/test_context_builder.py`
- `tests/test_context_engineering.py`
- `tests/test_protocol_compliance.py`
- `tests/test_tool_registry_schema_compat.py`
- `tests/test_read_tool.py`
- `tests/test_write_tool.py`
- `tests/test_edit_tool.py`
- `tests/test_bash_tool.py`
- `tests/test_todo_write_tool.py`

Verification:

- run a focused “core-only” pytest subset and record it as the baseline command

### Stage 1: Extract Bootstrap From Runtime

Objective:

- move startup and wiring concerns out of `scripts/chat_test_agent.py`

Create:

- `app/__init__.py`
- `app/bootstrap.py`
- `app/cli.py`

Modify:

- `scripts/chat_test_agent.py`

Plan:

- create a bootstrap function that assembles `Config`, `HelloAgentsLLM`, `ToolRegistry`, and the runtime runner
- make the script call into `app.cli` or keep the script as a thin compatibility wrapper
- preserve current CLI behavior first; do not redesign commands yet

Verification:

- add `tests/test_app_bootstrap.py`
- smoke-test the CLI bootstrap path

### Stage 2: Split CodeAgent Into Runner + Services

Objective:

- reduce `CodeAgent` into a thin compatibility façade or eliminate it in favor of smaller service objects

Create:

- `runtime/__init__.py`
- `runtime/runner.py`
- `runtime/messages.py`
- `runtime/context.py`
- `runtime/session.py`
- `runtime/errors.py`

Modify:

- `agents/codeAgent.py`
- `core/message.py`
- `core/session_store.py`
- `core/context_engine/*`

Plan:

- move the turn loop and step orchestration into `runtime/runner.py`
- move history/message lifecycle into `runtime/messages.py`
- move compaction and history shaping into `runtime/context.py`
- move snapshot helpers into `runtime/session.py`
- keep `agents/codeAgent.py` as a temporary shim that delegates to the new runtime objects

Verification:

- add `tests/runtime/test_runner.py`
- add `tests/runtime/test_messages.py`
- add `tests/runtime/test_session.py`
- keep old tests passing while new runtime tests are introduced

### Stage 3: Extract Prompt / Context Policy

Objective:

- make context engineering explicit and readable as a policy subsystem

Create:

- `runtime/prompt.py`

Modify:

- `core/context_engine/context_builder.py`
- `core/context_engine/input_preprocessor.py`
- `core/context_engine/summary_compressor.py`
- `core/context_engine/observation_truncator.py`

Plan:

- isolate system prompt assembly, code law injection, skill prompt injection, and MCP prompt injection
- isolate user-input preprocessing from prompt assembly
- expose a smaller `ContextManager` or similarly named API to the runner

Verification:

- add `tests/runtime/test_prompt.py`
- migrate `tests/test_context_builder.py` expectations to the new prompt/context surface

### Stage 4: Introduce ToolExecutor Boundary

Objective:

- stop using the agent object as the tool execution surface

Create:

- `tools/executor.py`

Modify:

- `tools/registry.py`
- `agents/codeAgent.py`
- builtin tools only if required for signature normalization

Plan:

- leave `ToolRegistry` responsible for schema exposure and tool lookup
- create `ToolExecutor` for execution policy, optimistic-lock injection coordination, and error packaging
- keep circuit breaker behavior, but make it an execution concern instead of an all-purpose registry concern if possible

Verification:

- add `tests/tools/test_executor.py`
- preserve `tests/test_tool_registry_schema_compat.py`

### Stage 5: Move Optional Systems Behind Explicit Extension Boundaries

Objective:

- preserve MCP, skills, and tracing without keeping them in the canonical runtime constructor

Create:

- `extensions/__init__.py`
- `extensions/mcp/__init__.py`
- `extensions/skills/__init__.py`
- `extensions/tracing/__init__.py`

Modify:

- `tools/mcp/*`
- `core/skills/skill_loader.py`
- `core/context_engine/trace_logger.py`
- `agents/codeAgent.py`

Plan:

- extract adapters so bootstrap opts into MCP/skills/tracing explicitly
- remove unconditional initialization from the core runner constructor
- keep a stable public surface for tool prompt injection and trace hooks

Verification:

- add `tests/extensions/test_mcp_extension.py`
- add `tests/extensions/test_skills_extension.py`

### Stage 6: Isolate Experimental Team Runtime

Objective:

- keep the team runtime in-repo without letting it define the main architecture

Create:

- `experimental/__init__.py`
- `experimental/teams/__init__.py`

Modify:

- `core/team_engine/*`
- `tools/builtin/team_*`
- `tools/builtin/send_message.py`
- `tools/builtin/task.py`

Plan:

- move team-engine modules under `experimental/teams/`
- decide whether `TaskTool` belongs to `experimental/teams` or should be split into a minimal core delegation tool and a team-specific advanced task tool
- default bootstrap should not import team runtime unless explicitly enabled

Verification:

- move team-heavy tests into `tests/experimental/`
- core runtime tests must pass with team runtime fully disabled

### Stage 7: Rewrite Repository Narrative

Objective:

- make the repository readable as a small elegant harness project

Modify:

- `README.md`
- `scripts/chat_test_agent.py`
- `docs/`
- test layout and developer docs

Plan:

- rewrite README around the canonical single-agent runtime
- document optional and experimental layers separately
- add a short “architecture map” diagram showing `app -> runtime -> tools -> extensions/experimental`

Verification:

- manual review: a new reader should be able to identify the canonical runtime files in under two minutes

## Detailed File-Level Migration Checklist

### Keep As-Is Or Nearly As-Is

- `tools/base.py`
- most builtin file/shell tools, after light renaming only if needed
- `core/llm.py` logic, though it should move
- `core/session_store.py` logic, though it should move

### Keep But Narrow Responsibility

- `tools/registry.py`
- `core/config.py`
- `scripts/chat_test_agent.py`

### Split Aggressively

- `agents/codeAgent.py`
- `core/context_engine/context_builder.py`
- `core/context_engine/history_manager.py`

### Move To Extensions

- `core/skills/skill_loader.py`
- `tools/mcp/adapter.py`
- `tools/mcp/client.py`
- `tools/mcp/config.py`
- `tools/mcp/loader.py`
- `tools/mcp/protocol.py`
- `core/context_engine/trace_logger.py`
- `core/context_engine/trace_sanitizer.py`

### Move To Experimental

- `core/team_engine/approval.py`
- `core/team_engine/cli_commands.py`
- `core/team_engine/display_mode.py`
- `core/team_engine/errors.py`
- `core/team_engine/events.py`
- `core/team_engine/execution.py`
- `core/team_engine/manager.py`
- `core/team_engine/message_router.py`
- `core/team_engine/progress_view.py`
- `core/team_engine/protocol.py`
- `core/team_engine/store.py`
- `core/team_engine/supervisor.py`
- `core/team_engine/task_board.py`
- `core/team_engine/task_board_store.py`
- `core/team_engine/tmux_orchestrator.py`
- `core/team_engine/turn_executor.py`
- `core/team_engine/worker.py`
- `tools/builtin/team_approvals.py`
- `tools/builtin/team_approve_plan.py`
- `tools/builtin/team_cleanup.py`
- `tools/builtin/team_collect.py`
- `tools/builtin/team_create.py`
- `tools/builtin/team_delete.py`
- `tools/builtin/team_fanout.py`
- `tools/builtin/team_status.py`
- `tools/builtin/team_task_create.py`
- `tools/builtin/team_task_get.py`
- `tools/builtin/team_task_list.py`
- `tools/builtin/team_task_update.py`
- `tools/builtin/send_message.py`

## Test Reorganization Plan

### Core Runtime Tests

- keep or migrate:
  - `tests/test_context_builder.py`
  - `tests/test_context_engineering.py`
  - `tests/test_history_manager.py`
  - `tests/test_summary_compressor.py`
  - `tests/test_observation_truncator.py`
  - `tests/test_protocol_compliance.py`
  - `tests/test_llm_provider_resolution.py`
  - `tests/test_llm_temperature_policy.py`

### Core Tool Tests

- keep or migrate:
  - `tests/test_bash_tool.py`
  - `tests/test_read_tool.py`
  - `tests/test_write_tool.py`
  - `tests/test_edit_tool.py`
  - `tests/test_multi_edit_tool.py`
  - `tests/test_glob_tool.py`
  - `tests/test_grep_tool.py`
  - `tests/test_list_files_tool.py`
  - `tests/test_todo_write_tool.py`
  - `tests/test_tool_registry_schema_compat.py`

### Extension Tests

- move or add:
  - `tests/test_mcp_protocol.py`
  - `tests/test_skills.py`
  - `tests/test_trace_logger.py`

### Experimental Team Tests

- move:
  - all `tests/test_team_*`
  - `tests/test_agent_teams_*`
  - `tests/test_task_tool_parallel_mode.py`
  - `tests/test_tmux_orchestrator.py`
  - `tests/test_turn_executor.py`

## Risks To Watch

- the refactor can accidentally break session compatibility if snapshot format changes too early
- moving `TaskTool` may expose hidden dependencies on the current `CodeAgent` constructor
- `tools/registry.py` currently mixes schema, execution, caching, and circuit breaker behavior; extracting too much at once will create churn
- team runtime may currently leak assumptions into the default bootstrap path
- docs and tests currently encode the existing mental model; they must be updated together

## Recommended Implementation Order

1. carve out `app/bootstrap.py` and `app/cli.py`
2. introduce `runtime/runner.py` and make `CodeAgent` delegate
3. move message/session/context helpers under `runtime/`
4. add `tools/executor.py`
5. move MCP/skills/tracing into `extensions/`
6. move team engine into `experimental/teams/`
7. rewrite tests and README to reflect the new canonical story

## Task-By-Task Execution Plan

### Task 1: Establish the Core Runtime Baseline

**Files:**
- Modify: `tests/run_all_tests.py`
- Test: `tests/test_context_builder.py`
- Test: `tests/test_context_engineering.py`
- Test: `tests/test_protocol_compliance.py`
- Test: `tests/test_bash_tool.py`
- Test: `tests/test_read_tool.py`
- Test: `tests/test_write_tool.py`
- Test: `tests/test_edit_tool.py`
- Test: `tests/test_todo_write_tool.py`

**Step 1: Define the baseline core test subset**

- create one explicit core-runtime pytest command in `tests/run_all_tests.py` comments or helper constants
- exclude all team-only and tmux-only tests from this first baseline

**Step 2: Run the core subset and record current behavior**

Run:

```bash
pytest \
  tests/test_context_builder.py \
  tests/test_context_engineering.py \
  tests/test_protocol_compliance.py \
  tests/test_bash_tool.py \
  tests/test_read_tool.py \
  tests/test_write_tool.py \
  tests/test_edit_tool.py \
  tests/test_todo_write_tool.py -q
```

Expected:

- current core path passes, or any failures are documented before refactor starts

**Step 3: Commit the baseline-only harness changes**

```bash
git add tests/run_all_tests.py
git commit -m "chore: define core runtime test baseline"
```

### Task 2: Extract App Bootstrap

**Files:**
- Create: `app/__init__.py`
- Create: `app/bootstrap.py`
- Create: `app/cli.py`
- Modify: `scripts/chat_test_agent.py`
- Test: `tests/test_app_bootstrap.py`

**Step 1: Write the failing bootstrap smoke test**

- add a test that imports the bootstrap entrypoint and verifies it can construct the runtime dependencies without starting an interactive UI loop

**Step 2: Run the new test to verify the import/bootstrap gap**

Run:

```bash
pytest tests/test_app_bootstrap.py -q
```

Expected:

- fail initially because `app.bootstrap` and `app.cli` do not exist yet

**Step 3: Create the bootstrap module**

- move config + llm + registry + runtime wiring out of `scripts/chat_test_agent.py`
- keep `scripts/chat_test_agent.py` as a compatibility entrypoint that calls `app.cli.main()`

**Step 4: Re-run bootstrap and core runtime tests**

Run:

```bash
pytest tests/test_app_bootstrap.py tests/test_bash_tool.py tests/test_protocol_compliance.py -q
```

Expected:

- new bootstrap path passes without changing canonical behavior

**Step 5: Commit**

```bash
git add app scripts/chat_test_agent.py tests/test_app_bootstrap.py
git commit -m "refactor: extract application bootstrap"
```

### Task 3: Introduce Runtime Runner

**Files:**
- Create: `runtime/__init__.py`
- Create: `runtime/runner.py`
- Modify: `agents/codeAgent.py`
- Test: `tests/runtime/test_runner.py`

**Step 1: Write a failing runner test**

- assert a `Runner`-style object can accept input, invoke the llm/tool path, and return the final answer through a compatibility façade

**Step 2: Run the runner test**

Run:

```bash
pytest tests/runtime/test_runner.py -q
```

Expected:

- fail because `runtime.runner` does not exist yet

**Step 3: Extract the turn loop**

- move `CodeAgent.run()` and the ReAct loop internals into `runtime/runner.py`
- leave `agents/codeAgent.py` temporarily delegating to the new runner

**Step 4: Verify compatibility**

Run:

```bash
pytest \
  tests/runtime/test_runner.py \
  tests/test_protocol_compliance.py \
  tests/test_context_engineering.py -q
```

Expected:

- core loop still behaves the same from the outside

**Step 5: Commit**

```bash
git add runtime agents/codeAgent.py tests/runtime/test_runner.py
git commit -m "refactor: extract runtime runner"
```

### Task 4: Consolidate Message, Context, and Session Services

**Files:**
- Create: `runtime/messages.py`
- Create: `runtime/context.py`
- Create: `runtime/session.py`
- Create: `runtime/prompt.py`
- Modify: `core/context_engine/context_builder.py`
- Modify: `core/context_engine/history_manager.py`
- Modify: `core/context_engine/input_preprocessor.py`
- Modify: `core/context_engine/summary_compressor.py`
- Modify: `core/context_engine/observation_truncator.py`
- Modify: `core/session_store.py`
- Modify: `core/message.py`
- Test: `tests/runtime/test_messages.py`
- Test: `tests/runtime/test_context.py`
- Test: `tests/runtime/test_prompt.py`
- Test: `tests/runtime/test_session.py`

**Step 1: Add failing tests for each new service boundary**

- message lifecycle
- context assembly / compaction
- prompt assembly
- session snapshot roundtrip

**Step 2: Run the new runtime service tests**

Run:

```bash
pytest tests/runtime/test_messages.py tests/runtime/test_context.py tests/runtime/test_prompt.py tests/runtime/test_session.py -q
```

Expected:

- fail initially because these service modules do not exist yet

**Step 3: Move logic with compatibility wrappers**

- copy logic into `runtime/*`
- keep old `core/context_engine/*` and `core/session_store.py` as temporary wrappers if that reduces churn

**Step 4: Verify both old and new tests**

Run:

```bash
pytest \
  tests/runtime/test_messages.py \
  tests/runtime/test_context.py \
  tests/runtime/test_prompt.py \
  tests/runtime/test_session.py \
  tests/test_context_builder.py \
  tests/test_history_manager.py \
  tests/test_summary_compressor.py -q
```

**Step 5: Commit**

```bash
git add runtime core tests/runtime
git commit -m "refactor: extract runtime context and session services"
```

### Task 5: Introduce ToolExecutor

**Files:**
- Create: `tools/executor.py`
- Modify: `tools/registry.py`
- Modify: `runtime/runner.py`
- Test: `tests/tools/test_executor.py`
- Test: `tests/test_tool_registry_schema_compat.py`

**Step 1: Add a failing executor test**

- verify registry/schema and execution concerns are no longer inseparable

**Step 2: Run the test**

Run:

```bash
pytest tests/tools/test_executor.py tests/test_tool_registry_schema_compat.py -q
```

**Step 3: Split responsibilities**

- registry: register tools, expose schemas, resolve handlers
- executor: execute tools, package errors, coordinate optimistic locks / circuit behavior

**Step 4: Re-run tool tests**

Run:

```bash
pytest \
  tests/tools/test_executor.py \
  tests/test_bash_tool.py \
  tests/test_read_tool.py \
  tests/test_write_tool.py \
  tests/test_edit_tool.py \
  tests/test_tool_registry_schema_compat.py -q
```

**Step 5: Commit**

```bash
git add tools runtime/runner.py tests/tools/test_executor.py
git commit -m "refactor: add tool executor boundary"
```

### Task 6: Move Optional Capabilities Into Extensions

**Files:**
- Create: `extensions/__init__.py`
- Create: `extensions/mcp/__init__.py`
- Create: `extensions/skills/__init__.py`
- Create: `extensions/tracing/__init__.py`
- Modify: `tools/mcp/adapter.py`
- Modify: `tools/mcp/client.py`
- Modify: `tools/mcp/config.py`
- Modify: `tools/mcp/loader.py`
- Modify: `tools/mcp/protocol.py`
- Modify: `core/skills/skill_loader.py`
- Modify: `core/context_engine/trace_logger.py`
- Modify: `core/context_engine/trace_sanitizer.py`
- Modify: `app/bootstrap.py`
- Test: `tests/extensions/test_mcp_extension.py`
- Test: `tests/extensions/test_skills_extension.py`
- Test: `tests/extensions/test_tracing_extension.py`

**Step 1: Write failing extension bootstrap tests**

- bootstrap without extensions
- bootstrap with selected extensions enabled

**Step 2: Run extension tests**

Run:

```bash
pytest tests/extensions/test_mcp_extension.py tests/extensions/test_skills_extension.py tests/extensions/test_tracing_extension.py -q
```

**Step 3: Move extension loading out of the default runner path**

- extensions become opt-in at bootstrap
- core runtime remains functional when none of them are enabled

**Step 4: Verify extension and core coexistence**

Run:

```bash
pytest \
  tests/extensions/test_mcp_extension.py \
  tests/extensions/test_skills_extension.py \
  tests/extensions/test_tracing_extension.py \
  tests/test_mcp_protocol.py \
  tests/test_skills.py \
  tests/test_trace_logger.py -q
```

**Step 5: Commit**

```bash
git add extensions app/bootstrap.py core tools tests/extensions
git commit -m "refactor: isolate optional extensions"
```

### Task 7: Move Team Runtime To Experimental

**Files:**
- Create: `experimental/__init__.py`
- Create: `experimental/teams/__init__.py`
- Modify: `core/team_engine/*`
- Modify: `tools/builtin/team_*.py`
- Modify: `tools/builtin/send_message.py`
- Modify: `tools/builtin/task.py`
- Modify: `app/bootstrap.py`
- Test: `tests/experimental/*`

**Step 1: Move tests before code**

- create `tests/experimental/`
- relocate team-runtime tests there without changing expectations yet

**Step 2: Run experimental-only tests**

Run:

```bash
pytest tests/experimental -q
```

**Step 3: Move runtime code**

- relocate `core/team_engine/*` into `experimental/teams/*`
- adjust imports so default bootstrap never touches experimental code unless enabled

**Step 4: Verify separation**

Run:

```bash
pytest tests/experimental -q
pytest tests/test_protocol_compliance.py tests/test_bash_tool.py -q
```

Expected:

- experimental tests still pass
- core runtime still passes with experimental system disabled

**Step 5: Commit**

```bash
git add experimental core/team_engine tools/builtin app/bootstrap.py tests/experimental
git commit -m "refactor: isolate experimental team runtime"
```

### Task 8: Rewrite Project Narrative And Remove Compatibility Debt

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-05-24-mycodeagent-harness-core-refactor-plan.md`
- Modify: any temporary compatibility wrappers left from prior steps

**Step 1: Remove or minimize obsolete wrappers**

- reduce `agents/codeAgent.py` to a compatibility façade or delete it if no longer needed
- reduce stale `core/context_engine/*` wrappers if all imports have moved

**Step 2: Rewrite the README around the canonical runtime**

- explain the single-agent harness first
- explain extensions second
- explain experimental team runtime last

**Step 3: Run the final tiered verification**

Run:

```bash
pytest tests/runtime tests/tools tests/extensions -q
pytest tests/experimental -q
```

**Step 4: Commit**

```bash
git add README.md agents core runtime tools extensions experimental tests
git commit -m "docs: align repository narrative with harness-core architecture"
```

## Minimal Success Criteria

The refactor is successful when all of the following are true:

- a new reader can locate the canonical runtime in `app/` + `runtime/` immediately
- the single-agent runtime works without importing team runtime
- MCP and skills can be enabled, but are not required for the baseline
- the team runtime still exists, but is clearly marked experimental
- tests are grouped by architectural tier instead of historical feature accretion
- `agents/codeAgent.py` is either gone or reduced to a compatibility façade

## Suggested Follow-Up Documents

- `docs/plans/2026-05-24-mycodeagent-core-runtime-extraction.md`
- `docs/plans/2026-05-24-mycodeagent-extension-boundary-plan.md`
- `docs/plans/2026-05-24-mycodeagent-test-reorganization-plan.md`
