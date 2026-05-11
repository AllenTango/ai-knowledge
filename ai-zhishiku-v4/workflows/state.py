"""KBState — 知识库工作流全局状态定义。

使用 TypedDict 定义，供 LangGraph StateGraph 使用。
遵循"报告式通信"原则：每个字段承载结构化摘要而非原始数据。
"""

from typing import TypedDict


class KBState(TypedDict):
    """知识库工作流全局状态。

    StateGraph 中所有节点均通过此状态进行数据传递，
    每个节点返回 dict 即可合并到当前状态。
    """

    sources: list[dict]
    """采集到的原始数据汇总。
    每项格式: {"id": str, "title": str, "source": "github"|"rss",
                "source_url": str, "fetched_at": str, "stars": int,
                "language": str, "description": str}
    collect_node 写入，去除了 API 响应中的冗余字段。
    """

    analyses: list[dict]
    """LLM 分析后的结构化报告。
    每项格式: {"id": str, "title": str, "summary": str,
                "tags": list[str], "score": float, "analyzed_at": str,
                "model_provider": str}
    analyze_node 写入，每个元素对应 sources 中的一条。
    score 范围 0.0-1.0。
    """

    articles: list[dict]
    """格式化、去重后的知识条目，ready for review/save。
    每项格式: {"id": str, "title": str, "source": str,
                "source_url": str, "fetched_at": str, "analyzed_at": str,
                "summary": str, "tags": list[str], "status": str,
                "score": float, "reviewer": str|null,
                "reviewed_at": str|null, "published_to": list[str],
                "retry_count": int}
    organize_node 写入，符合 AGENTS.md 标准知识条目格式。
    """

    review_feedback: str
    """审核反馈意见。
    review_node 在 review_passed=False 时写入，供下一轮
    organize_node 中的 LLM 修正步骤使用。
    格式: 简体中文，分维度列出问题。
    """

    review_passed: bool
    """审核是否通过四维度质量标准。
    True  → 流向 save_node → END。
    False → 流向 organize_node，进入重试循环（iteration 累加）。
    """

    iteration: int
    """当前审核循环轮次（从 0 递增，上限为 2）。
    0 = 初始状态  1 = 第一轮审核  2 = 第二轮审核
    review_node 在 iteration >= 2 时强制 review_passed=True。
    """

    cost_tracker: dict
    """全流程 Token 用量累积追踪报告。
    格式: {"total_tokens": int, "total_cost_cny": float,
            "providers": {"deepseek": {"tokens": int, "cost": float}, ...},
            "by_node": {"collect": int, "analyze": int,
                         "organize": int, "review": int, "save": int}}
    各节点执行完毕后累积自己的用量到此报告，供最终审计。
    """

    needs_human_review: bool
    """是否需要人工审核。
    当 review_passed=False 且 iteration 超过上限时由 human_flag_node 写入 True。
    为 True 时条目不写入主知识库（knowledge/articles/），
    而是写入待人工审核目录（knowledge/human_review/）。
    流程终结，不再流向 save。
    """

    plan: dict
    """本次采集策略配置。
    由 planner_node 写入，格式：
    {
        "strategy": "lite"|"standard"|"full",
        "per_source_limit": int,
        "relevance_threshold": float,
        "max_iterations": int,
        "rationale": str
    }
    各节点根据此配置控制行为强度。
    """
