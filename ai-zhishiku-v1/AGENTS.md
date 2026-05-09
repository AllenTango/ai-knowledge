# AGENTS.md

## 项目概述

AI 知识库助手（ai-zhishiku）是一套自动化知识采集与分发系统。系统每日从 GitHub Trending 和 Hacker News 中自动抓取 AI / LLM / Agent 领域的技术动态，通过 AI 模型对内容进行分析、摘要、结构化处理后存入本地 JSON 知识库，最终经由 Telegram、飞书、微信、QQ 等多渠道 IM 工具分发给订阅用户。同时提供一套基于 Dracula 暗黑主题的人工审核看板页面，供编辑人员对入库内容进行复核与修正。

---

## 技术栈

| 层次     | 选型                                        |
| -------- | ------------------------------------------- |
| 语言     | Python 3.12                                 |
| 编排引擎 | [OpenCode](https://github.com/anomalyco/opencode) + 国产大模型 |
| 工作流   | [LangGraph](https://github.com/langchain-ai/langgraph)       |
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
ai-zhishiku/
├── .opencode/
│   ├── agents/                # Agent 定义文件
│   │   ├── collector.md       # 采集 Agent —— 从 GitHub Trending / HN 抓取数据
│   │   ├── analyzer.md        # 分析 Agent —— AI 摘要、标签、评分
│   │   └── organizer.md       # 整理 Agent —— 结构化存储、去重、分发触发
│   └── skills/                # Skill 定义（可选）
│       └── distribution.md    # 多渠道分发 skill
├── knowledge/
│   ├── raw/                   # 原始抓取数据（临时）
│   └── articles/              # 分析后的结构化 JSON 知识条目
├── src/
│   ├── collector/             # 采集逻辑
│   ├── analyzer/              # 分析逻辑
│   ├── distributor/           # 分发逻辑
│   └── web/                   # Dracula 看板页面
├── config/
│   └── settings.yaml          # 全局配置
├── tests/
├── AGENTS.md                  # 本文件
└── README.md
```

---

## 知识条目 JSON 格式

每条知识以 JSON 文件存储在 `knowledge/articles/` 目录下：

```jsonc
{
  "id": "550e8400-e29b-41d4-a716-446655440000",                    // 唯一标识符（UUID，排除碰撞）
  "title": "LangChain v0.3 发布",       // 中文标题
  "source": "github",                   // 来源：github | hackernews
  "source_url": "https://github.com/langchain-ai/langchain/releases/tag/v0.3.0",
  "fetched_at": "2026-05-08T02:00:00Z", // 抓取时间（ISO 8601）
  "analyzed_at": "2026-05-08T02:05:00Z",// 分析完成时间（ISO 8601）
  "summary": "LangChain 发布 v0.3，重点改进了…", // AI 生成的中文摘要（50~200 字）
  "tags": ["langchain", "release", "llm-framework"], // 标签列表
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

## 内容规范

### 领域范围

仅收录与以下主题直接相关的条目：

| 类别     | 关键词示例                                                     |
| -------- | -------------------------------------------------------------- |
| LLM      | 大语言模型、GPT、Claude、Gemini、Llama、Mistral、prompt engineering |
| Agent    | AI Agent、multi-agent、tool calling、function calling、RAG      |
| 框架工具 | LangChain、LlamaIndex、CrewAI、AutoGen、Dify、Coze             |
| 基础设施 | vector database、embedding、fine-tuning、GPU、inference         |
| 安全对齐 | AI safety、red teaming、RLHF、guardrails                        |

凡无法归入上述类别的内容，一律标记为 `rejected`，不得进入审核队列。

### 摘要规范

1. **语言** —— `summary` 字段必须为简体中文，禁止中英混杂，专有名词首次出现时需附中文译名。
2. **长度** —— 50~200 字，不得超出上限。
3. **结构** —— 从原文提取「是什么 / 为什么重要 / 与 AI 领域有何关联」三个层次，缺一则视为不合格。
4. **客观性** —— 不得使用「震惊」「颠覆」「炸裂」等情绪化表述，保持技术笔调。

### 标题规范

1. `title` 必须是中文，允许保留产品名/项目名的英文原文（如「LangChain v0.3 发布」）。
2. 标题需准确反映条目核心内容，不得使用 clickbait 句式。

### 标签规范

1. 每条条目不少于 3 个标签，不多于 8 个。
2. 标签统一使用小写英文，多个单词以连字符连接（如 `llm-framework`）。
3. 标签必须从以下维度覆盖：主题（如 `agent`）、技术栈（如 `langchain`）、类型（如 `release`、`tutorial`、`paper`）。

### 评分标准

`score` 由 AI 模型综合以下维度评定（0.0 ~ 10.0）：

| 维度       | 权重 | 说明                                   |
| ---------- | ---- | -------------------------------------- |
| 领域相关性 | 40%  | 是否与 AI/LLM/Agent 直接相关           |
| 信息密度   | 30%  | 技术干货程度，是否具备可操作性         |
| 时效性     | 20%  | 是否为近期（7 日内）动态               |
| 来源权威性 | 10%  | 来源是否为知名项目/机构/作者           |

- `score >= 7.0` 可进入审核队列。
- `score < 5.0` 自动标记为 `rejected`。
- `5.0 <= score < 7.0` 保留为 `pending_review` 但降低优先级。

### 去重规则

1. 以 `source_url` 为唯一去重键，同一 URL 在 48 小时内不得重复入库。
2. 若同主题有多个来源报道，优先保留信息量最大的条目，其余作为「相关参考」链接附加到主条目的 `tags` 扩展字段中。

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
