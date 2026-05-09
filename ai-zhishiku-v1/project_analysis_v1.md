# AI 知识库助手（ai-zhishiku）项目分析报告

## 一、当前版本目录结构

```
ai-zhishiku/
├── AGENTS.md                    # 项目定义文档
├── .opencode/
│   ├── agents/                  # Agent 定义（5个）
│   │   ├── collector.md         # 采集 Agent
│   │   ├── analyzer.md          # 分析 Agent
│   │   ├── organizer.md          # 整理 Agent
│   │   ├── reviewer.md           # 审核 Agent
│   │   └── supervisor.md        # 编排监督 Agent
│   ├── skills/                  # Skill 定义（2个）
│   │   ├── github-trending/     # GitHub 采集技能
│   │   └── tech-summary/        # 技术分析技能
│   └── package.json             # OpenCode 配置
└── knowledge/                   # 数据存储
    ├── raw/                     # 原始采集数据
    ├── analyzer_output/         # 分析输出
    └── articles/                # 知识条目（待审核）
```

---

## 二、整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      Supervisor Agent                           │
│                    (编排监督，调度子 Agent)                       │
└─────────────────────────────────────────────────────────────────┘
         ↓           ↓           ↓           ↓
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Collector│  │ Analyzer │  │Organizer │  │ Reviewer │
│  采集     │→ │  分析     │→ │  整理     │→ │  审核    │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
     ↓            ↓            ↓            ↓
  raw/     analyzer_    articles/   pending_review
           output/
```

### 2.2 Agent 职责

| Agent | 职责 | 核心能力 |
|-------|------|----------|
| Supervisor | 编排调度 | Task 调用子 Agent，管理重试循环 |
| Collector | 采集数据 | 抓取 GitHub Trending / Hacker News |
| Analyzer | 分析内容 | 生成摘要、评分、标签 |
| Organizer | 整理入库 | 去重、格式化、状态判定 |
| Reviewer | 质量审核 | AI 审核、重试标记、人工升级 |

### 2.3 数据流

```
外部数据源 → collector → raw/
                         ↓
                   analyzer → analyzer_output/
                         ↓
                   organizer → articles/
                         ↓
                   reviewer → 审核结果
                         ↓
                   distributor → 发布到 IM 渠道
```

---

## 三、四部分之间的关系

### 3.1 关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                         AGENTS.md                               │
│                    (项目总纲，定义规范)                           │
│  • 知识条目 JSON 格式                                            │
│  • 状态流转规则                                                  │
│  • 内容规范（领域范围、摘要规范、标签规范、评分标准）                │
│  • Agent 角色概览                                                │
└─────────────────────────────────────────────────────────────────┘
         ↑                                      ↓
         │      ┌───────────────────────────────┘
         │      ↓
┌────────┴─────────────────────────────────────────┐
│                    .opencode/                     │
├─────────────────────┬─────────────────────────────┤
│      agents/        │         skills/             │
│  (Agent 角色定义)    │   (Skill 具体步骤)          │
│                     │                             │
│ • collector.md      │ • github-trending/         │
│ • analyzer.md       │   └── SKILL.md             │
│ • organizer.md      │ • tech-summary/            │
│ • reviewer.md       │   └── SKILL.md             │
│ • supervisor.md     │                             │
└─────────────────────┴─────────────────────────────┘
         ↑                      ↑
         │      ┌───────────────┘
         ↓      ↓
┌─────────────────────────────────────────────────────┐
│                     knowledge/                      │
│                  (数据存储目录)                       │
│  • raw/           - 原始采集数据                    │
│  • analyzer_output/ - 分析输出 (临时)              │
│  • articles/      - 知识条目 (待审核)              │
└─────────────────────────────────────────────────────┘
```

### 3.2 各部分职责

| 部分 | 职责 | 定义内容 |
|------|------|----------|
| **AGENTS.md** | 项目总纲 | JSON 格式规范、状态流转、内容标准、Agent 概览 |
| **.opencode/agents/** | Agent 角色 | 权限模型、工作流程、输出格式、质量标准 |
| **.opencode/skills/** | Skill 步骤 | 执行步骤、注意事项、输出格式 |
| **knowledge/** | 数据存储 | 目录结构、文件格式、流转状态 |

### 3.3 约束关系

```
AGENTS.md (规范)
    ↑
    ├── 定义 → .opencode/agents/ (Agent 角色)
    │           └── 权限模型必须符合 AGENTS.md 的安全要求
    │
    ├── 定义 → .opencode/skills/ (Skill 步骤)
    │           └── 输出路径必须与 Agent 规范一致
    │
    └── 定义 → knowledge/ (数据格式)
                └── JSON 字段必须符合 AGENTS.md 的格式标准
```

---

## 四、关键规范

### 4.1 数据流规范

| 阶段 | 输入 | 输出 | 目录 |
|------|------|------|------|
| 采集 | 外部数据源 | 原始数据 | knowledge/raw/ |
| 分析 | raw/ | 分析结果 | knowledge/analyzer_output/ |
| 整理 | analyzer_output/ | 知识条目 | knowledge/articles/ |
| 审核 | articles/ | 审核结果 | 修改 articles/ 条目 |

### 4.2 知识条目 JSON 格式

```json
{
  "id": "UUID",
  "title": "中文标题",
  "source": "github|hackernews",
  "source_url": "https://...",
  "fetched_at": "ISO 8601",
  "analyzed_at": "ISO 8601",
  "summary": "简体中文 50~200字",
  "tags": ["tag1", "tag2"],
  "status": "pending_review|approved|rejected|published",
  "score": 0.0~10.0,
  "reviewer": null|"reviewer-agent"|"human_needed",
  "reviewed_at": null|"ISO 8601",
  "published_to": [],
  "retry_count": 0
}
```

### 4.3 状态流转

```
pending_review ──▶ approved ──▶ published
    │                  │
    ├── retry (重试) ◀─┘
    │         (retry_count < 3)
    │
    └── rejected ◀─────┘
         (retry_count >= 3 或安全红线)
```

---

## 五、Skill 与 Agent 配合机制

### 5.1 触发流程

```
用户需求 → 语义匹配 Skill (description) → 加载 Agent (权限约束)
           → 执行 Skill 步骤 (allowed-tools)
```

### 5.2 权限约束

| Skill | 允许工具 | 对应 Agent |
|-------|----------|------------|
| github-trending | Read/Glob/WebFetch/Grep | collector |
| tech-summary | Read/Glob/WebFetch/Grep | analyzer |

---

## 六、当前数据状态

| 目录 | 文件数 | 说明 |
|------|--------|------|
| knowledge/raw/ | 1 | github-trending-2026-05-09.json |
| knowledge/analyzer_output/ | 1 | 20260509-analyzed.json |
| knowledge/articles/ | 15 | 待审核的知识条目 |

---

## 七、版本信息

- **版本**: v1.0
- **最后更新**: 2026-05-09
- **Agent 数量**: 5
- **Skill 数量**: 2