# M4-05 Cleanup Report

Date: 2026-07-13

This report records only code proved unused or replaced by an existing direct
consumer. It does not claim prospective line-count savings.

## Deleted layers

| Removed path or surface | Lines removed | Evidence |
| --- | ---: | --- |
| `core/agent.py` | 34 | `rg -n --glob '*.py' 'from core\\.agent\\|import core\\.agent' app core runtime tools extensions tests` found one production consumer, `runtime.host.CodeAgent`. Its four base fields are now directly initialized by that only implementation; the maintenance contract asserts no base protocol remains. |
| `runtime/observation_store.py` | 19 | It only re-exported `tools.observation_store`; the only non-document caller was one context test, now importing the owning tools boundary directly. |
| `tools/observation_budget.py` | 5 | It only re-exported `force_truncate_result`; `tools/orchestrator.py` now imports that existing function directly from `tools.observation_store`. |
| `utils/serialization.py` | 1 | The file contained only a docstring and the whole-tree call-site scan found no imports. |
| `tools/builtin/ask_user.py` and `prompts/tools_prompts/ask_user_prompt.py` | 90 | Default registration exposed an eighth schema item despite the seven-tool product limit. The test-first contract failed before deletion and now specifies the exact retained default surface. Its error code, permission special case, subagent exclusions, tests, and active docs were deleted with it. |

The before-removal file counts above are reproducible from the deletion
parent, rather than the current tree where these paths are intentionally
absent:

```bash
BASE=d48a38a^
for item in core/agent.py runtime/observation_store.py tools/observation_budget.py \
  utils/serialization.py tools/builtin/ask_user.py prompts/tools_prompts/ask_user_prompt.py; do
  printf '%s ' "$item"; git show "$BASE:$item" | wc -l
done
```

The committed M4-05 diff is **184 insertions and 189 deletions**:

```bash
git show --shortstat --format= d48a38a
```

Excluding this report itself yields 113 insertions and 189 deletions; limiting
the same committed diff to production and test paths yields 60 insertions and
185 deletions. Those filtered figures use these exact filters:

```bash
git show --numstat --format= d48a38a |
  awk -F '\t' '$3 != "docs/plans/2026-07-12-lean-runtime/CLEANUP_REPORT.md" {
    add += $1; del += $2
  } END { printf "%d additions, %d deletions\n", add, del }'

git show --numstat --format= d48a38a |
  awk -F '\t' '$3 ~ /^(app|core|extensions|prompts|runtime|tools|utils|tests)\// {
    add += $1; del += $2
  } END { printf "%d additions, %d deletions\n", add, del }'
```

## Contracts and scans

The new deterministic default-schema contract is:

```text
Bash, Edit, Glob, Grep, Read, Task, TodoWrite
```

Before the removal,
`uv run pytest -q tests/test_lean_defaults.py::test_default_host_exposes_the_bounded_seven_tool_stable_schema`
failed because the OpenAI schema also contained `AskUser`. The post-cleanup
stable-source scan is:

```bash
rg -n --glob '*.py' --glob '*.md' --glob '*.json' --glob '!docs/plans/**' \
  --glob '!build/**' --glob '!*.egg-info/**' \
  'core\\.agent|runtime\\.observation_store|tools\\.observation_budget|utils\\.serialization|AskUser|ask_user|ASK_USER_UNAVAILABLE' . || true
```

It produces no output. Historical plan and baseline records are intentionally
excluded because they are migration evidence, not stable product surface.

## Consciously retained code

| Path | Why it remains |
| --- | --- |
| `runtime/session.py` | `runtime/transcript.py` actively imports its one-way `load_legacy_session_snapshot` reader during the M3-03 transcript migration. Decision D-014 permits that read-only conversion while prohibiting snapshot persistence. |
| `runtime/factory.py` | It is the direct three-function composition boundary retained by M3 Decision D-013: context construction, persistence construction, and deferred subagent creation. It is not a one-product factory class or compatibility re-export. |
| `tools/observation_store.py` | It is the active typed truncation owner used directly by the orchestrator and product-root scenarios. |

## Ponytail review

The required deletion-focused review examined the complete M4-05 diff after
the behavior-preserving `CodeAgent.__str__`/`__repr__` regression was
restored locally. No further compatibility layer, speculative abstraction, or
duplicate wrapper remained to cut: **Lean already. Ship.**

## Follow-up outside this task

Active historical design documents still mention the M4-03-removed `LS` /
`ListFiles` surface. They are not caused by this deletion batch and are
recorded for the planned M5-02 documentation reconciliation rather than being
silently broadened into M4-05.
