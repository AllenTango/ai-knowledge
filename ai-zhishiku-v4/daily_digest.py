"""每日知识简报推送入口脚本。

从知识库加载当日文章，过滤低质量内容后推送到各渠道。
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from distribution.formatter import generate_daily_digest
from distribution.publisher import publish_daily_digest, PublishResult


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MIN_SCORE_THRESHOLD = 6.0


def load_articles(knowledge_dir: str, date: str) -> list[dict[str, Any]]:
    """加载指定日期的文章。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 日期字符串，格式为 YYYYMMDD。

    Returns:
        文章列表。
    """
    knowledge_path = Path(knowledge_dir)
    if not knowledge_path.exists():
        logger.warning(f"知识库目录不存在: {knowledge_dir}")
        return []

    pattern = f"{date}-*.json"
    files = list(knowledge_path.glob(pattern))

    if not files:
        logger.warning(f"日期 {date} 没有找到任何文章")
        return []

    articles = []
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                article = json.load(f)
                articles.append(article)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取文件失败 {file}: {e}")

    return articles


def filter_low_quality(articles: list[dict[str, Any]], min_score: float = MIN_SCORE_THRESHOLD) -> list[dict[str, Any]]:
    """过滤低质量文章。

    过滤掉 score 低于阈值的文章。

    Args:
        articles: 文章列表。
        min_score: 最低分数阈值。

    Returns:
        过滤后的文章列表。
    """
    filtered = []
    for article in articles:
        score = article.get("score", 0.0)
        if score >= min_score:
            filtered.append(article)
        else:
            logger.info(f"过滤低质量文章: {article.get('title', '无标题')} (score={score})")

    return filtered


def log_publish_results(results: list[PublishResult]) -> None:
    """记录推送结果。

    Args:
        results: 发布结果列表。
    """
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    logger.info(f"推送完成: 成功 {success_count} 个渠道, 失败 {fail_count} 个渠道")

    for result in results:
        status = "✅" if result.success else "❌"
        channel = result.channel
        if result.success:
            logger.info(f"  {status} {channel} (message_id: {result.message_id})")
        else:
            logger.error(f"  {status} {channel}: {result.error}")


async def run_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
    channels: list[str] | None = None,
    min_score: float = MIN_SCORE_THRESHOLD,
    dry_run: bool = False,
) -> int:
    """执行每日简报推送。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 日期字符串，格式为 YYYYMMDD，默认为当天日期。
        top_n: 选取的 Top N 数量，默认为 5。
        channels: 要发布的渠道列表。
        min_score: 最低分数阈值，低于此分数的文章将被过滤。
        dry_run: 是否仅打印预览而不实际推送。

    Returns:
        0 表示成功，1 表示失败，2 表示跳过（无高质量文章）。
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    logger.info(f"开始生成 {date} 每日简报...")

    articles = load_articles(knowledge_dir, date)
    if not articles:
        logger.warning(f"日期 {date} 没有找到任何文章，跳过推送")
        return 2

    filtered_articles = filter_low_quality(articles, min_score)
    if not filtered_articles:
        logger.warning(f"日期 {date} 没有高质量文章（score >= {min_score}），跳过推送")
        return 2

    logger.info(f"加载了 {len(articles)} 篇文章，过滤后保留 {len(filtered_articles)} 篇高质量文章")

    if dry_run:
        digest = generate_daily_digest(knowledge_dir, date, top_n)
        logger.info("=== 预览 Markdown 格式 ===")
        print(digest["markdown"])
        logger.info("=== 预览结束 ===")
        logger.info("[DRY RUN] 跳过实际推送")
        return 0

    results = await publish_daily_digest(
        knowledge_dir=knowledge_dir,
        date=date,
        top_n=top_n,
        channels=channels,
    )

    log_publish_results(results)

    success_count = sum(1 for r in results if r.success)
    if success_count > 0:
        return 0
    else:
        return 1


def main() -> int:
    """主入口函数."""
    parser = argparse.ArgumentParser(description="每日知识简报推送脚本")
    parser.add_argument(
        "--knowledge-dir",
        type=str,
        default="knowledge/articles",
        help="知识库目录路径",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="日期字符串，格式为 YYYYMMDD，默认为当天日期",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="选取的 Top N 数量",
    )
    parser.add_argument(
        "--channels",
        type=str,
        nargs="+",
        default=None,
        help="要发布的渠道列表，如 telegram qq feishu openclaw",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=MIN_SCORE_THRESHOLD,
        help=f"最低分数阈值，低于此分数的文章将被过滤（默认: {MIN_SCORE_THRESHOLD}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印预览而不实际推送",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出详细日志",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    return asyncio.run(
        run_daily_digest(
            knowledge_dir=args.knowledge_dir,
            date=args.date,
            top_n=args.top_n,
            channels=args.channels,
            min_score=args.min_score,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())