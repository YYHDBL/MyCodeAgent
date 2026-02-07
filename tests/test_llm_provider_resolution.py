"""LLM provider resolution tests."""

from core.llm import HelloAgentsLLM


def _clean_llm_env(monkeypatch):
    keys = [
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL_ID",
        "OPENAI_API_KEY",
        "ZHIPU_API_KEY",
        "GLM_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "MODELSCOPE_API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "OLLAMA_API_KEY",
        "OLLAMA_HOST",
        "VLLM_API_KEY",
        "VLLM_HOST",
        "SILICONFLOW_API_KEY",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_provider_name_is_normalized_for_siliconflow(monkeypatch, tmp_path):
    _clean_llm_env(monkeypatch)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_PROVIDER=SiliconFlow",
                "LLM_API_KEY=sk-test",
                "LLM_BASE_URL=https://api.siliconflow.cn/v1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    llm = HelloAgentsLLM(model="Qwen/Qwen2.5-7B-Instruct")

    assert llm.provider == "siliconflow"


def test_auto_detect_provider_by_base_url_for_siliconflow(monkeypatch, tmp_path):
    _clean_llm_env(monkeypatch)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_API_KEY=sk-test",
                "LLM_BASE_URL=https://api.siliconflow.cn/v1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    llm = HelloAgentsLLM(model="Qwen/Qwen2.5-7B-Instruct")

    assert llm.provider == "siliconflow"


def test_siliconflow_base_url_is_normalized(monkeypatch, tmp_path):
    _clean_llm_env(monkeypatch)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_PROVIDER=siliconflow",
                "LLM_API_KEY=sk-test",
                "LLM_BASE_URL=https://api.siliconflow.cn/v1/chat/completions",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    llm = HelloAgentsLLM(model="Qwen/Qwen2.5-7B-Instruct")

    assert llm.base_url == "https://api.siliconflow.cn/v1"
