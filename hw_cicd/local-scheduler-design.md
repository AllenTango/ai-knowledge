# 本地定时任务方案 —— 备选设计

## 概述

当 GitHub Actions 不可用或不满足需求时，可使用本地方案替代。支持 Linux/Mac (cron) 和 Windows (Task Scheduler) 两种平台。

## 流程覆盖

两个方案均调用同一个 `pipeline/pipeline.py`，完整执行 **采集 + 分析 + 整理 + 保存** 四步全流程：

| 步骤 | 内容 | 是否支持 |
|------|------|:-----:|
| Step 1 采集 | GitHub Search API + RSS 源抓取 | ✅ |
| Step 2 分析 | LLM 生成中文摘要/标签/评分 | ✅ |
| Step 3 整理 | 去重 + 格式标准化 | ✅ |
| Step 4 保存 | 写入 knowledge/articles/ | ✅ |

## 架构

```
scheduler/                       # 位于项目根目录 ai-zhishiku/scheduler/
├── run_pipeline.sh              # Linux/Mac 执行脚本
├── run_pipeline.ps1             # Windows 执行脚本
├── crontab.txt                  # Linux/Mac crontab 配置模板
└── setup_task_scheduler.ps1     # Windows 任务计划程序安装脚本
```

## 功能对比

| 功能 | GitHub Actions | 本地 cron | Windows Task Scheduler |
|------|---------------|-----------|----------------------|
| 定时触发 | ✅ | ✅ | ✅ |
| 手动触发 | workflow_dispatch | 直接执行脚本 | 右键"运行" |
| 日志记录 | Actions log | 文件日志 + 历史汇总 | 文件日志 + 历史汇总 |
| 日志回溯 | 90天保留 | 自定义天数 (默认30) | 自定义天数 (默认30) |
| 自动清理 | ❌ | ✅ | ✅ |
| 失败重试 | 需配置 | 脚本内无（可外层加循环） | schtasks 内置支持 |
| 环境变量 | secrets | .env 文件 | .env 文件 |

---

## 平台配置方法

### Linux/Mac (cron)

1. **编辑 crontab.txt**，将脚本路径替换为实际绝对路径：
```
0 8 * * * /真实路径/hw_cicd/scheduler/run_pipeline.sh
```

2. **安装 cron 任务**：
```bash
crontab hw_cicd/scheduler/crontab.txt
```

3. **验证**：
```bash
crontab -l                                 # 查看已安装任务
tail -f logs/collect_history.log           # 追踪日志
```

### Windows (Task Scheduler)

1. **管理员 PowerShell** 中运行：
```powershell
.\hw_cicd\scheduler\setup_task_scheduler.ps1
```

2. **验证**：
```cmd
schtasks /Query /TN AIMC-KnowledgeCollect   # 查看任务
```

3. **手动运行测试**：
```cmd
schtasks /Run /TN AIMC-KnowledgeCollect
```

---

## 日志系统

### 日志文件结构

```
logs/
├── collect_2026-05-10_064543.log   # 单次执行日志（时间戳命名）
├── collect_2026-05-10_160000.log
└── collect_history.log             # 汇总历史日志（所有执行）方便追溯
```

### 日志格式

每条日志带有 `[YYYY-MM-DD HH:MM:SS]` 时间戳前缀，包含：
- 采集参数记录
- 完整 pipeline 输出 (stdout + stderr)
- 执行耗时
- 退出码

### 日志清理策略

- **保留天数**: 默认 30 天，可通过 `$RetentionDays` / `RETENTION_DAYS` 参数调整
- **清理方式**: 脚本每次执行后自动清理过期日志
- **历史汇总日志** (`collect_history.log`): 不清除，持续追加

---

## 脚本参数

| 参数 | Linux/Mac | Windows | 说明 |
|------|-----------|---------|------|
| --sources | `SOURCES=` 环境变量 | `-Sources` | 数据源，逗号分隔 |
| --limit | `LIMIT=` 环境变量 | `-Limit` | 每源最大条数 |
| 日志保留 | `RETENTION_DAYS=` | `-RetentionDays` | 日志保留天数 |

### 使用示例

```bash
# Linux/Mac
./run_pipeline.sh --sources github --limit 5

# Windows
.\run_pipeline.ps1 -Sources github -Limit 5 -RetentionDays 14
```

---

## 与 GitHub Actions 的关系

| 项目 | GitHub Actions | 本地调度 |
|------|---------------|---------|
| 文件位置 | 仓库根 `.github/workflows/` | `hw_cicd/scheduler/` |
| 触发机制 | GitHub 服务器自动 | 本地 cron / Task Scheduler |
| 适用场景 | 主力方案 | 备选 / 本地开发测试 |
| 环境依赖 | GitHub Runner | 本地 Python 3.12 环境 |
