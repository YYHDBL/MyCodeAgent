# MyCodeAgent Structure Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## Implementation Status

Completed on branch `refactor/harness-core`.

Final convergence result:

- canonical user entrypoint is `main.py`
- `runtime/` is the only runtime center
- `agents/` has been removed
- `scripts/chat_test_agent.py` and the `scripts/` package were removed
- `core/` is limited to infrastructure: config, env, base agent abstraction, exceptions, and LLM client
- MCP, skills, and tracing live under `extensions/`
- team runtime lives under `experimental/teams/`
- tests are organized under `tests/runtime`, `tests/tools`, `tests/extensions`, and `tests/experimental`

The sections below are the execution plan that led to that result; old paths mentioned in task descriptions are migration sources, not current canonical locations.

**Goal:** Converge the current post-refactor transitional structure into a smaller, cleaner, more legible final repository layout suitable for long-term maintenance and learning-oriented presentation.

**Architecture:** The current repository has the right high-level layers, but still carries transitional duplication between old and new module locations. This plan removes double centers of gravity, promotes one clear user entrypoint, reduces compatibility noise, and leaves the repository with one obvious canonical runtime story.

**Tech Stack:** Python, pytest, Rich/prompt_toolkit CLI, OpenAI-compatible LLM client, optional MCP/experimental team runtime.

---

## Final Target Shape

```text
MyCodeAgent/
  main.py
  README.md
  app/
    __init__.py
    bootstrap.py
    cli.py
  runtime/
    __init__.py
    agent.py
    runner.py
    context.py
    messages.py
    prompt.py
    session.py
    permissions.py
    model_client.py
    errors.py
  tools/
    base.py
    registry.py
    executor.py
    builtin/
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
  docs/
  prompts/
  skills/
```

## Structural Principles

- root-level user entrypoint must be obvious
- `runtime/` must be the only canonical runtime center
- `core/` must either shrink to tiny infrastructure or disappear from the main narrative
- `agents/` should not remain as a second runtime story
- `scripts/` should hold developer scripts only, not the main product entrypoint
- compatibility wrappers should be temporary and minimized
- optional and experimental layers should remain visible but secondary

## Main Problems To Fix

1. The user-facing entrypoint still lives in `scripts/chat_test_agent.py`.
2. `runtime/` and `core/` still form a double-center structure.
3. `agents/codeAgent.py` still exists as a narrative distraction even if it is now a façade.
4. `tools/mcp/` and `extensions/mcp/` together still read like transitional duplication.
5. Test layout is improved, but the repo still communicates old and new stories simultaneously.

## Convergence Plan

### Task 1: Promote A Root-Level Canonical Entrypoint

**Files:**
- Create: `main.py`
- Modify: `scripts/chat_test_agent.py`
- Modify: `README.md`
- Test: `tests/test_app_bootstrap.py`

**Step 1: Write a failing entrypoint smoke test**

