# R0-01 Closeout Baseline and Safety Lock

Captured in the dedicated implementation worktree before any product change.
The command results below were captured on 2026-07-14 CST; the observed
capture timestamp after the gate run was `2026-07-14 11:39:44 CST (+0800)`.

## Worktree identity

```text
$ pwd
/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712
exit=0

$ git status --short --branch
## lean-runtime-20260712
exit=0

$ git log -1 --oneline --decorate
8f165ed (HEAD -> lean-runtime-20260712) docs: add lean runtime closeout execution plan
exit=0

$ git branch -vv --list lean-runtime-20260712 feature/skill-evolution
+ feature/skill-evolution cf0d0a0 (/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent) [origin/feature/skill-evolution: ahead 1] docs: add lean runtime execution plan
* lean-runtime-20260712   8f165ed docs: add lean runtime closeout execution plan
exit=0

$ git merge-base --is-ancestor feature/skill-evolution lean-runtime-20260712
exit=0
```

`feature/skill-evolution` is therefore an ancestor of the implementation
branch. The implementation worktree was clean before these evidence files.

## Protected original worktree

The original worktree is read-only for this closeout:

```text
/Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent
```

```text
$ git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent status --short --branch
## feature/skill-evolution...origin/feature/skill-evolution [ahead 1]
 M extensions/skill_evolution/adapter.py
 M extensions/skill_evolution/evolution/buffer.py
 M extensions/skill_evolution/evolution/observer.py
 M extensions/skill_evolution/evolution/success_store.py
 M runtime/session.py
 M tools/builtin/bash.py
exit=0

$ git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent log -1 --oneline --decorate
cf0d0a0 (HEAD -> feature/skill-evolution) docs: add lean runtime execution plan
exit=0

$ git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent diff --numstat -- extensions/skill_evolution/adapter.py extensions/skill_evolution/evolution/buffer.py extensions/skill_evolution/evolution/observer.py extensions/skill_evolution/evolution/success_store.py runtime/session.py tools/builtin/bash.py
0	1	extensions/skill_evolution/adapter.py
3	1	extensions/skill_evolution/evolution/buffer.py
1	1	extensions/skill_evolution/evolution/observer.py
3	1	extensions/skill_evolution/evolution/success_store.py
3	1	runtime/session.py
16	0	tools/builtin/bash.py
exit=0
```

The required default-locale hash command encountered an environment failure
before it could read a digest:

```text
$ git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent diff --binary -- extensions/skill_evolution/adapter.py extensions/skill_evolution/evolution/buffer.py extensions/skill_evolution/evolution/observer.py extensions/skill_evolution/evolution/success_store.py runtime/session.py tools/builtin/bash.py | shasum -a 256
perl: warning: Setting locale failed.
perl: warning: Please check that your locale settings:
	LC_ALL = "C.UTF-8",
	LC_CTYPE = "C.UTF-8",
	LANG = "C.UTF-8"
    are supported and installed on your system.
perl: warning: Falling back to the standard locale ("C").
panic: locale.c: 4486: Could not change LC_CTYPE locale to C.UTF-8, errno=9
pipeline_exit=9
```

The same required diff was then hashed with an explicit portable locale; this
does not modify the original worktree:

```text
$ LC_ALL=C LANG=C git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent diff --binary -- extensions/skill_evolution/adapter.py extensions/skill_evolution/evolution/buffer.py extensions/skill_evolution/evolution/observer.py extensions/skill_evolution/evolution/success_store.py runtime/session.py tools/builtin/bash.py | LC_ALL=C LANG=C shasum -a 256
655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce  -
exit=0
```

Protected paths, status, per-path numstat, and this binary-diff SHA-256 are
the R0 comparison baseline. A read-only recheck after writing the evidence
returned the same six status entries and the same
`655b2ab23db92f4d3811a235cb5358edfe7c2235041f6fa41bc1fb324b5790ce`
digest (both commands exited 0).

## Baseline gates

```text
$ uv run pytest -q
548 passed, 1 deselected, 6 subtests passed in 3.45s
exit=0 elapsed_seconds=3

$ uv run pytest -q tests/scenarios
23 passed in 0.44s
exit=0 elapsed_seconds=0

$ uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
20 passed, 6 subtests passed in 0.54s
exit=0 elapsed_seconds=0

$ uv run ruff check .
All checks passed!
exit=0 elapsed_seconds=0

$ uv lock --check
Resolved 46 packages in 2ms
exit=0 elapsed_seconds=0
```

The strict pre-closeout lint gate fails as expected. Its exact displayed
command reported `Found 100 errors` and exit 1. A fresh JSON rendering of the
same selection gave the reproducible count by rule:

