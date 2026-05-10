"""review_node 审核循环测试脚本。

测试场景：模拟 3 次审核循环
- 第 1 次：iteration=0，LLM 返回 review_passed=False + feedback1
- 第 2 次：iteration=1，LLM 返回 review_passed=False + feedback2
- 第 3 次：iteration=2，强制 review_passed=True（iteration>=2 兜底）

需求：
1. 前 2 次审核强制返回 review_passed: False（模拟审核不通过）
2. 第 3 次审核（iteration >= 2）返回 review_passed: True
3. 每次审核都给出不同的 feedback 内容
4. 打印当前 iteration 和 review_passed 值
"""

import sys
import json
import traceback
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

results = []
PASS = "PASS"
FAIL = "FAIL"


def check(label: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append(f"- **{status}** `{label}` {detail}")


# ═══════════════════════════════════════════════════════════════════
# 测试用例：3 次审核循环
# ═══════════════════════════════════════════════════════════════════

results.append("## review_node 审核循环测试\n")

FEEDBACKS = [
    "摘要过短（少于50字），缺乏技术细节，建议补充实现原理",
    "标签不准确：'llm' 应为 'llm-framework'，缺少 'agent' 相关标签",
    "（第3次审核时 iteration>=2，此反馈不会真正输出）",
]

REVIEW_RESPONSES = [
    {"passed": False, "total_score": 18, "dimensions": {"摘要质量": 3, "标签准确": 4, "分类合理": 6, "一致性": 5}, "feedback": FEEDBACKS[0]},
    {"passed": False, "total_score": 20, "dimensions": {"摘要质量": 4, "标签准确": 5, "分类合理": 6, "一致性": 5}, "feedback": FEEDBACKS[0]},
    {"passed": False, "total_score": 22, "dimensions": {"摘要质量": 5, "标签准确": 4, "分类合理": 7, "一致性": 6}, "feedback": FEEDBACKS[1]},
    {"passed": False, "total_score": 24, "dimensions": {"摘要质量": 6, "标签准确": 5, "分类合理": 7, "一致性": 6}, "feedback": FEEDBACKS[1]},
]

CALL_INDEX = [0]


def mock_chat_for_review(system: str, prompt: str, temperature: float = 0.2, **kwargs):
    """模拟 review_node 的 LLM 调用，返回不同的审核响应。"""
    idx = CALL_INDEX[0]
    CALL_INDEX[0] += 1
    response = REVIEW_RESPONSES[idx] if idx < len(REVIEW_RESPONSES) else {"passed": True, "total_score": 35, "dimensions": {"摘要质量": 9, "标签准确": 8, "分类合理": 9, "一致性": 9}, "feedback": "已通过"}
    text = json.dumps(response, ensure_ascii=False)
    class Usage:
        total_tokens = 200
    return (text, Usage())


mock_articles = [
    {
        "id": "test-001",
        "title": "LangChain v0.3 发布",
        "source": "github",
        "source_url": "https://github.com/langchain-ai/langchain/releases/tag/v0.3.0",
        "fetched_at": "2026-05-10T00:00:00Z",
        "analyzed_at": "2026-05-10T00:05:00Z",
        "summary": "短",
        "tags": ["langchain"],
        "status": "pending_review",
        "score": 0.7,
        "reviewer": None,
        "reviewed_at": None,
        "published_to": [],
        "retry_count": 0,
    },
    {
        "id": "test-002",
        "title": "AutoGen 多 Agent 框架",
        "source": "github",
        "source_url": "https://github.com/microsoft/autogen",
        "fetched_at": "2026-05-10T00:01:00Z",
        "analyzed_at": "2026-05-10T00:06:00Z",
        "summary": "这是一个多 Agent 协作框架",
        "tags": ["agent", "autogen"],
        "status": "pending_review",
        "score": 0.75,
        "reviewer": None,
        "reviewed_at": None,
        "published_to": [],
        "retry_count": 0,
    },
]

from workflows.nodes import review_node
from workflows.state import KBState

state: KBState = {
    "sources": [],
    "analyses": [],
    "articles": mock_articles,
    "review_feedback": "",
    "review_passed": False,
    "iteration": 0,
    "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
}

sys.stdout.write("\n" + "=" * 60 + "\n")
sys.stdout.write("审核循环测试开始\n")
sys.stdout.write("=" * 60 + "\n\n")

with patch("workflows.model_client.chat", side_effect=mock_chat_for_review):
    with patch("workflows.model_client.check_llm_available", return_value=True):
        try:
            # ── 第 1 次审核（iteration=0）────────────────────────────────
            sys.stdout.write(f"[审核 1] iteration={state['iteration']}\n")
            result1 = review_node(state)
            state.update(result1)
            sys.stdout.write(
                f"  → review_passed={result1.get('review_passed')}, "
                f"iteration={result1.get('iteration')}, "
                f"feedback={result1.get('review_feedback', '')[:40]}...\n"
            )
            sys.stdout.write("\n")

            check("第 1 次审核 iteration=0", result1.get("iteration") == 1)
            check("第 1 次审核 review_passed=False（模拟不通过）", result1.get("review_passed") == False)
            check("第 1 次 feedback 非空", result1.get("review_feedback") != "")

            # ── 第 2 次审核（iteration=1）────────────────────────────────
            sys.stdout.write(f"[审核 2] iteration={state['iteration']}\n")
            result2 = review_node(state)
            state.update(result2)
            sys.stdout.write(
                f"  → review_passed={result2.get('review_passed')}, "
                f"iteration={result2.get('iteration')}, "
                f"feedback={result2.get('review_feedback', '')[:40]}...\n"
            )
            sys.stdout.write("\n")

            check("第 2 次审核 iteration=1", result2.get("iteration") == 2)
            check("第 2 次审核 review_passed=False（模拟不通过）", result2.get("review_passed") == False)
            check("第 2 次 feedback 非空", result2.get("review_feedback") != "")

            # ── 第 3 次审核（iteration=2）────────────────────────────────
            sys.stdout.write(f"[审核 3] iteration={state['iteration']}\n")
            result3 = review_node(state)
            state.update(result3)
            sys.stdout.write(
                f"  → review_passed={result3.get('review_passed')}, "
                f"iteration={result3.get('iteration')}, "
                f"feedback={repr(result3.get('review_feedback', ''))[:60]}\n"
            )
            sys.stdout.write("\n")

            check("第 3 次审核 iteration=2", result3.get("iteration") == 3)
            check("第 3 次审核 iteration>=2 强制 review_passed=True", result3.get("review_passed") == True)
            check("第 3 次审核 feedback 为空（强制通过后不写 feedback）", result3.get("review_feedback") == "")

        except Exception as e:
            sys.stdout.write(f"异常: {e}\n")
            sys.stdout.write(traceback.format_exc() + "\n")
            check("审核循环执行", False, str(e))

sys.stdout.write("=" * 60 + "\n")
sys.stdout.write("审核循环测试结束\n")
sys.stdout.write("=" * 60 + "\n\n")

# ═══════════════════════════════════════════════════════════════════
# 附加测试：空 articles 时 review_node 的兜底行为
# ═══════════════════════════════════════════════════════════════════

results.append("\n## review_node 空 articles 兜底测试\n")

CALL_INDEX[0] = 0

empty_state: KBState = {
    "sources": [], "analyses": [], "articles": [],
    "review_feedback": "", "review_passed": False,
    "iteration": 0,
    "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
}

with patch("workflows.model_client.chat"):
    with patch("workflows.model_client.check_llm_available", return_value=True):
        result = review_node(empty_state)
        check("空 articles 时 review_passed=True", result.get("review_passed") == True)
        check("空 articles 时 iteration 递增", result.get("iteration") == 1)
        check("空 articles 时 feedback 为空", result.get("review_feedback") == "")

# ═══════════════════════════════════════════════════════════════════
# 附加测试：decide_next 与 review_node 的联动
# ═══════════════════════════════════════════════════════════════════

results.append("\n## decide_next 与 review_node 联动测试\n")

from workflows.graph import decide_next

check("review_passed=False → decide_next 返回 'organize'", decide_next({"review_passed": False, "iteration": 1, "sources": [], "analyses": [], "articles": [], "review_feedback": "test", "cost_tracker": {}}) == "organize")

state.update({"review_passed": True})
check("review_passed=True → decide_next 返回 'save'", decide_next(state) == "save")

# ═══════════════════════════════════════════════════════════════════
# 写入结果
# ═══════════════════════════════════════════════════════════════════

output_dir = Path(__file__).resolve().parent

pass_count = sum(1 for r in results if "**PASS**" in r)
fail_count = sum(1 for r in results if "**FAIL**" in r)

report = (
    "# review_node 审核循环测试报告\n\n"
    f"**通过: {pass_count} | 失败: {fail_count}**\n\n"
    + "\n".join(results)
    + f"\n\n*生成时间: {__import__('datetime').datetime.now().isoformat()}*\n"
)

(output_dir / "result.md").write_text(report, encoding="utf-8")

sys.stdout.write(f"\n通过={pass_count} 失败={fail_count}\n")
sys.stdout.write(f"报告: hw_node/result.md\n")

if fail_count > 0:
    sys.exit(1)