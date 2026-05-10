# ai-zhishiku-v3 多 Agent 架构调整方案

## 一、调整目标

从 v2 的**单体线性流水线**（`pipeline.py` 中 `step1→step2→step3→step4`）迁移为**多 Agent 协同模式**，每个 Agent 拥有独立的 Python 脚本和 CLI 入口，通过 Supervisor 编排调度。

---

## 二、目录结构目标

```
ai-zhishiku-v3/
├── patterns/
│   ├── __init__.py
│   ├── supervisor.py       # 编排监督 Agent（主入口）
│   └── router.py           # 基于意图分类的请求路由
│
├── workflows/
│   ├── __init__.py
│   ├── model_client.py     # LLM 统一客户端（从 pipeline/ 搬移）
│   ├── collector.py        # 采集 Agent
│   ├── analyzer.py         # 分析 Agent
│   ├── organizer.py        # 整理 Agent
│   └── reviewer.py         # 审核 Agent
│
├── pipeline/
│   └── model_client.py     # 转发层 → from workflows.model_client import *
│
├── knowledge/
│   ├── raw/                # 原始采集数据（Collector 写入）
│   ├── analyzer_output/    # 分析结果（Analyzer 写入）
│   └── articles/           # 知识条目（Organizer 写入）
│
├── .opencode/
│   └── agents/             # Agent Markdown 定义
│       ├── collector.md
│       ├── analyzer.md
│       ├── organizer.md
│       ├── reviewer.md
│       └── supervisor.md
│
├── scheduler/
│   └── run_pipeline.ps1    # 改为调用 patterns/supervisor.py
│
├── logs/
├── AGENTS.md
├── ARCHITECTURE.md
├── opencode.json
├── mcp_knowledge_server.py
└── requirements.txt
```

---

## 三、各文件职责

### 3.1 `workflows/` — 子 Agent 实现

| 文件 | 来源 | 职责 |
|---|---|---|
| `model_client.py` | 原 `pipeline/model_client.py` 搬移 | LLM 统一客户端（ProviderFactory、chat_with_retry、CostTracker） |
| `collector.py` | 从 `pipeline.py` 提取采集函数 | 从 GitHub / RSS 采集数据，写入 `knowledge/raw/` |
| `analyzer.py` | 从 `pipeline.py` 提取分析函数 | 读取 `raw/`，调 LLM 分析，写入 `analyzer_output/` |
| `organizer.py` | 从 `pipeline.py` 提取整理函数 | 读取 `analyzer_output/`，去重校验后写入 `articles/` |
| `reviewer.py` | **全新实现**，基于 `reviewer.md` 5 维评分标准 | 审核 articles 中 `pending_review` 条目，修改 `status` |

每个文件都提供：
- 可供其它模块 `import` 的导出函数
- 独立的 `if __name__ == "__main__"` CLI 入口
- 支持 `--help` 查看参数

### 3.2 `patterns/` — 编排与路由

| 文件 | 职责 |
|---|---|
| `supervisor.py` | Worker-Supervisor 质量审核循环：Worker 执行任务 → Supervisor 评分 → 重试循环 |
| `router.py` | 基于意图分类的请求路由：`classify_intent()` 判定用户意图 → `route()` 分发到对应模块 |

### 3.3 `pipeline/model_client.py`

转发层，保持向后兼容：
```python
from workflows.model_client import (
    chat_with_retry, chat, chat_json, tracker, ...
)
```

---

## 四、Worker-Supervisor 审核循环

### 4.1 流程

```
supervisor(task, max_retries=3)
  │
  ├─ round = 1
  │
  ├─ 1. Worker Agent
  │    └─ chat(system=WORKER_PROMPT, prompt=task) → output (JSON)
  │
  ├─ 2. Supervisor Agent（评分）
  │    └─ chat(system=SUPERVISOR_PROMPT, prompt=task + output)
  │       → {"passed": bool, "score": int, "feedback": str}
  │
  ├─ 3. 判断
  │    ├─ score >= 21（即 7×3）→ passed, 返回结果
  │    ├─ round < max_retries → round++, 带 feedback 重做（回到步骤 1）
  │    └─ round >= max_retries → 强制返回 + warning
  │
  └─ 返回: {"output": str, "attempts": int, "final_score": int, "warning": str}
```

### 4.2 评分维度

| 维度 | 范围 | 说明 |
|---|---|---|
| 准确性 | 1-10 | 回答是否准确、可靠、基于事实 |
| 深度 | 1-10 | 分析是否深入、全面、有洞察 |
| 格式 | 1-10 | JSON 格式是否规范、字段完整、结构清晰 |
| **总分** | **3-30** | **通过线: >= 21（平均 7/维度）** |

### 4.3 重试逻辑

| 条件 | 行为 |
|---|---|
| score >= 21 | 通过，返回结果 |
| score < 21 且 round <= max_retries | 将 Supervisor 的 feedback 附加到 Worker 提示词中，重新生成 |
| round > max_retries | 强制返回当前输出 + warning 标记 |

---

## 五、数据传递约定

| 阶段 | 输入 | 输出 |
|---|---|---|
| Collector | 外部 API / 网页 | `knowledge/raw/{source}-{date}.json` |
| Analyzer | `knowledge/raw/` | `knowledge/analyzer_output/{source}-analyzed-{date}.json` |
| Organizer | `knowledge/analyzer_output/` | `knowledge/articles/{date}-{source}-{slug}.json` |
| Reviewer | `knowledge/articles/` | 直接修改 articles 中条目的 `status`、`reviewer`、`reviewed_at`、`retry_count` |

