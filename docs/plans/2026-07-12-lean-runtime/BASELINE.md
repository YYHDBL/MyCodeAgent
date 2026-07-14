# Lean Runtime Baseline

Captured on 2026-07-12 from the committed source head
`cf0d0a02aa1f5c201bbefad56849c24ca2dba1a9` in the isolated
`lean-runtime-20260712` worktree.

## Source protection

```sh
git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent status --short
```

Recorded user-owned source changes:

```text
 M extensions/skill_evolution/adapter.py
 M extensions/skill_evolution/evolution/buffer.py
 M extensions/skill_evolution/evolution/observer.py
 M extensions/skill_evolution/evolution/success_store.py
 M runtime/session.py
 M tools/builtin/bash.py
```

The implementation worktree started clean at the same committed head. No source
file was reset, stashed, changed, or committed.

## Environment and dependency baseline

```sh
python3 --version
uv --version
sed -n '1,240p' requirements.txt
sed -n '1,240p' requirements-dev.txt
```

```text
Host Python: 3.14.3
uv: 0.9.8
Isolated test Python: 3.12.12 (created with `uv venv .venv --python python3`)
Core requirements: openai, pydantic, mcp, anyio, python-dotenv, rich,
prompt_toolkit (7 declared dependencies)
Dev requirements: pytest
```

`uv` creates environments without `pip` by design in this setup, so
`.venv/bin/python -m pip install ...` failed with `No module named pip`.
The isolated environment was repaired without product changes using:

```sh
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
```

## Measurement definitions

The stable-production metric excludes the planned research directory
`extensions/skill_evolution/` but includes current optional extensions. It is
reproducible with:

```sh
rg --files app core runtime tools extensions -g '*.py' \
  | rg -v '^extensions/skill_evolution/' | xargs wc -l | tail -1
```

Other baseline counts:

```sh
rg --files tests -g '*.py' | xargs wc -l | tail -1
rg --files experimental/teams tools/builtin prompts/tools_prompts -g '*.py' \
  | rg '(^experimental/teams/|/team_|/send_message)' | xargs wc -l | tail -1
rg --files extensions/skill_evolution -g '*.py' | xargs wc -l | tail -1
rg --files docs -g '*.md' | xargs wc -l | tail -1
```

| Metric | Baseline |
|---|---:|
| Stable production Python LOC | 19,320 |
| Test Python LOC | 17,904 |
| Teams-related Python LOC | 4,208 |
| Skill Evolution Python LOC | 2,070 |
| Markdown documentation LOC | 10,393 |

## Default-path inventory

`Config()` defaults include `long_term_memory_enabled=True` and
`enable_verification_agent=True`. `CodeAgent` constructor defaults include
`enable_mcp=True`, `enable_skills=True`, and `enable_tracing=True`. Agent Teams
and Skill Evolution are false by default, but their code remains on the stable
path behind flags.

The following command builds the registered core tool set with a fake LLM and
optional integrations disabled so it does not require credentials or start MCP:

```sh
.venv/bin/python - <<'PY'
from argparse import Namespace
from app.bootstrap import build_runtime

class DummyLLM:
    def __init__(self, **kwargs):
        self.model = kwargs.get('model') or 'baseline-model'
        self.provider = kwargs.get('provider') or 'baseline'

args = Namespace(name='baseline', model='baseline-model', api_key=None,
    base_url=None, provider='openai', temperature=None, system=None,
    teammate_mode=None, skill_evolution=False)
runtime = build_runtime(args, project_root='.', llm_class=DummyLLM,
    extension_flags={'mcp': False, 'skills': False, 'tracing': False})
print(len(runtime.tool_registry.list_tools()))
print('\n'.join(sorted(runtime.tool_registry.list_tools())))
PY
```

It reported 12 tools:

```text
AskUser, Bash, Edit, Glob, Grep, LS, Memory, MultiEdit, Read, Task, TodoWrite, Write
```

The final `agent.shutdown()` call in the exploratory command was invalid because
the current API exposes `close()` instead. The tool inventory printed before
that cleanup error; this is a baseline API defect/ambiguity to eliminate during
the runtime simplification, not a test failure.

## Test and startup evidence

```sh
.venv/bin/python -m pytest --collect-only -q
/usr/bin/time -p .venv/bin/python -m pytest -q
/usr/bin/time -p .venv/bin/python main.py --help
```

```text
Collection: 861 tests collected in 1.80s
Suite: 861 passed, 6 subtests passed in 7.74s (wall clock: 8.16s)
Help: exit 0, real 0.52s
```

`main.py --help` emitted the legacy help surface, including team display and
Skill Evolution flags. A direct runtime-build probe without an explicit
provider failed because the local environment contains conflicting provider
variables (`deepseek`, `qwen`, and `zhipu`). This did not affect help or the
test suite; deterministic tests use fake or explicit providers.
