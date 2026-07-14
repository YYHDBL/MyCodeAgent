# R3-03 Remove Duplicate Subagent Response Adapters

**Goal:** Make `core.llm` the only response-normalization owner and delete dead
host adapters from the subagent runtime.

**Files:**

- Modify: `runtime/subagents.py:346-397,738-744`
- Test: `tests/runtime/test_subagents.py`
- Regress: `tests/runtime/test_host.py`, `tests/runtime/test_runner.py`,
  `tests/scenarios/test_phase7_subagents.py`
- Modify: closeout `PROGRESS.md`

## Steps

1. Confirm call sites:

   ```bash
   rg -n "_ensure_json_input|_extract_content|_extract_reasoning_content|_extract_tool_calls|_extract_usage|_extract_response_meta|_extract_raw_response" \
     app core runtime tools extensions
   ```

   Expected: the `_SubagentRuntimeHost` methods have no production callers;
   `RuntimeRunner` already imports canonical helpers from `core.llm`.

2. Run characterization:

   ```bash
   uv run pytest -q tests/runtime/test_host.py tests/runtime/test_runner.py \
     tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py
   ```

3. Delete the unused `_SubagentRuntimeHost` extraction/input adapter methods
   and the now-unused `_attr` and `_response_message` functions. Remove imports
   made unused by the deletion.

4. Do not add forwarding wrappers. If a genuine caller appears, import and call
   `parse_tool_input`, `extract_response_content`,
   `extract_reasoning_content`, `extract_usage`, `extract_tool_calls`,
   `extract_response_meta`, or `serialize_response` directly from `core.llm`.

5. Run:

   ```bash
   uv run pytest -q tests/runtime/test_host.py tests/runtime/test_runner.py \
     tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py \
     tests/scenarios/test_lean_runtime_characterization.py
   uv run ruff check runtime/subagents.py
   uv run pytest -q
   wc -l runtime/subagents.py
   git diff --check
   ```

6. Update progress and commit:

   ```bash
   git commit -am "refactor(R3-03): share response normalization"
   ```

## Acceptance

- No duplicate response extraction methods remain in the subagent host.
- Main/subagent runner and completion scenarios pass unchanged.
- No forwarding abstraction replaces the deleted code.
