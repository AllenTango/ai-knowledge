# ai-zhishiku-v3 LangGraph 工作流集成方案

## 一、方案概述

将现有的单体流水线（`scheduler/run_pipeline.ps1` 顺序调用脚本）升级为基于 LangGraph 的 StateGraph 工作流，用节点 + 有向边 + 条件边管理完整的数据采集 → 分析 → 整理 → 审核 → 保存流程。

---

## 二、目录结构

```
ai-zhishiku-v3/
├── workflows/
│   ├── __init__.py
│   ├── model_client.py       # LLM 统一客户端
│   ├── collector.py          # 旧独立脚本（保留，可被复用）
│   ├── analyzer.py           # 旧独立脚本（保留）
│   ├── organizer.py          # 旧独立脚本（保留）
│   ├── reviewer.py           # 旧独立脚本（保留）
│   ├── state.py              # [新增] KBState TypedDict
│   ├── nodes.py              # [新增] 5 个 LangGraph 节点函数
│   └── graph.py              # [新增] build_graph() + decide_next
├── patterns/
│   ├── supervisor.py         # Worker-Supervisor 质量审核循环
│   └── router.py             # 基于意图分类的请求路由
├── knowledge/
│   ├── raw/
│   ├── analyzer_output/
│   └── articles/
├── LANGGRAPH_DESIGN.md       # [本文件]
├── ARCHITECTURE.md
├── AGENTS.md
└── requirements.txt          # [更新] 新增 langgraph
```

---

## 三、KBState 定义 (`workflows/state.py`)

使用 `TypedDict` 定义全局工作流状态，遵循"报告式通信"原则。

| 字段 | 类型 | 说明 |
|---|---|---|
| `sources` | `list[dict]` | 采集到的原始数据（结构化摘要，非完整响应体） |
| `analyses` | `list[dict]` | LLM 分析后的结构化报告 |
| `articles` | `list[dict]` | 格式化、去重后的知识条目，ready for review |
| `review_feedback` | `str` | 审核未通过时的改进建议（简体中文） |
| `review_passed` | `bool` | 审核是否通过四维度质量标准 |
| `iteration` | `int` | 当前审核循环轮次（0-2，上限 2） |
| `cost_tracker` | `dict` | 全流程 Token 用量累积报告 |

---

## 四、5 个节点函数 (`workflows/nodes.py`)

### 4.1 collect_node — 采集节点

- **输入**：无（修改 state.sources）
- **行为**：
  1. 用 `urllib.request` 调用 GitHub Search API，query 用 `urllib.parse.quote` 编码
  2. 用 `workflows.collector.fetch_rss_sources()` 采集 RSS 源
  3. 合并两类数据，写入 `state["sources"]`
- **输出**：`{"sources": [...], "cost_tracker": {...}}`
- **LLM 调用**: 无

### 4.2 analyze_node — 分析节点

- **输入**：`state.sources`
- **行为**：
  1. 遍历 sources，每条调用 `workflows.model_client.chat()` 生成中文摘要、标签、评分(0.0-1.0)
  2. System prompt 指导 LLM 输出 JSON: `{summary, tags, score}`
- **输出**：`{"analyses": [...], "cost_tracker": {...}}`

### 4.3 organize_node — 整理节点

- **输入**：`state.analyses`, `state.review_feedback`
- **行为**：
  1. **过滤**：移除 `score < 0.6` 的条目
  2. **去重**：按 `source_url` 去重（seen set）
  3. **修正**：如果 `review_feedback` 非空，用 LLM 逐条修正（注入 feedback 到 system prompt）
  4. **格式化**：转为 AGENTS.md 标准 article JSON 格式
- **输出**：`{"articles": [...], "cost_tracker": {...}}`

### 4.4 review_node — 审核节点

- **输入**：`state.articles`, `state.iteration`
- **行为**：
  1. **强制通过**：`iteration >= 2` → 直接 `review_passed=True`
  2. **四维度评分**（LLM 评估）：
     - 摘要质量 — 中文通畅性、合规性、三层结构
     - 标签准确 — 是否贴合内容、3-8 范围
     - 分类合理 — 是否属于 AI/LLM/Agent 领域
     - 一致性 — score 与 summary 质量匹配度
  3. 汇总：任一维度不通过则 `review_passed=False`
- **输出**：`{"review_passed": bool, "review_feedback": str, "iteration": int+1, "cost_tracker": {...}}`

### 4.5 save_node — 保存节点

- **输入**：`state.articles`
- **行为**：
  1. 创建 `knowledge/articles/` 目录
  2. 逐条写入 JSON 文件，命名：`{YYYYMMDD}-{source}-{slug}.json`
- **输出**：`{}`
- **LLM 调用**: 无

---

## 五、图定义 (`workflows/graph.py`)

```python
from langgraph.graph import StateGraph, END
from workflows.state import KBState
from workflows.nodes import (
    collect_node, analyze_node, organize_node,
    review_node, save_node,
)


def decide_next(state: KBState) -> str:
    """条件边：review 后分支。"""
    return "save" if state.get("review_passed") else "organize"


def build_graph():
    workflow = StateGraph(KBState)

    workflow.add_node("collect", collect_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("organize", organize_node)
    workflow.add_node("review", review_node)
    workflow.add_node("save", save_node)

    workflow.set_entry_point("collect")

    workflow.add_edge("collect", "analyze")
    workflow.add_edge("analyze", "organize")
    workflow.add_edge("organize", "review")

    workflow.add_conditional_edges(
        "review", decide_next,
        {"save": "save", "organize": "organize"},
    )
    workflow.add_edge("save", END)

    return workflow.compile()
```

---

## 六、图流转

```
START → collect_node → analyze_node → organize_node → review_node
                                              ↑              │
                                              │    False      │ True
                                              └──────────────┘
                                                              │
                                                         save_node → END
```

- **迭代上限**：`review_node` 在 `iteration >= 2` 时强制 `passed=True`，保证最多 2 次重试后必然终止
- **回退路径**：`review_passed=False` 不回到 analyze（避免每个条目重 LLM 分析），而是回到 organize（触发 LLM 按 feedback 修正）

---

## 七、需求核对清单

| # | 需求 | 状态 |
|---|---|---|
| 1 | 使用 `langgraph.graph` 的 `StateGraph`, `END` | ✅ |
| 2 | 导入 `workflows/nodes.py` 的 5 个节点函数 | ✅ |
| 3 | 导入 `workflows/state.py` 的 `KBState` | ✅ |
| 4 | 线性边: `collect → analyze → organize → review` | ✅ |
| 5 | 条件边: `True → save → END`, `False → organize` | ✅ |
| 6 | 入口点: `collect` | ✅ |
| 7 | `build_graph()` 返回编译后的 app | ✅ |
| 8 | RSS 源保留 | ✅ |
| 9 | 评分尺度: 0.0-1.0（<0.6 过滤） | ✅ |

---

## 八、文件变更清单

| 文件 | 操作 |
|---|---|
| `workflows/state.py` | 新建 — KBState TypedDict |
| `workflows/nodes.py` | 新建 — 5 个节点函数 |
| `workflows/graph.py` | 新建 — build_graph() |
| `requirements.txt` | 更新 — 新增 `langgraph>=0.3.0` |
| `LANGGRAPH_DESIGN.md` | 本文件 |
