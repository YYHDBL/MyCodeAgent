# R3-01 Data-Drive Provider Resolution

**Goal:** Replace repeated provider credential/default branches and private
dotenv caching with one small provider metadata boundary.

**Files:**

- Modify: `core/llm.py:133-560`
- Test: `tests/test_llm_provider_resolution.py`
- Test: `tests/test_app_bootstrap.py`
- Modify if behavior wording changes: `.env.example`, `README.md`
- Modify: closeout `DECISIONS.md`, `PROGRESS.md`

## Required Behavior

- Explicit constructor/CLI values win over environment values.
- Process environment wins over `.env`; `.env` fills missing values only.
- Explicit provider profiles retain their API-key names, base URL, and default
  model.
- `provider=auto` remains a generic OpenAI-compatible route using `LLM_*`.
- URL/provider aliases may be data-driven conveniences; opaque API-key-format
  guessing is not a required product capability.
- Kimi and MiniMax request quirks remain covered but are not provider-profile
  credential logic.

## Steps

1. Expand provider tests into a table covering retained profiles:

   ```python
   @pytest.mark.parametrize(
       ("provider", "key_env", "default_url", "default_model"),
       [
           ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-3.5-turbo"),
           ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com", "deepseek-chat"),
           # qwen, modelscope, kimi, zhipu, siliconflow, ollama, vllm, local
       ],
   )
   def test_explicit_provider_profile(...): ...
   ```

   Also add a precedence test using conflicting constructor, process-env, and
   `.env` values. Use a subprocess or resettable environment boundary so the
   global environment-loader cache cannot make the test order-dependent.

2. Run provider/bootstrap tests before refactoring and record the
   characterization result.

3. Introduce one immutable metadata map. A compact shape is sufficient:

   ```python
   PROVIDER_PROFILES = {
       "openai": {
           "key_envs": ("OPENAI_API_KEY",),
           "base_url_envs": (),
           "base_url": "https://api.openai.com/v1",
           "model": "gpt-3.5-turbo",
           "url_markers": ("api.openai.com",),
       },
       # retained profiles
   }
   ```

   Do not create a registry framework, plugin interface, or one-class-per
   provider hierarchy.

4. Rewrite `_resolve_credentials`, default-model selection, aliases, and URL
   detection as short table lookups. Delete key-format/port heuristics that are
   neither tested nor documented; record any deliberate compatibility change
   in `DECISIONS.md` and README.

5. Delete `HelloAgentsLLM._dotenv_values` and `_load_dotenv_first`. Use the
   existing `core.env.load_env` application boundary; `_get_env` should read the
   process environment only.

6. Run:

   ```bash
   uv run pytest -q tests/test_llm_provider_resolution.py \
     tests/test_llm_temperature_policy.py tests/test_app_bootstrap.py \
     tests/test_core_without_mcp.py
   uv run ruff check core/llm.py tests/test_llm_provider_resolution.py
   uv run pytest -q
   uv run python scripts/check_release_metrics.py || true
   git diff --check
   ```

7. Review the diff specifically for changed provider precedence, default model,
   endpoints, and secrets in logs. Update progress and commit:

   ```bash
   git commit -am "refactor(R3-01): data-drive provider resolution"
   ```

## Acceptance

- Provider mapping is visibly data-driven.
- No private dotenv cache/loader remains in `HelloAgentsLLM`.
- Tests cover explicit profiles, generic auto mode, aliases, base URL
  normalization, and precedence.
- No dependency is added.
