"""graph.py 行为测试脚本。

测试场景：
1. 正常通过路径：analyze → organize → review(passed=True) → organize → save → END
2. 强制触发 revise 路径：review(passed=False, iteration=0) → revise → review(iteration=1)
3. iteration>=3 触发 human_flag 路径

结果存储到 hw_graph/result.md
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

results = []
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def check(label: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append(f"- **{status}** `{label}` {detail}")


def make_state(overrides: dict) -> dict:
    base = {
        "sources": [{"id": "s1", "title": "Test Source", "source": "github",
                     "source_url": "http://x.com", "fetched_at": "2026-05-10T00:00:00Z",
                     "stars": 100, "language": "Python", "description": "test"}],
        "analyses": [{"id": "a1", "title": "Test Analysis", "summary": "内容摘要足够长以满足50字要求，这里补充更多细节",
                      "tags": ["test", "ai"], "score": 0.8, "source": "github",
                      "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
        "needs_human_review": False,
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════
# 1. route_after_review 三分支逻辑
# ═══════════════════════════════════════════════════════════════════

results.append("## route_after_review 三分支逻辑\n")

from workflows.graph import route_after_review

test_cases = [
    ("review_passed=True", {"review_passed": True, "iteration": 1}, "organize"),
    ("review_passed=False, iteration=0", {"review_passed": False, "iteration": 0}, "revise"),
    ("review_passed=False, iteration=2", {"review_passed": False, "iteration": 2}, "revise"),
    ("review_passed=False, iteration=3", {"review_passed": False, "iteration": 3}, "human_flag"),
    ("review_passed=False, iteration=5", {"review_passed": False, "iteration": 5}, "human_flag"),
]

for label, state_override, expected in test_cases:
    state = make_state(state_override)
    actual = route_after_review(state)
    check(f"route_after_review({label})", actual == expected, f"expected={expected} actual={actual}")

# ═══════════════════════════════════════════════════════════════════
# 2. build_graph() 编译成功，7 个节点
# ═══════════════════════════════════════════════════════════════════

results.append("\n## build_graph() 编译验证\n")

from workflows.graph import build_graph

try:
    graph = build_graph()
    check("build_graph() 执行成功", graph is not None)

    nodes = list(graph.nodes.keys())
    custom_nodes = [n for n in nodes if n not in ("__start__", "__end__")]
    check("7 个自定义节点", len(custom_nodes) == 7, f"节点={custom_nodes}")

    for expected in ["collect", "analyze", "organize", "review", "revise", "save", "human_flag"]:
        check(f"节点 '{expected}' 存在", expected in custom_nodes)

    graph_type = type(graph).__name__
    check("返回 CompiledStateGraph", "CompiledStateGraph" in graph_type, f"实际={graph_type}")
except Exception as e:
    check("build_graph() 编译", False, str(e))

# ═══════════════════════════════════════════════════════════════════
# 3. 模拟正常通过路径（mock review_node 返回 review_passed=True）
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 正常通过路径测试\n")

def mock_pass_state(state):
    from workflows.nodes import organize_node, save_node
    result = organize_node(state)
    state.update(result)
    result2 = save_node(state)
    return state, "save_done"

CALL_ORDER = []
ANALYSIS_MOCK_RESPONSE = {"reviews": [
    {"id": "a1", "summary_quality": 8, "technical_depth": 8, "relevance": 8, "originality": 8, "formatting": 8}
]}
REVISION_MOCK_RESPONSE = {"revised": [
    {"id": "a1", "summary": "修正后摘要", "tags": ["test"], "score": 0.85}
]}

call_idx = [0]
def mock_chat_json(prompt="", system="", temperature=0.1, **kwargs):
    idx = call_idx[0]
    call_idx[0] += 1
    class MockUsage:
        total_tokens = 100
    if idx < 2:
        return ANALYSIS_MOCK_RESPONSE, MockUsage()
    return REVISION_MOCK_RESPONSE, MockUsage()

def mock_check_llm():
    return True

state_pass = make_state({"review_passed": True, "iteration": 0})

with patch("workflows.model_client.chat_json", side_effect=mock_chat_json):
    with patch("workflows.model_client.check_llm_available", mock_check_llm):
        from workflows.nodes import review_node
        result = review_node(state_pass)
        check("review_node(review_passed=True) 返回 review_passed=True", result.get("review_passed") == True)
        check("review_node iteration 递增", result.get("iteration") == 1)
        check("route_after_review(passed=True) → 'organize'", route_after_review(result) == "organize")

# ═══════════════════════════════════════════════════════════════════
# 4. 模拟 revise 路径（mock review 返回 passed=False）
# ═══════════════════════════════════════════════════════════════════

results.append("\n## revise 路径测试\n")

call_idx[0] = 0
review_response = {"reviews": [
    {"id": "a1", "summary_quality": 4, "technical_depth": 3, "relevance": 6, "originality": 5, "formatting": 4}
]}
revise_response = {"revised": [
    {"id": "a1", "summary": "修正后摘要内容", "tags": ["ai", "test"], "score": 0.85}
]}

def mock_chat_json_fail(prompt="", system="", temperature=0.1, **kwargs):
    idx = call_idx[0]
    call_idx[0] += 1
    class MockUsage:
        total_tokens = 100
    if idx == 0:
        return review_response, MockUsage()
    return revise_response, MockUsage()

state_fail = make_state({"review_passed": False, "iteration": 0})

with patch("workflows.model_client.chat_json", side_effect=mock_chat_json_fail):
    with patch("workflows.model_client.check_llm_available", mock_check_llm):
        from workflows.nodes import review_node, revise_node

        result1 = review_node(state_fail)
        check("第1次 review 返回 review_passed=False", result1.get("review_passed") == False)
        check("第1次 review iteration=1", result1.get("iteration") == 1)
        check("第1次 review feedback 非空", result1.get("review_feedback") != "")

        state_fail.update(result1)
        check("route_after_review(passed=False, iter=1) → 'revise'", route_after_review(state_fail) == "revise")

        result2 = revise_node(state_fail)
        check("revise_node 返回 analyses", "analyses" in result2)
        check("revise_node 返回 cost_tracker", "cost_tracker" in result2)
        check("revise_node 不抛异常", True)

# ═══════════════════════════════════════════════════════════════════
# 5. 模拟 human_flag 路径（iteration >= 3）
# ═══════════════════════════════════════════════════════════════════

results.append("\n## human_flag 路径测试\n")

from workflows.nodes import human_flag_node

state_human = make_state({"review_passed": False, "iteration": 3, "analyses": [
    {"id": "h1", "title": "Human Flag Item", "summary": "测试摘要", "tags": ["test"],
     "score": 0.6, "source": "github", "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}
], "review_feedback": "多次审核未通过，技术深度不足"})
state_human["cost_tracker"] = {"total_tokens": 1000, "total_cost_cny": 0.0, "providers": {}, "by_node": {"review": 500}}

check("route_after_review(passed=False, iter=3) → 'human_flag'", route_after_review(state_human) == "human_flag")

try:
    result = human_flag_node(state_human)
    check("human_flag_node 执行成功", result == {})
    flag_dir = project_root / "knowledge" / "human_review"
    flags = list(flag_dir.glob("flag-*.json"))
    check("human_review 目录有文件", len(flags) > 0, f"文件数={len(flags)}")
    if flags:
        with open(flags[-1], "r", encoding="utf-8") as f:
            flag_data = json.load(f)
        check("flag 文件包含 analyses", "analyses" in flag_data)
        check("flag 文件包含 iteration", "iteration" in flag_data)
        check("flag 文件 iteration=3", flag_data.get("iteration") == 3)
        check("flag 文件包含 review_feedback", "review_feedback" in flag_data)
except Exception as e:
    check("human_flag_node 执行", False, str(e))

# ═══════════════════════════════════════════════════════════════════
# 6. revise_node 空 feedback 跳过
# ═══════════════════════════════════════════════════════════════════

results.append("\n## revise_node 空状态跳过测试\n")

state_empty = make_state({"analyses": [], "review_feedback": ""})
result = revise_node(state_empty)
check("revise_node(analyses=[], feedback='') 返回空 dict", result == {})

state_no_feedback = make_state({"review_feedback": ""})
result = revise_node(state_no_feedback)
check("revise_node(feedback='') 返回空 dict", result == {})

# ═══════════════════════════════════════════════════════════════════
# 写入结果
# ═══════════════════════════════════════════════════════════════════

output_dir = Path(__file__).resolve().parent

pass_count = sum(1 for r in results if "**PASS**" in r)
fail_count = sum(1 for r in results if "**FAIL**" in r)
skip_count = sum(1 for r in results if "**SKIP**" in r)

report = (
    "# workflows/graph.py 行为测试报告\n\n"
    f"**通过: {pass_count} | 失败: {fail_count} | 跳过: {skip_count}**\n\n"
    + "\n".join(results)
    + f"\n\n*生成时间: {__import__('datetime').datetime.now().isoformat()}*\n"
)

(output_dir / "result.md").write_text(report, encoding="utf-8")

sys.stdout.write(f"通过={pass_count} 失败={fail_count} 跳过={skip_count}\n")
sys.stdout.write(f"报告: hw_graph/result.md\n")

if fail_count > 0:
    sys.exit(1)