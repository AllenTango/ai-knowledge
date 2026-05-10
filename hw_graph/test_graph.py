"""workflows/graph.py 行为测试脚本。

测试点：
1. decide_next 分支逻辑（review_passed=True/False）
2. build_graph() 编译成功，返回 CompiledStateGraph
3. 图结构验证：5 个节点、5 条边（collect→analyze→organize→review、条件边×2）
4. 模拟 retry 循环路径：organize → review → organize → review → save
5. review_node iteration 强制通过逻辑
6. state 在循环中累积（articles 被更新，iteration 递增）

结果存储到 hw_graph/result.md
"""

import sys
import traceback
import inspect
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

results = []
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def check(label: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append(f"- **{status}** `{label}` {detail}")


# ═══════════════════════════════════════════════════════════════════
# 1. decide_next 分支逻辑
# ═══════════════════════════════════════════════════════════════════

results.append("## decide_next 分支逻辑\n")

from workflows.graph import decide_next
from workflows.state import KBState

test_cases = [
    ("review_passed=True", {"review_passed": True, "iteration": 1, "sources": [], "analyses": [], "articles": [], "review_feedback": "", "cost_tracker": {}}, "save"),
    ("review_passed=False", {"review_passed": False, "iteration": 0, "sources": [], "analyses": [], "articles": [], "review_feedback": "", "cost_tracker": {}}, "organize"),
    ("review_passed=False iteration=1", {"review_passed": False, "iteration": 1, "sources": [], "analyses": [], "articles": [], "review_feedback": "摘要过短", "cost_tracker": {}}, "organize"),
    ("review_passed=True iteration=2", {"review_passed": True, "iteration": 2, "sources": [], "analyses": [], "articles": [], "review_feedback": "", "cost_tracker": {}}, "save"),
]

for label, state, expected in test_cases:
    actual = decide_next(state)
    check(f"decide_next({label})", actual == expected, f"expected={expected} actual={actual}")

# ═══════════════════════════════════════════════════════════════════
# 2. build_graph() 编译成功
# ═══════════════════════════════════════════════════════════════════

results.append("\n## build_graph() 编译\n")

try:
    from workflows.graph import build_graph

    graph = build_graph()
    check("build_graph() 执行成功", graph is not None)

    graph_type = type(graph).__name__
    check("返回 CompiledStateGraph", "CompiledStateGraph" in graph_type, f"实际={graph_type}")

    check("graph 有 invoke 方法", hasattr(graph, "invoke"))
except Exception as e:
    check("build_graph() 编译", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 3. 图结构验证（检查 LangGraph 内部结构）
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 图结构验证\n")

try:
    from workflows.graph import build_graph

    graph = build_graph()

    nodes = list(graph.nodes.keys())
    check("自定义 5 个节点存在", all(n in nodes for n in ["collect", "analyze", "organize", "review", "save"]), f"节点={nodes}")

    for expected_node in ["collect", "analyze", "organize", "review", "save"]:
        check(f"节点 '{expected_node}' 存在", expected_node in nodes)

    channels = list(graph.channels.keys())
    check("所有 KBState 字段作为 channel 存在", all(k in channels for k in ["sources", "analyses", "articles", "review_feedback", "review_passed", "iteration", "cost_tracker"]), f"channels={channels}")

except Exception as e:
    check("图结构验证", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 4. 模拟 retry 循环（mock nodes，直接操作 state）
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 模拟 retry 循环路径\n")

try:
    from workflows.nodes import analyze_node, organize_node, review_node, save_node

    mock_sources = [
        {"id": "test-1", "title": "Test Project", "source": "github", "source_url": "https://github.com/test/project", "fetched_at": "2026-05-10T00:00:00Z", "stars": 1000, "language": "Python", "description": "An AI project"},
    ]
    mock_analyses = [
        {"id": "test-1", "title": "Test Project", "summary": "Too short", "tags": ["test"], "score": 0.7, "source": "github", "source_url": "https://github.com/test/project", "analyzed_at": "2026-05-10T00:00:00Z"},
    ]

    state = {
        "sources": mock_sources,
        "analyses": mock_analyses,
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
    }

    # 轮次 1: organize → review
    result1 = organize_node(state)
    state.update(result1)
    check("第1次 organize_node 执行", "articles" in result1, f"articles={len(result1.get('articles', []))}")

    result2 = review_node(state)
    state.update(result2)
    check("第1次 review_node 执行", "review_passed" in result2, f"review_passed={result2.get('review_passed')} iteration={result2.get('iteration')}")
    check("第1次 review 后 iteration=1", result2.get("iteration") == 1)

    # 轮次 2: organize（带 feedback）→ review
    if not state.get("review_passed", False):
        check("第1次 review 未通过，进入第2次循环", True)
        result3 = organize_node(state)
        state.update(result3)
        check("第2次 organize_node 执行（带 feedback）", "articles" in result3)

        result4 = review_node(state)
        state.update(result4)
        check("第2次 review_node 执行", "review_passed" in result4)
        check("第2次 review 后 iteration=2", result4.get("iteration") == 2)
        check("第2次 review iteration>=2 强制通过", result4.get("review_passed") == True)

        # 最终 save
        result5 = save_node(state)
        check("save_node 执行（强制通过后）", result5 == {})
    else:
        check("第1次 review 已通过（无 feedback 时）", True)
        result5 = save_node(state)
        check("save_node 执行（直接通过）", result5 == {})

except Exception as e:
    check("retry 循环模拟", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 5. 审查 iteration 强制通过逻辑
# ═══════════════════════════════════════════════════════════════════

results.append("\n## review_node iteration 强制通过逻辑\n")

try:
    from workflows.nodes import review_node

    empty_articles_state: KBState = {
        "sources": [], "analyses": [], "articles": [],
        "review_feedback": "", "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
    }

    for iteration in [0, 1, 2, 3]:
        empty_articles_state["iteration"] = iteration
        result = review_node(empty_articles_state)
        passed = result.get("review_passed")
        actual_iter = result.get("iteration")
        if iteration >= 2:
            check(f"iteration={iteration} → review_passed=True（强制通过）", passed == True, f"iteration={iteration} passed={passed}")
        else:
            check(f"iteration={iteration} → review_passed=True（空articles兜底）", passed == True, f"iteration={iteration} passed={passed}")

except Exception as e:
    check("iteration 强制通过逻辑", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 6. analyze_node 空 state 处理
# ═══════════════════════════════════════════════════════════════════

results.append("\n## analyze_node 空 state 处理\n")

try:
    from workflows.nodes import analyze_node

    empty_state: KBState = {
        "sources": [], "analyses": [], "articles": [],
        "review_feedback": "", "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
    }

    result = analyze_node(empty_state)
    check("analyze_node(sources=[]) 返回空更新", result == {}, "无网络请求，实际跳过")
    check("analyze_node 空 state 不抛异常", True)

    # 正常 state 但无 LLM
    from workflows.model_client import check_llm_available
    if not check_llm_available():
        results.append(f"- **SKIP** analyze_node LLM 调用测试（无 API Key）")
    else:
        normal_state = empty_state.copy()
        normal_state["sources"] = [{"id": "x", "title": "Test", "source": "github", "source_url": "http://x.com", "fetched_at": "2026-05-10T00:00:00Z", "stars": 0, "language": "Python", "description": "test"}]
        result = analyze_node(normal_state)
        check("analyze_node 正常 state 有输出", "analyses" in result)

except Exception as e:
    check("analyze_node 空 state 处理", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 7. organize_node feedback 修正逻辑
# ═══════════════════════════════════════════════════════════════════

results.append("\n## organize_node feedback 修正逻辑\n")

try:
    from workflows.nodes import organize_node

    state_with_feedback: KBState = {
        "sources": [], "analyses": [
            {"id": "x", "title": "Test", "summary": "Too short", "tags": ["test"], "score": 0.7,
             "source": "github", "source_url": "http://x.com", "analyzed_at": "2026-05-10T00:00:00Z"}
        ], "articles": [],
        "review_feedback": "摘要过短（少于50字），需补充技术细节",
        "review_passed": False,
        "iteration": 1,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
    }

    result = organize_node(state_with_feedback)
    check("organize_node 处理 feedback", "articles" in result)
    check("feedback 非空时 articles 生成", len(result.get("articles", [])) == 1)
    check("organize_node 不抛异常", True)

except Exception as e:
    check("organize_node feedback 修正逻辑", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 8. save_node 空 articles 处理
# ═══════════════════════════════════════════════════════════════════

results.append("\n## save_node 空 articles 处理\n")

try:
    from workflows.nodes import save_node

    empty_state: KBState = {
        "sources": [], "analyses": [], "articles": [],
        "review_feedback": "", "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
    }

    result = save_node(empty_state)
    check("save_node(articles=[]) 返回空 dict", result == {})
    check("save_node 空 articles 不抛异常", True)

except Exception as e:
    check("save_node 空 articles 处理", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 写入结果
# ═══════════════════════════════════════════════════════════════════

output_dir = Path(__file__).resolve().parent
output_dir.mkdir(parents=True, exist_ok=True)

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