# review_node 调整方案

## 需求逐项核查

| # | 需求 | 原 nodes.py 实现 | 是否满足 | 说明 |
|---|------|-----------------|---------|------|
| 1 | 审核对象为 `state["analyses"]` | 读取 `state["articles"]` | **不满足** | 旧实现审核 `articles`，但 `articles` 在 `organize` 之后才存在，review 应在 organize 之前 |
| 2 | 5 维度，每维 1-10 分，权重 25/25/20/15/15 | 4 维度，权重 25/25/20/15/15（最后一维为空） | **不满足** | 旧实现只有 4 维（摘要质量、标签准确、分类合理、一致性），且第 4 维权重累加为 100% 而非 85% |
| 3 | 代码重算加权总分 | 无（信任 LLM 返回的 `passed` 字段） | **不满足** | 新增 `_recompute_weighted_score()` 函数，代码级遍历维度重算 |
| 4 | 加权总分 >= 7.0 通过 | 无此逻辑 | **不满足** | 由代码在 `_recompute_weighted_score` 中计算后赋值 `review["passed"]` |
| 5 | 只审核前 5 条 analyses | 遍历所有 `articles` | **不满足** | 新增 `analyses[:5]` 截断逻辑 |
| 6 | temperature=0.1 | temperature=0.2 | **不满足** | 改为 0.1 |
| 7 | LLM 调用失败时自动通过 | 有此逻辑（但放在末尾） | **满足** | 新实现将检查前置（LLM 不可用时直接返回），`try/except` 包裹 LLM 调用，失败时自动通过 |
| 8 | 返回 `{review_passed, review_feedback, iteration, cost_tracker}` | 有此逻辑 | **满足** | 新实现返回字段完全一致 |

## 主要修改

### 1. 审核对象变更
```python
# 旧
articles = state.get("articles", [])

# 新
analyses = state.get("analyses", [])
```

### 2. 审核范围变更
```python
# 旧
for article in articles:  # 遍历所有

# 新
to_review = analyses[:5]  # 只取前 5 条
```

### 3. 评分维度变更
```python
# 旧: 4 维度（摘要质量、标签准确、分类合理、一致性）
# 新: 5 维度（summary_quality 25%、technical_depth 25%、relevance 20%、originality 15%、formatting 15%）
```

### 4. 代码级加权重算
```python
def _recompute_weighted_score(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for review in reviews:
        weighted = 0.0
        for dim_key in ("summary_quality", "technical_depth", "relevance", "originality", "formatting"):
            score = float(review.get(dim_key, 0))
            weight = {...}[dim_key]
            weighted += score * weight
        review["weighted_score"] = round(weighted, 2)
        review["passed"] = weighted >= 7.0
    return reviews
```

### 5. LLM 调用方式变更
```python
# 旧: chat()，手动提取 JSON，正则匹配
(text, usage) = chat(system=REVIEW_SYSTEM_PROMPT, prompt=review_input, temperature=0.2)
json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)

# 新: chat_json()，自动解析 JSON
parsed, usage = chat_json(prompt=prompt, system=REVIEW_SYSTEM_PROMPT, temperature=0.1)
reviews = parsed.get("reviews", [])
reviews = _recompute_weighted_score(reviews)
```

### 6. 批量审核替代逐条审核
```python
# 旧: 每条 article 一次 LLM 调用（循环 N 次）
for article in articles:
    (text, usage) = chat(...)  # N 次 API 调用

# 新: 5 条合并一次 LLM 调用（单次 API 调用）
prompt_lines = [f"id: {...}\ntitle: {...}\n..." for item in analyses[:5]]
prompt = "\n".join(prompt_lines)
parsed, usage = chat_json(prompt=prompt, ...)  # 1 次 API 调用
```

### 7. Prompt 设计变更
```python
# 旧: 每条单独评分，返回 {passed, total_score, dimensions, feedback}
# 新: 批量评分，返回 {reviews: [{id, summary_quality, ...}, ...]}
# 原因：一次调用审核多条，节省 token
```

## 流程对照

```
analyze_node → analyses[0..N] 填充
                          ↓
                 review_node(analyses)  ← 当前修改位置
                          ↓
              review_passed=True → save_node
              review_passed=False → organize_node → review_node
```

## 副作用处理

1. `organize_node` 读取 `review_feedback` 修正时，需适配新的 feedback 格式（`[id] 加权总分=X，低分维度: xxx=Y, ...`）
2. `review_node` 不再读取 `articles`，因此在 `organize_node` 执行前 review 阶段不存在 `articles` — 这是预期行为，符合"报告式通信"原则

## 测试要点

1. `analyses=[]` → review_passed=True（空分析跳过）
2. `analyses` 有 10 条 → 只审核前 5 条
3. LLM 返回的维度评分 → 代码重算加权，>=7.0 则 passed
4. LLM 调用失败（网络异常）→ 自动通过，不阻塞流程
5. `review_passed=False` 时 `review_feedback` 包含低分维度信息