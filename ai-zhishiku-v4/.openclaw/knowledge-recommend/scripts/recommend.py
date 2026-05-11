#!/usr/bin/env python3
"""知识库推荐脚本

查询知识库中评分最高的文章并返回 Markdown 格式的推荐列表。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_articles(knowledge_dir: str) -> list[dict[str, Any]]:
    """加载知识库所有条目。"""
    path = Path(knowledge_dir)
    if not path.exists():
        return []

    articles = []
    for file in path.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                articles.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            continue
    return articles


def score_to_emoji(score: float) -> str:
    """评分转 emoji 标识。"""
    if score >= 8.0:
        return "🟢"
    elif score >= 6.0:
        return "🟡"
    elif score >= 4.0:
        return "🟠"
    return "🔴"


def format_recommendation(articles: list[dict[str, Any]], top_n: int) -> str:
    """格式化推荐列表。"""
    if not articles:
        return "📭 知识库暂无条目"

    lines = [f"📚 知识推荐 Top {len(articles)}\n"]

    for i, article in enumerate(articles, 1):
        score = article.get("score", 0.0)
        title = article.get("title", "无标题")
        summary = article.get("summary", "")
        tags = article.get("tags", [])
        source = article.get("source", "未知")
        url = article.get("source_url", "")

        emoji = score_to_emoji(score)
        tags_str = " ".join(f"#{tag}" for tag in tags) if tags else ""

        lines.append(f"{emoji} **{score:.1f}分** | {title}")
        lines.append(f"   {summary[:150]}..." if len(summary) > 150 else f"   {summary}")
        if tags_str:
            lines.append(f"   标签: {tags_str}")
        lines.append(f"   来源: {source}")
        if url:
            lines.append(f"   🔗 {url}")
        lines.append("")  # 空行分隔

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="知识库推荐")
    parser.add_argument("--top", type=int, default=5, help="返回前 N 条 (1-10)")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低评分阈值 (0.0-10.0)")
    parser.add_argument(
        "--knowledge-dir",
        default="knowledge/articles",
        help="知识库目录路径"
    )
    args = parser.parse_args()

    # 参数校验
    top_n = max(1, min(10, args.top))

    # 加载并过滤
    articles = load_articles(args.knowledge_dir)
    if args.min_score > 0:
        articles = [a for a in articles if a.get("score", 0) >= args.min_score]

    # 过滤无内容的条目
    articles = [a for a in articles if a.get("score", 0) > 0 and a.get("title")]

    # 排序
    articles.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_articles = articles[:top_n]

    # 输出
    print(format_recommendation(top_articles, len(top_articles)))


if __name__ == "__main__":
    main()