- add a small test that imports `main` and confirms it delegates to `app.cli.main`

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_app_bootstrap.py -q
```

Expected:

- fail because `main.py` does not exist yet or is not wired as canonical entry

**Step 3: Implement the root entrypoint**

- create `main.py` at repository root
- make it the clearest supported launch path
- keep `scripts/chat_test_agent.py` only as a compatibility wrapper during transition

**Step 4: Re-run verification**

Run:

```bash
pytest tests/test_app_bootstrap.py -q
```

Expected:

- pass with canonical entrypoint behavior verified

**Step 5: Commit**

```bash
git add main.py scripts/chat_test_agent.py README.md tests/test_app_bootstrap.py
git commit -m "refactor: promote root-level canonical entrypoint"
```

### Task 2: Remove `agents/` From The Main Architecture Story

**Files:**
- Modify: `agents/codeAgent.py`
- Modify: `runtime/__init__.py`
- Modify: `README.md`
- Test: `tests/runtime/test_runner.py`

**Step 1: Write a failing narrative/compatibility test if needed**

- if `agents.codeAgent` must remain importable, test that it is only a compatibility alias and not the canonical module

**Step 2: Run test to verify the current ambiguity**

Run:

```bash
pytest tests/runtime/test_runner.py -q
```

**Step 3: Minimize the `agents/` façade**

- reduce `agents/codeAgent.py` to the thinnest possible alias
- ensure `runtime/` exports the canonical runtime objects without eager imports that create cycles
- remove any `README` language that suggests `agents/` is still the runtime center

**Step 4: Re-run verification**

Run:

```bash
pytest tests/runtime/test_runner.py tests/test_context_builder.py -q
```

Expected:

- runtime remains canonical
- compatibility imports still work if they are still supported

**Step 5: Commit**

```bash
git add agents runtime README.md
git commit -m "refactor: reduce agents layer to compatibility shim"
```

### Task 3: Shrink `core/` To True Infrastructure

**Files:**
- Modify: `core/config.py`
- Modify: `core/env.py`
- Modify: `core/llm.py`
- Modify: `core/exceptions.py`
- Modify: `core/context_engine/*`
- Modify: `core/session_store.py`
- Test: `tests/test_context_builder.py`
- Test: `tests/test_summary_compressor.py`
- Test: `tests/test_llm_provider_resolution.py`

**Step 1: Identify what remains legitimately infrastructural**

- config
- env loading
- provider/model client helpers
- exceptions

Everything else should either live in `runtime/`, `extensions/`, or `experimental/`.

**Step 2: Make old `core` modules clearly transitional**

- either keep tiny wrappers
- or move imports fully and update call sites
- avoid half-real, half-wrapper modules

**Step 3: Run verification**

Run:

```bash
pytest \
  tests/test_context_builder.py \
  tests/test_summary_compressor.py \
  tests/test_llm_provider_resolution.py -q
```

Expected:

- `core` no longer acts like a competing runtime center

**Step 4: Commit**

```bash
git add core runtime tests
git commit -m "refactor: shrink core to infrastructure-only responsibilities"
```

### Task 4: Eliminate Double Narrative Around MCP / Skills / Tracing

**Files:**
- Modify: `tools/mcp/*`
- Modify: `extensions/mcp/__init__.py`
- Modify: `extensions/tracing/__init__.py`
- Modify: `extensions/skills/*`
- Modify: `README.md`
- Test: `tests/extensions/test_mcp_extension.py`
- Test: `tests/extensions/test_skills_extension.py`
- Test: `tests/extensions/test_tracing_extension.py`

**Step 1: Decide one canonical home per extension surface**

- MCP canonical home should read as `extensions/mcp`
- skills canonical home should read as `extensions/skills`
- tracing canonical home should read as `extensions/tracing`

**Step 2: Remove narrative duplication**

- internal helpers can remain where needed temporarily
- but imports, docs, and bootstrap path should point to one obvious home

**Step 3: Run verification**

Run:

```bash
pytest \
  tests/extensions/test_mcp_extension.py \
  tests/extensions/test_skills_extension.py \
  tests/extensions/test_tracing_extension.py -q
```

**Step 4: Commit**

```bash
git add extensions tools README.md tests/extensions
git commit -m "refactor: converge extension surfaces"
```

### Task 5: Clean Up Scripts, Caches, And Repository Noise

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `scripts/__init__.py`

**Step 1: Ensure repo root is not cluttered by tool/cache artifacts in narrative docs**

- `.venv/`, `.uv_cache/`, `.npm_cache/`, `__pycache__/`, `.pytest_cache/` should remain ignored and not treated as structural

**Step 2: Reclassify `scripts/`**

- keep it only for development scripts, one-off helpers, or migration utilities
- remove the impression that `scripts/` is where the product starts

**Step 3: Commit**

```bash
git add .gitignore README.md scripts/__init__.py
git commit -m "chore: clean repository narrative and script role"
```

### Task 6: Final Architecture Review Pass

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-05-24-mycodeagent-harness-core-refactor-plan.md`
- Modify: `docs/plans/2026-05-24-mycodeagent-structure-convergence-plan.md`

**Step 1: Verify there is exactly one obvious answer to each question**

- where do I start the app?
- where is the runtime core?
- where are builtin tools?
- where are optional extensions?
- where are experimental systems?

**Step 2: Verify the repository passes the “new reader in 2 minutes” test**

- a new reader should not need to inspect `agents/`, `core/context_engine/`, and `scripts/` to understand the main story

**Step 3: Run final verification**

Run:

```bash
pytest tests/runtime tests/tools tests/extensions -q
pytest tests/experimental -q
```

**Step 4: Commit**

```bash
git add README.md docs/plans
git commit -m "docs: finalize repository structure convergence"
```

## Recommended Order

1. root entrypoint
2. runtime vs agents narrative cleanup
3. shrink `core/`
4. converge extension surfaces
5. clean script/repo noise
6. final architecture review

## Success Criteria

This cleanup is complete when:

- there is a root-level canonical entrypoint
- `runtime/` is the only obvious runtime center
- `agents/` is either gone from the main story or reduced to a trivial shim
- `core/` no longer reads like a second architecture tree
- extensions have one obvious home each
- `scripts/` no longer contains the user-facing primary entrypoint
- the project reads as a clean showcase harness rather than a transitional refactor snapshot
