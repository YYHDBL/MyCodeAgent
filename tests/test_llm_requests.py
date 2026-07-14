"""Characterization tests for the shared model request boundary."""

from types import SimpleNamespace

import pytest

from core.exceptions import HelloAgentsException
from core.llm import HelloAgentsLLM


def _response(content: str = "response"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class _Completions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _llm(monkeypatch, *, provider="openai", model="gpt-test", base_url=None):
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    monkeypatch.delenv("LLM_RETRY_BACKOFF", raising=False)
    return HelloAgentsLLM(
        provider=provider,
        model=model,
        api_key="test-key",
        base_url=base_url or "https://api.example/v1",
    )


def _set_completions(llm, outcomes):
    completions = _Completions(outcomes)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return completions


def test_invoke_raw_returns_the_unprojected_client_response(monkeypatch):
    llm = _llm(monkeypatch)
    response = _response()
    completions = _set_completions(llm, [response])

    assert llm.invoke_raw([{"role": "user", "content": "hello"}]) is response
    assert "stream" not in completions.requests[0]


def test_invoke_projects_message_content_from_the_same_response_shape(monkeypatch):
    llm = _llm(monkeypatch)
    _set_completions(llm, [_response("projected")])

    assert llm.invoke([{"role": "user", "content": "hello"}]) == "projected"


def test_invoke_retries_empty_choices_before_wrapping_the_final_failure(monkeypatch):
    llm = _llm(monkeypatch)
    llm.max_retries = 1
    completions = _set_completions(
        llm, [SimpleNamespace(choices=[]), SimpleNamespace(choices=[])]
    )
    monkeypatch.setattr("core.llm.time.sleep", lambda _: None)

    with pytest.raises(HelloAgentsException, match="LLM调用失败") as error:
        llm.invoke([{"role": "user", "content": "empty"}])

    assert str(error.value).count("LLM调用失败") == 1
    assert len(completions.requests) == 2


def test_nonstream_request_retries_with_exponential_backoff(monkeypatch):
    llm = _llm(monkeypatch)
    llm.max_retries = 2
    llm.retry_backoff = 0.25
    completions = _set_completions(
        llm, [RuntimeError("temporary"), RuntimeError("temporary"), _response("ok")]
    )
    sleeps = []
    monkeypatch.setattr("core.llm.time.sleep", sleeps.append)

    assert llm.invoke([{"role": "user", "content": "retry"}]) == "ok"
    assert len(completions.requests) == 3
    assert sleeps == [0.25, 0.5]


def test_nonstream_final_failure_is_wrapped_once_after_all_retries(monkeypatch):
    llm = _llm(monkeypatch)
    llm.max_retries = 1
    completions = _set_completions(llm, [RuntimeError("temporary"), RuntimeError("final")])
    monkeypatch.setattr("core.llm.time.sleep", lambda _: None)

    with pytest.raises(HelloAgentsException, match="LLM调用失败: final") as error:
        llm.invoke_raw([{"role": "user", "content": "retry"}])

    assert str(error.value).count("LLM调用失败") == 1
    assert len(completions.requests) == 2


def test_request_omits_none_values_and_keeps_minimax_policy(monkeypatch):
    llm = _llm(monkeypatch, provider="minimax", base_url="https://api.minimaxi.com/v1")
    completions = _set_completions(llm, [_response("ok")])

    llm.invoke(
        [{"role": "user", "content": "hello"}],
        max_tokens=None,
        metadata=None,
        tool_choice="auto",
    )

    request = completions.requests[0]
    assert "max_tokens" not in request
    assert "metadata" not in request
    assert "tool_choice" not in request
    assert request["n"] == 1


def test_stream_invoke_yields_nonempty_text_chunks(monkeypatch):
    llm = _llm(monkeypatch)
    chunks = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="one"))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="two"))]),
    ]
    completions = _set_completions(llm, [chunks])

    assert list(llm.stream_invoke([{"role": "user", "content": "stream"}])) == ["one", "two"]
    assert completions.requests[0]["stream"] is True
