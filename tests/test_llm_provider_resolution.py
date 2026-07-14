"""LLM provider resolution tests."""

import os
import subprocess
import sys

import pytest

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
        "SILICONFLOW_BASE_URL",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("provider", ["SiliconFlow", "silicon-flow", "silicon_flow"])
def test_provider_name_is_normalized_for_siliconflow(monkeypatch, provider):
    _clean_llm_env(monkeypatch)
    llm = HelloAgentsLLM(
        model="Qwen/Qwen2.5-7B-Instruct",
        provider=provider,
        api_key="sk-test",
        base_url="https://api.siliconflow.cn/v1",
    )

    assert llm.provider == "siliconflow"


def test_auto_detect_provider_by_base_url_for_siliconflow(monkeypatch):
    _clean_llm_env(monkeypatch)
    llm = HelloAgentsLLM(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key="sk-test",
        base_url="https://api.siliconflow.cn/v1",
    )

    assert llm.provider == "siliconflow"


def test_siliconflow_base_url_is_normalized(monkeypatch):
    _clean_llm_env(monkeypatch)
    llm = HelloAgentsLLM(
        model="Qwen/Qwen2.5-7B-Instruct",
        provider="siliconflow",
        api_key="sk-test",
        base_url="https://api.siliconflow.cn/v1/chat/completions",
    )

    assert llm.base_url == "https://api.siliconflow.cn/v1"


@pytest.mark.parametrize(
    ("provider", "key_env", "default_url", "default_model"),
    [
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-3.5-turbo"),
        ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com", "deepseek-chat"),
        (
            "qwen",
            "DASHSCOPE_API_KEY",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen-plus",
        ),
        (
            "modelscope",
            "MODELSCOPE_API_KEY",
            "https://api-inference.modelscope.cn/v1",
            "Qwen/Qwen2.5-72B-Instruct",
        ),
        ("kimi", "KIMI_API_KEY", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
        ("zhipu", "ZHIPU_API_KEY", "https://open.bigmodel.cn/api/paas/v4", "glm-4"),
        (
            "siliconflow",
            "SILICONFLOW_API_KEY",
            "https://api.siliconflow.cn/v1",
            "Qwen/Qwen2.5-7B-Instruct",
        ),
        ("ollama", "OLLAMA_API_KEY", "http://localhost:11434/v1", "llama3.2"),
        (
            "vllm",
            "VLLM_API_KEY",
            "http://localhost:8000/v1",
            "meta-llama/Llama-2-7b-chat-hf",
        ),
        ("local", "LLM_API_KEY", "http://localhost:8000/v1", "local-model"),
    ],
)
def test_explicit_provider_profile(
    monkeypatch, provider, key_env, default_url, default_model
):
    _clean_llm_env(monkeypatch)
    monkeypatch.setenv(key_env, "profile-key")

    llm = HelloAgentsLLM(provider=provider)

    assert llm.provider == provider
    assert llm.api_key == "profile-key"
    assert llm.base_url == default_url
    assert llm.model == default_model


def test_auto_provider_uses_generic_llm_values(monkeypatch):
    _clean_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "generic-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_MODEL_ID", "generic-model")

    llm = HelloAgentsLLM(provider="auto")

    assert (llm.provider, llm.api_key, llm.base_url, llm.model) == (
        "auto",
        "generic-key",
        "https://gateway.example/v1",
        "generic-model",
    )


def test_process_environment_wins_over_dotenv_and_constructor_wins_over_both(tmp_path):
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "LLM_PROVIDER=deepseek",
                "LLM_API_KEY=dotenv-key",
                "LLM_BASE_URL=https://dotenv.example/v1",
                "LLM_MODEL_ID=dotenv-model",
            )
        ),
        encoding="utf-8",
    )
    environment = os.environ | {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "process-key",
        "LLM_BASE_URL": "https://process.example/v1",
        "LLM_MODEL_ID": "process-model",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from core.config import Config; from core.llm import HelloAgentsLLM; "
            "from_env = HelloAgentsLLM(); "
            "llm = HelloAgentsLLM(model='constructor-model', api_key='constructor-key', "
            "base_url='https://constructor.example/v1', provider='qwen'); "
            "print('|'.join((from_env.provider, from_env.api_key, from_env.base_url, from_env.model))); "
            "print('|'.join((llm.provider, llm.api_key, llm.base_url, llm.model)))",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "openai|process-key|https://process.example/v1|process-model",
        "qwen|constructor-key|https://constructor.example/v1|constructor-model",
    ]

    dotenv_environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL_ID",
            "LLM_PROVIDER",
            "OPENAI_API_KEY",
        }
    } | {"LLM_PROVIDER": "openai"}
    dotenv_result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from core.config import Config; from core.llm import HelloAgentsLLM; "
            "llm = HelloAgentsLLM(); "
            "print('|'.join((llm.provider, llm.api_key, llm.base_url, llm.model)))",
        ],
        cwd=tmp_path,
        env=dotenv_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert (
        dotenv_result.stdout.strip()
        == "openai|dotenv-key|https://dotenv.example/v1|dotenv-model"
    )
