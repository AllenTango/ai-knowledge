"""LangGraph 工作流节点函数 — planner, collect, analyze, organize, review, revise, save, human_flag。

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
MAX_ITERATIONS = 3


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
    ct: dict[str, Any] = {
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
# 节点 0: planner_node — 制定工作流策略
# ═══════════════════════════════════════════════════════════════════

def plan_strategy(target_count: int | None = None) -> dict[str, Any]:
    """根据目标采集量返回工作流策略。

    Args:
        target_count: 目标采集条目数，None 时从环境变量 PLANNER_TARGET_COUNT 读取。

    Returns:
        策略 dict，包含 strategy / per_source_limit / relevance_threshold /
        max_iterations / rationale。
    """
    if target_count is None:
        target_count = int(os.getenv("PLANNER_TARGET_COUNT", "10"))

    if target_count < 10:
        strategy = "lite"
        per_source_limit = 5
        relevance_threshold = 0.7
        max_iterations = 1
        rationale = (
            f"目标采集量 {target_count} < 10，采用 lite 策略："
            "每个数据源限制 5 条，相关性阈值 0.7（高质量过滤），"
            "审核循环上限 1 次。适用于试探性采集，节省 token。"
        )
    elif target_count < 20:
        strategy = "standard"
        per_source_limit = 10
        relevance_threshold = 0.5
        max_iterations = 2
        rationale = (
            f"目标采集量 {target_count} 处于 [10, 20) 区间，采用 standard 策略："
            "每个数据源限制 10 条，相关性阈值 0.5（平衡质量和覆盖），"
            "审核循环上限 2 次。适用于日常采集场景。"
        )
    else:
        strategy = "full"
        per_source_limit = 20
        relevance_threshold = 0.4
        max_iterations = 3
        rationale = (
            f"目标采集量 {target_count} >= 20，采用 full 策略："
            "每个数据源限制 20 条，相关性阈值 0.4（宽口径收录），"
            "审核循环上限 3 次，配合人工标记兜底。适用于深度全量采集。"
        )

    return {
        "strategy": strategy,
        "per_source_limit": per_source_limit,
        "relevance_threshold": relevance_threshold,
        "max_iterations": max_iterations,
        "target_count": target_count,
        "rationale": rationale,
    }


def planner_node(state: KBState) -> dict[str, Any]:
    """Planner 节点：制定工作流策略。

    Args:
        state: KBState。

    Returns:
        dict: 包含 plan 配置。
    """
    logger.info("--- planner_node ---")

    target = state.get("target_count")
    plan = plan_strategy(target_count=target)
    logger.info(f"策略: {plan['strategy']} | {plan['rationale']}")

    return {"plan": plan}


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
    plan = state.get("plan", {})
    per_source_limit = plan.get("per_source_limit", 10)
    logger.info(f"per_source_limit: {per_source_limit}")

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

        for item in data.get("items", [])[:per_source_limit]:
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
        rss_items = fetch_rss_sources(limit=per_source_limit)
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

    # Step 1: 过滤低分条目（使用 plan 中的 relevance_threshold）
    plan = state.get("plan", {})
    threshold = plan.get("relevance_threshold", 0.6)
    filtered = [a for a in analyses if a.get("score", 0) >= threshold]
    logger.info(f"过滤后: {len(filtered)}/{len(analyses)} 条（阈值 {threshold}）")

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
# 节点 4: review_node — LLM 5 维度加权评分
# ═══════════════════════════════════════════════════════════════════

REVIEW_SYSTEM_PROMPT = """你是一个知识库质量审核员。
请对以下分析条目按 5 个维度评分，每个维度 1-10 分：

- summary_quality（摘要质量，权重 25%）：中文通畅、50-200字、结构完整（是什么/为什么/关联）
- technical_depth（技术深度，权重 25%）：技术细节、可行性、深度
- relevance（相关性，权重 20%）：与 AI/LLM/Agent 领域的关联度
- originality（原创性，权重 15%）：内容独特性，非泛泛而谈
- formatting（格式规范，权重 15%）：字段完整、标签合理、无空洞词

