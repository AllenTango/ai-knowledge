"""知识库自动化流水线主脚本。

实现四步流水线：采集、分析、整理、保存。支持 GitHub 和 RSS 数据源。

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20   # 完整流水线
    python pipeline/pipeline.py --sources github --limit 5       # 只采集 GitHub
    python pipeline/pipeline.py --sources rss --limit 10         # 只采集 RSS
    python pipeline/pipeline.py --sources github --limit 5 --dry-run  # 干跑模式
    python pipeline/pipeline.py --verbose                         # 详细日志
"""

import argparse
import itertools
import logging
import os
import re
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from model_client import chat_with_retry, tracker

import sys

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_RAW = PROJECT_ROOT / "knowledge" / "raw"
KNOWLEDGE_ANALYZER = PROJECT_ROOT / "knowledge" / "analyzer_output"
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"


def setup_args() -> argparse.ArgumentParser:
    """配置命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="AI 知识库自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
    parser.add_argument(
        "--providers",
        type=str,
        default="",
        help="LLM 提供商列表，逗号分隔（默认: 使用 .env 中的 LLM_PROVIDER）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式，不调用 LLM 分析，不保存文件",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志模式",
    )
    return parser


def ensure_directories() -> None:
    """确保必要的目录存在。"""
    KNOWLEDGE_RAW.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_ANALYZER.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_ARTICLES.mkdir(parents=True, exist_ok=True)
    logger.debug(f"目录初始化完成: {KNOWLEDGE_RAW}, {KNOWLEDGE_ANALYZER}, {KNOWLEDGE_ARTICLES}")


def fetch_github_trending(limit: int = 20) -> list[dict[str, Any]]:
    """从 GitHub Search API 采集 AI 相关热门项目。

    Args:
        limit: 最大采集条数。

    Returns:
        采集到的原始条目列表。
    """
    import urllib.parse

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
            results.append({
                "id": str(uuid.uuid4()),
                "source": "github",
                "source_url": item.get("html_url", ""),
                "title": item.get("full_name", ""),
                "content": item.get("description", "") or "",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
            })
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
        results.append({
            "id": str(uuid.uuid4()),
            "source": "rss",
            "source_url": link.strip(),
            "title": title.strip(),
            "content": desc.strip()[:500],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return results


def load_rss_sources() -> dict[str, str]:
    """加载 rss_sources.yaml 中的 RSS 源。

    Returns:
        源名称到 URL 的映射字典。
    """
    rss_file = Path(__file__).parent / "rss_sources.yaml"
    if not rss_file.exists():
        return {}

    try:
        import yaml
        with open(rss_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        sources = config.get("sources", [])
        return {
            s["name"]: s["url"]
            for s in sources
            if s.get("enabled", False)
        }
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


def step1_collect(sources: str, limit: int) -> list[dict[str, Any]]:
    """Step 1: 采集数据。

    Args:
        sources: 源标识，逗号分隔（github, rss）。
        limit: 每源最大条数。

    Returns:
        原始采集数据列表。
    """
    logger.info("=" * 50)
    logger.info("Step 1: 数据采集")
    logger.info("=" * 50)

    source_list = [s.strip() for s in sources.split(",")]
    results = []

    if "github" in source_list:
        results.extend(fetch_github_trending(limit))

    if "rss" in source_list:
        results.extend(fetch_rss_sources(limit))

    logger.info(f"采集阶段完成，共获取 {len(results)} 条原始数据")
    return results


def filter_ai_related(text: str) -> bool:
    """判断内容是否与 AI/LLM/Agent 相关。

    Args:
        text: 待检测文本。

    Returns:
        是否相关。
    """
    keywords = [
        "AI", "LLM", "GPT", "Claude", "Gemini", "Llama", "Mistral",
        "agent", "Agent", "RAG", "LangChain", "LlamaIndex", "CrewAI",
        "AutoGen", "embedding", "fine-tuning", "vector database",
        "prompt", "Prompt", "tool calling", "function calling",
        "machine learning", "deep learning", "transformer",
    ]
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def generate_prompt(item: dict[str, Any]) -> str:
    """生成分析用提示词。

    Args:
        item: 待分析条目。

    Returns:
        提示词字符串。
    """
    title = item.get("title", "")
    content = item.get("content", "")[:1000]
    source = item.get("source", "unknown")
    url = item.get("source_url", "")

    return f"""你是一个专业的 AI 技术资讯分析师。请根据以下内容生成结构化分析。

