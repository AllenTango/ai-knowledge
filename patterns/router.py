"""基于意图分类的请求路由。

两层意图分类策略：
1. 第一层：关键词快速匹配（零成本，不调 LLM）
2. 第二层：LLM 分类兜底（处理模糊意图）

三种意图：github_search / knowledge_query / general_chat
每种意图对应一个处理器函数。

统一入口: route(query: str) -> str

Usage:
    python -m patterns.router "查找 LangChain 相关文章"
    python -m patterns.router "github 上最近的 AI 项目"
    python -m patterns.router "你好，介绍一下你自己"
"""

import json
import logging
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.model_client import chat, chat_json

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
INDEX_FILE = PROJECT_ROOT / "knowledge" / "articles" / "index.json"

# ── 第一层：关键词匹配表 ─────────────────────────────────────────────

KEYWORD_MAP: dict[str, list[str]] = {
    "github_search": [
        "github",
        "repo",
        "仓库",
        "项目",
        "开源",
        "repository",
        "trending",
        "git",
    ],
    "knowledge_query": [
        "知识",
        "文章",
        "检索",
        "搜索",
        "查找",
        "article",
        "search",
        "find",
        "query",
        "查一下",
    ],
}

# ── LLM 分类提示词 ──────────────────────────────────────────────────

CLASSIFY_SYSTEM_PROMPT = """你是一个意图分类器。
请判断用户输入属于以下哪种意图，只输出 JSON：

{
    "intent": "github_search | knowledge_query | general_chat",
    "reason": "简短理由（中文，10字以内）"
}

规则：
- github_search：用户想搜索 GitHub 上的项目/仓库
- knowledge_query：用户想查询本地知识库中的文章
- general_chat：其他所有对话、问候、闲聊"""


# ── 第一层：关键词分类 ──────────────────────────────────────────────


def classify_by_keywords(query: str) -> str | None:
    """通过关键词匹配判断意图。

    Args:
        query: 用户输入。

    Returns:
        命中时返回意图名称，未命中返回 None。
    """
    query_lower = query.lower()
    for intent, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                logger.info(f"关键词命中: [{intent}] ← '{kw}' in '{query[:30]}...'")
                return intent
    return None


# ── 第二层：LLM 分类 ────────────────────────────────────────────────


def classify_by_llm(query: str) -> str:
    """通过 LLM 判断意图。

    Args:
        query: 用户输入。

    Returns:
        意图名称，默认返回 general_chat。
    """
    try:
        (result, _usage) = chat_json(
            system=CLASSIFY_SYSTEM_PROMPT,
            prompt=f"用户输入: {query}",
        )
        intent = result.get("intent", "general_chat")
        reason = result.get("reason", "")
        logger.info(f"LLM 分类: [{intent}] {reason}")
        if intent not in ("github_search", "knowledge_query", "general_chat"):
            return "general_chat"
        return intent
    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}，默认 general_chat")
        return "general_chat"


# ── 统一分类入口 ────────────────────────────────────────────────────


def classify_intent(query: str) -> str:
    """两层意图分类。

    Args:
        query: 用户输入。

    Returns:
        意图名称。
    """
    intent = classify_by_keywords(query)
    if intent:
        return intent
    return classify_by_llm(query)


# ── 处理器：github_search ──────────────────────────────────────────


def handle_github_search(query: str) -> str:
    """搜索 GitHub 仓库。

    Args:
        query: 用户原始输入。

    Returns:
        格式化后的搜索结果文本。
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page=5"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ai-knowledge-router/1.0",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"GitHub API 请求失败: {e}")
        return f"GitHub 搜索失败: {e}"

    items = data.get("items", [])[:5]
    if not items:
        return "未找到相关项目。"

    lines = [f"找到 {data.get('total_count', 0)} 个仓库，展示前 {len(items)} 个：\n"]
    for item in items:
        name = item.get("full_name", "unknown")
        desc = item.get("description", "无描述") or "无描述"
        stars = item.get("stargazers_count", 0)
        url_item = item.get("html_url", "")
        lang = item.get("language") or "未知"
        lines.append(f"  * {stars}  {name}  [{lang}]")
        lines.append(f"     {desc}")
        lines.append(f"     {url_item}")
        lines.append("")

    return "\n".join(lines)


# ── 处理器：knowledge_query ────────────────────────────────────────


def handle_knowledge_query(query: str) -> str:
    """从本地知识库 index.json 检索文章。

    Args:
        query: 用户原始输入。

    Returns:
        格式化后的检索结果文本。
    """
    if not INDEX_FILE.exists():
        return "知识库索引文件不存在，请先运行采集流程。"

    try:
        with open(INDEX_FILE, "r", encoding="utf-8-sig") as f:
            index: list[dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取索引文件失败: {e}")
        return "知识库索引读取失败。"

    if not index:
        return "知识库为空，暂无文章。"

    query_lower = query.lower()
    keywords = [kw.strip() for kw in re.split(r"[\s,，、]+", query_lower) if kw.strip()]

    def match_article(article: dict) -> bool:
        title = (article.get("title") or "").lower()
        summary = (article.get("summary") or "").lower()
        tags = " ".join(article.get("tags") or []).lower()
        for kw in keywords:
            if kw in title or kw in summary or kw in tags:
                return True
        return False

    matched = [a for a in index if match_article(a)]
    matched = sorted(matched, key=lambda a: a.get("score", 0), reverse=True)[:5]

    if not matched:
        return f"未找到与「{query}」相关的文章。"

    lines = [f"找到 {len(matched)} 篇相关文章：\n"]
    for article in matched:
        title = article.get("title", "无标题")
        score = article.get("score", 0)
        tags = ", ".join(article.get("tags", [])[:5])
        summary = (article.get("summary") or "")[:120]
        lines.append(f"  [{score}] {title}")
        if tags:
            lines.append(f"       标签: {tags}")
        if summary:
            lines.append(f"       {summary}")
        lines.append("")

    return "\n".join(lines)


# ── 处理器：general_chat ───────────────────────────────────────────


def handle_general_chat(query: str) -> str:
    """调用 LLM 直接回答用户。

    Args:
        query: 用户原始输入。

    Returns:
        LLM 的回复文本。
    """
    try:
        (text, _usage) = chat(
            system="你是一个 AI 知识库助手，专业回答 AI/LLM/Agent 领域相关问题。",
            prompt=query,
        )
        return text
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return f"抱歉，AI 回答暂时不可用: {e}"


# ── 处理器映射表 ───────────────────────────────────────────────────

HANDLER_MAP: dict[str, Any] = {
    "github_search": handle_github_search,
    "knowledge_query": handle_knowledge_query,
    "general_chat": handle_general_chat,
}


# ── 统一入口 ────────────────────────────────────────────────────────


def route(query: str) -> str:
    """统一路由入口。

    Args:
        query: 用户输入。

    Returns:
        处理结果文本。
    """
    if not query or not query.strip():
        return "请输入有效的问题。"

    query = query.strip()
    logger.info(f"路由请求: {query[:60]}")

    intent = classify_intent(query)
    handler = HANDLER_MAP.get(intent, handle_general_chat)

    logger.info(f"执行处理器: {intent}")
    return handler(query)


# ── 命令行入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stdout.write("用法: python -m patterns.router <query>\n")
        sys.stdout.write('示例: python -m patterns.router "查找 LangChain 文章"\n')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    result = route(query)
    sys.stdout.write(result + "\n")
