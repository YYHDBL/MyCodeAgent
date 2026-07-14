# M6-01 Remove Optional Project Memory

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:verification-before-completion`.

**Goal:** Remove the off-by-default long-term project-memory feature to meet the stable production LOC budget without weakening transcript recovery.

**Architecture:** Transcript facts and compact checkpoints remain the only recovery path. Remove the separate cross-session memory store, memory tool, prompt injection, configuration, and trace branches; do not leave disabled flags or aliases.

**Dependencies:** M5-02 release audit; Q-05 failed at 15,411 stable LOC.

**Files:**

- Delete: `runtime/memory/`
- Delete: `tools/builtin/memory.py`
- Delete: `prompts/tools_prompts/memory_prompt.py`
- Modify: `core/config.py`, `app/bootstrap.py`, `app/cli.py`, `runtime/factory.py`, `runtime/host.py`, `runtime/context/`, `runtime/loop.py` or owning trace path, `tools/executor.py`, `tools/permissions.py`
- Remove/reshape memory-only tests and docs.

## Acceptance

- No `Memory` tool, long-term-memory flag, store, prompt, injected model-view memory, or compatibility alias remains.
- Transcript resume, checkpoints, uncertain actions, JSONL tracing, Task/Explore, MCP, and Skills behavior remain covered.
- The default schema remains at most seven tools.
- Commit: `refactor(M6-01): remove optional project memory`.
