"""分析 Agent — 调用 LLM 对原始数据进行分析。

读取 `knowledge/raw/`，调用 LLM 生成中文摘要、标签和评分，
写入 `knowledge/analyzer_output/{source}-analyzed-{date}.json`。

Usage:
    python -m scripts.analyzer
    python -m scripts.analyzer --dry-run
"""

import itertools
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from scripts.model_client import chat_with_retry, tracker

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_RAW = PROJECT_ROOT / "knowledge" / "raw"
KNOWLEDGE_ANALYZER = PROJECT_ROOT / "knowledge" / "analyzer_output"


def filter_ai_related(text: str) -> bool:
    """判断内容是否与 AI/LLM/Agent 相关。

    Args:
        text: 待检测文本。

    Returns:
        是否相关。
    """
    keywords = [
        "AI",
        "LLM",
        "GPT",
        "Claude",
        "Gemini",
        "Llama",
        "Mistral",
        "agent",
        "Agent",
        "RAG",
        "LangChain",
        "LlamaIndex",
        "CrewAI",
        "AutoGen",
        "embedding",
        "fine-tuning",
        "vector database",
        "prompt",
        "Prompt",
        "tool calling",
        "function calling",
        "machine learning",
        "deep learning",
        "transformer",
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
    "tags": ["标签1", "标签2", "标签3"],
    "score": 8.5,
    "relevant": true
}}
"""


def load_raw_data() -> list[dict[str, Any]]:
    """加载 knowledge/raw/ 中最新的原始数据。

    Returns:
        原始采集数据列表。
    """
    if not KNOWLEDGE_RAW.exists():
        return []

    json_files = sorted(KNOWLEDGE_RAW.glob("*.json"), reverse=True)
    if not json_files:
        return []

    try:
        with open(json_files[0], "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取原始数据失败: {e}")
        return []


def analyze(dry_run: bool = False) -> list[dict[str, Any]]:
    """执行 LLM 分析。

    Args:
        dry_run: 是否干跑模式（跳过 LLM 调用）。

    Returns:
        分析后的条目列表。
    """
    logger.info("=" * 50)
    logger.info("内容分析")
    logger.info("=" * 50)

    items = load_raw_data()
    if not items:
        logger.warning("无原始数据可分析")
        return []

    logger.info(f"加载 {len(items)} 条原始数据")

    if dry_run:
        logger.info("干跑模式，跳过 LLM 调用")
        for item in items:
            item["summary"] = "[干跑] 摘要"
            item["tags"] = ["ai", "dry-run"]
            item["score"] = 8.0
            item["relevant"] = True
            item["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        save_analyzer_output(items)
        return items

    provider_env_keys = {
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    available_providers = [k for k, v in provider_env_keys.items() if os.getenv(v)]
    if not available_providers:
        logger.warning("未配置任何 API Key，跳过分析")
        return []

    llm_provider = os.getenv("LLM_PROVIDER", "")
    if "," in llm_provider:
        providers = [p.strip().lower() for p in llm_provider.split(",")]
        providers = [p for p in providers if p in available_providers]
        if not providers:
            logger.warning("LLM_PROVIDER 中的提供商均未配置 API Key")
            return items
    else:
        providers = available_providers

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

    logger.info(f"分析完成，共处理 {len(results)} 条")
    if len(providers) > 1:
        logger.info(f"模型使用统计: {provider_counts}")

    save_analyzer_output(results)
    return results


def save_analyzer_output(items: list[dict[str, Any]]) -> None:
    """保存分析结果到 analyzer_output 目录。

    Args:
        items: 分析后的条目列表。
    """
    KNOWLEDGE_ANALYZER.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI 知识库 — 分析 Agent")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，不调 LLM")
    parser.add_argument("--verbose", action="store_true", help="详细日志模式")

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    analyze(dry_run=args.dry_run)

    if not args.dry_run:
        tracker.report()
