# R0-01 Baseline and Safety Lock

**Goal:** Establish reproducible closeout evidence without altering either
worktree.

**Files:**

- Create: `docs/plans/2026-07-14-lean-runtime-closeout/BASELINE.md`
- Modify: `docs/plans/2026-07-14-lean-runtime-closeout/PROGRESS.md`

## Steps

1. Verify implementation state:

   ```bash
   pwd
   git status --short --branch
   git log -1 --oneline --decorate
   git branch -vv --list lean-runtime-20260712 feature/skill-evolution
   git merge-base --is-ancestor feature/skill-evolution lean-runtime-20260712
   ```

   Expected: dedicated worktree, branch `lean-runtime-20260712`, clean before
   evidence files, and ancestor command exit 0.

2. Record the original worktree without changing it:

   ```bash
   git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent status --short --branch
   git -C /Users/yyhdbl/Documents/算法/mycodeagent_v2/MyCodeAgent diff --binary -- \
     extensions/skill_evolution/adapter.py \
     extensions/skill_evolution/evolution/buffer.py \
     extensions/skill_evolution/evolution/observer.py \
     extensions/skill_evolution/evolution/success_store.py \
     runtime/session.py tools/builtin/bash.py | shasum -a 256
   ```

3. Run fresh baseline gates:

   ```bash
   uv run pytest -q
   uv run pytest -q tests/scenarios
   uv run pytest -q tests/extensions/test_mcp_extension.py tests/test_core_without_mcp.py tests/test_mcp_protocol.py
   uv run ruff check .
   uv run ruff check . --select E402,E722,F401,F541,F821,F841
   uv lock --check
   uv run python scripts/check_release_metrics.py
   ```

4. Reproduce the enabled bootstrap in a network-free test harness. Use
   `build_runtime`, a `Config(enable_verification_agent=True, enable_mcp=False,
   enable_skills=False, enable_tracing=False)`, and a dummy LLM constructor.
   Record the exact exception and stack location.

5. Time installed help in an unrelated temporary Git repository. Reuse the
   M5-02 procedure; do not rely on `uv run` alone.

6. Write `BASELINE.md` containing exact commands, exit codes, counts, timing,
   strict-lint findings, metric values, protected diff hash, and current heads.

7. Run `git diff --check`, update progress, and commit:

   ```bash
   git add docs/plans/2026-07-14-lean-runtime-closeout
   git commit -m "docs(R0-01): capture closeout baseline"
   ```

## Acceptance

- No product file changed.
- Original worktree status and diff hash are recorded.
- The verifier failure and 14,243-line metric are independently reproduced or
  any changed result is recorded exactly.
