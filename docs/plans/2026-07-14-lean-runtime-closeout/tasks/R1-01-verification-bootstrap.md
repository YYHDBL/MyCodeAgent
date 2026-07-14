# R1-01 Repair Verification-Agent Bootstrap

**Goal:** Make the advertised opt-in verification agent construct successfully
without adding default startup work.

**Files:**

- Modify: `runtime/host.py:118-125`
- Test: `tests/test_app_bootstrap.py`
- Modify: closeout `PROGRESS.md`

## Steps

1. Add a network-free failing test resembling:

   ```python
   def test_enabled_verification_agent_bootstraps(tmp_path):
       class EnabledConfig:
           @classmethod
           def from_env(cls):
               return Config(
                   enable_verification_agent=True,
                   enable_mcp=False,
                   enable_skills=False,
                   enable_tracing=False,
               )

       class DummyLLM:
           def __init__(self, **kwargs):
               self.model = kwargs.get("model")
               self.provider = kwargs.get("provider")

       runtime = build_runtime(
           Namespace(cwd=str(tmp_path)),
           config_class=EnabledConfig,
           llm_class=DummyLLM,
           extension_flags={"mcp": False, "skills": False, "tracing": False},
       )
       try:
           assert isinstance(runtime.agent.completion_verifier, SubagentCompletionVerifier)
       finally:
           runtime.agent.close()
   ```

2. Run only the new test. Expected RED: `NameError` at `runtime/host.py`.

3. Add the smallest lazy dependency inside the enabled branch:

   ```python
   if self.config.enable_verification_agent:
       from runtime.subagents import SubagentCompletionVerifier

       self.completion_verifier = SubagentCompletionVerifier(
           self._get_subagent_launcher()
       )
   ```

   Do not import or instantiate the verifier on the default path.

4. Run:

   ```bash
   uv run pytest -q tests/test_app_bootstrap.py tests/test_lean_defaults.py \
     tests/runtime/test_subagents.py tests/scenarios/test_phase7_subagents.py
   uv run ruff check runtime/host.py tests/test_app_bootstrap.py
   uv run pytest -q
   git diff --check
   ```

5. Update progress and commit:

   ```bash
   git commit -am "fix(R1-01): repair verification-agent bootstrap"
   ```

## Acceptance

- The new test demonstrates RED then GREEN.
- Enabled bootstrap constructs `SubagentCompletionVerifier`.
- Existing default test still proves `completion_verifier` is absent.
