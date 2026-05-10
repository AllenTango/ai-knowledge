"""LangGraph 工作流节点函数 — collect, analyze, organize, review, save。

每个节点接收 KBState，返回部分状态更新 dict，由 StateGraph 自动合并。
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflows.state import KBState

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"


def _merge_cost(
    cost_tracker: dict,
    tokens: int,
    provider: str,
    node_name: str,
) -> dict:
    """将本轮 token 用量累积到 cost_tracker 报告。

    Args:
        cost_tracker: 当前累积报告。
        tokens: 本轮消耗 token 数。
        provider: LLM 提供商名称。
        node_name: 节点名称（如 "analyze"）。

    Returns:
        更新后的 cost_tracker 副本。
    """
    ct = {
        "total_tokens": cost_tracker.get("total_tokens", 0) + tokens,
        "total_cost_cny": cost_tracker.get("total_cost_cny", 0.0),
        "providers": dict(cost_tracker.get("providers", {})),
        "by_node": dict(cost_tracker.get("by_node", {})),
    }
    ct["by_node"][node_name] = ct["by_node"].get(node_name, 0) + tokens

    if provider not in ct["providers"]:
        ct["providers"][provider] = {"tokens": 0, "cost": 0.0}
    ct["providers"][provider]["tokens"] = (
        ct["providers"][provider].get("tokens", 0) + tokens
    )
    return ct


# ═══════════════════════════════════════════════════════════════════
# 节点 1: collect_node — 双源采集（GitHub Search API + RSS）
# ═══════════════════════════════════════════════════════════════════

def collect_node(state: KBState) -> dict:
    """采集节点：GitHub Search API + RSS 双源采集。

    Args:
        state: KBState。

    Returns:
        dict: 包含 sources 和 cost_tracker 更新。
    """
    logger.info("--- collect_node ---")
    sources = []
    cost_tracker = dict(state.get("cost_tracker", {}))

    # ── GitHub Search API（urllib.request） ──────────────────────

    query_keywords = ["AI", "LLM", "agent", "langchain", "machine learning"]
    query = " OR ".join(query_keywords)
    encoded_query = urllib.parse.quote(query)
    url = (
        "https://api.github.com/search/repositories"
        f"?q={encoded_query}&sort=stars&order=desc&per_page=10"
    )

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ai-zhishiku-langgraph/1.0",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for item in data.get("items", [])[:10]:
            sources.append({
                "id": str(uuid.uuid4()),
                "title": item.get("full_name", ""),
                "source": "github",
                "source_url": item.get("html_url", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language") or "unknown",
                "description": item.get("description") or "",
            })
        logger.info(f"GitHub 采集: {len(sources)} 条")
    except Exception as e:
        logger.error(f"GitHub 采集失败: {e}")

    # ── RSS 源采集（复用 collector 模块） ────────────────────────

    try:
        from workflows.collector import fetch_rss_sources
        rss_items = fetch_rss_sources(limit=10)
        for item in rss_items:
            item.setdefault("id", str(uuid.uuid4()))
            item.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
            item.setdefault("stars", 0)
            item.setdefault("language", "unknown")
        sources.extend(rss_items)
        logger.info(f"RSS 采集: {len(rss_items)} 条")
    except Exception as e:
        logger.error(f"RSS 采集失败: {e}")

    cost_tracker = _merge_cost(cost_tracker, 0, "", "collect")
    logger.info(f"总数: {len(sources)} 条")
    return {"sources": sources, "cost_tracker": cost_tracker}


# ═══════════════════════════════════════════════════════════════════
# 节点 2: analyze_node — LLM 分析
# ═══════════════════════════════════════════════════════════════════

ANALYZE_SYSTEM_PROMPT = """你是一个 AI 技术资讯分析师。
请对以下项目进行结构化分析，输出 JSON：

{
    "summary": "中文摘要，50-200字，包含：是什么 / 为什么重要 / 与 AI 领域关联三个层次",
    "tags": ["标签1", "标签2"],
    "score": 0.85
}

