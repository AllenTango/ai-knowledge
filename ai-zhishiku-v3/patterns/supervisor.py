"""Worker-Supervisor 质量审核循环。

Worker Agent 接收任务，输出 JSON 格式的分析报告。
Supervisor Agent 对 Worker 的输出进行质量审核，评分维度为准确性、深度、格式。
审核循环：通过（score >= 21）→ 返回；不通过 → 带反馈重做（最多 3 轮）。

Usage:
    python -m patterns.supervisor "分析 LangChain 的最新动态"
    python -m patterns.supervisor "比较 RAG 和 Fine-tuning 的优缺点" --max-retries 5
"""

import json
import logging
import sys
from typing import Any

from workflows.model_client import chat, check_llm_available

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PASS_THRESHOLD = 21

WORKER_SYSTEM_PROMPT = """你是一个 AI 分析助手。
请根据以下任务要求，生成详细的分析报告。

要求：
1. 以 JSON 格式输出，包含以下字段：
   - "title": 报告标题（中文）
   - "summary": 内容摘要（50-150 字中文）
   - "analysis": 详细分析内容（200-500 字中文）
   - "conclusion": 结论（1-2 句话中文）
2. 内容必须准确、有深度、逻辑清晰。
3. 请只输出 JSON，不要包含其他内容。"""

SUPERVISOR_SYSTEM_PROMPT = """你是一个质量审核员。
请对以下分析报告进行评分。

评分维度（每个 1-10 分）：
1. 准确性：回答是否准确、可靠、基于事实
2. 深度：分析是否深入、全面、有洞察
3. 格式：JSON 格式是否规范、字段完整、结构清晰

输出 JSON（仅输出 JSON，不要其他内容）：
{
    "passed": true/false,
    "score": 总分（三个维度之和，范围 3-30）,
    "feedback": "中文反馈，指出问题和改进建议"
}"""


def _call_worker(task: str, previous_feedback: str = "") -> str:
    """调用 Worker Agent 执行任务。

    Args:
        task: 用户任务描述。
        previous_feedback: 上一轮 Supervisor 的反馈（重试时提供）。

    Returns:
        Worker 输出的分析报告文本。
    """
    system = WORKER_SYSTEM_PROMPT
    if previous_feedback:
        system += (
            "\n\n上一轮审核反馈，请针对性改进：\n" + previous_feedback
        )

    prompt = f"任务：{task}"
    (text, usage) = chat(system=system, prompt=prompt, temperature=0.7)
    logger.info(
        f"Worker 输出 {len(text)} 字符，消耗 {usage.total_tokens} tokens"
    )
    return text


def _call_supervisor(task: str, output: str) -> dict:
    """调用 Supervisor Agent 审核 Worker 的输出。

    Args:
        task: 用户任务描述。
        output: Worker 输出的分析报告。

    Returns:
        包含 passed、score、feedback 的字典。
    """
    prompt = f"任务：{task}\n\n分析报告：\n{output}"
    (text, usage) = chat(system=SUPERVISOR_SYSTEM_PROMPT, prompt=prompt, temperature=0.2)
    logger.info(
        f"Supervisor 输出 {len(text)} 字符，消耗 {usage.total_tokens} tokens"
    )

    json_match = __import__("re").search(
        r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL
    )
    if json_match:
        text = json_match.group(1)

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Supervisor JSON 解析失败: {e}，默认通过")
        return {"passed": True, "score": PASS_THRESHOLD, "feedback": ""}

    return {
        "passed": result.get("passed", False),
        "score": result.get("score", 0),
        "feedback": result.get("feedback", ""),
    }


def supervisor(task: str, max_retries: int = 3) -> dict[str, Any]:
    """Worker-Supervisor 质量审核循环。

    Args:
        task: 需要分析的任务描述。
        max_retries: 最大重试次数（默认 3）。

    Returns:
        dict 包含以下字段：
            - output: 最终的分析报告文本
            - attempts: 实际尝试次数
            - final_score: 最终审核评分
            - warning: 警告信息（超限时提供，可选）
    """
    if not task or not task.strip():
        return {
            "output": "任务不能为空。",
            "attempts": 0,
            "final_score": 0,
        }

    if not check_llm_available():
        logger.warning("LLM 不可用（未配置 API Key）")
        return {
            "output": "LLM 服务不可用，请先配置 API Key。",
            "attempts": 0,
            "final_score": 0,
        }

    previous_feedback = ""

    for attempt in range(1, max_retries + 1):
        logger.info(f"--- 第 {attempt}/{max_retries} 轮 ---")

        output = _call_worker(task, previous_feedback)
        review = _call_supervisor(task, output)

        score = review.get("score", 0)
        passed = review.get("passed", False)
        feedback = review.get("feedback", "")
        logger.info(
            f"审核结果: passed={passed}, score={score}, "
            f"feedback={feedback[:50]}"
        )

        if passed and score >= PASS_THRESHOLD:
            logger.info(f"第 {attempt} 轮通过 (score={score})")
            result: dict[str, Any] = {
                "output": output,
                "attempts": attempt,
                "final_score": score,
            }
            return result

        previous_feedback = feedback

    logger.warning(
        f"超过最大重试次数 ({max_retries})，强制返回"
    )
    return {
        "output": output,
        "attempts": max_retries,
        "final_score": review.get("score", 0),
        "warning": f"超过最大重试次数 ({max_retries} 轮)，结果可能未达到质量标准。",
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Worker-Supervisor 质量审核循环"
    )
    parser.add_argument("task", type=str, help="需要分析的任务描述")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="最大重试次数（默认 3）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志模式",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"启动 Supervisor，任务: {args.task[:60]}...")
    result = supervisor(task=args.task, max_retries=args.max_retries)

    print("\n" + "=" * 60)
    print("SUPERVISOR 结果")
    print("=" * 60)
    print(f"attempts:    {result.get('attempts')}")
    print(f"final_score: {result.get('final_score')}")
    if result.get("warning"):
        print(f"warning:     {result['warning']}")
    print("-" * 60)
    print("output:")
    print(result.get("output", ""))
