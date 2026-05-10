"""统一 LLM 调用客户端模块。

支持 DeepSeek、Qwen、MiniMax、OpenAI 等模型提供商，通过环境变量切换。
使用 httpx 直接调用 OpenAI 兼容 API。

返回说明:
    LLMResponse: 包含 content(str)、usage(Usage)、model(str) 等字段的响应对象。
    Usage: 包含 prompt_tokens、completion_tokens、total_tokens 的用量统计。

使用示例:
    # Windows PowerShell
    $ $env:LLM_PROVIDER = "deepseek"
    $ $env:DEEPSEEK_API_KEY = "your_api_key"
    $ python -m workflows.model_client

    # Linux/macOS Bash
    $ export LLM_PROVIDER=deepseek
    $ export DEEPSEEK_API_KEY=your_api_key
    $ python -m workflows.model_client
"""

import json
import logging
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# CostGuard 懒加载
_cost_guard: Any | None = None


def get_cost_guard() -> Any:
    """获取全局 CostGuard 单例（懒加载）。

    第一次调用时创建，后续复用同一实例。
    budget_yuan 从环境变量 BUDGET_YUAN 读取，默认 1.0。

    Returns:
        CostGuard 实例。
    """
    global _cost_guard
    if _cost_guard is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tests.cost_guard import CostGuard
        _cost_guard = CostGuard(
            budget_yuan=float(os.getenv("BUDGET_YUAN", "1.0"))
        )
    return _cost_guard


_LLM_AVAILABLE: bool | None = None


def check_llm_available() -> bool:
    """检查 LLM 是否可用（至少一个 API Key 已配置）。

    Returns:
        是否可用。
    """
    global _LLM_AVAILABLE
    if _LLM_AVAILABLE is not None:
        return _LLM_AVAILABLE

    for provider_config in ProviderFactory.PROVIDERS.values():
        if os.getenv(provider_config["env_key"]):
            _LLM_AVAILABLE = True
            return True
    _LLM_AVAILABLE = False
    return False


MODEL_PRICES: dict[str, dict[str, float]] = {
    "deepseek": {
        "deepseek-chat": 0.001,
        "deepseek-coder": 0.001,
    },
    "qwen": {
        "qwen-plus": 0.004,
        "qwen-turbo": 0.0015,
        "qwen-long": 0.0005,
    },
    "minimax": {
        "MiniMax-Text-01": 0.001,
        "abab6.5s-chat": 0.001,
    },
    "openai": {
        "gpt-4o": 0.005,
        "gpt-4o-mini": 0.00015,
        "gpt-4-turbo": 0.01,
    },
}

CHINA_MODEL_PRICES: dict[str, dict[str, float]] = {
    "deepseek": {"input": 1.0, "output": 2.0},
    "qwen": {"input": 4.0, "output": 12.0},
    "minimax": {"input": 1.0, "output": 10.0},
    "openai": {"input": 150.0, "output": 600.0},
}

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
TIMEOUT_SECONDS = 60
MAX_RETRIES = 3


