"""LangGraph 知识库工作流 — 图定义与条件边。

工作流节点：
  collect → analyze → organize → review
                                    │
                        decide_next:
                          - review_passed=True → save → END
                          - review_passed=False & iteration<2 → revise → organize
                          - review_passed=False & iteration>=2 → human_flag → END
"""

import logging

from langgraph.graph import StateGraph, END

from workflows.state import KBState
from workflows.nodes import (
    collect_node,
    analyze_node,
    organize_node,
    review_node,
    revise_node,
    save_node,
    human_flag_node,
    MAX_ITERATIONS,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def route_after_review(state: KBState) -> str:
    """条件边：review 之后根据 review_passed 和 iteration 三分支路由。

    Args:
        state: KBState 当前状态。

    Returns:
        "organize"    — review_passed=True，通过审核
        "revise"      — review_passed=False 且 iteration < 3，修正后重新审核
        "human_flag"  — review_passed=False 且 iteration >= 3，需人工判断
    """
    if state.get("review_passed", False):
        return "organize"

    iteration = state.get("iteration", 0)
    if iteration >= MAX_ITERATIONS:
        logger.info(f"iteration={iteration} >= 3，进入人工标记")
        return "human_flag"

    return "revise"


def build_graph():
    """构建并编译知识库工作流图。

    Returns:
        CompiledStateGraph — 可调用 .invoke(initial_state) 执行。
    """
    workflow = StateGraph(KBState)

    workflow.add_node("collect", collect_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("organize", organize_node)
    workflow.add_node("review", review_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("save", save_node)
    workflow.add_node("human_flag", human_flag_node)

    workflow.set_entry_point("collect")

    workflow.add_edge("collect", "analyze")
    workflow.add_edge("analyze", "organize")
    workflow.add_edge("organize", "review")

    workflow.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    workflow.add_edge("organize", "save")
    workflow.add_edge("revise", "review")
    workflow.add_edge("save", END)
    workflow.add_edge("human_flag", END)

    return workflow.compile()
