# AI 知识库看板方案

> 规划时间：2026-05-12
> 项目：ai-knowledge

## 背景

系统每日从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域技术动态，经 AI 分析后存入本地 JSON 知识库。编辑人员需要一套基于 Dracula 暗黑主题的看板页面，对入库内容进行复核与修正。

---

## 需求

### 两个看板

| 看板 | 访问路径 | 权限 | 核心功能 |
|------|----------|------|----------|
| **公开看板** | `/` | 公开只读 | 仅显示 `status: approved` 条目，网格/列表视图，搜索筛选排序 |
| **审核看板** | `/static/review.html` | 内部编辑 | 4 列 Kanban 拖拽换状态，详情编辑，批量操作，人工审核队列 |

### 功能清单

- [x] 4 列 Kanban 看板（待审核 / 已批准 / 已驳回 / 已发布）
- [x] 拖拽卡片换列（SortableJS）
- [x] 文章详情查看与编辑（标题/摘要/标签/评分）
- [x] 批量选择与批量批准/驳回/发布
- [x] 数据统计概览（总条数、各状态数量、均分）
- [x] 搜索与多条件筛选（来源/评分/标签）
- [x] Human Review 队列处理（标记条目 → 正式条目）
- [x] Dracula 暗黑主题

---

## 技术架构

```
浏览器 (Static HTML/CSS/JS + SortableJS CDN)
    │
    ├─ GET  /                    → 302 → /static/index.html
    ├─ GET  /static/*            → FastAPI StaticFiles
    ├─ GET  /mcp/stats           → 现有（读）
    ├─ GET  /mcp/search          → 现有（读）
    ├─ GET  /mcp/articles/{id}   → 现有（读）
    └─ POST /mcp/tools           → 扩展 9 个工具（6 新增）

零新依赖（无 Jinja2 / npm / 构建步骤）
```

### 后端写操作

所有写操作直写 JSON 文件，无数据库/ORM 层。

---

## 文件变更

### 修改文件

#### `mcp_knowledge_server.py`

新增 6 个函数：

| 函数 | 功能 |
|------|------|
| `get_all_articles(filters)` | 全量返回 + 多条件筛选（status/source/tag/score_min/keyword） |
| `update_article_status(id, status)` | 改状态并写回原 JSON 文件 |
| `update_article_fields(id, updates)` | 批量更新 title/summary/tags/score 并写回 |
| `batch_update_status(ids, status)` | 批量改状态 |
| `get_human_review_items()` | 读取 `knowledge/human_review/*.json` |
| `resolve_human_review(filename)` | 将标记条目转为 `pending_review` 状态，删除标记文件 |

**关键改造**：`load_articles()` 建立 `id → filename` 映射用于写回。

#### `scripts/mcp_http_server.py`

- `FastAPI.lifespan` 替代废弃的 `@app.on_event`
- `StaticFiles` 挂载 `/static` → `PROJECT_ROOT/static/`
- `GET /` → 302 重定向 `/static/index.html`
- `POST /mcp/tools` 扩展 9 个工具 case

### 新建文件

```
static/
├── index.html           # 公开看板（只读，已发布条目）
├── review.html          # 审核看板（拖拽/编辑/批量/human_review）
├── css/
│   └── dracula.css     # Dracula 暗黑主题（~500 行）
└── js/
    ├── api.js          # API 封装（8 个调用）
    ├── kanban.js       # 共享看板组件（卡片/列/模态框/搜索/Toast）
    └── review.js       # 审核页专用逻辑（拖拽/批量/队列）
```

---

## 看板设计

### 审核看板布局

```
┌──────────────────────────────────────────────────────────────────┐
│  🤖 AI 知识库 · 审核看板                         [🤖 人工队列 N]  │
├──────────────────────────────────────────────────────────────────┤
│  📚 19  │  ⏳ 18  │  ✅ 1  │  ❌ 0  │  📤 0  │  均分 7.8       │
├──────────────────────────────────────────────────────────────────┤
│  🔍[搜索...]  [来源▾] [评分▾] [标签▾]       [☐ 全选]           │
├─────────────────┬──────────────┬──────────────┬──────────────────┤
│ ⏳ 待审核 (18)   │ ✅ 已批准(1) │ ❌ 已驳回(0) │ 📤 已发布 (0)    │
│                 │              │              │                  │
│ ┌─────────────┐ │ ┌────────┐ │              │                  │
│ │ 9.5 ★       │ │ │ 8.0 ★  │ │              │                  │
│ │ Transformers│ │ │AutoGPT │ │              │                  │
│ └─────────────┘ │ └────────┘ │              │                  │
│ ...             │            │              │                  │
└─────────────────┴────────────┴──────────────┴──────────────────┘
```

### 详情/编辑模态框

- 查看完整摘要、标签、评分、元信息
- 编辑 title / summary / tags（标签增删）/ score
- 批准 / 驳回 / 发布 快捷按钮
- 拖拽换列直接触发状态变更

### Human Review 队列面板

右侧滑出面板，展示 `knowledge/human_review/` 中被标记的批次：
- 显示审核反馈原因
- 「全部通过」→ 转为 pending_review 条目
- 「全部驳回」→ 标记为 rejected

### Dracula 主题色

```css
--dracula-bg:       #282a36   /* 主背景 */
--dracula-fg:       #f8f8f2   /* 主文字 */
--dracula-line:     #44475a   /* 列背景 */
--dracula-comment:  #6272a4   /* 次要文字 */
--dracula-cyan:     #8be9fd   /* 已发布 */
--dracula-green:    #50fa7b   /* 已批准 / 高分 */
--dracula-orange:   #ffb86c   /* 中等评分 */
--dracula-pink:     #ff79c6   /* 强调 */
--dracula-purple:   #bd93f9   /* 标签 / 交互 */
--dracula-red:      #ff5555   /* 已驳回 / 低分 */
--dracula-yellow:   #f1fa8c   /* 待审核 */
```

---

## 实施结果

| 状态 | 文件 |
|------|------|
| ✅ 已完成 | `mcp_knowledge_server.py` — 6 个写操作函数 |
| ✅ 已完成 | `scripts/mcp_http_server.py` — 静态文件 + 扩展 tools |
| ✅ 已完成 | `static/css/dracula.css` — Dracula 主题 |
| ✅ 已完成 | `static/js/api.js` — API 封装 |
| ✅ 已完成 | `static/js/kanban.js` — 共享看板逻辑 |
| ✅ 已完成 | `static/index.html` — 公开看板 |
| ✅ 已完成 | `static/review.html` + `static/js/review.js` — 审核看板 |
| ✅ 已验证 | 服务器启动正常（19 条文章，7 条 human_review） |

### 访问地址

```bash
PYTHONPATH=. python3 scripts/mcp_http_server.py

# 公开看板
http://localhost:8080/

# 审核看板
http://localhost:8080/static/review.html
```

---

## 决策记录

| 问题 | 决策 |
|------|------|
| Human Review 处理方式 | 转为正式条目（pending_review）并删除标记文件 |
| 公开看板 URL | `/static/index.html`，`/` 重定向 |
| 拖拽实现 | SortableJS CDN（轻量、触屏支持） |
| 鉴权 | 暂不需要，后续可加 |
| 写操作方式 | 直写 JSON 文件，不加 ORM/数据库层 |