规则：
- tags: 3-8 个小写英文标签，用连字符连接（如 agent、llm-framework）
- score: 0.0-1.0 相关性评分（0.7+ = 高质量，<0.6 = 低质）
- 只输出 JSON，不要其他内容"""


def analyze_node(state: KBState) -> dict:
    """分析节点：对 sources 中每条用 LLM 生成摘要/标签/评分。

    Args:
        state: KBState。

    Returns:
        dict: 包含 analyses 和 cost_tracker 更新。
    """
    logger.info("--- analyze_node ---")

    from workflows.model_client import chat, check_llm_available

    if not check_llm_available():
        logger.warning("LLM 不可用，跳过分析")
        return {}

    sources = state.get("sources", [])
    if not sources:
        logger.warning("无原始数据可分析")
        return {}

    analyses = []
    cost_tracker = dict(state.get("cost_tracker", {}))
    provider = os.getenv("LLM_PROVIDER", "deepseek")

    for i, item in enumerate(sources):
        title = item.get("title", "")
        desc = item.get("description", "")[:500]
        source_url = item.get("source_url", "")

        prompt = f"项目: {title}\n描述: {desc}\nURL: {source_url}"
        try:
            (text, usage) = chat(system=ANALYZE_SYSTEM_PROMPT, prompt=prompt, temperature=0.7)

            # 提取 JSON
            json_match = re.search(
                r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL
            )
            if json_match:
                text = json_match.group(1)

            analysis = json.loads(text)
        except Exception as e:
            logger.warning(f"分析失败 ({title}): {e}")
            analysis = {"summary": "[分析失败]", "tags": [], "score": 0.0}

        analysis["id"] = item.get("id", str(uuid.uuid4()))
        analysis["title"] = analysis.get("title", title)
        analysis["source"] = item.get("source", "unknown")
        analysis["source_url"] = source_url
        analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        analysis["model_provider"] = provider

        tokens = usage.total_tokens if 'usage' in dir() else 0
        cost_tracker = _merge_cost(cost_tracker, tokens, provider, "analyze")
        analyses.append(analysis)

        logger.info(f"  [{i+1}/{len(sources)}] {title[:40]} score={analysis.get('score', '?')}")

    logger.info(f"分析完成: {len(analyses)} 条")
    return {"analyses": analyses, "cost_tracker": cost_tracker}


# ═══════════════════════════════════════════════════════════════════
# 节点 3: organize_node — 过滤 / 去重 / LLM修正 / 格式化
# ═══════════════════════════════════════════════════════════════════

FIX_SYSTEM_PROMPT = """你是知识库内容修正员。
请根据以下审核反馈，修正分析报告的内容。

审核反馈：
{feedback}

请修正后的输出 JSON（保持字段结构不变）：
{{
    "summary": "修正后的中文摘要",
    "tags": ["标签1", "标签2"],
    "score": 0.85
}}
只输出 JSON。"""


def organize_node(state: KBState) -> dict:
    """整理节点：过滤低分 / URL 去重 / 审核反馈修正 / 格式化为 articles。

    Args:
        state: KBState。

    Returns:
        dict: 包含 articles 和 cost_tracker 更新。
    """
    logger.info("--- organize_node ---")

    analyses = state.get("analyses", [])
    review_feedback = state.get("review_feedback", "")
    cost_tracker = dict(state.get("cost_tracker", {}))

    # Step 1: 过滤低分条目（score < 0.6）
    filtered = [a for a in analyses if a.get("score", 0) >= 0.6]
    logger.info(f"过滤后: {len(filtered)}/{len(analyses)} 条")

    # Step 2: 按 URL 去重
    seen_urls: set[str] = set()
    deduped = []
    for a in filtered:
        url = a.get("source_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(a)
        elif not url:
            deduped.append(a)
    logger.info(f"去重后: {len(deduped)} 条")

    # Step 3: 如有审核反馈，用 LLM 逐条修正
    if review_feedback:
        from workflows.model_client import chat, check_llm_available

        if check_llm_available():
            provider = os.getenv("LLM_PROVIDER", "deepseek")
            logger.info(f"LLM 修正: 反馈 = {review_feedback[:60]}...")
            system = FIX_SYSTEM_PROMPT.format(feedback=review_feedback)

            for item in deduped:
                prompt = json.dumps({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "tags": item.get("tags", []),
                    "score": item.get("score", 0),
                }, ensure_ascii=False)

                try:
                    (text, usage) = chat(system=system, prompt=prompt, temperature=0.3)

                    json_match = re.search(
                        r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL
                    )
                    if json_match:
                        text = json_match.group(1)

                    corrected = json.loads(text)
                    item["summary"] = corrected.get("summary", item.get("summary", ""))
                    item["tags"] = corrected.get("tags", item.get("tags", []))
                    item["score"] = corrected.get("score", item.get("score", 0))
                    cost_tracker = _merge_cost(
                        cost_tracker, usage.total_tokens, provider, "organize"
                    )
                except Exception as e:
                    logger.warning(f"修正失败 ({item.get('title', '?')}): {e}")

    # Step 4: 格式化为 articles（AGENTS.md 标准格式）
    articles = []
    for item in deduped:
        article = {
            "id": item.get("id", str(uuid.uuid4())),
            "title": item.get("title", ""),
            "source": item.get("source", "unknown"),
            "source_url": item.get("source_url", ""),
            "fetched_at": item.get("fetched_at", ""),
            "analyzed_at": item.get("analyzed_at", ""),
            "summary": item.get("summary", ""),
            "tags": item.get("tags", []),
            "status": "pending_review",
            "score": item.get("score", 0),
            "reviewer": None,
            "reviewed_at": None,
            "published_to": [],
            "retry_count": 0,
        }
        articles.append(article)

    logger.info(f"articles: {len(articles)} 条")
    return {"articles": articles, "cost_tracker": cost_tracker}


# ═══════════════════════════════════════════════════════════════════
# 节点 4: review_node — LLM 四维度评分
# ═══════════════════════════════════════════════════════════════════

REVIEW_SYSTEM_PROMPT = """你是一个知识库质量审核员。
请对以下知识条目按四个维度评分（每个维度 0-10 分）：

