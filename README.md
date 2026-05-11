# AI 知识库系统

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
│   Collector → Analyzer → Organizer → Reviewer → Save              │
├─────────────────────────────────────────────────────────────────────┤
│                           Agent 层 (OpenCode Agents)                │
│   Supervisor │ Collector │ Analyzer │ Organizer │ Reviewer         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 1. Clone 项目
git clone https://github.com/your-repo/ai-zhishiku.git
cd ai-zhishiku/ai-zhishiku-v4

# 2. 配置 .env
cp env.example .env
# 编辑 .env，填入你的 API Key 和渠道配置

# 3. 启动服务
docker compose up -d
```

---

## 目录结构

| 目录 | 说明 | 版本 |
|------|------|------|
| `ai-zhishiku-v4/` | 最新稳定版 (含 LangGraph + OpenCode) | V4 |
| `ai-zhishiku-v3/` | LangGraph 工作流版本 | V3 |
| `ai-zhishiku-v2/` | Pipeline 工作流版本 | V2 |
| `ai-zhishiku-v1/` | 初始版本 | V1 |
| `hw_graph/` | LangGraph 工作流研究 | - |
| `hw_sub_agent/` | OpenCode 子 Agent 研究 | - |
| `hw_llmapi_opencode/` | OpenCode LLM API 集成 | - |
| `hw_mcp/` | MCP 协议实现 | - |
| `hw_specs/` | 编码规范文档 | - |
| `hw_cicd/` | CI/CD 配置 | - |
| `hw_cost/` | 成本估算对比 | - |

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

## 版本历史

| 版本 | 核心能力 |
|------|----------|
| **V1** | 基础采集流程，单一数据源，命令行运行 |
| **V2** | Pipeline 工作流，支持 GitHub + RSS 多源采集，定时任务 |
| **V3** | 引入 LangGraph，状态机审核循环，多 Agent 协作 |
| **V4** | 完整版：OpenCode Agents + LangGraph 双工作流，MCP 服务器，Quality Hooks，人工审核看板 |

---

## 月度成本估算

| 项目 | 配置 | 月费用 (估算) |
|------|------|-------------|
| **大模型 API** | DeepSeek Chat (约 300K tokens/月) | ¥150-300 |
| **服务器** | 1 台 2C4G 云服务器 | ¥80-150 |
| **渠道消息** | Telegram/飞书/QQ 免费额度 | ¥0 |
| **总计** | | **¥230-450** |

> 注：实际成本取决于采集量、token 消耗和服务器选型。

---

## License

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 相关文档

- [AGENTS.md](ai-zhishiku-v4/AGENTS.md) - 项目技术规范
- [env.example](ai-zhishiku-v4/env.example) - 环境变量配置示例
- [.github/workflows/](.github/workflows/) - CI/CD 自动化