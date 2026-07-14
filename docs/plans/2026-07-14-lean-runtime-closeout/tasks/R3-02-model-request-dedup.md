# R3-02 Share Model Request and Retry Handling

**Goal:** Remove duplicate request construction/retry loops while preserving
the public model adapter behavior.

**Files:**

- Modify: `core/llm.py:437-679`
- Create or modify: `tests/test_llm_requests.py`
- Retain/regress: `tests/test_llm_temperature_policy.py`
- Modify: closeout `PROGRESS.md`

## Steps

1. Add focused characterization tests for:

   - `invoke_raw` returns the raw response;
   - `invoke` returns message content from the same response shape;
   - a transient client exception retries exactly `max_retries` times;
   - retry sleeps use the configured exponential backoff;
   - final failure is wrapped once as `HelloAgentsException`;
   - `None` request values are omitted;
   - MiniMax and Kimi policies remain applied;
   - streaming still yields text chunks.

2. Run the new tests before refactoring. They should pass as characterization;
   if a missing contract is discovered, first write a failing regression and
   document whether it is a bug or an intended simplification.

3. Extract one request builder, for example:

   ```python
   def _build_request(self, messages, *, stream=False, **overrides):
       request = {
           "model": self.model,
           "messages": self._normalize_messages_for_provider(messages),
           "temperature": self._resolve_temperature(overrides.pop("temperature", None)),
           "max_tokens": overrides.pop("max_tokens", self.max_tokens),
           "stream": stream or None,
           **overrides,
       }
       return self._apply_provider_compat(self._compact_request_kwargs(request))
   ```

4. Extract one non-streaming retry helper. `invoke_raw` calls it directly;
   `invoke` projects content from its result. Do not add async support,
   middleware, hooks, or a generalized transport abstraction.

5. Keep `think`/`stream_invoke` behavior and route their request construction
   through the same builder where practical. Do not silently add retries to
   streaming unless a test and decision explicitly require it.

6. Run:

   ```bash
   uv run pytest -q tests/test_llm_requests.py tests/test_llm_temperature_policy.py \
     tests/test_llm_provider_resolution.py tests/runtime/test_model_errors.py
   uv run ruff check core/llm.py tests/test_llm_requests.py
   uv run pytest -q
   wc -l core/llm.py
   git diff --check
   ```

   The combined R3-01/R3-02 change should materially reduce `core/llm.py`; a
   suggested guardrail is at most 480 lines, but behavior and clarity take
   precedence over forcing this advisory number.

7. Update progress and commit:

   ```bash
   git add core/llm.py tests/test_llm_requests.py \
     docs/plans/2026-07-14-lean-runtime-closeout/PROGRESS.md
   git commit -m "refactor(R3-02): share model request handling"
   ```

## Acceptance

- One non-streaming retry loop remains.
- One request builder owns normalization and omission of `None` fields.
- All public methods and provider quirks retain covered behavior.
