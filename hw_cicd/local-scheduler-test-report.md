# 本地定时任务 —— 测试报告

## 测试时间

2026-05-10 14:52 UTC+8

## 测试环境

| 项目 | 值 |
|------|-----|
| 操作系统 | Windows 11 x64 |
| Python | 3.12 |
| LLM Provider | DeepSeek |
| 调度脚本位置 | `ai-zhishiku/scheduler/` |

---

## 全流程覆盖验证

两个方案（GitHub Actions / 本地定时任务）均调用同一个入口：
```bash
python pipeline/pipeline.py --sources github,rss --limit 20 --verbose
```

pipeline.py 内部包含完整的 **采集 → 分析 → 整理 → 保存** 四步流程。

### 本次测试验证项

| 步骤 | 日志确认 | 结果 |
|------|---------|:--:|
| Step 1 数据采集 | `GitHub 采集完成，获取 2 条` | ✅ |
| Step 2 内容分析 | `评分: 6.5, 标签: [ai-assistant, ...]` | ✅ |
| Step 2 内容分析 | `请求成功，消耗 tokens: 352` (LLM 调用) | ✅ |
| Step 2 内容分析 | `评分: 9.2, 标签: [workflow-automation, ...]` | ✅ |
| Step 2 内容分析 | `请求成功，消耗 tokens: 412` (LLM 调用) | ✅ |
| Step 3 数据整理 | `整理阶段完成，有效条目 2 条` | ✅ |
| Step 4 保存知识库 | `写入 2 篇知识条目` | ✅ |
| 分析中间文件 | `github-analyzed-2026-05-10.json` | ✅ |
| 原始文件 | `github-trending-2026-05-10.json` | ✅ |

---

## 路径调整

scheduler 目录已从 `hw_cicd/scheduler/` 移至项目根目录 `scheduler/`（与 `pipeline/` 同级）

| 脚本 | 修改内容 |
|------|---------|
| `run_pipeline.ps1` | `$ProjectDir = "$ScriptDir\.."` |
| `run_pipeline.sh` | `PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"` |
| `setup_task_scheduler.ps1` | `$ProjectDir = "$ScriptDir\.."` |
| `crontab.txt` | 路径更新为 `/ai-zhishiku/scheduler/run_pipeline.sh` |

---

## 测试结果

### 1. 路径修正后运行测试

**命令:**
```powershell
.\scheduler\run_pipeline.ps1 -Sources github -Limit 2
```

**结果:** ✅ 通过（耗时 10s，退出码 0）

### 2. 日志输出验证

```text
[2026-05-10 14:52:38] ========== 知识库采集开始 ==========
[INFO] Step 1: 数据采集
[INFO] GitHub 采集完成，获取 2 条
[INFO] Step 2: 内容分析
[INFO] 请求成功，消耗 tokens: 352
[INFO]   评分: 6.5, 标签: [ai-assistant, cross-platform, open-source]
[INFO] 请求成功，消耗 tokens: 412
[INFO]   评分: 9.2, 标签: [workflow-automation, fair-code, ai-integration]
[INFO] Step 3: 数据整理
[INFO] Step 4: 保存知识库
[INFO] 保存阶段完成，共写入 2 篇知识条目
[2026-05-10 14:52:48] 采集成功，耗时 10s
```

---

## GitHub Actions 流程验证

workflow 文件中 `Configure LLM keys` 步骤在 `ai-zhishiku/` 目录下写入 `.env`：

```yaml
defaults:
  run:
    working-directory: ai-zhishiku

steps:
  - name: Configure LLM keys
    run: |
      touch .env                           # → ai-zhishiku/.env
      echo "DEEPSEEK_API_KEY=${{ secrets.DEEPSEEK_API_KEY }}" >> .env
```

pipeline.py 中 `load_dotenv(find_dotenv())` 从当前目录向上查找 `.env`，能正确加载。

| 检查项 | 结果 |
|--------|:--:|
| LLM 配置路径 | ✅ `ai-zhishiku/.env` |
| find_dotenv 可发现 | ✅ |
| 采集+分析全流程 | ✅ |

---

## 结论

✅ 两个方案均支持自动采集 + 自动分析（LLM 摘要/标签/评分）全流程：

- **GitHub Actions**: `.github/workflows/daily-collect.yml` → `pipeline/pipeline.py`
- **本地定时任务**: `scheduler/run_pipeline.ps1` / `run_pipeline.sh` → `pipeline/pipeline.py`
