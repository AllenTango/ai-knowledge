---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能。该技能对 knowledge/raw/ 中的原始采集数据进行深度分析，生成中文摘要、技术亮点、相关性评分和标签建议，为知识库条目入库提供结构化输出。
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术内容深度分析技能

## 使用场景

当需要对采集的技术内容进行深度分析总结时使用此技能。该技能适用于：

- 分析 GitHub Trending 或 Hacker News 采集的原始数据
- 为知识库条目生成结构化的分析结果
- 发现技术趋势和新兴概念

## 执行步骤

### 第1步：读取采集文件

使用 Read / Glob 读取 `knowledge/raw/` 目录下当日最新的采集文件。

- 获取文件列表：`knowledge/raw/` 中以采集日期命名的 JSON 文件
- 读取内容：解析文件中的 items 数组

### 第2步：逐条深度分析

对每条内容进行以下维度的分析：

| 分析维度 | 输出要求 |
|----------|----------|
| 摘要 | 简体中文，不超过 50 字，概括核心信息 |
| 技术亮点 | 2~3 个，用事实说话，不得编造 |
| 评分 | 1~10 分，附评分理由 |
| 标签建议 | 3~8 个，小写英文连字符格式 |

### 第3步：趋势发现

分析完成后，进行整体趋势发现：

- **共同主题**：哪些主题在本次采集中出现频率最高？
- **新概念**：有哪些新兴技术或概念首次出现？
- **领域分布**：各条目在 LLM / Agent / 框架工具 / 基础设施 / 安全对齐 五大类别中的分布

### 第4步：输出分析结果

将分析结果写入 `knowledge/analyzer_output/{date}-analyzed.json`（与 analyzer agent 规范一致）。

> 注意：输出路径与 analyzer agent 规范保持一致，确保 organizer 能正确读取分析结果。

## 评分标准

| 分数段 | 含义 | 判定标准 |
|--------|------|----------|
| 9 ~ 10 | 改变格局 | 重大技术突破、行业标杆发布、可能重塑 AI 应用范式的进展 |
| 7 ~ 8 | 直接有帮助 | 新工具/框架/方法发布、高质量教程、可落地的最佳实践 |
| 5 ~ 6 | 值得了解 | 行业动态、增量更新、可扩展视野但非刚需 |
| 1 ~ 4 | 可略过 | 与 AI 关联弱、仅提及 AI 但无实质内容、营销帖或低信息密度内容 |

### 约束条件

- 单次分析项目数量：最多 15 个
- 高分项目（9~10 分）占比：不超过 2 个

## 注意事项

1. **事实依据**：技术亮点必须基于 WebFetch 获取的原始内容，用事实说话，不得编造
2. **评分一致性**：评分需有明确依据，9-10 分项应有行业影响或技术突破
3. **标签准确性**：标签应覆盖主题、技术栈、类型三个维度
4. **摘要简洁**：不超过 50 字，聚焦核心价值
5. **趋势洞察**：趋势发现应具有参考价值，非泛泛而谈

## 输出格式

```json
{
  "source": "tech-summary",
  "skill": "tech-summary",
  "analyzed_at": "2026-05-09T02:00:00Z",
  "total_items": 15,
  "score_distribution": {
    "high": 2,
    "medium": 8,
    "low": 5
  },
  "trends": {
    "common_themes": ["Agent", "多模态"],
    "new_concepts": ["self-evolving agent"]
  },
  "items": [
    {
      "name": "owner/repo-name or HN-title",
      "url": "https://...",
      "summary": "中文摘要（≤50字）",
      "highlights": [
        "技术亮点1（事实）",
        "技术亮点2（事实）"
      ],
      "score": 8,
      "score_reason": "评分理由",
      "tags": ["agent", "framework", "open-source"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| source | string | 数据源，固定为 `tech-summary` |
| skill | string | 使用技能名，固定为 `tech-summary` |
| analyzed_at | string | 分析时间，ISO 8601 格式 |
| total_items | number | 分析的项目总数 |
| score_distribution | object | 分数分布统计（high: 9-10, medium: 7-8, low: 5-6） |
| trends | object | 趋势发现（共同主题、新概念） |
| items | array | 分析结果数组 |
| name | string | 项目名称或 HN 标题 |
| url | string | 原始链接 |
| summary | string | 中文摘要，不超过 50 字 |
| highlights | array | 技术亮点数组，2~3 个 |
| score | number | 评分，1~10 |
| score_reason | string | 评分理由 |
| tags | array | 标签建议，3~8 个 |