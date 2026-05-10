# patterns/router.py 设计解释

## Q1: 为什么用两层分类而不是直接 LLM 分类？

### 设计考量

两层分类（关键词快速匹配 + LLM 兜底）是 **成本-准确率权衡** 的结果：

| 维度 | 单层 LLM 分类 | 两层分类（当前方案） |
|---|---|---|
| **每次调用成本** | 每次均需 LLM API 调用（¥0.001~0.004/次） | 约 60% 的请求在关键词层零成本解决 |
| **延迟** | 1~3 秒（网络+推理） | 关键词层 < 1ms，LLM 层仅用于模糊请求 |
| **准确率** | 高（但过度杀伤简单请求） | 关键词层 100% 确定，LLM 层仅处理边界情况 |
| **可用性** | 依赖 LLM 服务可用性 | 关键词层离线可用，LLM 不可用时自动降级 |

### 实际数据分析

典型的用户请求分布预估：

```
用户请求
    │
    ├─ 明确意图（~60%）
    │   ├─ "github 上的 AI 项目" → 关键词命中 github_search
    │   ├─ "查一下 LangChain 文章" → 关键词命中 knowledge_query
    │   └─ 零成本，无 LLM 调用
    │
    └─ 模糊意图（~40%）
        ├─ "今天有什么新东西？" → LLM 分类
        ├─ "帮我看看" → LLM 分类
        └─ 需要 LLM 推理
```

### 降级保障

当 LLM 服务不可用时（API Key 未配置、网络故障、配额耗尽），`classify_by_llm()` 抛出异常并被捕获，默认返回 `general_chat`。这确保了系统至少能回退到关键词匹配 + 通用对话的基本能力，避免完全不可用。

---

## Q2: KEYWORD_RULES 的数据结构为什么是 list[tuple] 而不是 dict？

> **注意**：当前实现实际使用的是 **`dict[str, list[str]]`**（即 `KEYWORD_MAP`）。但这个问题本质是在问「为什么用映射结构而不是规则列表」。以下对比两种设计：

### 对比：dict[str, list[str]] vs list[tuple[str, list[str]]]

| 特性 | `dict[str, list[str]]`（当前） | `list[tuple[str, list[str]]]` |
|---|---|---|
| **查找速度** | O(1) 意图名 → 关键词列表 | O(n) 遍历所有规则 |
| **意图唯一性** | 天然保证 Key 唯一 | 需额外检查重复 |
| **动态增删** | `KEYWORD_MAP["new_intent"] = [...]` | `KEYWORD_RULES.append(("new_intent", [...]))` |
| **遍历分类** | `for intent, keywords in d.items()` | `for intent, keywords in lst`（同样写法） |
| **意图数量** | 小型（2~10 种），性能差异可忽略 |

### 为什么选 dict

1. **意图唯一性由语言保证** — dict 的 key 天然不重复，避免误注册同名意图
2. **语义更清晰** — `KEYWORD_MAP` 读作「意图 → 关键词列表的映射」，符合业务直觉
3. **随机访问** — 如果需要按名称查询某意图的关键词（如调试、动态配置），dict 的 O(1) 查找更便捷
4. **扩展性** — 如果后续要为每个意图增加元信息（如权重、描述），dict 的值可以平滑升级为嵌套结构：

   ```python
   KEYWORD_MAP: dict[str, dict] = {
       "github_search": {
           "keywords": ["github", "repo", ...],
           "weight": 1.0,
           "description": "GitHub 仓库搜索",
       },
   }
   ```

### list[tuple] 的适用场景

如果规则需要**有序优先级**（如先匹配 A，匹配不到再匹配 B），list[tuple] 更合适。但当前场景下各意图是并列关系，顺序不重要，dict 更简洁。

---

## Q3: classify_intent 的兜底逻辑是怎么工作的？

`classify_intent()` 实现了「关键词 → LLM → 默认值」的三级兜底链：

```python
def classify_intent(query: str) -> str:
    # Level 1: 关键词匹配（零成本）
    intent = classify_by_keywords(query)
    if intent:                     # ← 命中则直接返回，不走 LLM
        return intent

    # Level 2: LLM 分类（兜底）
    return classify_by_llm(query)  # ← 未命中则调 LLM
```

