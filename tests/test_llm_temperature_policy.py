"""LLM temperature policy tests."""

from core.llm import HelloAgentsLLM


class _DummyCompletions:
    def __init__(self, recorder: dict):
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.clear()
        self._recorder.update(kwargs)
        return {"ok": True}


class _DummyChat:
    def __init__(self, recorder: dict):
        self.completions = _DummyCompletions(recorder)


class _DummyClient:
    def __init__(self, recorder: dict):
        self.chat = _DummyChat(recorder)


def test_kimi_25_temperature_is_forced_to_one(monkeypatch):
    recorder = {}
    monkeypatch.setattr(HelloAgentsLLM, "_create_client", lambda self: _DummyClient(recorder))

    llm = HelloAgentsLLM(
        model="kimi2.5",
        provider="kimi",
        api_key="test-key",
        base_url="https://api.moonshot.cn/v1",
        temperature=0.3,
    )
    llm.invoke_raw([{"role": "user", "content": "hi"}])

    assert recorder["temperature"] == 1


def test_non_kimi_model_keeps_configured_temperature(monkeypatch):
    recorder = {}
    monkeypatch.setattr(HelloAgentsLLM, "_create_client", lambda self: _DummyClient(recorder))

    llm = HelloAgentsLLM(
        model="deepseek-chat",
        provider="deepseek",
        api_key="test-key",
        base_url="https://api.deepseek.com",
        temperature=0.3,
    )
    llm.invoke_raw([{"role": "user", "content": "hi"}])

    assert recorder["temperature"] == 0.3


def test_invoke_raw_omits_none_max_tokens(monkeypatch):
    recorder = {}
    monkeypatch.setattr(HelloAgentsLLM, "_create_client", lambda self: _DummyClient(recorder))

    llm = HelloAgentsLLM(
        model="MiniMax-M2.1",
        provider="auto",
        api_key="test-key",
        base_url="https://api.minimaxi.com/v1",
        temperature=1,
        max_tokens=None,
    )
    llm.invoke_raw([{"role": "user", "content": "hi"}])

    assert "max_tokens" not in recorder


def test_minimax_request_enforces_n_one_and_omits_auto_tool_choice(monkeypatch):
    recorder = {}
    monkeypatch.setattr(HelloAgentsLLM, "_create_client", lambda self: _DummyClient(recorder))

    llm = HelloAgentsLLM(
        model="MiniMax-M2.1",
        provider="auto",
        api_key="test-key",
        base_url="https://api.minimaxi.com/v1",
        temperature=1,
    )
    llm.invoke_raw(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "Ping", "description": "ping", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}}],
        tool_choice="auto",
    )

    assert recorder["n"] == 1
    assert "tool_choice" not in recorder


def test_minimax_merges_multiple_system_messages(monkeypatch):
    recorder = {}
    monkeypatch.setattr(HelloAgentsLLM, "_create_client", lambda self: _DummyClient(recorder))

    llm = HelloAgentsLLM(
        model="MiniMax-M2.1",
        provider="auto",
        api_key="test-key",
        base_url="https://api.minimaxi.com/v1",
        temperature=1,
    )
    llm.invoke_raw(
        [
            {"role": "system", "content": "S1"},
            {"role": "system", "content": "S2"},
            {"role": "user", "content": "U"},
        ]
    )

    sent_messages = recorder["messages"]
    assert len([m for m in sent_messages if m.get("role") == "system"]) == 1
    assert sent_messages[0]["role"] == "system"
    assert "S1" in sent_messages[0]["content"]
    assert "S2" in sent_messages[0]["content"]
