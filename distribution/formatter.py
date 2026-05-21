"""知识条目格式化模块。

将知识库中的 JSON 条目格式化为不同渠道的发布格式。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _get_score_emoji(score: float) -> str:
    """根据评分返回对应的 emoji 指示器。

    Args:
        score: 相关性评分，范围 0.0 ~ 10.0。

    Returns:
        评分对应的 emoji 字符。
    """
    if score >= 8.0:
        return "🟢"
    elif score >= 6.0:
        return "🟟"
    else:
        return "🔴"


def _get_score_level(score: float) -> str:
    """根据评分返回对应的颜色级别。

    Args:
        score: 相关性评分，范围 0.0 ~ 10.0。

    Returns:
        评分对应的颜色级别：green、yellow 或 red。
    """
    if score >= 8.0:
        return "green"
    elif score >= 6.0:
        return "yellow"
    else:
        return "red"


def _escape_telegram(text: str) -> str:
    """转义 Telegram MarkdownV2 的特殊字符。

    需要转义的字符：_*[]()~`>#+-=|{}.!

    Args:
        text: 待转义的文本。

    Returns:
        转义后的文本。
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def json_to_markdown(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Markdown 格式。

    Args:
        article: 知识条目字典，包含 title、source、fetched_at、score、tags、summary、source_url 等字段。

    Returns:
        格式化的 Markdown 字符串。
    """
    title = article.get("title", "无标题")
    source = article.get("source", "unknown")
    fetched_at = article.get("fetched_at", "")
    date_str = fetched_at[:10] if fetched_at else "未知"
    score = article.get("score", 0.0)
    tags = article.get("tags", [])
    summary = article.get("summary", "")
    source_url = article.get("source_url", "")

    score_emoji = _get_score_emoji(score)
    tags_str = " ".join(f"`{tag}`" for tag in tags) if tags else "无"

    lines = [
        f"### {title}",
        "",
        f"- **来源**: {source}",
        f"- **日期**: {date_str}",
        f"- **相关性评分**: {score_emoji} {score:.1f}",
        f"- **标签**: {tags_str}",
        "",
        f"**摘要**: {summary}",
        "",
        f"[查看原文]({source_url})",
    ]

    return "\n".join(lines)


def json_to_telegram(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Telegram MarkdownV2 格式。

    Args:
        article: 知识条目字典。

    Returns:
        格式化的 Telegram MarkdownV2 字符串。
    """
    title = _escape_telegram(article.get("title", "无标题"))
    source = article.get("source", "unknown")
    score = article.get("score", 0.0)
    tags = article.get("tags", [])
    summary = _escape_telegram(article.get("summary", ""))
    source_url = article.get("source_url", "")

    tags_str = " ".join(tag.replace(" ", "_") for tag in tags) if tags else "无"

    lines = [
        f"*{title}*",
        "",
        f"{summary}",
        "",
        f"📊 相关性: {score:.1f}",
        f"🏷️ 标签: {tags_str}",
        f"📁 来源: {source}",
        "",
        f"[🔗 原文链接]({source_url})",
    ]

    return "\n".join(lines)


def json_to_qq(article: dict[str, Any]) -> dict[str, Any]:
    """将单篇知识条目转换为 QQ 消息格式。

    Args:
        article: 知识条目字典。

    Returns:
        符合 QQ 消息格式的字典，包含 msg_type、header.template 等字段。
    """
    title = article.get("title", "无标题")
    score = article.get("score", 0.0)
    source = article.get("source", "unknown")
    summary = article.get("summary", "")
    tags = article.get("tags", [])
    source_url = article.get("source_url", "")

    color_level = _get_score_level(score)

    tags_str = " ".join(tags) if tags else "无"

    message = f"{summary}\n\n🏷️ {tags_str}\n📁 来源: {source}"

    return {
        "msg_type": "interactive",
        "header": {
            "template": color_level,
            "title": title[:100] if len(title) > 100 else title,
        },
        "elements": [
            {
                "tag": "markdown",
                "content": message[:500] if len(message) > 500 else message,
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "name": "查看原文",
                        "url": source_url,
                        "type": "open_url",
                    }
                ],
            },
        ],
    }


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
) -> dict[str, str]:
    """生成当日知识简报。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 日期字符串，格式为 YYYYMMDD，默认为当天日期。
        top_n: 选取的 Top N 数量，默认为 5。

    Returns:
        包含 markdown、telegram、feishu 格式的字典。
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    knowledge_path = Path(knowledge_dir)
    if not knowledge_path.exists():
        return {
            "markdown": f"📭 {date} 暂无新增知识条目",
            "telegram": f"📭 {date} 暂无新增知识条目",
            "feishu": {"msg_type": "text", "content": f"📭 {date} 暂无新增知识条目"},
        }

    pattern = f"{date}-*.json"
    files = list(knowledge_path.glob(pattern))

    if not files:
        return {
            "markdown": f"📭 {date} 暂无新增知识条目",
            "telegram": f"📭 {date} 暂无新增知识条目",
            "feishu": {"msg_type": "text", "content": f"📭 {date} 暂无新增知识条目"},
        }

    articles = []
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                article = json.load(f)
                articles.append(article)
        except (json.JSONDecodeError, IOError):
            continue

    articles.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    top_articles = articles[:top_n]

    markdown_parts = [f"# 📅 {date} 知识简报 (Top {len(top_articles)})", ""]
    telegram_parts = [f"📅 *{date} 知识简报 (Top {len(top_articles)})*", ""]
    feishu_parts = [f"📅 {date} 知识简报 (Top {len(top_articles)})", ""]

    for i, article in enumerate(top_articles, 1):
        markdown_parts.append(f"## {i}. {article.get('title', '无标题')}")
        markdown_parts.append(json_to_markdown(article))
        markdown_parts.append("")

        telegram_parts.append(f"*{i}. {article.get('title', '无标题')}*")
        telegram_parts.append(json_to_telegram(article))
        telegram_parts.append("")

        feishu_parts.append(f"**{i}. {article.get('title', '无标题')}**")
        feishu_parts.append(article.get("summary", ""))
        feishu_parts.append("")

    return {
        "markdown": "\n".join(markdown_parts),
        "telegram": "\n".join(telegram_parts),
        "feishu": {"msg_type": "text", "content": "\n".join(feishu_parts)},
    }