```text
$ uv run ruff check . --select E402,E722,F401,F541,F821,F841
Found 100 errors.
exit=1 elapsed_seconds=0

$ json=$(uv run ruff check . --select E402,E722,F401,F541,F821,F841 --output-format json); rc=$?; printf '%s' "$json" | uv run python -c 'import collections,json,sys; findings=json.load(sys.stdin); counts=collections.Counter(item["code"] for item in findings); print(f"findings={len(findings)}"); print("by_code=" + ", ".join(f"{code}:{counts[code]}" for code in sorted(counts)))'; printf 'ruff_exit=%s\n' "$rc"
findings=100
by_code=E402:49, E722:2, F401:45, F541:2, F821:1, F841:1
ruff_exit=1
```

The blocking undefined-name result is:

```text
F821 Undefined name `SubagentCompletionVerifier`
  --> runtime/host.py:122:40
```

The remaining strict findings are distributed across `app/cli.py` (4),
`core/env.py` (1), `demo/harness_portfolio.py` (13),
`prompts/agents_prompts/subagent_summary_prompt.py` (1),
`runtime/completion.py` (1), `runtime/host.py` (26), test files (41),
`tools/builtin/bash.py` (1), `tools/builtin/read_file.py` (1),
`tools/builtin/todo_write.py` (2), `tools/registry.py` (2), and
`utils/ui_components.py` (7). The rule totals above are authoritative for
R1's concrete cleanup checklist.

```text
$ uv run python scripts/check_release_metrics.py
release metric failure: stable production Python exceeds 14000: 14243
stable_production_python_lines=14243
stable_tool_count=7
stable_tools=Bash, Edit, Glob, Grep, Read, Task, TodoWrite
exit=1 elapsed_seconds=0
```

## Network-free enabled-verifier reproduction

This harness called `app.bootstrap.build_runtime` with a dummy LLM constructor
and a `Config(enable_verification_agent=True, enable_mcp=False,
enable_skills=False, enable_tracing=False)` returned by the injected config
class. It did not make a model or network call.

```text
$ uv run python - <<'PY'
from argparse import Namespace

from app.bootstrap import build_runtime
from core.config import Config


class DummyLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class EnabledConfig(Config):
    @classmethod
    def from_env(cls):
        return Config(
            enable_verification_agent=True,
            enable_mcp=False,
            enable_skills=False,
            enable_tracing=False,
        )


args = Namespace(cwd='.')
try:
    build_runtime(
        args,
        project_root='.',
        config_class=EnabledConfig,
        llm_class=DummyLLM,
    )
except Exception:
    import traceback
    traceback.print_exc()
    raise
PY
Traceback (most recent call last):
  File "<stdin>", line 21, in <module>
  File "/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712/app/bootstrap.py", line 98, in build_runtime
    agent = agent_class(**agent_kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712/runtime/host.py", line 96, in __init__
    self._initialize_runtime_components()
  File "/Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712/runtime/host.py", line 122, in _initialize_runtime_components
    self.completion_verifier = SubagentCompletionVerifier(
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^
NameError: name 'SubagentCompletionVerifier' is not defined
exit=1
```

The failure is therefore deterministic at `runtime/host.py:122`, before an
LLM/network operation. R1-01 owns the repair.

## Installed CLI help from an unrelated repository

The first attempt installed successfully but its Python timing wrapper did not
prepend the venv `bin` directory to `PATH`, so `subprocess.run(["mycodeagent",
"--help"])` raised `FileNotFoundError`. The following fresh rerun used a new
Python 3.12 venv and an unrelated temporary Git repository, with that venv
activated for the child command:

```text
$ uv venv --python 3.12 /tmp/mycodeagent-r0-venv.FzJhKa
Using CPython 3.12.12
Creating virtual environment at: /tmp/mycodeagent-r0-venv.FzJhKa

$ uv pip install --python /tmp/mycodeagent-r0-venv.FzJhKa/bin/python -e .
Resolved 13 packages in 4ms
Built mycodeagent @ file:///Users/yyhdbl/.config/superpowers/worktrees/MyCodeAgent/lean-runtime-20260712
Installed 13 packages

$ git -C /tmp/mycodeagent-r0-repo.NBzbzc init -q
exit=0

$ (cd /tmp/mycodeagent-r0-repo.NBzbzc && PATH=/tmp/mycodeagent-r0-venv.FzJhKa/bin:$PATH mycodeagent --help)
usage: mycodeagent [-h] [--name NAME] [--system SYSTEM] [--provider PROVIDER] ...
Run the MyCodeAgent local coding harness
exit=0 elapsed_seconds=1.266
```

The installed console command passed under the three-second threshold without
using `uv run`; its full help output includes the documented MCP,
verification-agent, one-shot, JSON, and resume options.

## R0 result and next work

No product file was edited. The baseline identifies two product blockers:

1. Enabled verification-agent construction raises the recorded `NameError`.
2. The unchanged release metric is 14,243 stable production Python lines,
   243 lines above the 14,000 limit.

The strict lint baseline also records 100 findings so later gates can remove
the ignores without concealing the verifier crash. Next task IDs are
`R1-01` and `R2-01` according to the task graph; this task changes no product
behavior and does not begin either successor.
