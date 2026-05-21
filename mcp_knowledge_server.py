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
KNOWLEDGE_HUMAN_REVIEW = PROJECT_ROOT / "knowledge" / "human_review"

_articles_cache: list[dict[str, Any]] = []
_id_to_filename: dict[str, str] = {}


def load_articles() -> list[dict[str, Any]]:
    """加载所有文章到内存缓存，同时建立 id → 文件名 映射供写操作使用。

    同时读取 knowledge/articles/ 和 knowledge/human_review/ 两个目录。
    """
    global _articles_cache, _id_to_filename
    if _articles_cache:
        return _articles_cache

    _articles_cache = []
    _id_to_filename = {}

    for dir_path in (KNOWLEDGE_ARTICLES, KNOWLEDGE_HUMAN_REVIEW):
        if not dir_path.exists():
            continue
        for json_file in dir_path.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    article = json.load(f)
                    _articles_cache.append(article)
                    article_id = article.get("id", "")
                    if article_id:
                        _id_to_filename[article_id] = str(json_file)
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


def get_all_articles(
    status: str | None = None,
    source: str | None = None,
    tag: str | None = None,
    score_min: float | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """全量返回文章列表，支持多条件筛选。

    Args:
        status: 按状态过滤（如 "pending_review", "approved" 等）。
        source: 按来源过滤（"github" | "rss"）。
        tag: 按标签过滤（article.tags 中包含该标签）。
        score_min: 最低评分过滤。
        keyword: 关键词搜索（匹配标题 / 摘要 / 标签）。

    Returns:
        符合条件的完整文章列表。
    """
    articles = load_articles()
    results = []
    kw_lower = keyword.lower() if keyword else ""

    for article in articles:
        if status and article.get("status") != status:
            continue
        if source and article.get("source") != source:
            continue
        if score_min is not None and article.get("score", 0) < score_min:
            continue
        if tag:
            tags = article.get("tags", [])
            if tag not in tags:
                continue
        if kw_lower:
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()
            tags_str = " ".join(article.get("tags", [])).lower()
            if kw_lower not in title and kw_lower not in summary and kw_lower not in tags_str:
                continue
        results.append(article)

    return results


def _write_article_file(article_id: str, article: dict[str, Any]) -> dict[str, Any]:
    """将文章写回对应目录并更新缓存。

    根据 article.status 将文件写入正确目录：
    - human_review → knowledge/human_review/
    - approved / rejected / pending_review → knowledge/articles/

    Args:
        article_id: 文章 ID。
        article: 完整文章 dict。

    Returns:
        {"success": True} 或 {"error": "..."}。
    """
    global _articles_cache, _id_to_filename

    status = article.get("status", "")
    if status == "human_review":
        target_dir = KNOWLEDGE_HUMAN_REVIEW
    else:
        target_dir = KNOWLEDGE_ARTICLES

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{article_id}.json"

    old_filename = _id_to_filename.get(article_id)
    if old_filename and Path(old_filename) != target_file:
        try:
            if Path(old_filename).exists():
                Path(old_filename).unlink()
        except IOError:
            pass

    try:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        _id_to_filename[article_id] = str(target_file)

        for i, cached in enumerate(_articles_cache):
            if cached.get("id") == article_id:
                _articles_cache[i] = article
                break

        return {"success": True, "file": str(target_file)}
    except IOError as e:
        return {"error": f"写入文件失败: {e}"}


def update_article_status(article_id: str, new_status: str) -> dict[str, Any]:
    """修改单篇文章的状态并写回文件。

    Args:
        article_id: 文章 ID。
        new_status: 新的状态值（pending_review | approved | rejected）。

    Returns:
        操作结果。
    """
    article = get_article(article_id)
    if article is None:
        return {"error": f"文章未找到: {article_id}"}

    valid_statuses = {"pending_review", "approved", "rejected"}
    if new_status not in valid_statuses:
        return {"error": f"无效状态 [{new_status}]，可选: {valid_statuses}"}

    from datetime import datetime, timezone
    article["status"] = new_status
    article["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    return _write_article_file(article_id, article)


def update_article_fields(article_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """批量更新文章字段并写回文件。

    Args:
        article_id: 文章 ID。
        updates: 要更新的字段 dict，支持 title / summary / tags / score。

    Returns:
        操作结果。
    """
    article = get_article(article_id)
    if article is None:
        return {"error": f"文章未找到: {article_id}"}

    allowed_fields = {"title", "summary", "tags", "score"}
    for key, value in updates.items():
        if key in allowed_fields:
            article[key] = value

    return _write_article_file(article_id, article)


def batch_update_status(article_ids: list[str], new_status: str) -> dict[str, Any]:
    """批量修改多篇文章的状态。

    Args:
        article_ids: 文章 ID 列表。
        new_status: 新的状态值。

    Returns:
        包含成功数和失败列表的结果。
    """
    valid_statuses = {"pending_review", "approved", "rejected"}
    if new_status not in valid_statuses:
        return {"error": f"无效状态 [{new_status}]"}

    results = {"success_count": 0, "failed": []}
    for aid in article_ids:
        res = update_article_status(aid, new_status)
        if "error" in res:
            results["failed"].append({"id": aid, "reason": res["error"]})
        else:
            results["success_count"] += 1

    return results


def get_human_review_items() -> list[dict[str, Any]]:
    """返回所有待人工审核条目。

    以 article 格式从 knowledge/human_review/ 目录读取每条记录，
    返回格式与 articles 一致，附加 _filename 字段供操作使用。

    Returns:
        human_review/ 目录下所有 article 格式 JSON 文件的内容列表。
    """
    if not KNOWLEDGE_HUMAN_REVIEW.exists():
        return []

    items = []
    for json_file in KNOWLEDGE_HUMAN_REVIEW.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                article = json.load(f)
                article["_filename"] = json_file.name
                items.append(article)
        except (json.JSONDecodeError, IOError):
            continue

    items.sort(key=lambda x: x.get("fetched_at", ""))
    return items


def resolve_human_review(filename: str, action: str = "approve") -> dict[str, Any]:
    """处理人工审核条目。

    将 human_review/ 目录中的 article 格式文件移入 articles/ 目录（若已存在则合并），
    然后删除 human_review 中的原文件。

    Args:
        filename: human_review/ 下的文件名（不含路径）。
        action: "approve"（转为 approved 条目）或 "reject"（标记为 rejected）。

    Returns:
        操作结果。
    """
    hr_file = KNOWLEDGE_HUMAN_REVIEW / filename
    if not hr_file.exists():
        return {"error": f"人工审核文件不存在: {filename}"}

    try:
        with open(hr_file, "r", encoding="utf-8") as f:
            article = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {"error": f"读取人工审核文件失败: {e}"}

    from datetime import datetime, timezone
    aid = article.get("id", "")
    if not aid:
        return {"error": "条目缺少 id 字段"}

    article_file = KNOWLEDGE_ARTICLES / f"{aid}.json"
    new_status = "approved" if action == "approve" else "rejected"

    try:
        if article_file.exists():
            with open(article_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {}

        existing.update({
            "id": aid,
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "source_url": article.get("source_url", ""),
            "fetched_at": article.get("fetched_at", ""),
            "analyzed_at": article.get("analyzed_at", ""),
            "summary": article.get("summary", ""),
            "tags": article.get("tags", []),
            "score": float(article.get("score", 0)),
            "status": new_status,
            "reviewer": "human-reviewer",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "published_to": existing.get("published_to", []),
            "retry_count": existing.get("retry_count", 0),
        })

        KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)
        with open(article_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        hr_file.unlink()
    except IOError as e:
        return {"error": f"写入文件失败: {e}"}

    global _articles_cache
    _articles_cache = []

    return {
        "success": True,
        "action": action,
        "article_id": aid,
        "new_status": new_status,
        "hr_file_removed": filename,
    }


def process_human_review_article(filename: str, article_id: str, action: str = "approve") -> dict[str, Any]:
    """处理人工审核条目。

    将 human_review/ 目录中的 article 格式文件移入 articles/ 目录，
    然后删除 human_review 中的原文件。

    Args:
        filename: human_review/ 下的文件名（不含路径）。
        article_id: 要处理的文章 ID（用于校验）。
        action: "approve"（→ approved）或 "reject"（→ rejected）。

    Returns:
        操作结果。
    """
    hr_file = KNOWLEDGE_HUMAN_REVIEW / filename
    if not hr_file.exists():
        return {"error": f"人工审核文件不存在: {filename}"}

    try:
        with open(hr_file, "r", encoding="utf-8") as f:
            article = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {"error": f"读取人工审核文件失败: {e}"}

    aid = article.get("id", "")
    if aid != article_id:
        return {"error": f"文件中的 article_id [{aid}] 与请求的 [{article_id}] 不匹配"}

    article_file = KNOWLEDGE_ARTICLES / f"{article_id}.json"
    new_status = "approved" if action == "approve" else "rejected"

    try:
        if article_file.exists():
            with open(article_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {}

        from datetime import datetime, timezone
        existing.update({
            "id": article_id,
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "source_url": article.get("source_url", ""),
            "fetched_at": article.get("fetched_at", ""),
            "analyzed_at": article.get("analyzed_at", ""),
            "summary": article.get("summary", ""),
            "tags": article.get("tags", []),
            "score": float(article.get("score", 0)),
            "status": new_status,
            "reviewer": "human-reviewer",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "published_to": existing.get("published_to", []),
            "retry_count": existing.get("retry_count", 0),
        })

        KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)
        with open(article_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        hr_file.unlink()
    except IOError as e:
        return {"error": f"写入文件失败: {e}"}

    global _articles_cache
    _articles_cache = []

    return {
        "success": True,
        "article_id": article_id,
        "action": action,
        "new_status": new_status,
        "hr_file_removed": filename,
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
    "get_all_articles": {
        "description": "全量返回文章列表，支持多条件筛选",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "按状态过滤（pending_review | approved | rejected）",
                },
                "source": {
                    "type": "string",
                    "description": "按来源过滤（github | rss）",
                },
                "tag": {
                    "type": "string",
                    "description": "按标签过滤",
                },
                "score_min": {
                    "type": "number",
                    "description": "最低评分过滤",
                },
                "keyword": {
                    "type": "string",
                    "description": "关键词搜索（匹配标题/摘要/标签）",
                },
            },
        },
    },
    "update_article_status": {
        "description": "修改单篇文章的状态并写回文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID",
                },
                "new_status": {
                    "type": "string",
                    "description": "新状态（pending_review | approved | rejected）",
                },
            },
            "required": ["article_id", "new_status"],
        },
    },
    "update_article_fields": {
        "description": "批量更新文章字段并写回文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID",
                },
                "updates": {
                    "type": "object",
                    "description": "要更新的字段，支持 title / summary / tags / score",
                    "additionalProperties": True,
                },
            },
            "required": ["article_id", "updates"],
        },
    },
    "batch_update_status": {
        "description": "批量修改多篇文章的状态",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "文章 ID 列表",
                },
                "new_status": {
                    "type": "string",
                    "description": "新状态",
                },
            },
            "required": ["article_ids", "new_status"],
        },
    },
    "get_human_review_items": {
        "description": "返回所有人工审核标记条目",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "resolve_human_review": {
        "description": "处理人工审核标记文件（批量）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "human_review/ 下的文件名",
                },
                "action": {
                    "type": "string",
                    "description": "操作：approve（转为 approved）或 reject（标记为驳回）",
                    "default": "approve",
                },
            },
            "required": ["filename"],
        },
    },
    "process_human_review_article": {
        "description": "处理标记文件中的单条 article",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "human_review/ 下的文件名",
                },
                "article_id": {
                    "type": "string",
                    "description": "要处理的文章 ID",
                },
                "action": {
                    "type": "string",
                    "description": "操作：approve 或 reject",
                    "default": "approve",
                },
            },
            "required": ["filename", "article_id"],
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
    elif name == "get_all_articles":
        result = get_all_articles(
            status=arguments.get("status"),
            source=arguments.get("source"),
            tag=arguments.get("tag"),
            score_min=arguments.get("score_min"),
            keyword=arguments.get("keyword"),
        )
    elif name == "update_article_status":
        result = update_article_status(
            article_id=arguments.get("article_id", ""),
            new_status=arguments.get("new_status", ""),
        )
    elif name == "update_article_fields":
        result = update_article_fields(
            article_id=arguments.get("article_id", ""),
            updates=arguments.get("updates", {}),
        )
    elif name == "batch_update_status":
        result = batch_update_status(
            article_ids=arguments.get("article_ids", []),
            new_status=arguments.get("new_status", ""),
        )
    elif name == "get_human_review_items":
        result = get_human_review_items()
    elif name == "resolve_human_review":
        result = resolve_human_review(
            filename=arguments.get("filename", ""),
            action=arguments.get("action", "approve"),
        )
    elif name == "process_human_review_article":
        result = process_human_review_article(
            filename=arguments.get("filename", ""),
            article_id=arguments.get("article_id", ""),
            action=arguments.get("action", "approve"),
        )
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