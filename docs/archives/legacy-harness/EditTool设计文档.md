# Edit Tool

`Edit` is the only file-mutation tool in the stable product. Its implementation
is [`tools/builtin/edit_file.py`](../tools/builtin/edit_file.py), and its
model-facing guidance is [`prompts/tools_prompts/edit_prompt.py`](../prompts/tools_prompts/edit_prompt.py).

## Input

Every call supplies a project-relative `path` and exactly one of these modes:

- `create_content` creates a missing text file, including parent directories.
  On an existing file it replaces the full content, but only after `Read` has
  supplied the optimistic-lock snapshot.
- `edits` is a non-empty ordered array of `{old_string, new_string}` objects
  for an existing file. Every old string must match exactly once in the
  original content and no matched regions may overlap.

`expected_mtime_ms` and `expected_size_bytes` are injected from the latest
`Read` result for existing-file mutation. `dry_run` previews the unified diff
without changing disk.

## Safety and result

`FileWorkspace` confines paths to the selected project, rejects binary and
non-regular files, preserves the predominant newline style for edits, and
performs one same-directory atomic commit. New-file creation will not overwrite
a concurrent creator. A stale snapshot returns `CONFLICT`; invalid anchors,
duplicate matches, overlap, and invalid paths return explicit protocol errors.

The response uses the common tool envelope. Its data includes `applied`,
`operation` (`create`, `replace`, or `edit`), `replacements`, a bounded
`diff_preview`, and `diff_truncated`; stats include byte and line deltas.

## Verification

`tests/tools/test_edit_contract.py` covers creation, full replacement,
single/multiple edits, overlap and duplicate rejection, dry run, snapshot
conflict, CRLF preservation, and rollback after an atomic replacement failure.
`tests/tools/test_workspace.py` covers the shared filesystem boundary.
