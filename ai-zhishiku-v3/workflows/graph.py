"""LangGraph 知识库工作流 — 图定义与条件边。

使用 langgraph.graph.StateGraph 构建 collect → analyze → organize → review → save 工作流，
review 之后通过条件边分支：
  - True  → save  → END
  - False → organize（回到整理节点，用 LLM 再次修正）
"""

import logging

from langgraph.graph import StateGraph, END                         # 需求 1

from workflows.state import KBState                                  # 需求 3
from workflows.nodes import (                                        # 需求 2
    collect_node,
    analyze_node,
    organize_node,
    review_node,
    save_node,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def decide_next(state: KBState) -> str:
    """条件边：review 之后根据 review_passed 分支。

    Args:
        state: KBState 当前状态。

    Returns:
        "save" — 流向保存节点 → END
        "organize" — 回到整理节点修正（携带 review_feedback）
    """
    return "save" if state.get("review_passed", False) else "organize"


def build_graph():
    """构建并编译知识库工作流图。

    Returns:
        CompiledGraph — 可调用 .invoke(initial_state) 执行。  # 需求 7
    """
    workflow = StateGraph(KBState)

    # 添加 5 个节点
    workflow.add_node("collect", collect_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("organize", organize_node)
    workflow.add_node("review", review_node)
    workflow.add_node("save", save_node)

    # 入口点（需求 6）
    workflow.set_entry_point("collect")

    # 线性边（需求 4）
    workflow.add_edge("collect", "analyze")
    workflow.add_edge("analyze", "organize")
    workflow.add_edge("organize", "review")

    # 条件边（需求 5）
    workflow.add_conditional_edges(
        "review",
        decide_next,
        {
            "save": "save",
            "organize": "organize",
        },
    )
    workflow.add_edge("save", END)

    return workflow.compile()
