"""审核 Agent — 对知识条目进行 5 维质量审核。

读取 `knowledge/articles/` 中 status 为 pending_review 的条目，
按 5 个维度评分（满分 100），判定通过/驳回/重试。

Usage:
    python -m workflows.reviewer
    python -m workflows.reviewer --verbose
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"

BUZZWORDS_CN = [
    "赋能", "抓手", "闭环", "打通", "全链路",
    "底层逻辑", "颗粒度", "对齐", "拉通", "沉淀",
    "强大的", "革命性的",
]
BUZZWORDS_EN = [
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
]
BUZZWORDS = BUZZWORDS_CN + BUZZWORDS_EN


def score_summary_quality(summary: str) -> int:
    """评估摘要质量（满分 25）。

    Args:
        summary: 摘要文本。

    Returns:
        得分。
    """
    length = len(summary)
    score = 0

    if length >= 50:
        score = 25
    elif length >= 20:
        score = 15
    else:
        score = 5

    tech_keywords = [
        "LLM", "GPT", "模型", "agent", "框架", "训练",
        "推理", "embedding", "RAG", "微调", "向量",
    ]
    has_tech = any(kw in summary for kw in tech_keywords)
    if has_tech:
        score = min(score + 5, 25)

    return score


def score_technical_depth(item_score: float) -> int:
    """评估技术深度（满分 25）。

    基于条目的 score 字段映射：score × 2.5。

    Args:
        item_score: 条目评分。

    Returns:
        得分。
    """
    return min(int(item_score * 2.5), 25)


def score_format(article: dict[str, Any]) -> int:
    """评估格式规范（满分 20）。

    检查 5 个字段，各 4 分。

    Args:
        article: 知识条目。

    Returns:
        得分。
    """
    checks = [
        bool(article.get("id")),
        bool(article.get("title")),
        bool(article.get("source_url", "").startswith("http")),
        article.get("status") in ("pending_review", "approved", "rejected", "published"),
        bool(article.get("fetched_at")) and bool(article.get("analyzed_at")),
    ]
    return sum(4 for c in checks if c)


def score_tags(tags: list[str]) -> int:
    """评估标签精度（满分 15）。

    Args:
        tags: 标签列表。

    Returns:
        得分。
    """
    count = len(tags)
    if count <= 3:
        return 15
    elif count <= 5:
        return 10
    return 5


def score_buzzwords(text: str) -> int:
    """空洞词检测（满分 15）。

    Args:
        text: 检测文本（标题 + 摘要）。

    Returns:
        得分。
    """
    text_lower = text.lower()
    for bw in BUZZWORDS:
        if bw.lower() in text_lower:
            logger.warning(f"  检测到空洞词: {bw}")
            return 0
    return 15


def set_verdict(total_score: int, article: dict[str, Any]) -> str:
    """根据总分和条目状态判定最终结果。

    Args:
        total_score: 5 维总分（0-100）。
        article: 知识条目。

    Returns:
        判定结果: approved | rejected | retry。
    """
    retry_count = article.get("retry_count", 0)

    if total_score >= 80:
        return "approved"
    elif total_score >= 60:
        return "approved"
    else:
        if retry_count < 3:
            return "retry"
        return "rejected"


def review_article(article: dict[str, Any]) -> dict[str, Any]:
    """对单条条目执行 5 维评分。

    Args:
        article: 待审核的知识条目。

    Returns:
        审核结果，包含 verdict、grade、score、breakdown、issues 等字段。
    """
    summary = article.get("summary", "")
    title = article.get("title", "")
    tags = article.get("tags", [])
    item_score = article.get("score", 5.0)

    s_summary = score_summary_quality(summary)
    s_depth = score_technical_depth(item_score)
    s_format = score_format(article)
    s_tags = score_tags(tags)
    s_buzz = score_buzzwords(f"{title} {summary}")

    total_score = s_summary + s_depth + s_format + s_tags + s_buzz

    if total_score >= 80:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    else:
        grade = "C"

    verdict = set_verdict(total_score, article)

    issues = []
    if s_summary < 20:
        issues.append("摘要质量不足")
    if s_depth < 15:
        issues.append("技术深度偏低")
    if s_format < 16:
        issues.append("格式规范有问题")
    if s_buzz == 0:
        issues.append("包含空洞词")
    if grade == "C":
        issues.append("总分不合格")

    return {
        "id": article.get("id", ""),
        "verdict": verdict,
        "grade": grade,
        "score": total_score,
        "breakdown": {
            "摘要质量": {"得分": s_summary, "满分": 25},
            "技术深度": {"得分": s_depth, "满分": 25},
            "格式规范": {"得分": s_format, "满分": 20},
            "标签精度": {"得分": s_tags, "满分": 15},
            "空洞词检测": {"得分": s_buzz, "满分": 15},
        },
        "reason": f"总分 {total_score}/100，等级 {grade}，"
                  f"判定: {verdict}",
        "issues": issues,
        "reviewer": "reviewer-agent",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def batch_review() -> list[dict[str, Any]]:
    """审核所有 pending_review 条目。

    Returns:
        审核结果列表。
    """
    logger.info("=" * 50)
    logger.info("条目审核")
    logger.info("=" * 50)

    if not KNOWLEDGE_ARTICLES.exists():
        logger.warning("articles 目录不存在")
        return []

    pending = []
    for json_file in sorted(KNOWLEDGE_ARTICLES.glob("*.json")):
        if json_file.name == "index.json":
            continue
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                article = json.load(f)
            if article.get("status") == "pending_review":
                pending.append((json_file, article))
        except (json.JSONDecodeError, IOError):
            continue

    logger.info(f"待审条目: {len(pending)} 条")

    pending.sort(
        key=lambda x: x[1].get("score", 0),
        reverse=True,
    )

    results = []
    for file_path, article in pending:
        title = article.get("title", "?")
        logger.info(f"审核: {file_path.name} ({title[:30]})")

        review = review_article(article)
        verdict = review["verdict"]
        logger.info(
            f"  等级 {review['grade']}, 总分 {review['score']}, "
            f"判定: {verdict}"
        )

        now = datetime.now(timezone.utc).isoformat()
        if verdict == "approved":
            article["status"] = "approved"
            article["reviewer"] = "reviewer-agent"
            article["reviewed_at"] = now
        elif verdict == "rejected":
            article["status"] = "rejected"
            article["reviewer"] = "reviewer-agent"
            article["reviewed_at"] = now
        elif verdict == "retry":
            article["retry_count"] = article.get("retry_count", 0) + 1
            if article["retry_count"] >= 3:
                article["status"] = "rejected"
                article["reviewer"] = "human_needed"
                article["reviewed_at"] = now
                logger.warning(
                    f"  retry_count >= 3，标记 human_needed"
                )

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        review["article_title"] = title
        results.append(review)

    statuses = {}
    for r in results:
        v = r["verdict"]
        statuses[v] = statuses.get(v, 0) + 1
    logger.info(f"审核完成: {statuses}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI 知识库 — 审核 Agent")
    parser.add_argument("--verbose", action="store_true", help="详细日志模式")

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    results = batch_review()
    print(f"\n审核完成，共 {len(results)} 条")
    for r in results:
        print(f"  [{r['verdict']}] {r.get('article_title', '?')} "
              f"- {r['score']}/100 ({r['grade']})")
