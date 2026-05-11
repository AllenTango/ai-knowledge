"""整理 Agent — 去重、校验、归档知识条目。

读取 `knowledge/analyzer_output/`，进行去重、格式校验，
写入 `knowledge/articles/{date}-{source}-{slug}.json`。

Usage:
    python -m scripts.organizer
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ANALYZER = PROJECT_ROOT / "knowledge" / "analyzer_output"
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"


def load_analyzer_output() -> list[dict[str, Any]]:
    """加载 analyzer_output 中最新的分析结果。

    Returns:
        分析后的条目列表。
    """
    if not KNOWLEDGE_ANALYZER.exists():
        return []

    json_files = sorted(KNOWLEDGE_ANALYZER.glob("*.json"), reverse=True)
    if not json_files:
        return []

    all_items = []
    for f in json_files[:2]:
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                items = json.load(fh)
                all_items.extend(items)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"读取 {f.name} 失败: {e}")

    return all_items


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对条目进行去重。

    Args:
        items: 待去重条目列表。

    Returns:
        去重后的条目列表。
    """
    seen_urls: dict[str, datetime] = {}
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)
    valid = []

    for item in items:
        url = item.get("source_url", "")
        if not url:
            continue

        fetched_str = item.get("fetched_at", "")
        if fetched_str:
            try:
                fetched_time = datetime.fromisoformat(fetched_str.replace("Z", "+00:00"))
            except Exception:
                fetched_time = datetime.now(timezone.utc)
        else:
            fetched_time = datetime.now(timezone.utc)

        if url in seen_urls:
            old_fetched = seen_urls[url]
            # 保留更新鲜的条目（相同 URL，新条目优先）
            if fetched_time <= old_fetched:
                logger.info(f"  去重（相同或更旧）: {url}")
                continue
            # 否则用更新鲜的替换
            seen_urls[url] = fetched_time
        else:
            seen_urls[url] = fetched_time

        if fetched_time < cutoff_time:
            logger.info(f"  过期: {url}")
            continue
        valid.append(item)

    return valid


def validate_item(item: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验条目格式。

    Args:
        item: 待校验条目。

    Returns:
        (是否通过, 错误列表)。
    """
    errors = []

    if not item.get("id"):
        errors.append("缺少 id")
    if not item.get("title"):
        errors.append("缺少 title")
    if not item.get("source_url", "").startswith("http"):
        errors.append("source_url 格式非法")
    if not item.get("fetched_at"):
        errors.append("缺少 fetched_at")
    if not item.get("analyzed_at"):
        errors.append("缺少 analyzed_at")
    if not item.get("summary"):
        errors.append("缺少 summary")
    elif len(item["summary"]) < 10:
        errors.append("summary 过短")

    tags = item.get("tags", [])
    if not tags or not isinstance(tags, list):
        errors.append("tags 缺失或类型错误")

    score = item.get("score", 0)
    if not isinstance(score, (int, float)):
        errors.append("score 类型错误")
    elif score < 0 or score > 10:
        errors.append("score 超出 0-10 范围")

    return len(errors) == 0, errors


def classify_status(item: dict[str, Any]) -> str:
    """根据分值判定状态。

    Args:
        item: 待判定条目。

    Returns:
        状态字符串。
    """
    score = item.get("score", 0)
    if score < 5.0:
        return "rejected"
    return "pending_review"


def organize() -> list[dict[str, Any]]:
    """执行整理流程：去重 → 校验 → 分类 → 归档。

    Returns:
        归档后的有效条目列表。
    """
    logger.info("=" * 50)
    logger.info("数据整理")
    logger.info("=" * 50)

    items = load_analyzer_output()
    if not items:
        logger.warning("无分析结果可整理")
        return []

    logger.info(f"加载 {len(items)} 条分析结果")

    items = deduplicate(items)
    logger.info(f"去重后剩余 {len(items)} 条")

    validated = []
    for item in items:
        ok, errors = validate_item(item)
        if not ok:
            logger.warning(f"  校验失败 ({item.get('title', '?')}): {errors}")
            continue

        if not item.get("relevant", True):
            item["status"] = "rejected"
            validated.append(item)
            continue

        item["status"] = classify_status(item)
        item["retry_count"] = 0
        item["published_to"] = []
        item["reviewer"] = None
        item["reviewed_at"] = None

        if not item.get("id"):
            item["id"] = str(uuid.uuid4())

        validated.append(item)

    valid_items = [i for i in validated if i.get("status") != "rejected"]
    logger.info(f"有效条目 {len(valid_items)} 条")

    save_articles(valid_items)
    return valid_items


def save_articles(items: list[dict[str, Any]]) -> None:
    """保存整理后的条目到 articles 目录。

    Args:
        items: 待保存条目列表。
    """
    KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    counters: dict[str, int] = {}
    saved_count = 0

    for item in items:
        if item.get("status") not in ("pending_review", "approved"):
            continue

        source = item.get("source", "unknown")
        counters[source] = counters.get(source, 0) + 1
        seq = counters[source]

        title = item.get("title", "untitled")
        slug = re.sub(r"[^a-zA-Z0-9]", "-", title.lower())[:30].strip("-")
        if not slug:
            slug = f"item-{seq}"

        article_file = KNOWLEDGE_ARTICLES / f"{timestamp[:8]}-{source}-{slug}.json"

        with open(article_file, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        saved_count += 1
        logger.info(f"  已保存: {article_file.name}")

    logger.info(f"归档完成，共保存 {saved_count} 篇")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI 知识库 — 整理 Agent")
    parser.add_argument("--verbose", action="store_true", help="详细日志模式")

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    organize()
