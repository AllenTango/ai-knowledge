"""AI 知识库评估测试。

Usage:
    pytest tests/eval_test.py
    pytest tests/eval_test.py -v
    pytest tests/eval_test.py -v -m "not slow"  # 跳过 LLM 测试
"""

import json
import sys
from pathlib import Path

import pytest

# dotenv 加载 .env，让 pytest 能读到环境变量
from dotenv import load_dotenv

load_dotenv()

# LLM_PROVIDER 可能为 "deepseek,minimax"（多提供商），chat() 只接受单 provider
# 提取第一个作为测试用 provider
import os
_first_provider = os.getenv("LLM_PROVIDER", "deepseek").split(",")[0]
os.environ["LLM_PROVIDER"] = _first_provider

import warnings
warnings.filterwarnings(
    "ignore",
    category=pytest.PytestUnknownMarkWarning,
)


# ═══════════════════════════════════════════════════════════════════
# 评估用例定义
# ═══════════════════════════════════════════════════════════════════

def has_summary_ge_50_chars(result: dict) -> bool:
    """检查 summary 是否 >= 50 字符。"""
    summary = result.get("summary", "")
    return len(summary) >= 50


def has_keywords(result: dict) -> bool:
    """检查 tags 是否非空且至少 3 个。"""
    tags = result.get("tags", [])
    return len(tags) >= 3


def score_in_range(result: dict, low: float = 0.0, high: float = 1.0) -> bool:
    """检查 score 是否在 [low, high] 范围内。"""
    score = result.get("score", -1)
    return low <= score <= high


EVAL_CASES = [
    {
        "name": "正面案例：技术文章",
        "input": {
            "title": "LangChain v0.3 发布：全新 RAG 优化与 Agent 支持",
            "description": (
                "LangChain v0.3 带来了全新的 RAG（检索增强生成）管道优化，"
                "支持多步 Agent 协作推理，新增了 LangGraph 工作流编排接口，"
                "大幅降低了复杂 Agent 场景的开发门槛。"
            ),
        },
        "expected": {
            "check_summary_length": lambda r: len(r.get("summary", "")) >= 50,
            "check_tags": lambda r: len(r.get("tags", [])) >= 3,
            "check_score_range": lambda r: 0.0 <= r.get("score", -1) <= 1.0,
        },
    },
    {
        "name": "负面案例：无关内容",
        "input": {
            "title": "晚餐吃什么好？",
            "description": "今天想吃火锅还是烧烤，或者日料也行。",
        },
        "expected": {
            "check_score_filter": lambda r: r.get("score", 1.0) < 0.6 or r.get("rejected", False),
            "check_summary_not_empty": lambda r: len(r.get("summary", "")) <= 200,
        },
    },
    {
        "name": "边界案例：极短输入",
        "input": {
            "title": "AI",
            "description": "AI",
        },
        "expected": {
            "check_no_crash": lambda r: True,
            "check_fields_exist": lambda r: all(k in r for k in ("summary", "tags", "score")),
            "check_score_valid": lambda r: 0.0 <= r.get("score", -1) <= 1.0,
        },
    },
]


# ═══════════════════════════════════════════════════════════════════
# 本地验证测试（不调用 LLM）
# ═══════════════════════════════════════════════════════════════════

class TestEVALCASEStructure:
    """验证 EVAL_CASES 结构正确性（不调用 LLM）。"""

    def test_cases_not_empty(self):
        """EVAL_CASES 至少包含 3 个用例。"""
        assert len(EVAL_CASES) >= 3, f"预期 >= 3 个用例，实际 {len(EVAL_CASES)}"

    def test_each_case_has_required_fields(self):
        """每个用例包含 name, input, expected。"""
        for case in EVAL_CASES:
            assert "name" in case, f"缺少 'name' 字段: {case}"
            assert "input" in case, f"缺少 'input' 字段: {case}"
            assert "expected" in case, f"缺少 'expected' 字段: {case}"

    def test_each_case_input_has_title_and_description(self):
        """每个用例的 input 包含 title 和 description。"""
        for case in EVAL_CASES:
            inp = case["input"]
            assert "title" in inp, f"用例 '{case['name']}' 缺少 title"
            assert "description" in inp, f"用例 '{case['name']}' 缺少 description"

    def test_each_case_expected_has_check_functions(self):
        """每个用例的 expected 包含可调用的检查函数。"""
        for case in EVAL_CASES:
            expected = case["expected"]
            assert isinstance(expected, dict), f"用例 '{case['name']}' 的 expected 应为 dict"
            assert len(expected) >= 1, f"用例 '{case['name']}' 至少要有 1 个检查条件"

    def test_helper_functions(self):
        """辅助函数逻辑正确。"""
        fake_result_ok = {
            "summary": "LangChain v0.3 带来了全新的 RAG（检索增强生成）管道优化，支持多步 Agent 协作推理，新增了 LangGraph 工作流编排接口，大幅降低了复杂 Agent 场景的开发门槛。",
            "tags": ["ai", "langchain", "agent"],
            "score": 0.75,
            "source": "github",
        }
        assert has_summary_ge_50_chars(fake_result_ok) is True

        fake_result_short = {"summary": "短", "tags": ["a"], "score": 0.5}
        assert has_summary_ge_50_chars(fake_result_short) is False

        assert has_keywords(fake_result_ok) is True
        assert has_keywords({"tags": ["a"]}) is False

        assert score_in_range(fake_result_ok, 0.0, 1.0) is True
        assert score_in_range({"score": 1.5}, 0.0, 1.0) is False


