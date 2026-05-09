# `@collector`（@mention）与 Task 工具委派的区别

## 角色背景

本项目（ai-zhishiku）的 `collector` Agent（采集 Agent）在 `.opencode/agents/collector.md` 中定义：**只采集、不写入**，所有输出通过对话返回，由上层工作流接管存储。

## 核心定位对比

| | `@collector`（@mention） | Task 工具委派 |
|---|---|---|
| **本质** | 在对话中「叫」collector 加入，类似同事间喊一声 | 主动拆解任务、指派 collector 执行，结果汇总到主 Agent |
| **调用方式** | 在消息中写 `@collector` | 主 Agent 调用 `task` 工具，指定 `subagent_type: collector` |
| **返回路径** | collector 的回复出现在对话消息流中，**所有参与者可见** | collector 的结果通过 `task_id` 返回，**仅主 Agent 可见** |
| **适用阶段** | 采集阶段需要**协作讨论**或追问时 | 采集阶段属于**流水线执行**，结果需统一汇总时 |

## 何时用 `@collector`

1. **追问与澄清**——分析 Agent 发现某条数据来源可疑，对 `@collector` 追问：「这条数据的 popularity 是实时抓取的吗？」
2. **补充采集**——主 Agent 发现漏采了 HN 数据，直接 `@collector` 追加：「请补采 Hacker News 今日 AI 相关 Top 5」
3. **人工介入场景**——编辑人员 `@collector` 询问某条数据的背景或来源
4. **强调透明性**——所有 Agent 的发言在同一对话中对所有参与者可见，适合需要多人「会诊」的场景

## 何时用 Task 工具委派

1. **流水线作业**——采集→分析→整理三步分阶段执行，主 Agent 掌握全流程进度
2. **隔离执行**——collector 的工具调用和中间结果不对外暴露，适合处理敏感数据
3. **结果汇总写入**——collector 返回 JSON 数据后，主 Agent 统一写入文件，本次全流程均采用此方式
4. **精细控制**——Task 可指定超时时间、并发数量、具体 prompt 模板

## 关键差异总结

| 维度 | `@collector`（@mention） | Task 工具委派 |
|---|---|---|
| 交互模式 | 对话式（双向交流，可多轮追问） | 单向委托（结果导向，Task 完成即结束） |
| 信息可见性 | 所有 Agent 可见（对话消息流） | 仅主 Agent 可见（通过 task_id 返回） |
| 适用流程 | 并行讨论、交叉确认、追加采集 | 顺序/并行流水线，独立执行单元 |
| 控制粒度 | 粗（靠对话引导，无法指定工具集） | 细（可指定 prompt、超时、工具权限） |
| 状态管理 | 共享对话上下文 | 独立 task_id，可断点续用 |
| collector 权限 | 只能读/抓取，不能写文件 | 同上（由 collector.md 决定） |

## 本次全流程的实践

本次执行了完整的三阶段流水线：

1. **Task 委派 `@collector`** → 采集 GitHub Trending Top 10，结果返回给我
2. **Task 委派 `@analyzer`** → 对采集数据深度分析（摘要、亮点、评分）
3. **Task 委派 `@organizer`** → 整理为标准知识条目，写入 `knowledge/articles/`

三步均用 Task 工具委派，因为：
- 每步输出是结构化数据，需主 Agent 统一写入文件
- 各阶段独立执行，不需要 Agent 间来回讨论
- 流程清晰、可控，便于错误追踪

如果 `@organizer` 在整理时发现某条数据缺失来源需要 `@collector` 补采，则应切换为 `@collector` 追加讨论，组合使用两种方式。

## 组合使用模式

```
主 Agent ──Task──▶ collector（批量采集）
                    │
              发现数据可疑？
                    │是
                    ▼
          主 Agent ──@collector──▶ 追问（对话式讨论）
                    │
                    ▼
主 Agent 汇总 Task 结果 + @mention 讨论结果 → 统一写入文件
```

这种「Task 为骨架、@mention 为血肉」的模式兼顾流水线效率与关键节点的 Agent 协作质量。