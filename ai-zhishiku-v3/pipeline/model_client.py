"""转发层 — 复用 workflows/model_client.py。

保持通过 ``from pipeline.model_client import ...`` 导入的旧代码正常工作。

Usage:
    from pipeline.model_client import chat, chat_with_retry, tracker
"""
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "workflows"))

from workflows.model_client import (  # noqa: E402
    MODEL_PRICES,
    CHINA_MODEL_PRICES,
    DEFAULT_PROVIDER,
    TIMEOUT_SECONDS,
    MAX_RETRIES,
    Usage,
    LLMResponse,
    CostTracker,
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderFactory,
    chat_with_retry,
    estimate_token_count,
    calculate_cost,
    quick_chat,
    chat,
    chat_json,
    tracker,
)