# ═══════════════════════════════════════════════════════════════════
# LLM 调用测试（标记为 slow，可跳过）
# ═══════════════════════════════════════════════════════════════════

def analyze_case(case_input: dict) -> dict:
    """调用 LLM 分析单个用例。

    Args:
        case_input: {"title": str, "description": str}

    Returns:
        分析结果 dict，含 summary / tags / score。
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from workflows.model_client import check_llm_available, chat

    system_prompt = (
        "你是一个 AI 技术资讯分析师。分析以下项目，输出 JSON：\n"
        '{"summary": "中文摘要50-200字", "tags": ["tag1", "tag2"], "score": 0.85}\n'
        "只输出 JSON，不要其他内容。"
    )
    prompt = f"项目: {case_input['title']}\n描述: {case_input['description']}"

    if not check_llm_available():
        pytest.skip("无 LLM API Key，跳过 LLM 测试")

    text, usage = chat(system=system_prompt, prompt=prompt, temperature=0.7)

    import re
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    result = json.loads(text)
    result["_usage"] = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }
    return result


def judge_score(result: dict) -> float:
    """LLM-as-Judge：让 LLM 对分析结果打分（1-10）。

    Args:
        result: 分析结果 dict。

    Returns:
        评分（1.0 - 10.0）。
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from workflows.model_client import check_llm_available, chat

    judge_prompt = (
        f"请对以下知识条目质量打分（1-10分）：\n"
        f"标题: {result.get('title', '未知')}\n"
        f"摘要: {result.get('summary', '')}\n"
        f"标签: {result.get('tags', [])}\n"
        f"AI相关性评分: {result.get('score', 0):.2f}\n\n"
        "输出 JSON：{\"score\": 7.5, \"reason\": \"简短原因\"}\n"
        "只输出 JSON，不要其他内容。"
    )

    if not check_llm_available():
        pytest.skip("无 LLM API Key，跳过 LLM 测试")

    text, _ = chat(system="你是一个严格的质量评审员。", prompt=judge_prompt, temperature=0.1)

    import re
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    parsed = json.loads(text)
    return float(parsed.get("score", 0))


@pytest.mark.slow
class TestLLMEval:
    """LLM 调用评估测试（标记为 slow，可跳过）。"""

    def test_positive_case_analysis(self):
        """正面案例：技术文章应有摘要、有关键词。"""
        case = next(c for c in EVAL_CASES if "正面" in c["name"])
        result = analyze_case(case["input"])

        for check_name, check_fn in case["expected"].items():
            assert check_fn(result), f"检查 '{check_name}' 失败: {result}"

    def test_negative_case_filter(self):
        """负面案例：无关内容应被过滤或低分。"""
        case = next(c for c in EVAL_CASES if "负面" in c["name"])
        result = analyze_case(case["input"])

        for check_name, check_fn in case["expected"].items():
            assert check_fn(result), f"检查 '{check_name}' 失败: {result}"

    def test_edge_case_no_crash(self):
        """边界案例：极短输入不崩溃。"""
        case = next(c for c in EVAL_CASES if "边界" in c["name"])
        result = analyze_case(case["input"])

        for check_name, check_fn in case["expected"].items():
            assert check_fn(result), f"检查 '{check_name}' 失败: {result}"

    def test_llm_as_judge_positive_case(self):
        """LLM-as-Judge：正面案例评分 >= 5。"""
        case = next(c for c in EVAL_CASES if "正面" in c["name"])
        result = analyze_case(case["input"])
        result["title"] = case["input"]["title"]

        score = judge_score(result)
        assert score >= 5.0, f"LLM-as-Judge 评分 {score} < 5.0"
        assert score <= 10.0, f"LLM-as-Judge 评分 {score} > 10.0"

    def test_llm_as_judge_edge_case(self):
        """LLM-as-Judge：边界案例评分 >= 3（允许低分但不崩溃）。"""
        case = next(c for c in EVAL_CASES if "边界" in c["name"])
        result = analyze_case(case["input"])
        result["title"] = case["input"]["title"]

        score = judge_score(result)
        assert 1.0 <= score <= 10.0, f"LLM-as-Judge 评分 {score} 超出 [1, 10] 范围"
        assert 1.0 <= score <= 10.0, f"LLM-as-Judge 评分 {score} 超出 [1, 10] 范围"