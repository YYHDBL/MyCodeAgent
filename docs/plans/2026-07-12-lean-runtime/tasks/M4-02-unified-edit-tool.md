# M4-02 Unified Edit Tool Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development`.

**Goal:** Replace Write, Edit, and MultiEdit with one atomic Edit tool supporting create and ordered multi-edit operations.

**Architecture:** Build one Edit schema on `FileWorkspace`, applying validated replacements in memory and committing them with one atomic write.

**Tech Stack:** Python, difflib, FileWorkspace, pytest.

**Dependencies:** M4-01.

**Files:**

- Modify: `tools/builtin/edit_file.py`
- Delete after migration: `tools/builtin/write_file.py`
- Delete after migration: `tools/builtin/edit_file_multi.py`
- Modify: `tools/registry.py`
- Modify: `runtime/host.py` or current tool registration owner
- Consolidate prompts into: `prompts/tools_prompts/edit_prompt.py`
- Delete: `prompts/tools_prompts/write_prompt.py`, `prompts/tools_prompts/multi_edit_prompt.py`
- Create: `tests/tools/test_edit_contract.py`
- Retire/merge: `tests/test_write_tool.py`, `tests/test_edit_tool.py`, `tests/test_multi_edit_tool.py`

## Proposed Input

```json
{
  "path": "relative/file.py",
  "edits": [{"old_string": "...", "new_string": "..."}],
  "create_content": null,
  "expected_mtime_ms": null,
  "expected_size_bytes": null,
  "dry_run": false
}
```

Exactly one of `edits` or `create_content` is used. Existing-file full replacement should not require a separate Write tool.

## Steps

1. Write contract tests for create, single edit, multiple non-overlapping edits, overlap rejection, duplicate match rejection, dry run, snapshot conflict, newline preservation, and atomic rollback.
2. Implement on `FileWorkspace`; keep all edits atomic.
3. Migrate prompts, schemas, registration, completion evidence, and scenarios to `Edit`.
4. Delete old tools and duplicated tests; do not keep aliases in the final schema.
5. Run edit contract, registry fingerprint, protocol, completion, and scenarios.

## Acceptance

- Final model schema contains `Edit` and not `Write`/`MultiEdit`.
- Mutation safety is equal or stronger with substantially less code.
- Commit: `refactor(M4-02): unify file mutation in Edit`.
