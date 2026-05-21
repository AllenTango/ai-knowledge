"""知识库发布模块。

将知识条目或简报推送到各个分发渠道。
"""

import asyncio
import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp
from dotenv import find_dotenv, load_dotenv

# 加载 .env 环境变量
load_dotenv(find_dotenv())

from distribution.formatter import generate_daily_digest


@dataclass
class PublishResult:
    """发布结果记录。

    Attributes:
        channel: 发布渠道名称。
        success: 是否发布成功。
        message_id: 渠道返回的消息 ID（可选）。
        error: 错误信息（可选）。
        timestamp: 发布时间。
    """

    channel: str
    success: bool
    message_id: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


class BasePublisher(ABC):
    """发布器抽象基类。

    定义发布器的通用接口。
    """

    @abstractmethod
    async def send_message(self, content: str, **kwargs) -> PublishResult:
        """发送单条消息。

        Args:
            content: 消息内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """

    @abstractmethod
    async def send_digest(self, content: str, **kwargs) -> PublishResult:
        """发送简报。

        Args:
            content: 简报内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """


class TelegramPublisher(BasePublisher):
    """Telegram 发布器。

    通过 Telegram Bot API 异步发送 MarkdownV2 消息。
    """

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        """初始化 Telegram 发布器。

        Args:
            token: Telegram Bot Token，默认从环境变量 TELEGRAM_BOT_TOKEN 读取。
            chat_id: Telegram Chat ID，默认从环境变量 TELEGRAM_CHAT_ID 读取。
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None

    async def send_message(self, content: str, **kwargs) -> PublishResult:
        """发送单条 MarkdownV2 消息。

        Args:
            content: 消息内容（MarkdownV2 格式）。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        if not self.token or not self.chat_id:
            return PublishResult(
                channel="telegram",
                success=False,
                error="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured",
            )

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": content,
            "parse_mode": "MarkdownV2",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return PublishResult(
                            channel="telegram",
                            success=True,
                            message_id=str(data.get("result", {}).get("message_id")),
                        )
                    else:
                        return PublishResult(
                            channel="telegram",
                            success=False,
                            error=data.get("description", "Unknown error"),
                        )
        except asyncio.TimeoutError:
            return PublishResult(
                channel="telegram",
                success=False,
                error="Request timeout (30s)",
            )
        except Exception as e:
            return PublishResult(
                channel="telegram",
                success=False,
                error=str(e),
            )

    async def send_digest(self, content: str, **kwargs) -> PublishResult:
        """发送简报。

        Args:
            content: 简报内容（MarkdownV2 格式）。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        return await self.send_message(content)


class QQPublisher(BasePublisher):
    """QQ 发布器。

    发送卡片消息。
    """

    def __init__(self, webhook_url: str | None = None, group_id: str | None = None):
        """初始化 QQ 发布器。

        Args:
            webhook_url: QQ Webhook URL，默认从环境变量 QQ_WEBHOOK_URL 读取。
            group_id: QQ 群号，默认从环境变量 QQ_GROUP_ID 读取。
        """
        self.webhook_url = webhook_url or os.getenv("QQ_WEBHOOK_URL")
        self.group_id = group_id or os.getenv("QQ_GROUP_ID")

    async def send_message(self, content: str, **kwargs) -> PublishResult:
        """发送卡片消息。

        Args:
            content: 消息内容（JSON 字符串或字典）。
            **kwargs: 额外参数，支持 card 参数传递卡片 dict。

        Returns:
            发布结果。
        """
        if not self.webhook_url:
            return PublishResult(
                channel="qq",
                success=False,
                error="QQ_WEBHOOK_URL not configured",
            )

        card = kwargs.get("card")
        if not card:
            card = {"msg_type": "text", "content": content}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=card,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        return PublishResult(channel="qq", success=True)
                    else:
                        return PublishResult(
                            channel="qq",
                            success=False,
                            error=f"HTTP {resp.status}",
                        )
        except asyncio.TimeoutError:
            return PublishResult(
                channel="qq",
                success=False,
                error="Request timeout (30s)",
            )
        except Exception as e:
            return PublishResult(
                channel="qq",
                success=False,
                error=str(e),
            )

    async def send_digest(self, content: str, **kwargs) -> PublishResult:
        """发送简报。

        Args:
            content: 简报内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        card = kwargs.get("card")
        if not card:
            card = {"msg_type": "text", "content": content}
        return await self.send_message(content, card=card)