1. 摘要质量(0-10): 中文通畅性、50-200字合规、是否包含
   "是什么 / 为什么重要 / 与 AI 领域关联"三层结构
2. 标签准确(0-10): 标签是否贴合内容、3-8个范围、
   小写英文连字符格式
3. 分类合理(0-10): 条目是否属于 AI/LLM/Agent/机器学习领域
4. 一致性(0-10): score 与 summary 质量是否匹配
   （高分低质 = 扣分）

总分 = 四维度之和。通过线 = 28（平均 7 分/维度）。

输出 JSON:
{
    "passed": true/false,
    "total_score": 总分,
    "dimensions": {"摘要质量": n, "标签准确": n, "分类合理": n, "一致性": n},
    "feedback": "未通过时的具体问题和改进方向"
}
只输出 JSON。"""


def review_node(state: KBState) -> dict:
    """审核节点：四维度评分 + 强制通过兜底。

    Args:
        state: KBState。

    Returns:
        dict: 包含 review_passed / review_feedback / iteration / cost_tracker。
    """
    logger.info("--- review_node ---")

    articles = state.get("articles", [])
    iteration = state.get("iteration", 0)
    cost_tracker = dict(state.get("cost_tracker", {}))

    # 强制通过：iteration >= 2 → 兜底
    if iteration >= 2:
        logger.info(f"iteration={iteration} >= 2，强制通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    if not articles:
        logger.warning("无 articles 可审核")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    from workflows.model_client import chat, check_llm_available

    if not check_llm_available():
        logger.warning("LLM 不可用，默认通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    provider = os.getenv("LLM_PROVIDER", "deepseek")
    feedbacks = []
    all_passed = True

    for article in articles:
        review_input = json.dumps({
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "tags": article.get("tags", []),
            "score": article.get("score", 0),
        }, ensure_ascii=False)

        try:
            (text, usage) = chat(
                system=REVIEW_SYSTEM_PROMPT, prompt=review_input, temperature=0.2
            )

            json_match = re.search(
                r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL
            )
            if json_match:
                text = json_match.group(1)

            review = json.loads(text)
            cost_tracker = _merge_cost(
                cost_tracker, usage.total_tokens, provider, "review"
            )
        except Exception as e:
            logger.warning(f"审核失败 ({article.get('title', '?')}): {e}")
            review = {"passed": True, "total_score": 30, "dimensions": {}, "feedback": ""}

        if not review.get("passed", False):
            all_passed = False
            feedbacks.append(
                f"[{article.get('title', '?')}] {review.get('feedback', '')}"
            )

        dims = review.get("dimensions", {})
        logger.info(
            f"  审核: {article.get('title', '?')[:30]} "
            f"passed={review['passed']} "
            f"摘要={dims.get('摘要质量','?')} "
            f"标签={dims.get('标签准确','?')} "
            f"分类={dims.get('分类合理','?')} "
            f"一致={dims.get('一致性','?')}"
        )

    new_iteration = iteration + 1
    logger.info(
        f"审核完成: passed={all_passed}, iteration={new_iteration}"
    )

    return {
        "review_passed": all_passed,
        "review_feedback": "; ".join(feedbacks) if feedbacks else "",
        "iteration": new_iteration,
        "cost_tracker": cost_tracker,
    }


# ═══════════════════════════════════════════════════════════════════
# 节点 5: save_node — 写入 knowledge/articles/
# ═══════════════════════════════════════════════════════════════════

def save_node(state: KBState) -> dict:
    """保存节点：将 articles 写入 knowledge/articles/ 目录。

    文件命名: {YYYYMMDD}-{source}-{slug}.json

    Args:
        state: KBState。

    Returns:
        dict: 空更新（流程终止）。
    """
    logger.info("--- save_node ---")

    articles = state.get("articles", [])
    if not articles:
        logger.info("无 articles 可保存")
        return {}

    KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    saved = 0

    for item in articles:
        title = item.get("title", "untitled")
        slug = re.sub(r"[^a-zA-Z0-9]", "-", title.lower())[:30].strip("-")
        if not slug:
            slug = f"item-{uuid.uuid4().hex[:8]}"

        source = item.get("source", "unknown")
        filename = f"{date_str}-{source}-{slug}.json"
        filepath = KNOWLEDGE_ARTICLES / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        saved += 1
        logger.info(f"  已保存: {filename}")

    logger.info(f"保存完成: {saved} 篇")
    return {}
