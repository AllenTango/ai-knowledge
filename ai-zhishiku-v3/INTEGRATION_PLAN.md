# 三大模块接入 LangGraph 方案

## 概述

将 `tests/` 下的 CostGuard / Security / Eval 独立模块接入 `workflows/` 的 LangGraph 工作流节点。

## 实施原则

1. `model_client.py` 统一处理 CostGuard（所有 LLM 调用自动记录），节点调用时传 `node_name` 即可区分
2. Security 只接入最高风险点：`collect_node` 入口（外部数据清洗）+ `organize_node` 出口（PII 过滤）
3. Eval 的 LLM-as-Judge 按策略分级：`full` 启用，`lite`/`standard` 跳过
4. 不改 `state.py`、`graph.py`

---

## 一、CostGuard 接入

### 1.1 model_client.py

```python
# 文件顶部新增（懒加载）
from tests.cost_guard import CostGuard

_cost_guard: CostGuard | None = None

def get_cost_guard() -> CostGuard:
    global _cost_guard
    if _cost_guard is None:
        _cost_guard = CostGuard(
            budget_yuan=float(os.getenv("BUDGET_YUAN", "1.0"))
        )
    return _cost_guard


# chat() 签名修改
def chat(
    messages=None, system="", prompt="", provider_name="",
    node_name: str = "unknown",
    **kwargs,
) -> tuple[str, Usage]:
    ...
    response = chat_with_retry(msgs, provider_name=provider_name, **kwargs)
    guardian = get_cost_guard()
    guardian.record(node_name, {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }, model=response.model)
    guardian.check()  # 超限抛 BudgetExceededError
    return response.content, response.usage


# chat_json() 签名修改，透传 node_name 到 chat()
def chat_json(
    messages=None, system="", prompt="", provider_name="",
    node_name: str = "unknown",
    **kwargs,
) -> tuple[dict, Usage]:
    ...
    text, usage = chat(
        messages=msgs, provider_name=provider_name,
        node_name=node_name, **kwargs
    )
    ...
```

### 1.2 nodes.py 调用方追加 node_name

| 节点 | 函数 | node_name |
|------|------|-----------|
| analyze_node | `chat()` | `"analyze"` |
| organize_node | `chat()` | `"organize"` |
| review_node | `chat_json()` | `"review"` |
| revise_node | `chat_json()` | `"revise"` |

---

## 二、Security 接入

### 2.1 collect_node 入口清洗

```python
from tests.security import sanitize_input

# 对每条 GitHub/RSS item
title, _ = sanitize_input(item.get("title", ""))
desc, _ = sanitize_input(item.get("description", ""))
```

### 2.2 organize_node 出口过滤

```python
from tests.security import filter_output

# 格式化 articles 时
summary, pii_dets = filter_output(item.get("summary", ""))
tags_str = ", ".join(item.get("tags", []))
_, tag_dets = filter_output(tags_str)
```

---

## 三、Eval 接入

### 3.1 review_node · 仅 full 策略

```python
plan = state.get("plan", {})
if plan.get("strategy") == "full":
    from tests.eval_test import judge_score
    eval_score = judge_score({"title": ..., "summary": ..., "tags": ..., "score": ...})
```

---

## 改动文件清单

| 文件 | 改动行 | 内容 |
|------|--------|------|
| `workflows/model_client.py` | +30 | 新增 get_cost_guard() + chat()/chat_json() 签名 |
| `workflows/nodes.py` | ~15 | 4 处 node_name + collect sanitize + organize filter + review eval |
| `tests/cost_guard.py` | 0 | 不变 |
| `tests/security.py` | 0 | 不变 |
| `tests/eval_test.py` | 0 | 不变 |

## 不改文件

- `workflows/graph.py`
- `workflows/state.py`
- `workflows/collector.py`
- `workflows/analyzer.py`
- `workflows/organizer.py`
- `workflows/reviewer.py`
