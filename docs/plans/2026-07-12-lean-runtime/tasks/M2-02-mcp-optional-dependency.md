# M2-02 Optional MCP Dependency Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Keep MCP capability while removing its dependency, imports, child processes, and network work from the core path.

**Architecture:** Put MCP behind one lazy adapter boundary and a packaging extra; the stable runtime sees only registered tools after explicit enablement.

**Tech Stack:** Python, MCP SDK, AnyIO, uv optional extras, pytest.

**Dependencies:** M2-01.

**Files:**

- Modify: `pyproject.toml`
- Update mechanically: `uv.lock`
- Modify: `extensions/mcp/bootstrap.py`
- Modify: `extensions/mcp/client.py`
- Modify: `extensions/mcp/__init__.py`
- Modify: `mcp_servers.json` or replace with a disabled example
- Modify: `tests/extensions/test_mcp_extension.py`
- Create: `tests/test_core_without_mcp.py`

## Contract

- Core install does not require `mcp` or `anyio`.
- `mycodeagent[mcp]` installs them.
- MCP modules are imported only after explicit enablement.
- No bundled server starts by default.
- Missing MCP extra produces one actionable error, not a traceback or silent skip.

## Steps

1. Add a subprocess/import test that shadows or omits `mcp` and imports/starts core CLI successfully.
2. Move MCP dependencies into a `mcp` optional extra.
3. Guard imports at the adapter boundary; do not spread `try/except ImportError` throughout core code.
4. Make server configuration user-owned or clearly an example; startup mode must be explicit.
5. Test explicit MCP initialization with fakes, then run the optional-extra integration tests.
6. Record core dependency count before and after.

## Acceptance

- `rg '^from mcp|^import anyio' app core runtime tools` returns no matches.
- Core tests run in an environment without MCP packages.
- Commit: `refactor(M2-02): make MCP an opt-in extra`.
