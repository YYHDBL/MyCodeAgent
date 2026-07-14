"""Small synchronous transport for OpenAI-compatible chat-completions APIs."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ResponseObject:
    """Expose JSON response fields through the SDK-shaped attribute interface."""

    def __init__(self, value: dict[str, Any]):
        self._value = value

    def __getattr__(self, name: str) -> Any:
        try:
            return _to_object(self._value[name])
        except KeyError as exc:
            raise AttributeError(name) from exc

    def model_dump(self) -> dict[str, Any]:
        return self._value


def _to_object(value: Any) -> Any:
    if isinstance(value, dict):
        return ResponseObject(value)
    if isinstance(value, list):
        return [_to_object(item) for item in value]
    return value


class _Completions:
    def __init__(self, client: "OpenAICompatibleClient"):
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_completion(kwargs)


class _Chat:
    def __init__(self, client: "OpenAICompatibleClient"):
        self.completions = _Completions(client)


class OpenAICompatibleClient:
    """Subset of the official SDK used by ``HelloAgentsLLM`` without extra deps."""

    def __init__(self, api_key: str, base_url: str, timeout: int):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.chat = _Chat(self)

    def _request(self, payload: dict[str, Any]):
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            return urlopen(request, timeout=self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI-compatible API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"OpenAI-compatible API request failed: {exc.reason}") from exc

    def _create_completion(self, payload: dict[str, Any]) -> Any:
        if payload.get("stream"):
            return self._stream(payload)
        with self._request(payload) as response:
            return ResponseObject(json.loads(response.read().decode("utf-8")))

    def _stream(self, payload: dict[str, Any]):
        with self._request(payload) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                if data:
                    yield ResponseObject(json.loads(data))
