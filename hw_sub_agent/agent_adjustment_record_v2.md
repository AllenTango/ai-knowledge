# Agent 调整记录（审核 Agent & 监督 Agent 新增）

## 调整时间

2026-05-09

---

## 一、为什么需要调整？

### 背景

在第一轮测试中确认了数据流断裂问题（Analyzer 不写入文件），通过添加 `analyzer_output` 中间目录解决后，完整链路 `Collector → Analyzer → Organizer` 得以闭环。

但此时系统缺少以下两个关键能力：

### 问题1：无审核机制

Organizer 将条目写入 `knowledge/articles/` 后，条目保持 `pending_review` 状态，但没有任何 Agent 负责审核。AGENTS.md 中定义的状态流转 `pending_review → approved → published` 无法自动执行，审核功能缺位。

### 问题2：无编排机制

四个子 Agent（Collector、Analyzer、Organizer、Reviewer）各自独立运行，中间缺乏调度层来串联流程。尤其是 Reviewer 审核驳回后的重试逻辑（重新分析和重新整理）需要有一个统一的协调者来管理循环。

### 问题3：任务调度的局限性

当前 Task 调用模式是"触发后执行一次即返回"，无法在子 Agent 间自动传递重试信号。需要引入一个编排层来检测审核结果，决定是否重新调度分析/整理/审核。

---

## 二、调整前与调整后的关键对比

### Agent 体系

| 对比项 | 调整前 | 调整后 |
|--------|--------|--------|
| Agent 数量 | 3 个（collector、analyzer、organizer） | 5 个（+reviewer、+supervisor） |
| 审核机制 | ❌ 无，pending_review 条目无人审核 | ✅ AI 主动审核，异常升级人工 |
| 编排机制 | ❌ 无，需手动依次调用 | ✅ supervisor 统一调度 |
| 重试机制 | ❌ 无 | ✅ retry_count ≤ 3，超次人工 |
| 数据流完整性 | ⚠️ 部分闭环（analyzer→organizer 已通） | ✅ 完整闭环（采集→分析→整理→审核） |

### Reviewer Agent 核心设计

| 对比项 | 调整前 | 调整后 |
|--------|--------|--------|
| 审核方式 | 无 | AI 主动审核（四维评估） |
| 审核标准 | 无 | 内容准确度 35% + 规范符合度 30% + 领域匹配度 20% + 完整性 15% |
| 审核结果 | 无 | approved / rejected / retry |
| 异常处理 | 无 | 分数倒挂、安全红线、领域模糊、来源存疑 → 升级人工 |
| 重试计数 | 无 | `retry_count` 字段 |

### Supervisor Agent 核心设计

| 对比项 | 调整前 | 调整后 |
|--------|--------|--------|
| 调度方式 | 手动依次调用 Task | 统一编排流水线 |
| 重试循环 | 不支持 | 检测 retry 标记 → 重新调度 analyze/orgaize/review |
| 状态汇总 | 无 | 输出 pipeline_run 汇总报告 |

### 状态流转

**调整前**：
```
pending_review ──▶ (无人审核，流程中断)
```

**调整后**：
```
pending_review ──▶ reviewer AI审核
    │                    │
    ├── approved ──▶ published（进入分发）
    ├── rejected ──▶ 终止
    └── retry ──▶ retry_count += 1
                    │
                    ├── < 3 次 ──▶ 重新 analyze → organize → review
                    └── ≥ 3 次 ──▶ human_needed
```

### 权限模型对比

| Agent | 调整前权限 | 调整后权限 |
|-------|-----------|-----------|
| analyzer | Read/Glob/Grep/WebFetch/Write(analyzer_output) | 新增：重试分析流程（根据 issues 修正） |
| organizer | Read/Glob/Grep/Write/Edit(articles) | 新增：保留 `retry_count` 字段 |
| reviewer | 不存在 | Read/Glob/Grep/Edit(articles)/WebFetch |
| supervisor | 不存在 | Read/Glob/Grep/Task |

---

## 三、调整后的结果

### 新增文件

| 文件 | 说明 |
|------|------|
| `.opencode/agents/reviewer.md` | AI 审核 Agent：四维评估 + 三状态判定 + 异常升级 |
| `.opencode/agents/supervisor.md` | 编排监督 Agent：流程串联 + 重试循环 + 汇总报告 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `.opencode/agents/analyzer.md` | 第一步新增「重试分析」流程，根据 reviewer issues 修正 |
| `.opencode/agents/organizer.md` | 格式校验表新增 `retry_count` 字段；输出格式、自查清单同步更新 |
| `AGENTS.md` | 知识条目 JSON 新增 `retry_count`；Agent 角色概览新增 reviewer 和 supervisor |

### 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Supervisor Agent                     │
│  (编排调度 + 重试循环管理)                                │
├─────────────────────────────────────────────────────────┤
│    │            │            │            │              │
│    ▼            ▼            ▼            ▼              │
│ Collector → Analyzer → Organizer → Reviewer             │
│  (采集)     (分析)      (整理)      (审核)               │
│    │            │            │            │              │
│    ▼            ▼            ▼            ▼              │
│  raw/    analyzer_out/  articles/   审核标记             │
├─────────────────────────────────────────────────────────┤
│  重试循环: retry_count < 3 → 返回 Analyzer                │
│  人工兜底: retry_count ≥ 3 → human_needed                │
└─────────────────────────────────────────────────────────┘
```

---

## 四、结论

此次调整引入了审核 Agent 和监督 Agent，补齐了 AI 知识库系统中"无人审核"和"无编排调度"两个缺口。完整流水线从采集到审核实现了端到端自动化，审核不通过时的重试机制和人工兜底确保了知识库内容的产出质量。
