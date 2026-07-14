# M4-01 Shared FileWorkspace Implementation Plan

> **For GPT/Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `security-review`.

**Goal:** Centralize repeated safe filesystem primitives before merging file tools.

**Architecture:** Provide one concrete project-root workspace using standard-library path resolution, snapshots, and atomic writes; tools remain thin operations.

**Tech Stack:** Python pathlib/os/tempfile, pytest.

**Dependencies:** M3-03 and M3 milestone gate.

**Files:**

- Create: `tools/workspace.py`
- Create: `tests/tools/test_workspace.py`
- Modify: `tools/builtin/read_file.py`
- Modify: one mutation tool (`tools/builtin/edit_file.py`) as the first consumer
- Do not merge/delete tools in this task.

## Required API

Keep the API small and evidence-driven. Expected responsibilities:

- resolve a relative path under project root;
- reject absolute/traversal/symlink escape;
- detect directory/binary/nonexistent cases;
- capture a file snapshot (`mtime_ns`, size, optional content hash if justified);
- read text with declared encoding behavior;
- atomically write when an expected snapshot still matches.

Do not move tool-specific diff formatting, prompt text, or response wording into the workspace.

## Steps

1. Write parameterized tests for path normalization, traversal, symlink escape, missing path, directory, binary, snapshot match/mismatch, and atomic write failure.
2. Implement `FileWorkspace` with `pathlib`, `tempfile`, and `os.replace`; add no dependency.
3. Refactor Read and one Edit path to use it without changing their public result schema.
4. Remove the duplicated code only from those consumers.
5. Run workspace, Read, Edit, permission, and protocol tests.

## Acceptance

- Security behavior is centralized and independently tested.
- No broad “filesystem service” or backend interface is introduced.
- Commit: `refactor(M4-01): centralize safe file workspace operations`.
