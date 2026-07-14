"""Contracts for the core standard-library OpenAI-compatible transport."""

from __future__ import annotations

import json


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _StreamingResponse(_Response):
    def __iter__(self):
        return iter(
            [
                b"event: message\n",
                b'data: {"choices":[{"delta":{"content":"one"}}]}\n',
                b'data: {"choices":[{"delta":{"content":"two"}}]}\n',
                b"data: [DONE]\n",
            ]
        )


def test_chat_completions_posts_openai_shape_and_exposes_attribute_response(monkeypatch):
    from core.openai_compat import OpenAICompatibleClient
    import core.openai_compat as transport

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(b'{"choices":[{"message":{"content":"hello"}}]}')

    monkeypatch.setattr(transport, "urlopen", fake_urlopen)
    response = OpenAICompatibleClient("secret", "https://example.test/v1", 12).chat.completions.create(
        model="test-model", messages=[{"role": "user", "content": "hi"}]
    )

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["body"]["model"] == "test-model"
    assert captured["timeout"] == 12
    assert response.choices[0].message.content == "hello"
    assert response.model_dump() == {"choices": [{"message": {"content": "hello"}}]}


def test_chat_completions_stream_yields_sse_chunks(monkeypatch):
    from core.openai_compat import OpenAICompatibleClient

    client = OpenAICompatibleClient("secret", "https://example.test/v1", 12)
    monkeypatch.setattr(client, "_request", lambda _payload: _StreamingResponse(b""))

    chunks = list(
        client.chat.completions.create(
            model="test-model", messages=[{"role": "user", "content": "hi"}], stream=True
        )
    )

    assert [chunk.choices[0].delta.content for chunk in chunks] == ["one", "two"]
