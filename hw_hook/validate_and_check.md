# 脚本功能重叠分析

## validate_json.py vs check_quality.py 功能对比

### 功能重叠部分

| 检查项 | validate_json.py | check_quality.py | 目的差异 |
|--------|----------------|-----------------|----------|
| 摘要长度 | >= 50 字（错误） | >= 50 字满分（评分） | 校验 vs 评分 |
| 标签数量 | >= 1 个（错误） | 1-3 最佳（评分） | 最低要求 vs 最佳实践 |
| URL 格式 | 格式校验（错误） | 格式存在性（维度） | 格式校验 vs 评分维度 |
| 字段存在性 | 7 个必填字段 | id/title/status/timestamp | 基础校验 vs 质量维度 |

### 核心差异

| 对比项 | validate_json.py | check_quality.py |
|--------|----------------|-----------------|
| **目的** | 格式校验（合法性） | 质量评分（优劣性） |
| **标准** | 通过/失败二元判定 | A/B/C 多级评分 |
| **关注点** | 字段完整性与类型正确性 | 内容质量与规范符合度 |
| **输出** | 错误列表 | 5 维度得分 + 总分 |
| **退出码** | 有错误返回 1 | C 级存在返回 1 |
| **计分制** | 无 | 100 分制 |

---

## 重叠检查项详解

### 1. 摘要长度

- **validate_json.py**：摘要 < 50 字视为错误，触发校验失败
- **check_quality.py**：>= 50 字得 25 分（满分），20-50 字得 15 分，< 20 字得 0 分

### 2. 标签数量

- **validate_json.py**：tags 为空列表视为错误
- **check_quality.py**：1-3 个标签得 15 分（满分），4-5 个得 10 分，>= 6 个得 5 分

### 3. 格式规范

- **validate_json.py**：检查 source_url 格式是否为 https?://...（错误）
- **check_quality.py**：格式规范维度占 20 分，检查 id/title/source_url/status/timestamp 五项，各 4 分

---

## 互补关系

两者设计为**互补组合**，形成完整的质量保障体系：

```
validate_json.py (格式校验)
        ↓
  格式正确？
    ↓ 是
check_quality.py (质量评分)
        ↓
  质量等级？
    ↓ A/B/C
  发布 / 修正 / 拒绝
```

- **validate_json.py**：入口校验，确保文件符合基本规范
- **check_quality.py**：质量评估，判断内容优劣程度

---

## 建议

在实际使用中，建议按顺序执行：

```bash
# 1. 先校验格式
python hooks/validate_json.py knowledge/articles/*.json

# 2. 格式通过后评估质量
python hooks/check_quality.py knowledge/articles/*.json
```

或集成到流水线中自动串联，形成完整的内容审核流程。
