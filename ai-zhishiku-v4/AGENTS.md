# AGENTS.md

## 项目概述

AI 知识库助手（ai-zhishiku-v4）是一套自动化知识采集与分发系统。系统每日从 GitHub Trending 和 Hacker News 中自动抓取 AI / LLM / Agent 领域的技术动态，通过 AI 模型对内容进行分析、摘要、结构化处理后存入本地 JSON 知识库，最终经由 Telegram、飞书、微信、QQ 等多渠道 IM 工具分发给订阅用户。同时提供一套基于 Dracula 暗黑主题的人工审核看板页面，供编辑人员对入库内容进行复核与修正。

---

## 技术栈

| 层次     | 选型                                        |
| -------- | ------------------------------------------- |
| 语言     | Python 3.10                                 |
| 编排引擎 | [OpenCode](https://github.com/anomalyco/opencode) + 国产大模型 |
| 工作流   | [LangGraph](https://github.com/langchain-ai/langgraph) + 自研 Pipeline |
| 多渠道分发 | [OpenClaw](https://github.com/anomalyco/openclaw)            |
| 前端看板 | 自建 Dracula 暗黑主题页面                    |
| 数据格式 | JSON                                        |

---

## 编码规范

1. **PEP 8** —— 所有 Python 代码必须符合 [PEP 8](https://peps.python.org/pep-0008/) 风格。
2. **snake_case** —— 变量、函数、方法、模块名统一使用 `snake_case`；类名使用 `PascalCase`。
3. **Google 风格 docstring（中文）** —— 所有公开函数/类必须编写 docstring，格式遵循 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)，内容是中文。示例：

   ```python
   def fetch_trending(source: str, limit: int = 20) -> list[dict]:
       """从指定源抓取热门条目。

       Args:
           source: 数据源名称，可选 "github" | "hackernews"。
           limit: 最大抓取条数，默认 20。

       Returns:
           包含原始条目的列表，每个条目为 dict。
       """
   ```

4. **禁止裸 `print()`** —— 所有输出必须通过 `logging` 模块完成，不得在代码中使用裸 `print()` 语句。
5. **类型注解** —— 公共函数签名必须包含完整的类型注解。
6. **禁止一次性导入 `*`** —— 禁止使用 `from module import *`。

---

## 项目结构

```
ai-zhishiku-v4/
├── workflows/                      # LangGraph 工作流节点实现
│   ├── __init__.py
│   ├── state.py                   # KBState 状态定义（TypedDict）
│   ├── graph.py                   # LangGraph 图定义与条件边
│   └── nodes.py                   # 节点函数（planner/collect/analyze/organize/review/revise/save/human_flag_node）
│                                   # 注意：LLM 客户端位于 scripts/model_client.py
├── pipeline/                       # Pipeline 工作流（独立顺序脚本）
│   ├── pipeline.py                # 四步流水线主脚本（采集→分析→整理→保存）
│   └── rss_sources.yaml           # RSS 订阅源配置
│                                   # 注意：无独立 model_client.py，调用 scripts/model_client.py
├── patterns/                       # OpenCode patterns
│   ├── __init__.py
│   ├── supervisor.py              # Worker-Supervisor 质量审核循环
│   └── router.py                  # 基于意图分类的请求路由
├── .opencode/                      # OpenCode 配置
│   ├── agents/                     # OpenCode Agent 定义文件
│   │   ├── collector.md           # 采集 Agent
│   │   ├── analyzer.md            # 分析 Agent
│   │   ├── organizer.md           # 整理 Agent
│   │   ├── reviewer.md            # 审核 Agent
│   │   └── supervisor.md          # 编排监督 Agent
│   └── skills/                     # OpenCode Skills 定义
│       ├── github-trending/        # GitHub Trending 采集技能
│       └── tech-summary/           # 技术内容深度分析技能
├── hooks/                          # 质量检查钩子
│   ├── check_quality.py           # 5 维度质量评分工具
│   ├── validate_json.py           # JSON 格式校验工具
│   └── preflight_checklist.py     # 上线前全面检查（API KEY/权限/备份/成本/GitHub Actions 等）
├── scripts/                        # 辅助脚本（核心业务逻辑）
│   ├── collector.py               # 数据采集（GitHub/RSS）
│   ├── analyzer.py                # AI 分析（过滤/评分）
│   ├── organizer.py               # 数据整理（去重/格式化）
│   ├── reviewer.py               # 审核评分（空洞词/摘要质量）
│   ├── model_client.py            # LLM 统一客户端（所有工作流共用）
│   ├── cost_guard.py              # 成本守卫（限制单次/累计成本）
│   ├── security.py               # 安全工具（sanitize_input/filter_output）
│   ├── daily_digest.py            # 简报推送脚本（支持 --date/--dry-run/--force）
│   └── mcp_http_server.py         # MCP HTTP API 服务器（FastAPI + uvicorn）
├── scheduler/                      # 定时调度脚本
│   ├── run_pipeline.sh            # Linux/Mac 调度脚本
│   ├── daily_digest_cron.sh       # 每日简报推送（每天 09:00）
│   └── crontab.txt                # crontab 配置示例
├── distribution/                    # 分发渠道
│   ├── __init__.py
│   ├── formatter.py               # 内容格式化
│   └── publisher.py               # 发布执行（OpenClaw/Telegram/飞书）
├── bot/                            # 机器人模块
│   ├── __init__.py
│   └── knowledge_bot.py          # 知识库交互机器人（搜索/订阅/权限）
├── daily_digest.py                 # 每日摘要生成
├── docker/                        # Docker 容器配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── crontab.txt
│   └── docker-entrypoint.sh
├── reports/                       # 检查报告（preflight-*.json）
├── .github/workflows/             # GitHub Actions
│   └── daily-collect.yml          # 每日自动采集工作流
├── knowledge/                      # 知识库存储
│   ├── raw/                       # 原始采集数据
│   ├── analyzer_output/           # AI 分析结果
│   ├── articles/                  # 知识条目（最终入库）
│   └── human_review/              # 需人工审核的条目
├── tests/                          # 测试与评估
│   └── eval_test.py               # 评估测试（含 judge_score）
│                                   # 注意：cost_guard.py 和 security.py 在 scripts/ 下
├── .openclaw/                      # 小芽的家（身份文件）
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── IDENTITY.md
│   ├── USER.md
│   ├── HEARTBEAT.md
│   ├── TOOLS.md
│   ├── memory/
│   └── workspace-state.json
├── mcp_knowledge_server.py        # MCP 知识库服务器（JSON-RPC over stdio）
├── opencode.json                  # OpenCode 配置
├── requirements.txt               # Python 依赖
├── .env                           # 环境变量（API Key 等）
└── AGENTS.md                      # 本文件
```

---

## 工作流架构

本项目包含**三种独立的工作流**，可根据场景选择：

### 1. Pipeline 工作流（推荐用于定时采集）

顺序执行，适合定时任务：

```
采集（GitHub/RSS）→ 分析（LLM）→ 整理（去重/格式化）→ 保存（JSON）
```

**使用方式：**
```bash
export PYTHONPATH=$(pwd)
python3 pipeline/pipeline.py --sources github,rss --limit 20 --verbose
```

或使用 scheduler 脚本：
```bash
bash scheduler/run_pipeline.sh --sources github,rss --limit 20
```

### 2. LangGraph 工作流（支持审核循环）

状态机图，支持 AI 审核和重试：

```
planner → collect → analyze → organize → review
                                          │
                          route_after_review:
                            - review_passed=True → save → END
                            - review_passed=False & iteration<max → revise → review
                            - review_passed=False & iteration>=max → human_flag_node → END
```

**使用方式：**
```python
from workflows.graph import build_graph
g = build_graph()
result = g.invoke(initial_state)
```

### 3. OpenCode sub-agent 流程（Agent 协作）

基于 OpenCode 的多 Agent 协作，通过 `.opencode/agents/` 目录下的 markdown 定义文件驱动：

- collector.md → 采集 Agent
- analyzer.md → 分析 Agent
- organizer.md → 整理 Agent
- reviewer.md → 审核 Agent
- supervisor.md → 编排监督 Agent

**注意**：运行此流程需要安装 opencode CLI。配置文件（opencode.json, .opencode/agents/*.md）已就绪。

---

## 知识条目 JSON 格式

每条知识以 JSON 文件存储在 `knowledge/articles/` 目录下：

```jsonc
{
  "id": "550e8400-e29b-41d4-a716-446655440000",                    // 唯一标识符（UUID，排除碰撞）
  "title": "LangChain v0.3 发布",       // 中文标题
  "source": "github",                   // 来源：github | rss
  "source_url": "https://github.com/langchain-ai/langchain/releases/tag/v0.3.0",
  "fetched_at": "2026-05-08T02:00:00Z", // 抓取时间（ISO 8601）
  "analyzed_at": "2026-05-08T02:05:00Z",// 分析完成时间（ISO 8601）
  "summary": "LangChain 发布 v0.3，重点改进了…", // AI 生成的中文摘要（50~200 字）
  "tags": ["langchain", "release", "llm-framework"], // 标签列表（3~8个）
  "status": "pending_review",           // 状态：pending_review | approved | rejected | published
  "score": 8.5,                         // AI 相关性评分（0.0 ~ 10.0）
  "reviewer": null,                     // 审核人（人工审核后填充）
  "reviewed_at": null,                  // 审核时间
  "published_to": [],                   // 已分发渠道列表，如 ["telegram", "feishu"]
  "retry_count": 0                      // 审核重试次数，初始为 0，≥3 需人工审核
}
```

### 状态流转

```
pending_review ──▶ approved ──▶ published
    │                  │
    └──────▶ rejected ◀┘
```

- `pending_review` —— AI 分析完毕，等待人工审核。
- `approved` —— 人工审核通过，加入分发队列。
- `rejected` —— 人工审核驳回（不相关 / 低质量）。
- `published` —— 已分发至目标渠道。

---

## 数据标准（评分与审核）

### 评分标准

`score` 由 AI 模型综合以下维度评定（**统一为 0.0 ~ 10.0**，所有工作流一致）：

| 维度       | 权重 | 说明                                   |
| ---------- | ---- | -------------------------------------- |
| 领域相关性 | 40%  | 是否与 AI/LLM/Agent 直接相关           |
| 信息密度   | 30%  | 技术干货程度，是否具备可操作性         |
| 时效性     | 20%  | 是否为近期（7 日内）动态               |
| 来源权威性 | 10%  | 来源是否为知名项目/机构/作者           |

- `score >= 7.0` 可进入审核队列。
- `score < 5.0` 自动标记为 `rejected`。
- `5.0 <= score < 7.0` 保留为 `pending_review` 但降低优先级。

### 审核标准

**Pipeline 工作流**：无自动审核，所有条目直接进入 `pending_review`，依赖人工审核。

**LangGraph 工作流**：5 维度加权评分自动审核：

| 维度             | 权重 | 说明                           |
| ---------------- | ---- | ------------------------------ |
| technical_depth  | 30%  | 技术深度与专业性               |
| relevance        | 25%  | 与 AI 领域的相关程度           |
| originality      | 20%  | 原创性与独特见解               |
| clarity          | 15%  | 表达清晰度与可读性             |
| utility          | 10%  | 实用价值与可操作性             |

- 审核循环最多 `max_iterations` 次（默认 2）
- `review_passed=True` → 直接保存
- `review_passed=False & iteration<max` → `revise_node` 修正后重新审核
- `review_passed=False & iteration>=max` → `human_flag_node` 人工标记

### 去重规则

1. 以 `source_url` 为唯一去重键，同一 URL 在 48 小时内不得重复入库。
2. 若同主题有多个来源报道，优先保留信息量最大的条目，其余作为「相关参考」链接附加到主条目的 `tags` 扩展字段中。

---

## 内容规范

### 领域范围

仅收录与以下主题直接相关的条目：

| 类别     | 关键词示例                                                     |
| -------- | -------------------------------------------------------------- |
| LLM      | 大语言模型、GPT、Claude、Gemini、Llama、Mistral、prompt engineering |
| Agent    | AI Agent、multi-agent、tool calling、function calling、RAG      |
| 框架工具 | LangChain、LlamaIndex、CrewAI、AutoGen、Dify、Coze           |
| 基础设施 | vector database、embedding、fine-tuning、GPU、inference         |
| 安全对齐 | AI safety、red teaming、RLHF、guardrails                        |

凡无法归入上述类别的内容，一律标记为 `rejected`，不得进入审核队列。

### 摘要规范

1. **语言** —— `summary` 字段必须为简体中文，禁止中英混杂，专有名词首次出现时需附中文译名。
2. **长度** —— 50~200 字，不得超出上限。
3. **结构** —— 从原文提取「是什么 / 为什么重要 / 与 AI 领域有何关联」三个层次，缺一则视为不合格。
4. **客观性** —— 不得使用「赋能」「抓手」「闭环」「打通」「震惊」「颠覆」「炸裂」等空洞词或情绪化表述，保持技术笔调。

### 标题规范

1. `title` 必须是中文，允许保留产品名/项目名的英文原文（如「LangChain v0.3 发布」）。
2. 标题需准确反映条目核心内容，不得使用 clickbait 句式。

### 标签规范

1. 每条条目不少于 3 个标签，不多于 **8 个**。
2. 标签统一使用小写英文，多个单词以连字符连接（如 `llm-framework`）。
3. 标签必须从以下维度覆盖：主题（如 `agent`）、技术栈（如 `langchain`）、类型（如 `release`、`tutorial`、`paper`）。

---

## Agent 角色概览

| 角色         | 文件                     | 职责                                                                 | 触发方式        |
| ------------ | ------------------------ | -------------------------------------------------------------------- | --------------- |
| 采集 Agent   | `.opencode/agents/collector.md` | 从 GitHub Trending、Hacker News 抓取当日 AI/LLM/Agent 相关条目，去重后写入 `knowledge/raw/` | 定时 / 手动触发 |
| 分析 Agent   | `.opencode/agents/analyzer.md`  | 读取原始数据，调用 LLM 生成中文摘要、标签和相关性评分，输出结构化 JSON 到 `knowledge/analyzer_output/` | 采集完成后自动  |
| 整理 Agent   | `.opencode/agents/organizer.md` | 对 `knowledge/analyzer_output/` 中的条目进行去重、合并、归档，写入 `knowledge/articles/` | 分析完成后自动  |
| 审核 Agent   | `.opencode/agents/reviewer.md`  | 审核 articles 中 pending_review 条目，判定通过/驳回/重试；超 3 次重试标记人工审核 | 整理完成后自动  |
| 监督 Agent   | `.opencode/agents/supervisor.md` | 编排完整流水线，管理重试循环，调度子 Agent | 作为主入口触发   |

---

## 红线（绝对禁止的操作）

1. **禁止抓取与 AI/LLM/Agent 无关的内容** —— 采集 Agent 必须过滤非目标领域条目，不得浪费 token 与存储。
2. **禁止在未审核状态下直接发布** —— 所有知识条目必须先经过 `approved` 状态，严禁跳过人工审核直接发布到外部渠道。
3. **禁止输出英文摘要** —— 分析 Agent 输出的 `summary` 字段必须是中文，不得输出英文摘要或混合语言。
4. **禁止重复发布** —— 同一条目（以 `source_url` 去重）不得在 48 小时内重复推送到相同渠道。
5. **禁止硬编码 API Key / Token** —— 所有密钥、Token、Webhook 地址必须从 `config/settings.yaml` 或环境变量中读取，严禁硬编码在源代码中。
6. **禁止使用裸 `print()`** —— 见编码规范第 4 条。
7. **禁止在未确认来源可靠性的情况下分发内容** —— 涉及高风险安全漏洞或虚假信息的内容，必须先经人工二次确认后方可分发。

---

## 环境要求

- Python 3.10+
- 依赖：`pip install -r requirements.txt`
- 环境变量：`.env` 文件（参考 `env.example`）

### PYTHONPATH 配置

所有脚本依赖项目根目录的模块，运行时需要设置 PYTHONPATH：

```bash
export PYTHONPATH=$(pwd)
```

或使用 `PYTHONPATH=. python3 ...` 方式运行。

### MCP Knowledge Server

MCP 服务器通过 stdio 通信，用于 AI 工具调用知识库：

```bash
python3 mcp_knowledge_server.py
```

提供工具：search_articles, get_article, knowledge_stats

---
