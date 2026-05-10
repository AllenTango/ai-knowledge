---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能。该技能从 GitHub Trending 页面抓取当日热门项目，过滤 AI/LLM/Agent 相关内容，生成结构化 JSON 供后续分析使用。
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要从 GitHub Trending 抓取热门开源项目作为知识库素材时，使用此技能。该技能适用于：

- 每日定时采集任务
- 补充知识库中的开源项目信息
- 构建 AI/LLM/Agent 领域的技术动态库

## 执行步骤

### 第1步：搜索热门仓库

使用 GitHub API 或 WebFetch 访问 GitHub Trending 页面，获取当日热门仓库列表。

- API：`https://api.github.com/search/repositories?q=created:>${7daysago}&sort=stars&order=desc`
- 页面：`https://github.com/trending`

### 第2步：提取项目信息

从原始数据中提取每个仓库的以下信息：

- `name`：项目名称（owner/repo 格式）
- `url`：仓库主页 URL
- `description`：项目描述
- `stars`：星标数量
- `language`：主要编程语言
- `topics`：项目标签数组
- `created_at`：创建时间

### 第3步：过滤项目

根据知识库的内容规范进行过滤：

**纳入条件**（符合任一即纳入）：
- 主题属于 AI/LLM/Agent 领域
- 与大语言模型、Prompt Engineering、AI Agent、Multi-Agent、工具调用、RAG 相关
- 框架/工具类：LangChain、LlamaIndex、CrewAI、AutoGen、Dify、Coze 等
- 基础设施类：Vector Database、Embedding、Fine-tuning、GPU Inference

**排除条件**：
- Awesome 列表类（仅做资源聚合，无实际项目代码）
- 教程/文档类项目
- 与 AI 领域无关的热门项目
- Stars < 100（信息密度过低）

### 第4步：去重

检查待采集条目是否与知识库已有数据重复：

- 对比 `knowledge/articles/` 中 48 小时内的已有 `source_url`
- 对比 `knowledge/raw/` 中已采集的历史 URL
- 相同 URL 仅保留最新的一条

### 第5步：撰写中文摘要

每条项目需撰写 30~80 字的中文摘要，采用以下公式：

```
项目名 + 做什么 + 为什么值得关注
```

示例：
- **项目名**：LangChain
- **做什么**：开源的大语言模型应用开发框架
- **为什么值得关注**：提供了 Prompt 模板、Chain 机制、Agent 抽象等核心功能，是构建 LLM 应用的主流选择之一

### 第6步：排序取 Top 15

按 Stars 降序排列，选取前 15 条作为最终输出。

### 第7步：输出 JSON

将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`。

## 注意事项

1. **过滤准确性**：严格遵守领域范围，避免采集与 AI/LLM/Agent 无关的内容
2. **摘要质量**：摘要不得编造信息，必须基于项目的实际 description 和 README 内容
3. **去重完整性**：去重检查应覆盖 articles 和 raw 两个目录
4. **时效性**：仅采集当日 Trending，数据需包含 `collected_at` 时间戳
5. **语言一致性**：摘要必须为简体中文，项目名保留英文原文

## 输出格式

```json
{
  "source": "github-trending",
  "skill": "github-trending",
  "collected_at": "2026-05-09T02:00:00Z",
  "items": [
    {
      "name": "owner/repo-name",
      "url": "https://github.com/owner/repo-name",
      "summary": "中文摘要（30~80字）",
      "stars": 1234,
      "language": "Python",
      "topics": ["agent", "llm", "open-source"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| source | string | 数据源，固定为 `github-trending` |
| skill | string | 使用技能名，固定为 `github-trending` |
| collected_at | string | 采集时间，ISO 8601 格式 |
| items | array | 项目数组，最多 15 条 |
| name | string | 项目名称（owner/repo 格式） |
| url | string | 仓库主页 URL |
| summary | string | 中文摘要，30~80 字 |
| stars | number | 星标数量 |
| language | string | 主要编程语言 |
| topics | array | 项目标签数组 |