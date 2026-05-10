# workflows/graph.py 行为测试报告

**通过: 34 | 失败: 0 | 跳过: 0**

## route_after_review 三分支逻辑

- **PASS** `route_after_review(review_passed=True)` expected=organize actual=organize
- **PASS** `route_after_review(review_passed=False, iteration=0)` expected=revise actual=revise
- **PASS** `route_after_review(review_passed=False, iteration=2)` expected=revise actual=revise
- **PASS** `route_after_review(review_passed=False, iteration=3)` expected=human_flag actual=human_flag
- **PASS** `route_after_review(review_passed=False, iteration=5)` expected=human_flag actual=human_flag

## build_graph() 编译验证

- **PASS** `build_graph() 执行成功` 
- **PASS** `7 个自定义节点` 节点=['collect', 'analyze', 'organize', 'review', 'revise', 'save', 'human_flag']
- **PASS** `节点 'collect' 存在` 
- **PASS** `节点 'analyze' 存在` 
- **PASS** `节点 'organize' 存在` 
- **PASS** `节点 'review' 存在` 
- **PASS** `节点 'revise' 存在` 
- **PASS** `节点 'save' 存在` 
- **PASS** `节点 'human_flag' 存在` 
- **PASS** `返回 CompiledStateGraph` 实际=CompiledStateGraph

## 正常通过路径测试

- **PASS** `review_node(review_passed=True) 返回 review_passed=True` 
- **PASS** `review_node iteration 递增` 
- **PASS** `route_after_review(passed=True) → 'organize'` 

## revise 路径测试

- **PASS** `第1次 review 返回 review_passed=False` 
- **PASS** `第1次 review iteration=1` 
- **PASS** `第1次 review feedback 非空` 
- **PASS** `route_after_review(passed=False, iter=1) → 'revise'` 
- **PASS** `revise_node 返回 analyses` 
- **PASS** `revise_node 返回 cost_tracker` 
- **PASS** `revise_node 不抛异常` 

## human_flag 路径测试

- **PASS** `route_after_review(passed=False, iter=3) → 'human_flag'` 
- **PASS** `human_flag_node 执行成功` 
- **PASS** `human_review 目录有文件` 文件数=2
- **PASS** `flag 文件包含 analyses` 
- **PASS** `flag 文件包含 iteration` 
- **PASS** `flag 文件 iteration=3` 
- **PASS** `flag 文件包含 review_feedback` 

## revise_node 空状态跳过测试

- **PASS** `revise_node(analyses=[], feedback='') 返回空 dict` 
- **PASS** `revise_node(feedback='') 返回空 dict` 

*生成时间: 2026-05-10T23:36:45.098742*
