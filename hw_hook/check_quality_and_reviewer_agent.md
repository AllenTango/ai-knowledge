# 质量评估功能对比分析

## reviewer Agent 与 check_quality.py 一致性对比

### 功能一致性

两者均实现相同的 5 维度质量评估体系（满分 100 分）：

| 维度 | 满分 | reviewer.md | check_quality.py | 是否一致 |
|------|------|-------------|------------------|----------|
| 摘要质量 | 25 | >=50 字满分，>=20 字基线 15，含技术关键词+5 | 完全一致 | ✓ |
| 技术深度 | 25 | score (1-10) 映射到 0-25 | 完全一致 | ✓ |
| 格式规范 | 20 | id/title/source_url/status/timestamp 各 4 分 | 完全一致 | ✓ |
| 标签精度 | 15 | 1-3 个最佳，4-5 个 10 分，>=6 个 5 分 | 完全一致 | ✓ |
| 空洞词检测 | 15 | 无空洞词满分 | 完全一致 | ✓ |
| 空洞词黑名单 | - | 中文/英文两组 | 中文/英文两组 | ✓ |
| 等级标准 | - | A>=80, B>=60, C<60 | A>=80, B>=60, C<60 | ✓ |

### 关键差异

| 对比项 | reviewer.md | check_quality.py |
|--------|-------------|------------------|
| 类型 | Agent 提示词规范 | 可编程自动化工具 |
| 执行方式 | 通过 LLM/Agent 执行 | 命令行脚本调用 |
| 集成方式 | LangGraph 工作流 | CI/CD 流水线 |
| 输出格式 | JSON 判定结果含 breakdown | 控制台报告 + 退出码 |
| 输入方式 | 读取 knowledge/articles/ | CLI 参数（单文件或通配符） |

---

## 完整自动化实现建议

无需修改 check_quality.py 脚本，通过以下方式实现 reviewer 的完整自动化：

### 1. 工作流集成

将 check_quality.py 作为 **前置检查钩子** 或 **CI 步骤** 接入 LangGraph 流水线：

```yaml
# pre-commit hook 示例
- repo: local
  hooks:
    - id: quality-check
      name: 知识条目质量评估
      entry: python hooks/check_quality.py
      language_system: python
      files: knowledge/articles/.*\.json$
      stages: [pre-commit]
```

### 2. LangGraph 节点调用

在流水线中添加质量评估节点：

```python
def quality_assessment_node(state):
    """质量评估节点"""
    files = glob("knowledge/articles/*.json")
    result = subprocess.run(
        ["python", "hooks/check_quality.py"] + files,
        capture_output=True,
        text=True
    )
    if result.returncode == 1:
        return {"action": "retry_batch", "grade_distribution": parse_output(result.stdout)}
    return {"action": "proceed_to_distribution"}
```

### 3. 输出格式增强

修改 check_quality.py 支持 JSON 输出，便于下游处理：

```python
def main() -> int:
    # ... 现有逻辑 ...
    import json
    output = [{
        "file": r.file_path,
        "score": r.total_score,
        "grade": r.grade,
        "breakdown": {d.name: {"得分": d.score, "详情": d.details} for d in dimensions}
    } for r in reports]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if grade_c > 0 else 0
```

### 4. 阈值配置外部化

将阈值配置移至 `config/settings.yaml`：

```yaml
quality:
  grade_a_threshold: 80
  grade_b_threshold: 60
  min_summary_length: 50
  max_tags_count: 3
  hollow_words:
    cn: [赋能, 抓手, 闭环, 打通, 全链路, 底层逻辑, 颗粒度, 对齐, 拉通, 沉淀, 强大的, 革命性的]
    en: [groundbreaking, revolutionary, game-changing, cutting-edge]
```

### 5. WebFetch 集成

由于 reviewer.md 包含 WebFetch 用于 URL 验证，建议添加 `--verify-url` 选项：

```python
def verify_url(source_url: str) -> bool:
    """抓取并验证 URL 内容与摘要一致性"""
    try:
        content = fetch_url(source_url)
        return any(kw in content for kw in TECH_KEYWORDS)
    except Exception:
        return False
```

---

## 结论

check_quality.py 是 reviewer.md 质量评估规则的完整可编程实现，具备以下优势：

1. **自动化评分** — 无需 LLM 调用即可完成质量评估
2. **CLI 接口** — 便于集成到各种流水线
3. **结果一致** — 与 Agent 审核结果保持一致
4. **退出码** — 支持流水线自动化决策

要实现 reviewer 的完整自动化，只需将 check_quality.py 作为分发前的验证步骤接入 LangGraph 流水线，配置好阈值参数和 JSON 输出即可。
