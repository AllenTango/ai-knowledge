# workflows/graph.py 完整行为测试报告

**通过: 77 | 失败: 0 | 跳过: 0**

## plan_strategy 三档策略

- **PASS** `target=5 → strategy=lite` 实际=lite
- **PASS** `target=5 per_source_limit=5` 实际=5
- **PASS** `target=5 relevance_threshold=0.7` 实际=0.7
- **PASS** `target=5 max_iterations=1` 实际=1
- **PASS** `target=5 有 rationale` 
- **PASS** `target=9 → strategy=lite` 实际=lite
- **PASS** `target=9 per_source_limit=5` 实际=5
- **PASS** `target=9 relevance_threshold=0.7` 实际=0.7
- **PASS** `target=9 max_iterations=1` 实际=1
- **PASS** `target=9 有 rationale` 
- **PASS** `target=10 → strategy=standard` 实际=standard
- **PASS** `target=10 per_source_limit=10` 实际=10
- **PASS** `target=10 relevance_threshold=0.5` 实际=0.5
- **PASS** `target=10 max_iterations=2` 实际=2
- **PASS** `target=10 有 rationale` 
- **PASS** `target=15 → strategy=standard` 实际=standard
- **PASS** `target=15 per_source_limit=10` 实际=10
- **PASS** `target=15 relevance_threshold=0.5` 实际=0.5
- **PASS** `target=15 max_iterations=2` 实际=2
- **PASS** `target=15 有 rationale` 
- **PASS** `target=19 → strategy=standard` 实际=standard
- **PASS** `target=19 per_source_limit=10` 实际=10
- **PASS** `target=19 relevance_threshold=0.5` 实际=0.5
- **PASS** `target=19 max_iterations=2` 实际=2
- **PASS** `target=19 有 rationale` 
- **PASS** `target=20 → strategy=full` 实际=full
- **PASS** `target=20 per_source_limit=20` 实际=20
- **PASS** `target=20 relevance_threshold=0.4` 实际=0.4
- **PASS** `target=20 max_iterations=3` 实际=3
- **PASS** `target=20 有 rationale` 
- **PASS** `target=30 → strategy=full` 实际=full
- **PASS** `target=30 per_source_limit=20` 实际=20
- **PASS** `target=30 relevance_threshold=0.4` 实际=0.4
- **PASS** `target=30 max_iterations=3` 实际=3
- **PASS** `target=30 有 rationale` 

## planner_node 写入 plan

- **PASS** `planner_node 返回 plan` 
- **PASS** `planner_node plan.strategy=standard` 
- **PASS** `planner_node plan.target_count=15` 

## 场景 A：standard 首次审核通过（理想路径）

- **PASS** `场景A: review_node review_passed=True` 
- **PASS** `场景A: review_node iteration=1` 
- **PASS** `场景A: review_feedback=''` 
- **PASS** `场景A: route → 'organize'` 

## 场景 B：首次未过 → revise → 第二次通过

- **PASS** `场景B 第1次: review_passed=False` 
- **PASS** `场景B 第1次: iteration=1` 
- **PASS** `场景B 第1次: route → 'revise'` 
- **PASS** `场景B revise: 返回 analyses` 
- **PASS** `场景B revise: 返回 cost_tracker` 
- **PASS** `场景B 第2次: review_passed=True` 
- **PASS** `场景B 第2次: iteration=2` 
- **PASS** `场景B 第2次: route → 'organize'` 

## 场景 C：三次未过 → human_flag 兜底

- **PASS** `场景C: 三次审核 iteration=[1,2,3]` 实际=[1, 2, 3]
- **PASS** `场景C: 最终路由 'human_flag'` 
- **PASS** `场景C: human_flag_node 执行成功` 
- **PASS** `场景C: human_review 目录有文件` 
- **PASS** `场景C: flag iteration=3` 

## lite 策略：max_iterations=1，直接 human_flag

- **PASS** `lite plan.strategy=lite` 
- **PASS** `lite plan.max_iterations=1` 
- **PASS** `lite plan.relevance_threshold=0.7` 
- **PASS** `lite iter=0 < max_iterations=1, route='revise'` 
- **PASS** `lite iter=1 >= max_iterations=1 → route='human_flag'` 

## full 策略：per_source_limit=20, threshold=0.4

- **PASS** `full plan.strategy=full` 
- **PASS** `full plan.per_source_limit=20` 
- **PASS** `full plan.relevance_threshold=0.4` 
- **PASS** `full plan.max_iterations=3` 
- **PASS** `full: collect_node 返回 sources` 
- **PASS** `full: collect_node 采集数量=20（per_source_limit）` 实际=20
- **PASS** `full: organize_node threshold=0.4，0.45>=0.4 保留` 
- **PASS** `full: organize_node threshold=0.4，0.39<0.4 过滤` 

## build_graph 编译验证（8 节点）

- **PASS** `8 个自定义节点` 节点=['planner', 'collect', 'analyze', 'organize', 'review', 'revise', 'save', 'human_flag']
- **PASS** `节点 'planner' 存在` 
- **PASS** `节点 'collect' 存在` 
- **PASS** `节点 'analyze' 存在` 
- **PASS** `节点 'organize' 存在` 
- **PASS** `节点 'review' 存在` 
- **PASS** `节点 'revise' 存在` 
- **PASS** `节点 'save' 存在` 
- **PASS** `节点 'human_flag' 存在` 

*生成时间: 2026-05-11T00:09:36.414348*