@dataclass
class Usage:
    """Token 用量统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class LLMResponse:
    """LLM 调用响应。"""

    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """LLM 调用成本追踪器。

    追踪各提供商的 token 消耗和估算成本（元）。

    使用示例:
        tracker = CostTracker()
        tracker.record(response.usage, "deepseek")
        tracker.estimated_cost("deepseek")
        tracker.report()
    """

    def __init__(self):
        self._records: dict[str, list[Usage]] = {}

    def record(self, usage: Usage, provider: str) -> None:
        """记录一次 API 调用。

        Args:
            usage: Token 用量统计。
            provider: 提供商名称（如 "deepseek", "qwen", "openai"）。
        """
        provider = provider.lower()
        if provider not in self._records:
            self._records[provider] = []
        self._records[provider].append(usage)
        logger.debug(f"已记录 {provider} 用量: {usage.prompt_tokens} + {usage.completion_tokens} tokens")

    def estimated_cost(self, provider: str) -> float:
        """返回指定提供商的估算成本（元）。

        Args:
            provider: 提供商名称。

        Returns:
            估算成本（元）。
        """
        provider = provider.lower()
        if provider not in self._records:
            return 0.0

        prices = CHINA_MODEL_PRICES.get(provider, {"input": 0.0, "output": 0.0})
        total_cost = 0.0

        for usage in self._records[provider]:
            prompt_cost = (usage.prompt_tokens / 1_000_000) * prices.get("input", 0)
            completion_cost = (usage.completion_tokens / 1_000_000) * prices.get("output", 0)
            total_cost += prompt_cost + completion_cost

        return total_cost

    def total_tokens(self, provider: str = "") -> int:
        """返回总 token 消耗。

        Args:
            provider: 提供商名称，空字符串表示所有提供商。

        Returns:
            总 token 数量。
        """
        if not provider:
            total = 0
            for usages in self._records.values():
                for u in usages:
                    total += u.total_tokens
            return total

        provider = provider.lower()
        if provider not in self._records:
            return 0

        return sum(u.total_tokens for u in self._records[provider])

    def total_requests(self, provider: str = "") -> int:
        """返回总请求次数。

        Args:
            provider: 提供商名称，空字符串表示所有提供商。

        Returns:
            总请求次数。
        """
        if not provider:
            return sum(len(v) for v in self._records.values())

        provider = provider.lower()
        return len(self._records.get(provider, []))

    def report(self, provider: str = "") -> None:
        """打印成本报告。

        Args:
            provider: 提供商名称，空字符串表示所有提供商。
        """
        if provider:
            providers = [provider.lower()]
        else:
            providers = list(self._records.keys())

        if not providers:
            logger.info("暂无成本记录")
            return

        logger.info("=" * 40)
        logger.info("成本报告")
        logger.info("=" * 40)

        for p in providers:
            if p not in self._records:
                continue

            requests = len(self._records[p])
            tokens = sum(u.total_tokens for u in self._records[p])
            prompt_tokens = sum(u.prompt_tokens for u in self._records[p])
            completion_tokens = sum(u.completion_tokens for u in self._records[p])
            cost = self.estimated_cost(p)

            logger.info(f"提供商: {p}")
            logger.info(f"  请求次数: {requests}")
            logger.info(f"  总 tokens: {tokens:,} (输入: {prompt_tokens:,}, 输出: {completion_tokens:,})")
            logger.info(f"  估算成本: ¥{cost:.6f}")
            logger.info("")

        total_cost = sum(self.estimated_cost(p) for p in providers)
        total_requests = sum(self.total_requests(p) for p in providers)
        total_tokens = sum(self.total_tokens(p) for p in providers) if not provider else self.total_tokens(provider)

        logger.info(f"总计: {total_requests} 次请求, {total_tokens:,} tokens, ¥{total_cost:.6f}")
        logger.info("=" * 40)


class LLMProvider(ABC):
    """LLM 提供商抽象基类。"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供商名称。"""

    @property
    @abstractmethod
    def base_url(self) -> str:
        """API 基础地址。"""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """默认模型名称。"""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> LLMResponse:
        """发送聊天请求。"""

    @abstractmethod
    def estimate_cost(self, usage: Usage, model: str = "") -> float:
        """估算成本（USD）。"""


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容接口提供商。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model: str,
        provider_name: str,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._provider_name = provider_name
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def default_model(self) -> str:
        return self._default_model

    def chat(self, messages: list[dict[str, str]], model: str = "", **kwargs) -> LLMResponse:
        if not model:
            model = self._default_model

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        url = f"{self._base_url}/chat/completions"
        logger.debug(f"请求 URL: {url}")

        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"响应: {data}")

        llm_response = LLMResponse(
            content=data["choices"][0]["message"]["content"],
            usage=Usage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0),
            ),
            model=data.get("model", model),
            finish_reason=data["choices"][0].get("finish_reason", ""),
            raw_response=data,
        )

        tracker.record(llm_response.usage, self._provider_name.lower())
        return llm_response

    def estimate_cost(self, usage: Usage, model: str = "") -> float:
        if not model:
            model = self._default_model

        price_map = MODEL_PRICES.get(self._provider_name, {})
        price = price_map.get(model, 0.001)

        total_million_tokens = usage.total_tokens / 1_000_000
        return total_million_tokens * price


