"""迁移旧版 human_review flag 文件为 article 格式。

将 knowledge/human_review/ 目录中旧版 flag 格式文件：
    {"flagged_at, iteration, review_feedback, analyses_count, analyses: [...]}
迁移为新版 article 格式，每个条目一个 {id}.json 文件。

Usage:
    python3 scripts/migrate_human_review.py
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"
KNOWLEDGE_HUMAN_REVIEW = PROJECT_ROOT / "knowledge" / "human_review"


def migrate_flag_file(flag_file: Path) -> dict[str, int]:
    """迁移单个 flag 文件，将其 analyses 数组转为 article 格式文件。

    Args:
        flag_file: flag JSON 文件路径。

    Returns:
        {"migrated": int, "skipped": int, "errors": list[str]}。
    """
    results = {"migrated": 0, "skipped": 0, "errors": []}

    try:
        with open(flag_file, "r", encoding="utf-8") as f:
            flag_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        results["errors"].append(f"读取失败: {e}")
        return results

    analyses = flag_data.get("analyses", [])
    if not analyses:
        logger.info(f"  空文件，跳过: {flag_file.name}")
        results["skipped"] += 1
        return results

    KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)

    for article_data in analyses:
        aid = article_data.get("id", "")
        if not aid:
            results["errors"].append(f"  条目缺少 id，跳过")
            continue

        article_file = KNOWLEDGE_ARTICLES / f"{aid}.json"

        try:
            if article_file.exists():
                with open(article_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            else:
                existing = {}

            existing.update({
                "id": aid,
                "title": article_data.get("title", ""),
                "source": article_data.get("source", ""),
                "source_url": article_data.get("source_url", ""),
                "fetched_at": article_data.get("fetched_at", ""),
                "analyzed_at": article_data.get("analyzed_at", ""),
                "summary": article_data.get("summary", ""),
                "tags": article_data.get("tags", []),
                "score": float(article_data.get("score", 0)),
                "status": "human_review",
                "reviewer": "human-flag",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "published_to": existing.get("published_to", []),
                "retry_count": existing.get("retry_count", 0),
            })

            with open(article_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            logger.info(f"  迁移: {aid} -> {article_file.name}")
            results["migrated"] += 1
        except IOError as e:
            results["errors"].append(f"  写入失败 [{aid}]: {e}")

    return results


def main():
    logger.info("=" * 50)
    logger.info("human_review flag 文件迁移")
    logger.info("=" * 50)

    if not KNOWLEDGE_HUMAN_REVIEW.exists():
        logger.warning(f"目录不存在: {KNOWLEDGE_HUMAN_REVIEW}")
        return

    flag_files = sorted(KNOWLEDGE_HUMAN_REVIEW.glob("*.json"))
    if not flag_files:
        logger.info("无 flag 文件需要迁移")
        return

    logger.info(f"发现 {len(flag_files)} 个 flag 文件")

    total_migrated = 0
    total_skipped = 0
    total_errors: list[str] = []

    for flag_file in flag_files:
        logger.info(f"处理: {flag_file.name}")
        result = migrate_flag_file(flag_file)
        total_migrated += result["migrated"]
        total_skipped += result["skipped"]
        total_errors.extend(result["errors"])

        if result["migrated"] > 0:
            try:
                flag_file.unlink()
                logger.info(f"  已删除旧文件: {flag_file.name}")
            except IOError as e:
                logger.error(f"  删除旧文件失败: {e}")

    logger.info("=" * 50)
    logger.info(f"迁移完成: {total_migrated} 条已迁移, {total_skipped} 个空文件跳过")
    if total_errors:
        logger.warning(f"错误: {total_errors}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