class FeishuPublisher(BasePublisher):
    """飞书发布器。

    通过飞书 Webhook 发送消息。
    """

    def __init__(self, webhook_url: str | None = None):
        """初始化飞书发布器。

        Args:
            webhook_url: 飞书 Webhook URL，默认从环境变量 FEISHU_WEBHOOK_URL 读取。
        """
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")

    async def send_message(self, content: str, **kwargs) -> PublishResult:
        """发送文本消息。

        Args:
            content: 消息内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        if not self.webhook_url:
            return PublishResult(
                channel="feishu",
                success=False,
                error="FEISHU_WEBHOOK_URL not configured",
            )

        payload = {"msg_type": "text", "content": {"text": content}}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        return PublishResult(channel="feishu", success=True)
                    else:
                        return PublishResult(
                            channel="feishu",
                            success=False,
                            error=f"HTTP {resp.status}",
                        )
        except asyncio.TimeoutError:
            return PublishResult(
                channel="feishu",
                success=False,
                error="Request timeout (30s)",
            )
        except Exception as e:
            return PublishResult(
                channel="feishu",
                success=False,
                error=str(e),
            )

    async def send_digest(self, content: str, **kwargs) -> PublishResult:
        """发送简报。

        Args:
            content: 简报内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        return await self.send_message(content)