class ProviderFactory:
    """LLM 提供商工厂。"""

    PROVIDERS: dict[str, dict[str, str]] = {
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat",
            "env_key": "DEEPSEEK_API_KEY",
        },
        "qwen": {
            "name": "Qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus",
            "env_key": "DASHSCOPE_API_KEY",
        },
        "minimax": {
            "name": "MiniMax",
            "base_url": "https://api.minimaxi.com/v1",
            "default_model": "MiniMax-M2.7",
            "env_key": "MINIMAX_API_KEY",
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4o-mini",
            "env_key": "OPENAI_API_KEY",
        },
    }

    @classmethod
    def create(cls, provider_name: str = "") -> LLMProvider:
        name = (provider_name or DEFAULT_PROVIDER).lower()

        if name not in cls.PROVIDERS:
            raise ValueError(f"未知提供商: {name}，可用: {list(cls.PROVIDERS.keys())}")

        config = cls.PROVIDERS[name]
        api_key = os.getenv(config["env_key"])

        if not api_key:
            raise ValueError(f"环境变量 {config['env_key']} 未设置")

        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=config["base_url"],
            default_model=config["default_model"],
            provider_name=config["name"],
        )


def chat_with_retry(
    messages: list[dict[str, str]],
    provider_name: str = "",
    model: str = "",
    max_retries: int = MAX_RETRIES,
    **kwargs,
) -> LLMResponse:
    """带重试的聊天请求。

    Args:
        messages: 消息列表。
        provider_name: 提供商名称，默认从环境变量读取。
        model: 模型名称。
        max_retries: 最大重试次数。
        **kwargs: 传递给 LLM 的额外参数（如 temperature）。

    Returns:
        LLMResponse 对象。

    Raises:
        Exception: 重试耗尽后抛出。
    """
    provider = ProviderFactory.create(provider_name)

    for attempt in range(max_retries):
        try:
            logger.info(f"请求尝试 {attempt + 1}/{max_retries}")
            response = provider.chat(messages, model=model, **kwargs)
            logger.info(f"请求成功，消耗 tokens: {response.usage.total_tokens}")
            return response
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code in (429, 500, 502, 503, 504):
                wait_time = 2**attempt
                logger.warning(f"请求失败 ({status_code})，{wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                logger.error(f"HTTP 错误: {status_code}")
                raise
        except httpx.TimeoutException:
            wait_time = 2**attempt
            logger.warning(f"请求超时，{wait_time} 秒后重试...")
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"请求异常: {e}")
            raise

    raise Exception(f"重试 {max_retries} 次后仍失败")


def estimate_token_count(text: str) -> int:
    """估算文本的 Token 数量。

    简单估算：中文约 2 tokens/字，英文约 4 tokens/词。

    Args:
        text: 输入文本。

    Returns:
        估算的 token 数量。
    """
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    english_words = len(text.split()) - chinese_chars

    return int(chinese_chars * 2 + english_words / 4)


def calculate_cost(usage: Usage, provider_name: str = "", model: str = "") -> float:
    """计算调用成本（USD）。

    Args:
        usage: 用量统计。
        provider_name: 提供商名称。
        model: 模型名称。

    Returns:
        成本（美元）。
    """
    if not provider_name:
        provider_name = DEFAULT_PROVIDER.lower()

    provider = ProviderFactory.create(provider_name)
    return provider.estimate_cost(usage, model)


def quick_chat(prompt: str, system: str = "", provider_name: str = "") -> str:
    """一句话调用 LLM 的便捷函数。

    Args:
        prompt: 用户提示词。
        system: 系统提示词（可选）。
        provider_name: 提供商名称（可选）。

    Returns:
        LLM 响应内容。
    """
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    logger.info(f"使用提供商: {provider_name or DEFAULT_PROVIDER}")
    response = chat_with_retry(messages, provider_name=provider_name)

    usage = response.usage
    cost = calculate_cost(usage, provider_name or DEFAULT_PROVIDER)
    logger.info(f"Token 消耗: {usage.total_tokens}，预估成本: ${cost:.6f}")

    return response.content


