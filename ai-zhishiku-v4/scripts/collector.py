"""采集 Agent — 从 GitHub Trending / RSS 采集原始数据。

写入 `knowledge/raw/{source}-{date}.json`。

Usage:
    python -m scripts.collector --sources github,rss --limit 20
    python -m scripts.collector --sources github --limit 5
    python -m scripts.collector --sources rss --limit 10
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_RAW = PROJECT_ROOT / "knowledge" / "raw"


def ensure_directories() -> None:
    """确保 knowledge/raw/ 目录存在。"""
    KNOWLEDGE_RAW.mkdir(parents=True, exist_ok=True)


def fetch_github_trending(limit: int = 20) -> list[dict[str, Any]]:
    """从 GitHub Search API 采集 AI 相关热门项目。

    Args:
        limit: 最大采集条数。

    Returns:
        采集到的原始条目列表。
    """
    date_7days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    keywords = ["AI", "LLM", "agent", "langchain", "llamaindex", "rag"]
    query_parts = [f"{kw} pushed:>{date_7days_ago}" for kw in keywords]
    query = " OR ".join(query_parts)

    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    }
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {token}"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])[:limit]

        results = []
        for item in items:
            results.append(
                {
                    "id": str(uuid.uuid4()),
                    "source": "github",
                    "source_url": item.get("html_url", ""),
                    "title": item.get("full_name", ""),
                    "content": item.get("description", "") or "",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "topics": item.get("topics", []),
                }
            )
        logger.info(f"GitHub 采集完成，获取 {len(results)} 条")
        return results
    except httpx.HTTPStatusError as e:
        logger.error(f"GitHub API 请求失败: {e.response.status_code}")
        return []
    except Exception as e:
        logger.error(f"GitHub 采集异常: {e}")
        return []


def parse_rss_feed(url: str, limit: int = 20) -> list[dict[str, Any]]:
    """简易 RSS 解析函数。

    Args:
        url: RSS 订阅源地址。
        limit: 最大解析条数。

    Returns:
        解析后的条目列表。
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            xml_content = response.text
    except Exception as e:
        logger.error(f"RSS 请求失败 ({url}): {e}")
        return []

    pattern = re.compile(
        r"<item>.*?<title><!\[CDATA\[(.*?)\]\]></title>.*?"
        r"<link>(.*?)</link>.*?"
        r"<description><!\[CDATA\[(.*?)\]\]></description>.*?"
        r"</item>",
        re.DOTALL,
    )
    matches = pattern.findall(xml_content)[:limit]

    results = []
    for title, link, desc in matches:
        results.append(
            {
                "id": str(uuid.uuid4()),
                "source": "rss",
                "source_url": link.strip(),
                "title": title.strip(),
                "content": desc.strip()[:500],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return results


def load_rss_sources() -> dict[str, str]:
    """加载 rss_sources.yaml 中的 RSS 源。

    Returns:
        源名称到 URL 的映射字典。
    """
    rss_file = PROJECT_ROOT / "pipeline" / "rss_sources.yaml"
    if not rss_file.exists():
        return {}

    try:
        import yaml

        with open(rss_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        sources = config.get("sources", [])
        return {s["name"]: s["url"] for s in sources if s.get("enabled", False)}
    except Exception as e:
        logger.warning(f"RSS 配置加载失败: {e}")
        return {}


def fetch_rss_sources(limit: int = 20) -> list[dict[str, Any]]:
    """从所有启用的 RSS 源采集内容。

    Args:
        limit: 每源最大采集条数。

    Returns:
        采集到的原始条目列表。
    """
    rss_map = load_rss_sources()
    all_items = []
    for name, url in rss_map.items():
        logger.info(f"正在采集 RSS: {name}")
        items = parse_rss_feed(url, limit)
        for item in items:
            item["source_name"] = name
        all_items.extend(items)
        logger.info(f"  {name} 获取 {len(items)} 条")

    logger.info(f"RSS 采集完成，共 {len(all_items)} 条")
    return all_items


def collect(sources: str = "github,rss", limit: int = 20) -> list[dict[str, Any]]:
    """采集数据主函数。

    Args:
        sources: 源标识，逗号分隔（github, rss）。
        limit: 每源最大条数。

    Returns:
        原始采集数据列表。
    """
    logger.info("=" * 50)
    logger.info("数据采集")
    logger.info("=" * 50)

    ensure_directories()
    source_list = [s.strip() for s in sources.split(",")]
    results = []

    if "github" in source_list:
        results.extend(fetch_github_trending(limit))
    if "rss" in source_list:
        results.extend(fetch_rss_sources(limit))

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if results:
        raw_file = KNOWLEDGE_RAW / f"raw-{date_str}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"原始数据已保存: {raw_file.name}")

    logger.info(f"采集完成，共获取 {len(results)} 条原始数据")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI 知识库 — 采集 Agent")
    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="数据源，逗号分隔，可选 github, rss（默认: github,rss）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每源最大采集条数（默认: 20）",
    )
    parser.add_argument("--verbose", action="store_true", help="详细日志模式")

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    collect(sources=args.sources, limit=args.limit)