---

## 六、reviewer.py 审核标准（全新实现）

### 5 维评分（满分 100）

| 维度 | 满分 | 规则 |
|---|---|---|
| 摘要质量 | 25 | ≥50 字满分，≥20 字得 15 分，含技术关键词 +5 |
| 技术深度 | 25 | score × 2.5 |
| 格式规范 | 20 | id/title/source_url/status/timestamp 各 4 分 |
| 标签精度 | 15 | 1-3 个标签满分，4-5 个得 10 分，≥6 个得 5 分 |
| 空洞词检测 | 15 | 不含黑名单词汇满分，否则 0 分 |

### 等级与判定

| 等级 | 总分 | 判定 |
|---|---|---|
| A | ≥80 | approved |
| B | ≥60 | approved（无问题）或 retry（有可修正问题） |
| C | <60 | retry（retry_count<3）或 rejected+human_needed（≥3） |

### 空洞词黑名单

中文：赋能、抓手、闭环、打通、全链路、底层逻辑、颗粒度、对齐、拉通、沉淀、强大的、革命性的
英文：groundbreaking、revolutionary、game-changing、cutting-edge

---

## 七、`patterns/router.py` — 基于意图分类的请求路由

### 7.1 需求

1. **两层意图分类策略**：
   - 第一层：关键词快速匹配（零成本，不调 LLM）
   - 第二层：LLM 分类兜底（处理模糊意图）
2. **三种意图**：`github_search` / `knowledge_query` / `general_chat`
3. **每种意图对应一个处理器函数**
4. **`github_search`**：调用 GitHub Search API（`urllib.request`）；query 参数必须用 `urllib.parse.quote` 编码（处理中文与空格）
5. **`knowledge_query`**：从本地 `knowledge/articles/index.json` 检索
6. **`general_chat`**：调用 LLM 直接回答（调用 `workflows/model_client.py` 的 `chat()` 函数）
7. **统一入口函数**：`route(query: str) -> str`
8. **包含 `if __name__ == "__main__"` 测试入口**

### 7.2 依赖

使用 `workflows/model_client.py` 的 `chat()` 和 `chat_json()` 函数：
- `chat(messages, system, provider_name) -> (text, usage)` — 返回响应文本和用量
- `chat_json(messages, system, provider_name) -> (dict, usage)` — 返回解析后的 JSON 对象和用量

### 7.3 两层分类逻辑

```
route(query)
  │
  ├─ 第一层：关键词快速匹配
  │   ├─ 命中 github / repo / 仓库 / 项目 → intent = github_search
  │   ├─ 命中 article / 文章 / 知识 / 检索 → intent = knowledge_query
  │   └─ 未明确命中 → 进入第二层
  │
  └─ 第二层：LLM 分类兜底
      └─ chat_json(system_prompt, query) → 返回意图类型
```

### 7.4 关键词匹配表

| 意图 | 关键词（小写匹配） |
|---|---|
| `github_search` | `github`, `repo`, `仓库`, `项目`, `开源`, `repository`, `trending` |
| `knowledge_query` | `知识`, `文章`, `检索`, `搜索`, `查找`, `article`, `search`, `find`, `query` |

未命中任何关键词 → 走 LLM 分类。

### 7.5 三种处理器

| 处理器 | 输入 | 行为 |
|---|---|---|
| `handle_github_search(query)` | 用户原始 query | 用 `urllib.request` 调用 `https://api.github.com/search/repositories`，query 用 `urllib.parse.quote` 编码，返回格式化结果 |
| `handle_knowledge_query(query)` | 用户原始 query | 读取 `knowledge/articles/index.json`，检索 title/summary/tags 字段含关键词的条目，返回格式化结果 |
| `handle_general_chat(query)` | 用户原始 query | 调用 `chat()` 直接回答用户 |

---

## 八、文件变更清单

### 已完成文件

| # | 文件 | 状态 |
|---|---|---|
| 1 | `workflows/__init__.py` | ✅ |
| 2 | `workflows/model_client.py`（含 `chat()` / `chat_json()`） | ✅ |
| 3 | `patterns/__init__.py` | ✅ |
| 4 | `patterns/router.py` | ✅ |
| 5 | `pipeline/model_client.py`（转发层） | ✅ |
| 6 | `knowledge/articles/index.json` | ✅ |
| 7 | `ARCHITECTURE.md`（本文件，持续更新） | ✅ |

### 待完成

| # | 文件 | 说明 |
|---|---|---|
| 8 | `patterns/supervisor.py` | Worker-Supervisor 质量审核循环 |
| 9 | `workflows/collector.py` | 从 `pipeline.py` 提取采集逻辑 |
| 10 | `workflows/analyzer.py` | 从 `pipeline.py` 提取分析逻辑 |
| 11 | `workflows/organizer.py` | 从 `pipeline.py` 提取整理逻辑 |
| 12 | `workflows/reviewer.py` | 全新实现 5 维审核 |
| 13 | 删除 `pipeline/pipeline.py` | 单体流水线废弃 |
| 14 | 更新 `scheduler/run_pipeline.ps1` | 指向 supervisor |
| 15 | 更新 `.opencode/agents/*.md` (×5) | 添加脚本调用指引 |
| 16 | 更新 `AGENTS.md` | 反映 v3 目录结构 |
