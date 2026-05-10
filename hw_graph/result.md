# workflows/graph.py 行为测试报告

**通过: 30 | 失败: 0 | 跳过: 1**

## decide_next 分支逻辑

- **PASS** `decide_next(review_passed=True)` expected=save actual=save
- **PASS** `decide_next(review_passed=False)` expected=organize actual=organize
- **PASS** `decide_next(review_passed=False iteration=1)` expected=organize actual=organize
- **PASS** `decide_next(review_passed=True iteration=2)` expected=save actual=save

## build_graph() 编译

- **PASS** `build_graph() 执行成功` 
- **PASS** `返回 CompiledStateGraph` 实际=CompiledStateGraph
- **PASS** `graph 有 invoke 方法` 

## 图结构验证

- **PASS** `自定义 5 个节点存在` 节点=['__start__', 'collect', 'analyze', 'organize', 'review', 'save']
- **PASS** `节点 'collect' 存在` 
- **PASS** `节点 'analyze' 存在` 
- **PASS** `节点 'organize' 存在` 
- **PASS** `节点 'review' 存在` 
- **PASS** `节点 'save' 存在` 
- **PASS** `所有 KBState 字段作为 channel 存在` channels=['sources', 'analyses', 'articles', 'review_feedback', 'review_passed', 'iteration', 'cost_tracker', '__start__', '__pregel_tasks', 'branch:to:collect', 'branch:to:analyze', 'branch:to:organize', 'branch:to:review', 'branch:to:save']

## 模拟 retry 循环路径

- **PASS** `第1次 organize_node 执行` articles=1
- **PASS** `第1次 review_node 执行` review_passed=True iteration=1
- **PASS** `第1次 review 后 iteration=1` 
- **PASS** `第1次 review 已通过（无 feedback 时）` 
- **PASS** `save_node 执行（直接通过）` 

## review_node iteration 强制通过逻辑

- **PASS** `iteration=0 → review_passed=True（空articles兜底）` iteration=0 passed=True
- **PASS** `iteration=1 → review_passed=True（空articles兜底）` iteration=1 passed=True
- **PASS** `iteration=2 → review_passed=True（强制通过）` iteration=2 passed=True
- **PASS** `iteration=3 → review_passed=True（强制通过）` iteration=3 passed=True

## analyze_node 空 state 处理

- **PASS** `analyze_node(sources=[]) 返回空更新` 无网络请求，实际跳过
- **PASS** `analyze_node 空 state 不抛异常` 
- **SKIP** analyze_node LLM 调用测试（无 API Key）

## organize_node feedback 修正逻辑

- **PASS** `organize_node 处理 feedback` 
- **PASS** `feedback 非空时 articles 生成` 
- **PASS** `organize_node 不抛异常` 

## save_node 空 articles 处理

- **PASS** `save_node(articles=[]) 返回空 dict` 
- **PASS** `save_node 空 articles 不抛异常` 

*生成时间: 2026-05-10T22:33:13.537632*
