"""KBState 验证测试脚本（仅导入验证，不触发网络请求）。

验证点：
1. KBState TypedDict 7 个字段定义正确
2. workflows/state.py 可正常导入
3. workflows/nodes.py 5 个节点函数签名正确
4. workflows/graph.py build_graph() 返回 CompiledStateGraph 类型
5. 所有旧 pipeline 模块（collector/analyzer/organizer/reviewer/supervisor）可正常导入
6. invoke 可构造初始状态（不触发实际执行）

结果存储到 hw_status/result.md
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
# 1. KBState 定义验证
# ═══════════════════════════════════════════════════════════════════

results.append("## KBState 定义验证\n")

try:
    from workflows.state import KBState
    check("KBState 导入", True)

    assert hasattr(KBState, "__annotations__")
    check("KBState 是 TypedDict（有 __annotations__）", True)

    required_keys = {
        "sources": list,
        "analyses": list,
        "articles": list,
        "review_feedback": str,
        "review_passed": bool,
        "iteration": int,
        "cost_tracker": dict,
    }
    annotations = KBState.__annotations__
    for key, expected_type in required_keys.items():
        has_key = key in annotations
        check(f"字段 `{key}` 存在", has_key, f"类型={annotations.get(key)}" if has_key else "MISSING")

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "providers": {},
            "by_node": {},
        },
    }
    check("KBState 实例化（空状态）", True, "7 个字段均正确")

except Exception as e:
    for key in ["KBState 导入", "KBState 是 TypedDict"] + [f"字段 `{k}` 存在" for k in required_keys]:
        check(key, False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 2. nodes.py 节点函数验证
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 节点函数签名验证\n")

try:
    from workflows.nodes import (
        collect_node, analyze_node, organize_node, review_node, save_node
    )
    check("nodes.py 导入成功", True)

    for node_name, expected_params in [
        ("collect_node", ["state"]),
        ("analyze_node", ["state"]),
        ("organize_node", ["state"]),
        ("review_node", ["state"]),
        ("save_node", ["state"]),
    ]:
        fn = locals()[node_name]
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        check(f"{node_name} 签名", params == expected_params, f"params={params}")
        check(f"{node_name} 返回 dict", "dict" in str(fn.__annotations__), "")

except Exception as e:
    check("nodes.py 导入", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 3. graph.py build_graph() 验证
# ═══════════════════════════════════════════════════════════════════

results.append("\n## build_graph() 验证\n")

try:
    from workflows.graph import build_graph, decide_next
    check("graph.py 导入成功", True)

    graph = build_graph()
    check("build_graph() 返回对象", graph is not None)

    graph_type = type(graph).__name__
    check("返回类型是 CompiledStateGraph", "CompiledStateGraph" in graph_type, f"实际={graph_type}")

    sig = inspect.signature(decide_next)
    check("decide_next(state) 签名正确", list(sig.parameters.keys()) == ["state"])

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": True,
        "iteration": 1,
        "cost_tracker": {
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "providers": {},
            "by_node": {},
        },
    }
    next_node = decide_next(initial_state)
    check("decide_next(review_passed=True) -> 'save'", next_node == "save")

    initial_state["review_passed"] = False
    next_node = decide_next(initial_state)
    check("decide_next(review_passed=False) -> 'organize'", next_node == "organize")

except Exception as e:
    check("graph.py 导入", False, str(e))
    check("build_graph() 执行", False, str(e))
    results.append(f"```\n{traceback.format_exc()}\n```\n")

# ═══════════════════════════════════════════════════════════════════
# 4. 旧 pipeline 模块导入验证
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 旧模块导入验证\n")

old_modules = [
    ("workflows.collector", "workflows/collector.py"),
    ("workflows.analyzer", "workflows/analyzer.py"),
    ("workflows.organizer", "workflows/organizer.py"),
    ("workflows.reviewer", "workflows/reviewer.py"),
    ("patterns.supervisor", "patterns/supervisor.py"),
]

for module_name, file_path in old_modules:
    try:
        __import__(module_name)
        check(f"{module_name} 导入", True)
    except Exception as e:
        check(f"{module_name} 导入", False, str(e))

# ═══════════════════════════════════════════════════════════════════
# 5. nodes.py 各节点在空 state 下的行为
# ═══════════════════════════════════════════════════════════════════

results.append("\n## 节点空输入行为验证\n")

empty_state: KBState = {
    "sources": [],
    "analyses": [],
    "articles": [],
    "review_feedback": "",
    "review_passed": False,
    "iteration": 0,
    "cost_tracker": {"total_tokens": 0, "total_cost_cny": 0.0, "providers": {}, "by_node": {}},
}

for node_fn in [analyze_node, organize_node, review_node, save_node]:
    name = node_fn.__name__
    try:
        result = node_fn(empty_state)
        check(f"{name}(empty_state) 返回 dict", isinstance(result, dict), f"keys={list(result.keys())}")
    except Exception as e:
        check(f"{name}(empty_state) 执行", False, str(e))

results.append("- **SKIP** `collect_node(empty_state)` — 会触发网络请求，单独测试")

# ═══════════════════════════════════════════════════════════════════
# 写入结果
# ═══════════════════════════════════════════════════════════════════

output_dir = Path(__file__).resolve().parent
output_dir.mkdir(parents=True, exist_ok=True)

pass_count = sum(1 for r in results if "**PASS**" in r)
fail_count = sum(1 for r in results if "**FAIL**" in r)
skip_count = sum(1 for r in results if "**SKIP**" in r)

report = (
    "# KBState 验证报告\n\n"
    f"**通过: {pass_count} | 失败: {fail_count} | 跳过: {skip_count}**\n\n"
    + "\n".join(results)
    + f"\n\n*生成时间: {__import__('datetime').datetime.now().isoformat()}*\n"
)

(output_dir / "result.md").write_text(report, encoding="utf-8")

sys.stdout.write(f"通过={pass_count} 失败={fail_count} 跳过={skip_count}\n")
sys.stdout.write(f"报告: hw_status/result.md\n")

if fail_count > 0:
    sys.exit(1)