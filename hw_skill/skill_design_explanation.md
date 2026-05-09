# Skill 设计说明：github-trending 与 tech-summary 的关系

## 输入输出关系

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ github-trending     │     │ tech-summary        │     │   后续流程          │
│ (采集)              │     │ (分析)              │     │ (Organizer等)       │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│ 输入: GitHub API    │     │ 输入: knowledge/raw/│     │ 输入:               │
│       (外部数据)    │     │       采集文件      │     │   tech-summary     │
│                     │     │                     │     │   输出              │
│ 输出:               │ ──▶ │ 输出:               │ ──▶ │                     │
│ knowledge/raw/      │     │ knowledge/raw/      │     │                     │
│ github-trending-    │     │ tech-summary-       │     │                     │
│ YYYY-MM-DD.json     │     │ YYYY-MM-DD.json     │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### 数据流向

1. **github-trending**：从 GitHub API 抓取热门项目 → 输出原始采集数据到 `knowledge/raw/`
2. **tech-summary**：读取 `knowledge/raw/` 中的原始数据 → 深度分析 → 输出分析结果到 `knowledge/raw/`
3. **后续流程**：Organizer 读取 tech-summary 的输出，进行去重、入库等处理

---

## 为什么要拆成两个？

### 1. 职责分离

| Skill | 职责 |
|-------|------|
| github-trending | 只负责"抓"——从外部获取原始数据 |
| tech-summary | 只负责"分析"——对数据深度加工 |

两个 Skill 各司其职，不互相侵入边界。

### 2. 数据复用

`knowledge/raw/` 目录下可能存放多种采集源的数据：
- `github-trending-YYYY-MM-DD.json`（GitHub 热门）
- `hackernews-YYYY-MM-DD.json`（Hacker News）
- 其他自定义采集源

`tech-summary` 可以统一分析所有来源的数据，不局限于 GitHub：
- 输入：任意采集文件
- 输出：统一的分析结构

如果合并为一个 Skill，则只能用于 GitHub 数据，无法复用于其他来源。

### 3. 流程解耦

| 操作 | 频率 |
|------|------|
| github-trending 采集 | 每日 2 次（早/晚） |
| tech-summary 分析 | 每日 1 次（汇总分析） |

采集和分析可以独立调度，互不影响。

### 4. 输出可追溯

| 数据类型 | 存储位置 |
|----------|----------|
| 原始采集数据 | `knowledge/raw/github-trending-*.json` |
| 分析结果 | `knowledge/raw/tech-summary-*.json` |

分开存储的好处：
- 问题出在采集环节 → 回溯原始数据
- 问题出在分析环节 → 对比原始与分析结果

---

## 如果合并成一个会怎样？

合并为一个 Skill（如 `github-collection-and-analysis`）的问题：

| 问题 | 影响 |
|------|------|
| 复用性差 | 无法单独用于 Hacker News 或其他数据源 |
| 职责混乱 | 一个 Skill 既要抓数据又要分析，边界模糊 |
| 调试困难 | 问题出在采集还是分析？定位成本高 |
| 扩展性差 | 新增采集源需要改动 Skill 逻辑 |

---

## 结论

拆分成两个 Skill 更符合**职责单一、数据可复用、流程可组合**的设计原则。

| 设计原则 | 体现 |
|----------|------|
| 职责单一 | 采集和分析各自独立 |
| 数据可复用 | tech-summary 可分析任意采集源 |
| 流程可组合 | 两个 Skill 可独立调度，灵活组合 |