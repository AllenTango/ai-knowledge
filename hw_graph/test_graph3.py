"""graph.py 完整行为测试脚本。

测试场景：
1. standard 策略：首次审核通过（理想路径）
2. standard 策略：首次未过 → revise → 第二次通过
3. standard 策略：三次未过 → human_flag 兜底
4. lite 策略：max_iterations=1，首次未过直接 human_flag
5. full 策略：per_source_limit=20, threshold=0.4

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


def make_state(overrides: dict | None = None) -> dict:
    base = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
        "needs_human_review": False,
        "plan": {
            "strategy": "standard",
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "target_count": 10,
            "rationale": "standard",
        },
        "target_count": 10,
    }
    if overrides:
        base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════
# 1. plan_strategy 三档策略
# ═══════════════════════════════════════════════════════════════════

results.append("## plan_strategy 三档策略\n")

from workflows.nodes import plan_strategy

for target, expected_strategy, expected_limit, expected_threshold, expected_iter in [
    (5, "lite", 5, 0.7, 1),
    (9, "lite", 5, 0.7, 1),
    (10, "standard", 10, 0.5, 2),
    (15, "standard", 10, 0.5, 2),
    (19, "standard", 10, 0.5, 2),
    (20, "full", 20, 0.4, 3),
    (30, "full", 20, 0.4, 3),
]:
    plan = plan_strategy(target_count=target)
    check(f"target={target} → strategy={expected_strategy}", plan["strategy"] == expected_strategy, f"实际={plan['strategy']}")
    check(f"target={target} per_source_limit={expected_limit}", plan["per_source_limit"] == expected_limit, f"实际={plan['per_source_limit']}")
    check(f"target={target} relevance_threshold={expected_threshold}", plan["relevance_threshold"] == expected_threshold, f"实际={plan['relevance_threshold']}")
    check(f"target={target} max_iterations={expected_iter}", plan["max_iterations"] == expected_iter, f"实际={plan['max_iterations']}")
    check(f"target={target} 有 rationale", "rationale" in plan and len(plan["rationale"]) > 10)


# ═══════════════════════════════════════════════════════════════════
# 2. planner_node 写入 plan
# ═══════════════════════════════════════════════════════════════════

results.append("\n## planner_node 写入 plan\n")

from workflows.nodes import planner_node

state1 = make_state({"target_count": 15})
result1 = planner_node(state1)
check("planner_node 返回 plan", "plan" in result1)
check("planner_node plan.strategy=standard", result1["plan"]["strategy"] == "standard")
check("planner_node plan.target_count=15", result1["plan"]["target_count"] == 15)


# ═══════════════════════════════════════════════════════════════════
# 3. 场景 A：standard 首次审核通过
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 场景 A：standard 首次审核通过（理想路径）\n")

call_idx = [0]

pass_response = {"reviews": [
    {"id": "a1", "summary_quality": 8, "technical_depth": 8, "relevance": 8, "originality": 8, "formatting": 8}
]}

def mock_chat_json_pass(prompt="", system="", temperature=0.1, **kwargs):
    class MockUsage:
        total_tokens = 100
    return pass_response, MockUsage()

state_a = make_state({"analyses": [
    {"id": "a1", "title": "Test Item", "summary": "足够长的摘要内容以满足50字要求，包含技术细节",
     "tags": ["ai", "test"], "score": 0.8, "source": "github",
     "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}
], "target_count": 10, "plan": plan_strategy(10)})

with patch("workflows.model_client.chat_json", side_effect=mock_chat_json_pass):
    with patch("workflows.model_client.check_llm_available", return_value=True):
        from workflows.nodes import review_node

        result_a = review_node(state_a)
        check("场景A: review_node review_passed=True", result_a.get("review_passed") == True)
        check("场景A: review_node iteration=1", result_a.get("iteration") == 1)
        check("场景A: review_feedback=''", result_a.get("review_feedback") == "")

        from workflows.graph import route_after_review
        check("场景A: route → 'organize'", route_after_review(result_a) == "organize")


# ═══════════════════════════════════════════════════════════════════
# 4. 场景 B：首次未过 → revise → 第二次通过
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 场景 B：首次未过 → revise → 第二次通过\n")

call_idx[0] = 0

fail_response = {"reviews": [
    {"id": "a1", "summary_quality": 4, "technical_depth": 3, "relevance": 6, "originality": 5, "formatting": 4}
]}
pass_response2 = {"reviews": [
    {"id": "a1", "summary_quality": 8, "technical_depth": 8, "relevance": 8, "originality": 8, "formatting": 8}
]}
revise_response = {"revised": [
    {"id": "a1", "summary": "修正后摘要，包含足够技术细节", "tags": ["ai", "test"], "score": 0.85}
]}

def mock_chat_json_b(prompt="", system="", temperature=0.1, **kwargs):
    idx = call_idx[0]
    call_idx[0] += 1
    class MockUsage:
        total_tokens = 100
    if idx == 0:
        return fail_response, MockUsage()
    elif idx == 1:
        return revise_response, MockUsage()
    return pass_response2, MockUsage()

state_b = make_state({"analyses": [
    {"id": "a1", "title": "Test B", "summary": "短", "tags": ["test"],
     "score": 0.6, "source": "github", "source_url": "http://x.com",
     "analyzed_at": "2026-05-10T00:00:00Z"}
], "target_count": 10, "plan": plan_strategy(10)})

with patch("workflows.model_client.chat_json", side_effect=mock_chat_json_b):
    with patch("workflows.model_client.check_llm_available", return_value=True):
        from workflows.nodes import review_node, revise_node

        result_b1 = review_node(state_b)
        check("场景B 第1次: review_passed=False", result_b1.get("review_passed") == False)
        check("场景B 第1次: iteration=1", result_b1.get("iteration") == 1)
        check("场景B 第1次: route → 'revise'", route_after_review(result_b1) == "revise")

        state_b.update(result_b1)
        result_b2 = revise_node(state_b)
        check("场景B revise: 返回 analyses", "analyses" in result_b2)
        check("场景B revise: 返回 cost_tracker", "cost_tracker" in result_b2)

        state_b.update(result_b2)
        result_b3 = review_node(state_b)
        check("场景B 第2次: review_passed=True", result_b3.get("review_passed") == True)
        check("场景B 第2次: iteration=2", result_b3.get("iteration") == 2)
        check("场景B 第2次: route → 'organize'", route_after_review(result_b3) == "organize")


# ═══════════════════════════════════════════════════════════════════
# 5. 场景 C：三次未过 → human_flag 兜底
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 场景 C：三次未过 → human_flag 兜底\n")

call_idx[0] = 0

def mock_chat_json_always_fail(prompt="", system="", temperature=0.1, **kwargs):
    idx = call_idx[0]
    call_idx[0] += 1
    class MockUsage:
        total_tokens = 100
    if temperature == 0.4:
        return {"revised": [{"id": "a1", "summary": "修正", "tags": ["a"], "score": 0.6}]}, MockUsage()
    return {"reviews": [{"id": "a1", "summary_quality": 4, "technical_depth": 3, "relevance": 5, "originality": 4, "formatting": 3}]}, MockUsage()

state_c = make_state({"analyses": [
    {"id": "a1", "title": "Test C", "summary": "短", "tags": ["test"],
     "score": 0.5, "source": "github", "source_url": "http://x.com",
     "analyzed_at": "2026-05-10T00:00:00Z"}
], "target_count": 10, "plan": plan_strategy(10)})

with patch("workflows.model_client.chat_json", side_effect=mock_chat_json_always_fail):
    with patch("workflows.model_client.check_llm_available", return_value=True):
        from workflows.nodes import review_node, revise_node, human_flag_node

        iterations_seen = []
        routes_seen = []
        for i in range(3):
            result_c = review_node(state_c)
            state_c.update(result_c)
            iterations_seen.append(result_c.get("iteration"))
            route = route_after_review(result_c)
            routes_seen.append(route)
            if route != "revise":
                break
            result_r = revise_node(state_c)
            state_c.update(result_r)

        check("场景C: 三次审核 iteration=[1,2,3]", iterations_seen == [1, 2, 3], f"实际={iterations_seen}")
        check("场景C: 最终路由 'human_flag'", routes_seen[-1] == "human_flag")

        result_hf = human_flag_node(state_c)
        check("场景C: human_flag_node 执行成功", result_hf == {})

        flag_dir = project_root / "knowledge" / "human_review"
        flags = sorted(flag_dir.glob("flag-*.json"))
        check("场景C: human_review 目录有文件", len(flags) > 0)
        if flags:
            flag_data = None
            for f in reversed(flags):
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if data.get("iteration") == 3:
                        flag_data = data
                        break
            if not flag_data:
                flag_data = {"iteration": "unknown"}
            check("场景C: flag iteration=3", flag_data.get("iteration") == 3)


# ═══════════════════════════════════════════════════════════════════
# 6. lite 策略：max_iterations=1，首次未过直接 human_flag
# ═══════════════════════════════════════════════════════════════════

results.append("\n## lite 策略：max_iterations=1，直接 human_flag\n")

call_idx[0] = 0
lite_plan = plan_strategy(5)
check("lite plan.strategy=lite", lite_plan["strategy"] == "lite")
check("lite plan.max_iterations=1", lite_plan["max_iterations"] == 1)
check("lite plan.relevance_threshold=0.7", lite_plan["relevance_threshold"] == 0.7)

state_lite = make_state({"analyses": [
    {"id": "l1", "title": "Lite Item", "summary": "测试", "tags": ["test"],
     "score": 0.5, "source": "github", "source_url": "http://x.com",
     "analyzed_at": "2026-05-10T00:00:00Z"}
], "plan": lite_plan, "iteration": 0})

check("lite iter=0 < max_iterations=1, route='revise'", route_after_review(state_lite) == "revise")

state_lite["iteration"] = 1
check("lite iter=1 >= max_iterations=1 → route='human_flag'", route_after_review(state_lite) == "human_flag")


# ═══════════════════════════════════════════════════════════════════
# 7. full 策略：per_source_limit=20, threshold=0.4
# ═══════════════════════════════════════════════════════════════════

results.append("\n## full 策略：per_source_limit=20, threshold=0.4\n")

full_plan = plan_strategy(30)
check("full plan.strategy=full", full_plan["strategy"] == "full")
check("full plan.per_source_limit=20", full_plan["per_source_limit"] == 20)
check("full plan.relevance_threshold=0.4", full_plan["relevance_threshold"] == 0.4)
check("full plan.max_iterations=3", full_plan["max_iterations"] == 3)

# 验证 collect_node 使用 plan
from workflows.nodes import collect_node
state_full = make_state({"plan": full_plan, "target_count": 30})

collected_sources = []
original_fetch = None

def mock_github_request(url, headers=None, timeout=15):
    class MockResp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"items": [
                {"full_name": f"test/repo-{i}", "html_url": f"http://x.com/{i}",
                 "stargazers_count": 100, "language": "Python", "description": "test"}
                for i in range(25)
            ]}).encode()
    return MockResp()

with patch("urllib.request.urlopen", mock_github_request):
    with patch("workflows.collector.fetch_rss_sources", return_value=[]):
        result_fc = collect_node(state_full)
        check("full: collect_node 返回 sources", "sources" in result_fc)
        check("full: collect_node 采集数量=20（per_source_limit）", len(result_fc.get("sources", [])) == 20, f"实际={len(result_fc.get('sources', []))}")

# 验证 organize_node 使用 threshold=0.4
from workflows.nodes import organize_node
state_org = make_state({"analyses": [
    {"id": "o1", "title": "Org Test", "summary": "足够长的摘要内容", "tags": ["ai"],
     "score": 0.45, "source": "github", "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}
], "plan": full_plan})

result_org = organize_node(state_org)
check("full: organize_node threshold=0.4，0.45>=0.4 保留", len(result_org.get("articles", [])) == 1)

state_org2 = make_state({"analyses": [
    {"id": "o2", "title": "Org Test2", "summary": "足够长的摘要内容", "tags": ["ai"],
     "score": 0.39, "source": "github", "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}
], "plan": full_plan})
result_org2 = organize_node(state_org2)
check("full: organize_node threshold=0.4，0.39<0.4 过滤", len(result_org2.get("articles", [])) == 0)


# ═══════════════════════════════════════════════════════════════════
# 8. build_graph 编译验证
# ═══════════════════════════════════════════════════════════════════

results.append("\n## build_graph 编译验证（8 节点）\n")

from workflows.graph import build_graph

graph = build_graph()
nodes = list(graph.nodes.keys())
custom_nodes = [n for n in nodes if n not in ("__start__", "__end__")]
check("8 个自定义节点", len(custom_nodes) == 8, f"节点={custom_nodes}")

for expected in ["planner", "collect", "analyze", "organize", "review", "revise", "save", "human_flag"]:
    check(f"节点 '{expected}' 存在", expected in custom_nodes)


# ═══════════════════════════════════════════════════════════════════
# 写入结果
# ═══════════════════════════════════════════════════════════════════

output_dir = Path(__file__).resolve().parent

pass_count = sum(1 for r in results if "**PASS**" in r)
fail_count = sum(1 for r in results if "**FAIL**" in r)
skip_count = sum(1 for r in results if "**SKIP**" in r)

report = (
    "# workflows/graph.py 完整行为测试报告\n\n"
    f"**通过: {pass_count} | 失败: {fail_count} | 跳过: {skip_count}**\n\n"
    + "\n".join(results)
    + f"\n\n*生成时间: {__import__('datetime').datetime.now().isoformat()}*\n"
)

(output_dir / "result.md").write_text(report, encoding="utf-8")

sys.stdout.write(f"通过={pass_count} 失败={fail_count} 跳过={skip_count}\n")
sys.stdout.write(f"报告: hw_graph/result.md\n")

if fail_count > 0:
    sys.exit(1)