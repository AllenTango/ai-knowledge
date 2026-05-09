# Skill 与 Agent 数据流冲突处理记录

## 异常时间

2026-05-09

---

## 一、异常描述

### 问题现象

在执行采集 → 分析 → 整理流程时，发现 organizer 无法正确读取分析结果。

### 异常根因

| 组件 | 规范输出路径 | 实际输出路径 | 冲突原因 |
|------|--------------|--------------|----------|
| analyzer agent | `knowledge/analyzer_output/` | ✅ 正确 | - |
| tech-summary skill | `knowledge/raw/` | ❌ 错误 | Skill 定义与 Agent 规范不一致 |

organizer 从 `knowledge/analyzer_output/` 读取分析结果，但 tech-summary skill 输出到 `knowledge/raw/`，导致数据流断裂。

---

## 二、处理方案

### 1. 临时处理

手动移动文件到正确位置：

```bash
mv knowledge/raw/tech-summary-2026-05-09.json \
   knowledge/analyzer_output/20260509-analyzed.json
```

### 2. 根本修复

修改 `.opencode/skills/tech-summary/SKILL.md`：

```diff
- 将分析结果写入 `knowledge/raw/tech-summary-YYYY-MM-DD.json`。
+ 将分析结果写入 `knowledge/analyzer_output/{date}-analyzed.json`（与 analyzer agent 规范一致）。
+
+ > 注意：输出路径与 analyzer agent 规范保持一致，确保 organizer 能正确读取分析结果。
```

---

## 三、如何避免 organizer 整理时出现异常

### 方案1：统一数据流规范

| 阶段 | 输出目录 | 使用者 |
|------|----------|--------|
| 采集 | `knowledge/raw/` | collector、github-trending skill |
| 分析 | `knowledge/analyzer_output/` | analyzer、tech-summary skill |
| 整理 | `knowledge/articles/` | organizer |

**执行原则**：所有 Agent 和 Skill 必须遵循统一的输出目录规范。

### 方案2：Skill 设计检查清单

创建新 Skill 时，必须确认：

- [ ] 输出路径是否与同阶段 Agent 规范一致？
- [ ] organizer 能否从该路径读取数据？
- [ ] 是否与上下游组件的输入输出匹配？

### 方案3：数据流验证机制

organizer 执行前增加自检：

```python
def validate_input():
    # 检查 analyzer_output 目录是否存在分析结果
    files = glob("knowledge/analyzer_output/*-analyzed.json")
    if not files:
        raise NoInputError("缺少分析阶段的输出文件")
    # 检查是否有未处理的数据在 raw 目录
    raw_files = glob("knowledge/raw/*.json")
    if raw_files:
        warn("raw 目录存在未处理文件")
```

### 方案4：文档同步

当修改 Agent 规范时，同步更新相关 Skill：

| Agent 修改 | 需要同步的 Skill |
|------------|------------------|
| analyzer 输出路径 | tech-summary |
| organizer 读取路径 | 所有分析类 Skill |
| collector 输出路径 | github-trending |

---

## 四、数据流图（修复后）

```
┌─────────────────────────────────────────────────────────────┐
│                         采集阶段                             │
├─────────────────────────────────────────────────────────────┤
│  collector agent                              github-trending skill
│       ↓                                               ↓
│  knowledge/raw/                              knowledge/raw/
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                         分析阶段                             │
├─────────────────────────────────────────────────────────────┤
│  analyzer agent                                tech-summary skill
│       ↓                                               ↓
│  knowledge/analyzer_output/              knowledge/analyzer_output/
│       (统一)                                          (统一)
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                         整理阶段                             │
├─────────────────────────────────────────────────────────────┤
│  organizer
│       ↓
│  knowledge/articles/
└─────────────────────────────────────────────────────────────┘
```

---

## 五、总结

| 问题 | 方案 |
|------|------|
| Skill 与 Agent 输出路径不一致 | 统一为 `knowledge/analyzer_output/` |
| 临时数据流断裂 | 手动移动文件 |
| 未来预防 | 1. 统一数据流规范<br>2. Skill 设计检查清单<br>3. 数据流验证机制<br>4. 文档同步机制 |

**核心原则**：Skill 是 Agent 的具体步骤实现，必须遵循 Agent 定义的输入输出规范。