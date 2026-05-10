"""MCP 知识库服务器。

提供 JSON-RPC 2.0 over stdio 协议，供 AI 工具搜索本地知识库。

Usage:
    python pipeline/mcp_knowledge_server.py

MCP 工具:
    - search_articles: 按关键词搜索文章标题和摘要
    - get_article: 按 ID 获取文章完整内容
    - knowledge_stats: 返回统计信息（文章总数、来源分布、热门标签）
"""

import json
import sys
import re
from pathlib import Path
from typing import Any
from collections import Counter

PROJECT_ROOT = Path(__file__).parent
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"

_articles_cache: list[dict[str, Any]] = []


def load_articles() -> list[dict[str, Any]]:
    """加载所有文章到内存缓存。"""
    global _articles_cache
    if _articles_cache:
        return _articles_cache

    _articles_cache = []
    if not KNOWLEDGE_ARTICLES.exists():
        return _articles_cache

    for json_file in KNOWLEDGE_ARTICLES.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                article = json.load(f)
                _articles_cache.append(article)
        except (json.JSONDecodeError, IOError):
            continue

    return _articles_cache


def search_articles(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """按关键词搜索文章标题和摘要。

    Args:
        keyword: 搜索关键词。
        limit: 返回结果数量限制，默认 5。

    Returns:
        匹配的文章列表（仅返回 id, title, source, summary, score, tags）。
    """
    articles = load_articles()
    keyword_lower = keyword.lower()

    matches = []
    for article in articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = " ".join(article.get("tags", [])).lower()

        if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
            matches.append({
                "id": article.get("id", ""),
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "summary": article.get("summary", "")[:200],
                "score": article.get("score", 0),
                "tags": article.get("tags", [])[:5],
            })

    return matches[:limit]


def get_article(article_id: str) -> dict[str, Any] | None:
    """按 ID 获取文章完整内容。

    Args:
        article_id: 文章 ID。

    Returns:
        完整的文章内容，未找到返回 None。
    """
    articles = load_articles()
    for article in articles:
        if article.get("id") == article_id:
            return article
    return None


def knowledge_stats() -> dict[str, Any]:
    """返回知识库统计信息。

    Returns:
        包含文章总数、来源分布、热门标签的字典。
    """
    articles = load_articles()

    source_counts = Counter(a.get("source", "unknown") for a in articles)

    all_tags = []
    for article in articles:
        all_tags.extend(article.get("tags", []))
    tag_counts = Counter(all_tags)
    top_tags = [{"tag": tag, "count": count} for tag, count in tag_counts.most_common(10)]

    status_counts = Counter(a.get("status", "unknown") for a in articles)

    return {
        "total_articles": len(articles),
        "source_distribution": dict(source_counts),
        "top_tags": top_tags,
        "status_distribution": dict(status_counts),
    }


TOOLS = {
    "search_articles": {
        "description": "按关键词搜索文章标题和摘要",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量限制，默认 5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    "get_article": {
        "description": "按 ID 获取文章完整内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID",
                },
            },
            "required": ["article_id"],
        },
    },
    "knowledge_stats": {
        "description": "返回知识库统计信息（文章总数、来源分布、热门标签）",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """处理 MCP initialize 请求。"""
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "knowledge-mcp-server",
            "version": "1.0.0",
        },
        "capabilities": {
            "tools": {},
        },
    }


def handle_tools_list(params: dict[str, Any]) -> dict[str, Any]:
    """处理 MCP tools/list 请求。"""
    tools = []
    for name, spec in TOOLS.items():
        tools.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        })
    return {"tools": tools}


def handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """处理 MCP tools/call 请求。"""
    name = params.get("name")
    arguments = params.get("arguments", {})

    if name == "search_articles":
        result = search_articles(
            keyword=arguments.get("keyword", ""),
            limit=arguments.get("limit", 5),
        )
    elif name == "get_article":
        result = get_article(article_id=arguments.get("article_id", ""))
    elif name == "knowledge_stats":
        result = knowledge_stats()
    else:
        result = {"error": f"Unknown tool: {name}"}

    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    """根据请求方法分发处理。"""
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        result = handle_initialize(request.get("params", {}))
    elif method == "tools/list":
        result = handle_tools_list(request.get("params", {}))
    elif method == "tools/call":
        result = handle_tools_call(request.get("params", {}))
    else:
        result = {"error": f"Unknown method: {method}"}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def main() -> None:
    """主循环：读取 stdin，处理 JSON-RPC 请求，写入 stdout。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()