输出 JSON（不要包含其他内容）：
{
    "reviews": [
        {
            "id": "条目id",
            "summary_quality": 8,
            "technical_depth": 7,
            "relevance": 9,
            "originality": 6,
            "formatting": 8
        },
        ...
    ]
}"""


def _recompute_weighted_score(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """代码级重算加权总分，不信任 LLM 算术。

    Args:
        reviews: LLM 返回的维度评分列表。

    Returns:
        附加了 weighted_score 和 passed 字段的 reviews。
    """
    for review in reviews:
        weighted = 0.0
        for dim_key in ("summary_quality", "technical_depth", "relevance", "originality", "formatting"):
            score = float(review.get(dim_key, 0))
            weight = {"summary_quality": 0.25, "technical_depth": 0.25, "relevance": 0.20, "originality": 0.15, "formatting": 0.15}[dim_key]
            weighted += score * weight
        review["weighted_score"] = round(weighted, 2)
        review["passed"] = weighted >= 7.0
    return reviews


def review_node(state: KBState) -> dict[str, Any]:
    """审核节点：对 analyses 执行 5 维度加权质量评分。

    - 审核对象：state["analyses"]（非 articles）
    - 只审核前 5 条（控制 token 消耗）
    - 5 维度：summary_quality/technical_depth/relevance/originality/formatting
    - 代码重算加权总分，>= 7.0 通过
    - temperature=0.1，LLM 失败自动通过

    Args:
        state: KBState。

    Returns:
        dict: 包含 review_passed / review_feedback / iteration / cost_tracker。
    """
    logger.info("--- review_node ---")

    analyses = state.get("analyses", [])
    iteration = state.get("iteration", 0)
    cost_tracker = dict(state.get("cost_tracker", {}))

    if not analyses:
        logger.warning("analyses 为空，跳过审核")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    from workflows.model_client import chat_json, check_llm_available

    if not check_llm_available():
        logger.warning("LLM 不可用，默认审核通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    provider = os.getenv("LLM_PROVIDER", "deepseek")
    to_review = analyses[:5]

    prompt_lines = []
    for item in to_review:
        prompt_lines.append(
            f"id: {item.get('id', 'unknown')}\n"
            f"title: {item.get('title', '')}\n"
            f"summary: {item.get('summary', '')}\n"
            f"tags: {item.get('tags', [])}\n"
            f"score: {item.get('score', 0)}\n---"
        )
    prompt = "\n".join(prompt_lines)

    try:
        parsed, usage = chat_json(
            prompt=prompt,
            system=REVIEW_SYSTEM_PROMPT,
            temperature=0.1,
        )

        tokens = usage.total_tokens
        cost_tracker = _merge_cost(cost_tracker, tokens, provider, "review")

        reviews = parsed.get("reviews", [])
        reviews = _recompute_weighted_score(reviews)

    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}，自动通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    failed = [r for r in reviews if not r.get("passed", False)]
    all_passed = len(failed) == 0

    for item in to_review:
        review = next(
            (r for r in reviews if r.get("id") == item.get("id")), None
        )
        if review:
            logger.info(
                f"  {item.get('title', '?')[:35]} "
                f"总分={review.get('weighted_score', '?')} "
                f"passed={review.get('passed')}"
            )

    new_iteration = iteration + 1
    feedback = ""
    if not all_passed:
        feedback_parts = []
        for r in failed:
            dim_list = [
                f"{dim_key}={r.get(dim_key, 0)}"
                for dim_key in ("summary_quality", "technical_depth", "relevance", "originality", "formatting")
                if r.get(dim_key, 0) < 7
            ]
            feedback_parts.append(
                f"[{r.get('id', '?')}] 加权总分={r.get('weighted_score', 0)}，"
                f"低分维度: {', '.join(dim_list) if dim_list else '整体偏低'}"
            )
        feedback = "; ".join(feedback_parts)

    logger.info(
        f"审核完成: passed={all_passed}, iteration={new_iteration}, "
        f"反馈={feedback[:80] if feedback else '(无)'}"
    )

    return {
        "review_passed": all_passed,
        "review_feedback": feedback,
        "iteration": new_iteration,
        "cost_tracker": cost_tracker,
    }


# ═══════════════════════════════════════════════════════════════════
# 节点 4.5: revise_node — LLM 注入 feedback 改写 analyses
# ═══════════════════════════════════════════════════════════════════

REVISE_SYSTEM_PROMPT = """你是一个知识库内容修正员。
请根据审核反馈，对以下分析条目进行修正。

审核反馈（来自质量审核员）：
{feedback}

请逐条修正，输出 JSON：
{{
    "revised": [
        {{
            "id": "条目id（不可修改）",
            "summary": "修正后的中文摘要",
            "tags": ["修正后的标签"],
            "score": 0.85
        }},
        ...
    ]
}}

