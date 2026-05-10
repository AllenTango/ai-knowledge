# workflows/graph.py 设计解释

## 1. add_conditional_edges 的三个参数

```python
workflow.add_conditional_edges(
    "review",        # 参数一：source — 从哪个节点引出条件边
    decide_next,     # 参数二：condition — 一个函数，接收当前 state，返回分支名称
    {               # 参数三：mapping — 字符串 → 目标节点的映射字典
        "save": "save",
        "organize": "organize",
    },
)
```

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `source` | 源节点名称 | `"review"` |
| `condition` | 一个函数：`KBState → str` | `decide_next(state) → "save"\|"organize"` |
| `mapping` | 分支名 → 目标节点的映射 | `{"save": "save_node", "organize": "organize_node"}` |

LangGraph 执行流程：

```
review_node → decide_next(state)
                ↓
            "organize"  或  "save"
                ↓              ↓
            mapping["organize"] = "organize" → organize_node
            mapping["save"] = "save" → save_node
```

## 2. decide_next 返回的字符串和 mapping 字典的关系

`decide_next` 的返回值必须**是 mapping 字典的 key**：

- `decide_next` 返回 `"save"` → LangGraph 查 `mapping["save"]` → 流向 `"save"` 节点
- `decide_next` 返回 `"organize"` → LangGraph 查 `mapping["organize"]` → 流向 `"organize"` 节点

**key 和 value 可以相同也可以不同**。当前设计中 key=value 是因为分支名恰好就是节点名，但这不是必须的。例如下面的写法也完全有效：

```python
workflow.add_conditional_edges(
    "review",
    decide_next,
    {
        "APPROVED": "save",      # "APPROVED" 是内部分支名，指向 save 节点
        "REJECTED": "organize",  # "REJECTED" 是内部分支名，指向 organize 节点
    },
)
```

## 3. review 未通过时回到 organize，怎么知道要修正？

核心机制：**StateGraph 在节点间传递的是同一个 KBState 字典引用**。

```
review_node(state) → 更新 state["review_passed"]=False, state["review_feedback"]="..."
                                                ↓
                              organize_node(state) 读取 state["review_feedback"]
                                                    ↓
                              organize_node 检测到 review_feedback 非空
                                                    ↓
                              调用 LLM 根据 feedback 逐条修正 summary/tags/score
```

流程：
1. `review_node` 执行后，state 中 `review_feedback` 字段被写入审核意见
2. 图回到 `organize_node`，它读取 `state["review_feedback"]`
3. `organize_node` 发现 `review_feedback` 非空，触发 LLM 修正逻辑（见 `organize_node` 的 Step 3）
4. 修正后的 articles 重新流入 `review_node` 进行第二轮审核

## 4. 循环什么时候结束？

循环结束条件由两个机制共同控制：

### 机制 A：decide_next 条件边
- `review_passed = True` → 流向 `save` → 流向 `END`（正常结束）
- `review_passed = False` → 流向 `organize` → 重新进入 `review`

### 机制 B：review_node 内部强制通过
```python
if iteration >= 2:
    return {"review_passed": True, ...}  # 强制通过
```

循环最多 2 次（3 次执行 review_node：iteration=0/1/2）。第 3 次审核时 iteration=2，强制 `review_passed=True`，条件边流向 `save` → 结束。

### 循环流程图

```
collect → analyze → organize → review
              ↑                    │
              │     review_passed=False & iteration<2
              └────────────────────┘
                                   │
              review_passed=True  │
                    ↓              ↓
                   save → END      organize → review (第2次)

review_node(iteration=2): 强制 review_passed=True → save → END
```

| 场景 | 循环次数 | 结束原因 |
|------|---------|---------|
| 一次性通过 | 0 | review_passed=True |
| 第一次未过，第二次通过 | 1 | iteration=1 → review_passed=True |
| 两次都未过 | 2 | iteration=2 → 强制 passed → save → END |

## 副作用（Side Effect）

LangGraph 图中每次节点执行都会**累积**修改 KBState：

- 第 1 次：`sources` 填充 → `analyses` 填充 → `articles` 填充 → `review_passed=False`, `iteration=1`
- 第 2 次：`articles` 被 LLM 修正 → 重新审核 → `review_passed=True` 或 `iteration=2`
- 第 3 次：`review_passed=True` → `save` → 写入文件

同一个 KBState 字典在图执行过程中不断被更新，这是 LangGraph 的标准累积模式。