标题: {title}
来源: {source}
URL: {url}
内容摘要: {content}

请按以下 JSON 格式输出分析结果（仅输出 JSON，不要其他内容）：
{{
    "summary": "中文摘要，50-200字，必须包含「是什么」「为什么重要」「与 AI 领域关联」三个层次",
    "tags": ["标签1", "标签2", "标签3"],  // 3-8个标签，小写英文，连字符连接
    "score": 8.5,  // 0.0-10.0 评分，参考：领域相关性40%、信息密度30%、时效性20%、来源权威性10%
    "relevant": true  // 是否与 AI/LLM/Agent 领域相关
}}
"""


def step2_analyze(items: list[dict[str, Any]], dry_run: bool, providers: list[str] = None) -> list[dict[str, Any]]:
    """Step 2: 调用 LLM 分析内容。

    Args:
        items: 待分析条目列表。
        dry_run: 是否干跑模式。
        providers: LLM 提供商列表，为空则使用 .env 中的 LLM_PROVIDER。

    Returns:
        分析后的条目列表。
    """
    logger.info("=" * 50)
    logger.info("Step 2: 内容分析")
    logger.info("=" * 50)

    if dry_run:
        logger.info("干跑模式，跳过 LLM 调用")
        for item in items:
            item["summary"] = "[干跑] 摘要"
            item["tags"] = ["ai", "dry-run"]
            item["score"] = 8.0
            item["relevant"] = True
            item["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        return items

    provider_env_keys = {
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    available_providers = [k for k, v in provider_env_keys.items() if os.getenv(v)]

    if not providers:
        llm_provider = os.getenv("LLM_PROVIDER", "")
        if "," in llm_provider:
            explicit_providers = [p.strip().lower() for p in llm_provider.split(",")]
            valid_providers = [p for p in explicit_providers if p in available_providers]
            if len(valid_providers) < len(explicit_providers):
                missing = set(explicit_providers) - set(valid_providers)
                logger.warning(f"以下提供商未配置 API Key，已跳过: {missing}")
            if valid_providers:
                logger.info(f"从 LLM_PROVIDER 读取多提供商: {valid_providers}")
                providers = valid_providers
            else:
                logger.warning(f"LLM_PROVIDER 中的提供商均未配置 API Key: {explicit_providers}")
                return items
        elif available_providers:
            logger.info(f"自动检测到已配置的提供商: {available_providers}")
            providers = available_providers
        else:
            logger.warning("未配置任何 API Key，跳过分析")
            return items
    else:
        requested = [p.strip().lower() for p in providers]
        valid = [p for p in requested if p in available_providers]
        if not valid:
            logger.warning(f"指定提供商 {requested} 均未配置 API Key，跳过分析")
            return items
        providers = valid

    logger.info(f"使用提供商: {providers}")
    provider_cycle = itertools.cycle(providers)
    provider_counts = {p: 0 for p in providers}

    results = []
    for i, item in enumerate(items):
        current_provider = next(provider_cycle)
        logger.info(f"分析进度: {i+1}/{len(items)} [{current_provider}]")

        if not filter_ai_related(item.get("title", "") + item.get("content", "")):
            logger.info(f"  跳过非 AI 相关内容: {item.get('title', '')[:30]}")
            continue

        prompt = generate_prompt(item)
        messages = [
            {"role": "system", "content": "你是一个专业的 AI 技术资讯分析师。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = chat_with_retry(messages, provider_name=current_provider)
            content = response.content.strip()

            import re
            content = re.sub(r"</think>.*?<think>", "", content, flags=re.DOTALL)
            content = re.sub(r"<think>.*", "", content)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

            json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            content = content.strip()

            analysis = json.loads(content)
            item["summary"] = analysis.get("summary", "")
            item["tags"] = analysis.get("tags", [])
            item["score"] = analysis.get("score", 5.0)
            item["relevant"] = analysis.get("relevant", True)
            item["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            item["model_provider"] = current_provider
            provider_counts[current_provider] += 1

            logger.info(f"  评分: {item['score']}, 标签: {item['tags'][:3]}")

        except json.JSONDecodeError as e:
            logger.warning(f"  解析失败: {e}")
            item["summary"] = "[解析失败]"
            item["tags"] = []
            item["score"] = 5.0
            item["relevant"] = True
            item["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.warning(f"  分析异常: {e}")
            item["summary"] = "[分析异常]"
            item["tags"] = []
            item["score"] = 5.0
            item["relevant"] = True
            item["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        results.append(item)

    logger.info(f"分析阶段完成，共处理 {len(results)} 条")
    if len(providers) > 1:
        logger.info(f"模型使用统计: {provider_counts}")
    return results


def save_analyzer_output(items: list[dict[str, Any]]) -> None:
    """保存分析结果到 analyzer_output 目录。

    Args:
        items: 分析后的条目列表。
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    github_items = [i for i in items if i.get("source") == "github"]
    rss_items = [i for i in items if i.get("source") == "rss"]

    if github_items:
        output_file = KNOWLEDGE_ANALYZER / f"github-analyzed-{date_str}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(github_items, f, ensure_ascii=False, indent=2)
        logger.info(f"GitHub 分析结果已保存: {output_file.name}")

    if rss_items:
        output_file = KNOWLEDGE_ANALYZER / f"rss-analyzed-{date_str}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(rss_items, f, ensure_ascii=False, indent=2)
        logger.info(f"RSS 分析结果已保存: {output_file.name}")


