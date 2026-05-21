# AI 知识库系统 V4

基于多 Agent 协作的 AI 技术知识库——自动采集、智能分析、定时推送

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           分发层 (Distribution)                     │
│   Telegram Bot │ 飞书 Webhook │ QQ Bot │ MCP Server                │
├─────────────────────────────────────────────────────────────────────┤
│                           工程层 (Engineering)                      │
│   Scheduler (Cron) │ Quality Hooks │ Daily Digest │ MCP Server     │
├─────────────────────────────────────────────────────────────────────┤
│                           Pipeline 层                               │
│   Collector → Analyzer → Organizer → Reviewer → Save               │
├─────────────────────────────────────────────────────────────────────┤
│                           Agent 层 (OpenCode Agents)                │
│   Supervisor │ Collector │ Analyzer │ Organizer │ Reviewer         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 1. Clone 项目
git clone https://github.com/AllenTango/ai-knowledge.git
cd ai-knowledge

# 2. 配置 .env
cp env.example .env
# 编辑 .env，填入你的 API Key 和渠道配置

# 3. 启动服务
docker compose up -d
```

---

## 目录结构

| 目录 | 说明 |
|------|------|
| `workflows/` | LangGraph 工作流节点实现 |
| `pipeline/` | Pipeline 工作流（独立顺序脚本） |
| `patterns/` | OpenCode patterns (Supervisor/Router) |
| `.opencode/agents/` | OpenCode Agent 定义文件 |
| `.opencode/skills/` | OpenCode Skills 定义 |
| `scripts/` | 核心业务逻辑脚本 |
| `scheduler/` | 定时调度脚本 |
| `distribution/` | 分发渠道模块 |
| `bot/` | 知识库交互机器人 |
| `knowledge/` | 知识库存储 (raw/analyzer_output/articles/human_review) |
| `hooks/` | 质量检查钩子 |
| `tests/` | 测试与评估 |

---

## 技术栈

| 类别 | 选型 |
|------|------|
| **LLM 引擎** | DeepSeek (支持切换其他 provider) |
| **Agent 编排** | OpenCode + 自定义 Supervisor |
| **工作流** | LangGraph + 自研 Pipeline |
| **容器化** | Docker + Docker Compose |
| **分发渠道** | Telegram Bot / 飞书 Webhook / QQ Bot / MCP Server |
| **数据存储** | JSON 文件 (本地知识库) |

---

## 三种工作流

| 工作流 | 说明 | 适用场景 |
|--------|------|----------|
| **Pipeline** | 顺序执行：采集→分析→整理→保存 | 定时任务、简单流程 |
| **LangGraph** | 状态机图，支持审核循环和重试 | 复杂审核流程、AI 质量控制 |
| **OpenCode** | 多 Agent 协作，Supervisor 编排 | Agent 协作开发、动态任务 |

---

## 版本历史

| 版本 | 核心能力 |
|------|----------|
| **V1** | 基础采集流程，单一数据源，命令行运行 |
| **V2** | Pipeline 工作流，支持 GitHub + RSS 多源采集，定时任务 |
| **V3** | 引入 LangGraph，状态机审核循环，多 Agent 协作 |
| **V4** | 完整版：OpenCode Agents + LangGraph 双工作流，MCP 服务器，Quality Hooks |

---

## 月度成本估算

| 项目 | 配置 | 月费用 (估算) |
|------|------|-------------|
| **大模型 API** | DeepSeek (约 300K tokens/月) | ¥150-300 |
| **服务器** | 1 台 2C4G 云服务器 | ¥80-150 |
| **渠道消息** | Telegram/飞书/QQ 免费额度 | ¥0 |
| **总计** | | **¥230-450** |

---

## License

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 相关文档

- [AGENTS.md](AGENTS.md) - 项目技术规范
- [env.example](env.example) - 环境变量配置示例
- [.github/workflows/](.github/workflows/) - CI/CD 自动化