### 三级兜底的状态流转

```
classify_intent("今天有什么新闻")
    │
    ├─ Level 1: classify_by_keywords()
    │   ├─ 检查 KEYWORD_MAP 中的每个关键词
    │   ├─ "今天"、"新闻" 不在任何关键词列表中
    │   └─ 返回 None → 进入 Level 2
    │
    ├─ Level 2: classify_by_llm()
    │   ├─ 构建分类提示词 → 调 chat_json()
    │   ├─ 成功 → 返回 LLM 判定的意图
    │   ├─ LLM 异常（网络/配额/Key 缺失）
    │   │   └─ 捕获异常，logger.warning
    │   └─ 返回 "general_chat"（最安全的默认值）
    │
    └─ 返回 general_chat → route() 执行通用对话
```

### 异常安全性

```
classify_by_llm() 内部：
    try:
        (result, _usage) = chat_json(...)
        intent = result.get("intent", "general_chat")
        if intent not in 合法意图列表:
            return "general_chat"          # ← 非法返回值降级
        return intent
    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}")
        return "general_chat"              # ← 任何异常降级
```

这意味着：**无论 LLM 返回什么（包括乱码、空值、异常），classify_intent 永远不会抛出异常**，始终返回一个合法意图。

---

## Q4: 如果要新增一种意图（比如 arxiv_search），需要改哪几处？

需要修改 **4 处**：

### 修改 1: `KEYWORD_MAP` — 添加关键词规则（零成本匹配）

```python
# patterns/router.py 第 34~43 行

KEYWORD_MAP: dict[str, list[str]] = {
    "github_search": [...],
    "knowledge_query": [...],
    "arxiv_search": [                       # ← 新增
        "arxiv", "论文", "paper",          # ← 中英文关键词
        "预印本", "学术", "research",
    ],
}
```

### 修改 2: `CLASSIFY_SYSTEM_PROMPT` — 告知 LLM 新意图（LLM 兜底用）

```python
# patterns/router.py 第 47~58 行

CLASSIFY_SYSTEM_PROMPT = """你是一个意图分类器。
{
    "intent": "github_search | knowledge_query | arxiv_search | general_chat",  # ← 新增
    ...
}

规则：
- arxiv_search：用户想搜索学术论文/arXiv 论文              # ← 新增
- github_search：...
- knowledge_query：...
- general_chat：..."""
```

### 修改 3: 实现处理器函数

```python
# patterns/router.py 新增一个函数

def handle_arxiv_search(query: str) -> str:
    """搜索 arXiv 论文。

    Args:
        query: 用户原始输入。

    Returns:
        格式化后的搜索结果文本。
    """
    import urllib.parse
    import urllib.request

    encoded = urllib.parse.quote(f"all:{query}")
    url = f"http://export.arxiv.org/api/query?search_query={encoded}&max_results=5&sortBy=relevance"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"arXiv API 请求失败: {e}")
        return f"arXiv 搜索失败: {e}"

    # 解析 XML 响应...
    return formatted_result
```

### 修改 4: `HANDLER_MAP` — 注册新处理器

```python
# patterns/router.py 第 257~261 行

HANDLER_MAP: dict[str, Any] = {
    "github_search": handle_github_search,
    "knowledge_query": handle_knowledge_query,
    "general_chat": handle_general_chat,
    "arxiv_search": handle_arxiv_search,          # ← 新增
}
```

### 修改总结（仅 4 处，皆在同一文件）

| # | 修改位置 | 改动量 | 说明 |
|---|---|---|---|
| 1 | `KEYWORD_MAP` | +3~5 行 | 关键词规则，第一层分类用 |
| 2 | `CLASSIFY_SYSTEM_PROMPT` | +2 行 | LLM 提示词，第二层分类用 |
| 3 | 新处理器函数 | +30~50 行 | 核心业务逻辑 |
| 4 | `HANDLER_MAP` | +1 行 | 注册映射 |

**设计原则**：新增一种意图只需改 `patterns/router.py` 这一个文件，不侵入其他模块。关键词匹配 + LLM 提示词 + 处理器 + 映射表四点联动，缺一不可。