def chat(
    messages: list[dict[str, str]] | None = None,
    system: str = "",
    prompt: str = "",
    provider_name: str = "",
    node_name: str = "unknown",
    **kwargs,
) -> tuple[str, Usage]:
    """便捷聊天函数，返回 (响应文本, 用量) 元组。

    Args:
        messages: 完整的消息列表（可选）。与 system+prompt 二选一。
        system: 系统提示词，与 prompt 组合使用（当 messages 为 None 时）。
        prompt: 用户提示词，与 system 组合使用（当 messages 为 None 时）。
        provider_name: 提供商名称。
        node_name: 调用节点名称（用于 CostGuard 追踪），默认 "unknown"。
        **kwargs: 传递给 LLM 的额外参数（如 temperature）。

    Returns:
        (text, usage) 元组。
    """
    if messages is None:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
    else:
        msgs = messages

    response = chat_with_retry(msgs, provider_name=provider_name, **kwargs)

    guardian = get_cost_guard()
    guardian.record(node_name, {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }, model=response.model)
    guardian.check()

    return response.content, response.usage


def chat_json(
    messages: list[dict[str, str]] | None = None,
    system: str = "",
    prompt: str = "",
    provider_name: str = "",
    node_name: str = "unknown",
    **kwargs,
) -> tuple[dict, Usage]:
    """以 JSON 模式调用 LLM，返回 (解析后的 dict, 用量) 元组。

    在 system 提示或 user 提示中自动追加 JSON 输出指令。
    透传 node_name 到 chat()，由 CostGuard 统一记录用量。

    Args:
        messages: 完整的消息列表（可选）。与 system+prompt 二选一。
        system: 系统提示词。
        prompt: 用户提示词。
        provider_name: 提供商名称。
        node_name: 调用节点名称（透传到 chat()），默认 "unknown"。
        **kwargs: 传递给 LLM 的额外参数（如 temperature）。

    Returns:
        (parsed_dict, usage) 元组。

    Raises:
        json.JSONDecodeError: 当 LLM 返回非法 JSON 时抛出。
    """
    if messages is None:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system +
                         "\n\n请始终以 JSON 格式输出，不要包含其他内容。"})
        msgs.append({"role": "user", "content": prompt +
                      "\n\n请只输出 JSON 格式，不要包含其他内容。"})
    else:
        msgs = messages

    text, usage = chat(
        messages=msgs, provider_name=provider_name,
        node_name=node_name, **kwargs,
    )

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    parsed = json.loads(text)
    return parsed, usage


if __name__ == "__main__":
    logger.info("测试 LLM 客户端...")

    provider_name = os.getenv("LLM_PROVIDER", "deepseek")
    api_key = os.getenv(f"{provider_name.upper()}_API_KEY") or os.getenv(
        {
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "DASHSCOPE_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "openai": "OPENAI_API_KEY",
        }.get(provider_name, "DEEPSEEK_API_KEY")
    )

    if not api_key:
        logger.warning("未设置 API_KEY，跳过实际调用测试")
        logger.info("测试 Token 估算...")
        test_text = "这是一个测试文本，用于估算 token 数量。"
        estimated = estimate_token_count(test_text)
        logger.info(f"文本: {test_text}")
        logger.info(f"估算 tokens: {estimated}")
    else:
        logger.info(f"当前提供商: {provider_name}")
        logger.info("执行 quick_chat 测试...")

        result = quick_chat(
            "请用一句话介绍一下 LangChain 是什么？",
            system="你是一个专业的 AI 技术助手。",
        )
        logger.info(f"LLM 响应: {result}")

        logger.info("测试 chat_with_retry...")
        messages = [
            {"role": "system", "content": "你是一个 AI 助手。"},
            {"role": "user", "content": "你好，请介绍一下你自己。"},
        ]
        response = chat_with_retry(messages)
        logger.info(f"响应: {response.content}")
        logger.info(f"用量: {response.usage}")
        logger.info(f"模型: {response.model}")


tracker = CostTracker()