class OpenClawPublisher(BasePublisher):
    """OpenClaw 发布器。

    通过 OpenClaw CLI 发送消息到各平台。
    """

    def __init__(
        self,
        channel: str | None = None,
        target: str | None = None,
    ):
        """初始化 OpenClaw 发布器。

        Args:
            channel: 渠道名称，默认从环境变量 OPENCLAW_CHANNEL 读取。
                     可选值: telegram|whatsapp|discord|slack|signal|imessage|feishu|qqbot 等
            target: 目标标识，默认从环境变量 OPENCLAW_TARGET 读取。
                    - QQ 私聊 (c2c): 用户的 OpenID（如 8C2BACBF5360C259880C54AA9D6D8133）
                    - QQ 群聊: 群 ID
                    - Telegram: Chat ID（数字或 @username）
        """
        self.channel = channel or os.getenv("OPENCLAW_CHANNEL", "qqbot")
        self.target = target or os.getenv("OPENCLAW_TARGET")

    async def send_message(self, content: str, **kwargs) -> PublishResult:
        """发送消息。

        Args:
            content: 消息内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        if not self.target:
            return PublishResult(
                channel="openclaw",
                success=False,
                error="OPENCLAW_TARGET not configured",
            )

        return await self._send_via_cli(content)

    async def send_digest(self, content: str, **kwargs) -> PublishResult:
        """发送简报。

        Args:
            content: 简报内容。
            **kwargs: 额外参数。

        Returns:
            发布结果。
        """
        return await self.send_message(content)

    async def _send_via_cli(self, message: str) -> PublishResult:
        """通过 OpenClaw CLI 发送消息。

        Args:
            message: 消息内容。

        Returns:
            发布结果。
        """
        try:
            cmd = [
                "openclaw",
                "message",
                "send",
                "--channel", self.channel,
                "--target", self.target,
                "--message", message,
                "--json",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30,
            )

            if process.returncode == 0:
                try:
                    result = json.loads(stdout.decode("utf-8"))
                    message_id = (
    result.get("payload", {}).get("result", {}).get("messageId")
    or result.get("messageId")
)
                    return PublishResult(
                        channel="openclaw",
                        success=True,
                        message_id=str(message_id) if message_id else None,
                    )
                except json.JSONDecodeError:
                    return PublishResult(channel="openclaw", success=True)
            else:
                error_msg = stderr.decode("utf-8").strip() or "Unknown error"
                return PublishResult(
                    channel="openclaw",
                    success=False,
                    error=error_msg,
                )

        except asyncio.TimeoutError:
            return PublishResult(
                channel="openclaw",
                success=False,
                error="Command timeout (30s)",
            )
        except FileNotFoundError:
            return PublishResult(
                channel="openclaw",
                success=False,
                error="openclaw command not found",
            )
        except Exception as e:
            return PublishResult(
                channel="openclaw",
                success=False,
                error=str(e),
            )


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
    channels: list[str] | None = None,
) -> list[PublishResult]:
    """统一异步入口，发布当日简报到所有渠道。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 日期字符串，格式为 YYYYMMDD，默认为当天日期。
        top_n: 选取的 Top N 数量，默认为 5。
        channels: 要发布的渠道列表，默认为 ["telegram", "qq", "feishu"]。

    Returns:
        各渠道发布结果的列表。
    """
    if channels is None:
        channels = ["telegram", "qq", "feishu"]

    digest = generate_daily_digest(knowledge_dir, date, top_n)

    publishers: dict[str, BasePublisher] = {}
    if "telegram" in channels:
        publishers["telegram"] = TelegramPublisher()
    if "qq" in channels:
        publishers["qq"] = QQPublisher()
    if "feishu" in channels:
        publishers["feishu"] = FeishuPublisher()
    if "openclaw" in channels:
        publishers["openclaw"] = OpenClawPublisher()

    results: list[PublishResult] = []

    async def publish_channel(channel: str, publisher: BasePublisher) -> PublishResult:
        if channel == "telegram":
            return await publisher.send_digest(digest["telegram"])
        elif channel == "qq":
            return await publisher.send_digest(digest["telegram"])
        elif channel == "feishu":
            return await publisher.send_digest(digest["feishu"]["content"])
        elif channel == "openclaw":
            return await publisher.send_digest(digest["telegram"])
        return PublishResult(channel=channel, success=False, error="Unknown channel")

    tasks = [publish_channel(ch, pub) for ch, pub in publishers.items()]
    results = await asyncio.gather(*tasks)

    return results


async def publish_article(
    article: dict[str, Any],
    channels: list[str] | None = None,
) -> list[PublishResult]:
    """发布单篇文章到所有渠道。

    Args:
        article: 文章字典。
        channels: 要发布的渠道列表，默认为 ["telegram", "qq", "feishu"]。

    Returns:
        各渠道发布结果的列表。
    """
    from distribution.formatter import json_to_markdown, json_to_telegram, json_to_qq

    if channels is None:
        channels = ["telegram", "qq", "feishu"]

    publishers: dict[str, BasePublisher] = {}
    if "telegram" in channels:
        publishers["telegram"] = TelegramPublisher()
    if "qq" in channels:
        publishers["qq"] = QQPublisher()
    if "feishu" in channels:
        publishers["feishu"] = FeishuPublisher()
    if "openclaw" in channels:
        publishers["openclaw"] = OpenClawPublisher()

    results: list[PublishResult] = []

    async def publish_channel(channel: str, publisher: BasePublisher) -> PublishResult:
        if channel == "telegram":
            return await publisher.send_message(json_to_telegram(article))
        elif channel == "qq":
            return await publisher.send_message("", card=json_to_qq(article))
        elif channel == "feishu":
            return await publisher.send_message(json_to_markdown(article))
        elif channel == "openclaw":
            return await publisher.send_message(json_to_telegram(article))
        return PublishResult(channel=channel, success=False, error="Unknown channel")

    tasks = [publish_channel(ch, pub) for ch, pub in publishers.items()]
    results = await asyncio.gather(*tasks)

    return results