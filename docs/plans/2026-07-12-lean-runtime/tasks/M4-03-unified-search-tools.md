# M4-03 Unified Search Toolset Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Cover directory listing, filename discovery, globbing, and content search with only Glob and Grep.

**Architecture:** Use one Glob path-discovery implementation and one Grep content-search implementation, sharing root resolution and result budgets.

**Tech Stack:** Python pathlib, ripgrep when available, pytest.

**Dependencies:** M4-01. May run in parallel with M4-02.

**Files:**

- Modify: `tools/builtin/search_files_by_name.py` or migrate behavior into `search_code.py`/new `glob.py`
- Modify: `tools/builtin/search_code.py`
- Delete after migration: `tools/builtin/list_files.py`
- Delete after migration: redundant filename-search module
- Modify: registration owner and prompt files
- Create: `tests/tools/test_search_contract.py`
- Retire/merge: `tests/test_list_files_tool.py`, `tests/test_glob_tool.py`, `tests/test_grep_tool.py`

## Contract

- `Glob` lists a directory or matches file paths recursively with exclusions and deterministic ordering.
- `Grep` searches file content and can optionally filter candidate paths by glob.
- Prefer `pathlib` for simple traversal and installed `rg` for content performance; provide one clear fallback rather than two full implementations.
- Both tools enforce project-root boundaries and output budgets.

## Steps

1. Write parameterized contract tests for listing, recursive glob, hidden/ignored policy, filename match, content match, binary skip, invalid regex, limit/truncation, and deterministic order.
2. Define the smallest schemas that cover real scenarios; do not preserve every historical option.
3. Reuse `FileWorkspace` root resolution.
4. Migrate registration, prompts, scenarios, and callers.
5. Delete `ListFiles` and redundant filename-search code/tests.
6. Run search contracts, registry, protocol, context-budget, and scenarios.

## Acceptance

- Final schema contains only Glob/Grep for discovery and search.
- Common searches require no Bash fallback.
- Commit: `refactor(M4-03): consolidate file discovery and search`.