规则：
- id 字段不可修改，只修正 summary/tags/score
- 如果 feedback 中没有提到某条目，保持原样
- 只输出 JSON，不要包含其他内容"""


def revise_node(state: KBState) -> dict[str, Any]:
    """修正节点：根据 review_feedback 注入改写 analyses。

    读取 state["analyses"] 和 state["review_feedback"]，
    将 feedback 注入 LLM prompt，批量修正后返回新的 analyses。

    Args:
        state: KBState。

    Returns:
        dict: 包含 analyses（改进后）和 cost_tracker。
    """
    logger.info("--- revise_node ---")

    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")

    if not analyses or not feedback:
        logger.info("analyses 或 feedback 为空，跳过修正")
        return {}

    from workflows.model_client import chat_json, check_llm_available

    if not check_llm_available():
        logger.warning("LLM 不可用，跳过修正")
        return {}

    provider = os.getenv("LLM_PROVIDER", "deepseek")

    prompt_lines = []
    for item in analyses[:5]:
        prompt_lines.append(
            f"id: {item.get('id', 'unknown')}\n"
            f"title: {item.get('title', '')}\n"
            f"summary: {item.get('summary', '')}\n"
            f"tags: {item.get('tags', [])}\n"
            f"score: {item.get('score', 0)}\n---"
        )
    prompt = "\n".join(prompt_lines)

    system = REVISE_SYSTEM_PROMPT.format(feedback=feedback)

    try:
        parsed, usage = chat_json(
            prompt=prompt,
            system=system,
            temperature=0.4,
        )

        tokens = usage.total_tokens
        cost_tracker = _merge_cost(
            dict(state.get("cost_tracker", {})), tokens, provider, "revise"
        )

        revised_list = parsed.get("revised", [])
        if not revised_list:
            logger.warning("LLM 未返回 revised 列表，跳过修正")
            return {}

        revised_map = {r.get("id"): r for r in revised_list if r.get("id")}
        improved = []
        for item in analyses:
            item_id = item.get("id")
            if item_id in revised_map:
                revised_item = dict(item)
                revised_item["summary"] = revised_map[item_id].get("summary", item.get("summary", ""))
                revised_item["tags"] = revised_map[item_id].get("tags", item.get("tags", []))
                revised_item["score"] = revised_map[item_id].get("score", item.get("score", 0))
                improved.append(revised_item)
                logger.info(f"  修正: {item.get('title', '?')[:35]}")
            else:
                improved.append(item)

        logger.info(f"修正完成: {len(improved)} 条")
        return {"analyses": improved, "cost_tracker": cost_tracker}

    except Exception as e:
        logger.warning(f"修正失败: {e}，返回原 analyses")
        return {"analyses": analyses, "cost_tracker": dict(state.get("cost_tracker", {}))}


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


# ═══════════════════════════════════════════════════════════════════
# 节点 6: human_flag_node — 人工标记（循环出口）
# ═══════════════════════════════════════════════════════════════════

HUMAN_FLAG_DIR = PROJECT_ROOT / "knowledge" / "human_review"


def human_flag_node(state: KBState) -> dict[str, Any]:
    """人工标记节点：超过最大循环次数仍未通过，将问题条目写入独立目录。

    当 review_passed 持续为 False 且 iteration 超过上限时，
    说明问题不在"质量"而在"数据本身"，需要人工介入判断。
    将当前 analyses 和 review_feedback 写入待人工审核目录，不污染主知识库。

    Args:
        state: KBState。

    Returns:
        dict: 空更新（图终止）。
    """
    logger.info("--- human_flag_node ---")

    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)

    HUMAN_FLAG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    flag_file = HUMAN_FLAG_DIR / f"flag-{date_str}-{uuid.uuid4().hex[:8]}.json"

    flag_data = {
        "flagged_at": datetime.now(timezone.utc).isoformat(),
        "iteration": iteration,
        "review_feedback": feedback,
        "analyses_count": len(analyses),
        "analyses": analyses,
    }

    with open(flag_file, "w", encoding="utf-8") as f:
        json.dump(flag_data, f, ensure_ascii=False, indent=2)

    logger.info(f"人工标记: {flag_file.name}，{len(analyses)} 条条目")
    logger.info(f"反馈: {feedback[:120] if feedback else '(无)'}...")

    return {}
