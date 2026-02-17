"""HelloAgents统一LLM接口 - 基于OpenAI原生API"""

import logging
import os
import time
from typing import Literal, Optional, Iterator, Dict
from openai import OpenAI

from .exceptions import HelloAgentsException

logger = logging.getLogger(__name__)

# 支持的LLM提供商
SUPPORTED_PROVIDERS = Literal[
    "openai", "deepseek", "qwen", "modelscope",
    "kimi", "zhipu", "siliconflow", "ollama", "vllm", "local", "auto"
]

class HelloAgentsLLM:
    """
    为HelloAgents定制的LLM客户端。
    它用于调用任何兼容OpenAI接口的服务，并默认使用流式响应。

    设计理念：
    - 参数优先，环境变量兜底
    - 流式响应为默认，提供更好的用户体验
    - 支持多种LLM提供商
    - 统一的调用接口
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[SUPPORTED_PROVIDERS] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs
    ):
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        支持自动检测provider或使用统一的LLM_*环境变量配置。

        Args:
            model: 模型名称，如果未提供则从环境变量LLM_MODEL_ID读取
            api_key: API密钥，如果未提供则从环境变量读取
            base_url: 服务地址，如果未提供则从环境变量LLM_BASE_URL读取
            provider: LLM提供商，如果未提供则自动检测
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间，从环境变量LLM_TIMEOUT读取，默认60秒
        """
        # 优先加载 .env（如存在则读取配置）
        self._dotenv_values: Dict[str, str] = {}
        self._load_dotenv_first()

        # 优先使用传入参数，如果未提供，则从环境变量加载
        self.model = model or self._get_env("LLM_MODEL_ID")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout or int(self._get_env("LLM_TIMEOUT", "120"))
        self.max_retries = int(self._get_env("LLM_MAX_RETRIES", "2"))
        self.retry_backoff = float(self._get_env("LLM_RETRY_BACKOFF", "1.0"))
        self.kwargs = kwargs
        self._temperature_policy_notice_emitted = False

        # 自动检测provider或使用指定的provider
        self.provider = self._resolve_provider(provider, api_key, base_url)

        # 根据provider确定API密钥和base_url
        self.api_key, resolved_base_url = self._resolve_credentials(api_key, base_url)
        self.base_url = self._normalize_base_url(resolved_base_url)

        # 验证必要参数
        if not self.model:
            self.model = self._get_default_model()
        if not all([self.api_key, self.base_url]):
            raise HelloAgentsException("API密钥和服务地址必须被提供或在.env文件中定义。")

        # 创建OpenAI客户端
        self._client = self._create_client()

    def _load_dotenv_first(self) -> None:
        """
        优先加载 .env 中的配置。
        若 .env 不存在或未配置对应键，则自然回退到系统环境变量。
        """
        try:
            from dotenv import load_dotenv, find_dotenv, dotenv_values
        except Exception:
            return

        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            values = dotenv_values(dotenv_path)
            # 仅保留有值的键
            self._dotenv_values = {
                k: v for k, v in values.items() if v is not None and str(v).strip() != ""
            }
            # 读取但不覆盖系统环境变量（优先级由 _get_env 控制）
            load_dotenv(dotenv_path, override=False)
        else:
            # 尝试当前目录（如无 .env 将无效果）
            values = dotenv_values()
            self._dotenv_values = {
                k: v for k, v in values.items() if v is not None and str(v).strip() != ""
            }
            load_dotenv(override=False)

    def _get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        优先从 .env 读取配置；若无则回退系统环境变量。
        """
        if key in self._dotenv_values:
            return self._dotenv_values.get(key)
        return os.getenv(key, default)

    def _resolve_provider(self, provider: Optional[str], api_key: Optional[str], base_url: Optional[str]) -> str:
        """
        解析 provider：
        1) 显式参数 provider
        2) 环境变量/ .env 中的 LLM_PROVIDER
        3) 自动探测
        """
        if provider:
            return self._normalize_provider(provider)
        env_provider = self._get_env("LLM_PROVIDER")
        if env_provider:
            return self._normalize_provider(env_provider)
        return self._auto_detect_provider(api_key, base_url)

    def _normalize_provider(self, provider: str) -> str:
        """标准化 provider 名称，兼容大小写和常见别名。"""
        normalized = provider.strip().lower()
        aliases = {
            "silicon-flow": "siliconflow",
            "silicon_flow": "siliconflow",
        }
        return aliases.get(normalized, normalized)

    def _normalize_base_url(self, base_url: Optional[str]) -> Optional[str]:
        """将误填的完整接口路径归一化为 OpenAI 客户端所需的 base_url。"""
        if not base_url:
            return base_url
        normalized = base_url.strip().rstrip("/")
        for suffix in ("/chat/completions", "/completions"):
            if normalized.lower().endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    def _auto_detect_provider(self, api_key: Optional[str], base_url: Optional[str]) -> str:
        """
        自动检测LLM提供商

        检测逻辑：
        1. 优先检查特定提供商的环境变量
        2. 根据API密钥格式判断
        3. 根据base_url判断
        4. 默认返回通用配置
        """
        # 1. 检查特定提供商的环境变量（若命中多个则报错）
        env_map = {
            "openai": ["OPENAI_API_KEY"],
            "zhipu": ["ZHIPU_API_KEY", "GLM_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
            "qwen": ["DASHSCOPE_API_KEY"],
            "modelscope": ["MODELSCOPE_API_KEY"],
            "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
            "siliconflow": ["SILICONFLOW_API_KEY"],
            "ollama": ["OLLAMA_API_KEY", "OLLAMA_HOST"],
            "vllm": ["VLLM_API_KEY", "VLLM_HOST"],
        }
        hits = []
        for prov, keys in env_map.items():
            for key in keys:
                if self._get_env(key):
                    hits.append(prov)
                    break
        if len(hits) > 1:
            providers = ", ".join(sorted(set(hits)))
            raise HelloAgentsException(
                f"检测到多个 provider 配置: {providers}。请显式设置 provider 或 LLM_PROVIDER。"
            )
        if len(hits) == 1:
            return hits[0]

        # 2. 根据API密钥格式判断
        actual_api_key = api_key or self._get_env("LLM_API_KEY")
        if actual_api_key:
            actual_key_lower = actual_api_key.lower()
            if actual_api_key.startswith("ms-"):
                return "modelscope"
            elif actual_key_lower == "ollama":
                return "ollama"
            elif actual_key_lower == "vllm":
                return "vllm"
            elif actual_key_lower == "local":
                return "local"
            elif actual_api_key.startswith("sk-") and len(actual_api_key) > 50:
                # 可能是OpenAI、DeepSeek或Kimi，需要进一步判断
                pass
            elif actual_api_key.endswith(".") or "." in actual_api_key[-20:]:
                # 智谱AI的API密钥格式通常包含点号
                return "zhipu"

        # 3. 根据base_url判断
        actual_base_url = base_url or self._get_env("LLM_BASE_URL")
        if actual_base_url:
            base_url_lower = actual_base_url.lower()
            if "api.openai.com" in base_url_lower:
                return "openai"
            elif "api.deepseek.com" in base_url_lower:
                return "deepseek"
            elif "dashscope.aliyuncs.com" in base_url_lower:
                return "qwen"
            elif "api-inference.modelscope.cn" in base_url_lower:
                return "modelscope"
            elif "api.moonshot.cn" in base_url_lower:
                return "kimi"
            elif "open.bigmodel.cn" in base_url_lower:
                return "zhipu"
            elif "api.siliconflow.cn" in base_url_lower:
                return "siliconflow"
            elif "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
                # 本地部署检测 - 优先检查特定服务
                if ":11434" in base_url_lower or "ollama" in base_url_lower:
                    return "ollama"
                elif ":8000" in base_url_lower and "vllm" in base_url_lower:
                    return "vllm"
                elif ":8080" in base_url_lower or ":7860" in base_url_lower:
                    return "local"
                else:
                    # 根据API密钥进一步判断
                    if actual_api_key and actual_api_key.lower() == "ollama":
                        return "ollama"
                    elif actual_api_key and actual_api_key.lower() == "vllm":
                        return "vllm"
                    else:
                        return "local"
            elif any(port in base_url_lower for port in [":8080", ":7860", ":5000"]):
                # 常见的本地部署端口
                return "local"

        # 4. 默认返回auto，使用通用配置
        return "auto"

    def _resolve_credentials(self, api_key: Optional[str], base_url: Optional[str]) -> tuple[str, str]:
        """根据provider解析API密钥和base_url"""
        if self.provider == "openai":
            resolved_api_key = api_key or self._get_env("OPENAI_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://api.openai.com/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "deepseek":
            resolved_api_key = api_key or self._get_env("DEEPSEEK_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://api.deepseek.com"
            return resolved_api_key, resolved_base_url

        elif self.provider == "qwen":
            resolved_api_key = api_key or self._get_env("DASHSCOPE_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "modelscope":
            resolved_api_key = api_key or self._get_env("MODELSCOPE_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://api-inference.modelscope.cn/v1/"
            return resolved_api_key, resolved_base_url

        elif self.provider == "kimi":
            resolved_api_key = api_key or self._get_env("KIMI_API_KEY") or self._get_env("MOONSHOT_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://api.moonshot.cn/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "zhipu":
            resolved_api_key = api_key or self._get_env("ZHIPU_API_KEY") or self._get_env("GLM_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4"
            return resolved_api_key, resolved_base_url

        elif self.provider == "siliconflow":
            resolved_api_key = api_key or self._get_env("SILICONFLOW_API_KEY") or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("SILICONFLOW_BASE_URL") or self._get_env("LLM_BASE_URL") or "https://api.siliconflow.cn/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "ollama":
            resolved_api_key = api_key or self._get_env("OLLAMA_API_KEY") or self._get_env("LLM_API_KEY") or "ollama"
            resolved_base_url = base_url or self._get_env("OLLAMA_HOST") or self._get_env("LLM_BASE_URL") or "http://localhost:11434/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "vllm":
            resolved_api_key = api_key or self._get_env("VLLM_API_KEY") or self._get_env("LLM_API_KEY") or "vllm"
            resolved_base_url = base_url or self._get_env("VLLM_HOST") or self._get_env("LLM_BASE_URL") or "http://localhost:8000/v1"
            return resolved_api_key, resolved_base_url

        elif self.provider == "local":
            resolved_api_key = api_key or self._get_env("LLM_API_KEY") or "local"
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL") or "http://localhost:8000/v1"
            return resolved_api_key, resolved_base_url

        else:
            # auto或其他情况：使用通用配置，支持任何OpenAI兼容的服务
            resolved_api_key = api_key or self._get_env("LLM_API_KEY")
            resolved_base_url = base_url or self._get_env("LLM_BASE_URL")
            return resolved_api_key, resolved_base_url

    def _create_client(self) -> OpenAI:
        """创建OpenAI客户端"""
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )

    @staticmethod
    def _compact_request_kwargs(kwargs: dict) -> dict:
        """Drop None-valued fields for provider compatibility."""
        return {k: v for k, v in kwargs.items() if v is not None}

    def _is_minimax_backend(self) -> bool:
        base = (self.base_url or "").lower()
        return "minimaxi.com" in base or "minimax.io" in base

    def _apply_provider_compat(self, request_kwargs: dict) -> dict:
        """Apply backend-specific request normalization."""
        normalized = dict(request_kwargs)
        if self._is_minimax_backend():
            normalized["n"] = 1
            if normalized.get("tool_choice") == "auto":
                normalized.pop("tool_choice", None)
        return normalized

    def _requires_temperature_one(self) -> bool:
        """Kimi 2.5 / K2 系列模型仅接受 temperature=1。"""
        if self.provider != "kimi":
            return False
        model = (self.model or "").strip().lower()
        if not model:
            return False
        strict_markers = (
            "kimi2.5",
            "kimi-2.5",
            "kimi_2.5",
            "kimi-k2",
            "kimi k2",
            "k2-",
            "-k2",
            "/k2",
            "k2",
        )
        return any(marker in model for marker in strict_markers)

    def _resolve_temperature(self, requested: Optional[float]) -> float:
        """根据模型约束解析 temperature。"""
        value = self.temperature if requested is None else requested
        try:
            temp = float(value)
        except Exception:
            temp = float(self.temperature)

        if self._requires_temperature_one() and temp != 1.0:
            if not self._temperature_policy_notice_emitted:
                logger.warning(
                    "模型 %s 仅支持 temperature=1，已自动从 %.3f 调整为 1。",
                    self.model,
                    temp,
                )
                self._temperature_policy_notice_emitted = True
            return 1
        return temp
    
    def _get_default_model(self) -> str:
        """获取默认模型"""
        if self.provider == "openai":
            return "gpt-3.5-turbo"
        elif self.provider == "deepseek":
            return "deepseek-chat"
        elif self.provider == "qwen":
            return "qwen-plus"
        elif self.provider == "modelscope":
            return "Qwen/Qwen2.5-72B-Instruct"
        elif self.provider == "kimi":
            return "moonshot-v1-8k"
        elif self.provider == "zhipu":
            return "glm-4"
        elif self.provider == "siliconflow":
            return "Qwen/Qwen2.5-7B-Instruct"
        elif self.provider == "ollama":
            return "llama3.2"  # Ollama常用模型
        elif self.provider == "vllm":
            return "meta-llama/Llama-2-7b-chat-hf"  # vLLM常用模型
        elif self.provider == "local":
            return "local-model"  # 本地模型占位符
        else:
            # auto或其他情况：根据base_url智能推断默认模型
            base_url = self._get_env("LLM_BASE_URL", "") or ""
            base_url_lower = base_url.lower()
            if "modelscope" in base_url_lower:
                return "Qwen/Qwen2.5-72B-Instruct"
            elif "deepseek" in base_url_lower:
                return "deepseek-chat"
            elif "dashscope" in base_url_lower:
                return "qwen-plus"
            elif "moonshot" in base_url_lower:
                return "moonshot-v1-8k"
            elif "bigmodel" in base_url_lower:
                return "glm-4"
            elif "siliconflow" in base_url_lower:
                return "Qwen/Qwen2.5-7B-Instruct"
            elif "ollama" in base_url_lower or ":11434" in base_url_lower:
                return "llama3.2"
            elif ":8000" in base_url_lower or "vllm" in base_url_lower:
                return "meta-llama/Llama-2-7b-chat-hf"
            elif "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
                return "local-model"
            else:
                return "gpt-3.5-turbo"

    def think(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
    ) -> Iterator[str]:
        """
        调用大语言模型进行思考，并返回流式响应。
        这是主要的调用方法，默认使用流式响应以获得更好的用户体验。

        Args:
            messages: 消息列表
            temperature: 温度参数，如果未提供则使用初始化时的值

        Yields:
            str: 流式响应的文本片段
        """
        logger.info("正在调用 %s 模型...", self.model)
        try:
            request_kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self._resolve_temperature(temperature),
                "max_tokens": self.max_tokens,
                "stream": True,
            }
            if tools:
                request_kwargs["tools"] = tools
                if tool_choice is not None:
                    request_kwargs["tool_choice"] = tool_choice
            request_kwargs = self._apply_provider_compat(request_kwargs)
            request_kwargs = self._compact_request_kwargs(request_kwargs)
            response = self._client.chat.completions.create(**request_kwargs)

            # 处理流式响应
            logger.debug("大语言模型响应成功（streaming）")
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content

        except Exception as e:
            logger.error("调用LLM API时发生错误: %s", e)
            raise HelloAgentsException(f"LLM调用失败: {str(e)}")

    def invoke(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        非流式调用LLM，返回完整响应。
        适用于不需要流式输出的场景。
        """
        for attempt in range(self.max_retries + 1):
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self._resolve_temperature(kwargs.get("temperature")),
                    "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                }
                extra_kwargs = {k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
                if extra_kwargs:
                    request_kwargs.update(extra_kwargs)
                request_kwargs = self._apply_provider_compat(request_kwargs)
                request_kwargs = self._compact_request_kwargs(request_kwargs)
                response = self._client.chat.completions.create(**request_kwargs)
                return response.choices[0].message.content
            except Exception as e:
                if attempt >= self.max_retries:
                    raise HelloAgentsException(f"LLM调用失败: {str(e)}")
                wait_s = self.retry_backoff * (2 ** attempt)
                logger.warning(
                    "LLM调用失败，%.1fs后重试（%d/%d）: %s",
                    wait_s,
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                time.sleep(wait_s)

    def invoke_raw(self, messages: list[dict[str, str]], **kwargs):
        """
        非流式调用LLM，返回原始响应对象。
        适用于需要查看完整结构的场景。
        """
        for attempt in range(self.max_retries + 1):
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self._resolve_temperature(kwargs.get("temperature")),
                    "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                }
                extra_kwargs = {k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
                if extra_kwargs:
                    request_kwargs.update(extra_kwargs)
                request_kwargs = self._apply_provider_compat(request_kwargs)
                request_kwargs = self._compact_request_kwargs(request_kwargs)
                response = self._client.chat.completions.create(**request_kwargs)
                return response
            except Exception as e:
                if attempt >= self.max_retries:
                    raise HelloAgentsException(f"LLM调用失败: {str(e)}")
                wait_s = self.retry_backoff * (2 ** attempt)
                logger.warning(
                    "LLM调用失败，%.1fs后重试（%d/%d）: %s",
                    wait_s,
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                time.sleep(wait_s)

    def stream_invoke(self, messages: list[dict[str, str]], **kwargs) -> Iterator[str]:
        """
        流式调用LLM的别名方法，与think方法功能相同。
        保持向后兼容性。
        """
        temperature = kwargs.get('temperature')
        yield from self.think(messages, temperature)