def step3_organize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Step 3: 整理数据。

    Args:
        items: 待整理条目列表。

    Returns:
        整理后的条目列表。
    """
    logger.info("=" * 50)
    logger.info("Step 3: 数据整理")
    logger.info("=" * 50)

    seen_urls: dict[str, datetime] = {}
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)

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

        if url in seen_urls and seen_urls[url] > fetched_time:
            logger.info(f"  去重: {url}")
            continue
        if url in seen_urls and fetched_time < cutoff_time:
            logger.info(f"  过期: {url}")
            continue

        seen_urls[url] = fetched_time

        if not item.get("relevant", True):
            item["status"] = "rejected"
            continue

        score = item.get("score", 0.0)
        if score >= 7.0:
            item["status"] = "pending_review"
        elif score >= 5.0:
            item["status"] = "pending_review"
        else:
            item["status"] = "rejected"

        item["retry_count"] = 0
        item["published_to"] = []
        item["reviewer"] = None
        item["reviewed_at"] = None

        if not item.get("id"):
            item["id"] = str(uuid.uuid4())

    valid_items = [i for i in items if i.get("status") != "rejected"]
    logger.info(f"整理阶段完成，有效条目 {len(valid_items)} 条")
    return valid_items


def step4_save(items: list[dict[str, Any]]) -> None:
    """Step 4: 保存到知识库。

    Args:
        items: 待保存条目列表。
    """
    logger.info("=" * 50)
    logger.info("Step 4: 保存知识库")
    logger.info("=" * 50)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    github_items = [i for i in items if i.get("source") == "github"]
    rss_items = [i for i in items if i.get("source") == "rss"]

    if github_items:
        raw_file = KNOWLEDGE_RAW / f"github-trending-{date_str}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(github_items, f, ensure_ascii=False, indent=2)
        logger.info(f"GitHub 原始数据已保存: {raw_file.name}")

    if rss_items:
        raw_file = KNOWLEDGE_RAW / f"rss-{date_str}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(rss_items, f, ensure_ascii=False, indent=2)
        logger.info(f"RSS 原始数据已保存: {raw_file.name}")

    saved_count = 0
    counters: dict[str, int] = {}

    for item in items:
        if item.get("status") != "pending_review":
            continue

        source = item.get("source", "unknown")
        counters[source] = counters.get(source, 0) + 1
        seq = counters[source]

        article_id = item.get("id", str(uuid.uuid4()))
        article_file = KNOWLEDGE_ARTICLES / f"{timestamp[:8]}-{source}-{seq:02d}.json"

        with open(article_file, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        saved_count += 1
        logger.info(f"  已保存: {article_file.name}")

    logger.info(f"保存阶段完成，共写入 {saved_count} 篇知识条目")


def main() -> None:
    """主函数。"""
    parser = setup_args()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("AI 知识库自动化流水线启动")
    logger.info(f"参数: sources={args.sources}, limit={args.limit}, providers={args.providers or 'default'}, dry_run={args.dry_run}")

    ensure_directories()

    items = step1_collect(args.sources, args.limit)
    items = step2_analyze(items, args.dry_run, args.providers.split(",") if args.providers else None)
    save_analyzer_output(items)
    items = step3_organize(items)
    step4_save(items)

    logger.info("流水线执行完成")

    if not args.dry_run:
        tracker.report()


if __name__ == "__main__":
    main()