# GitHub Actions 工作流配置说明

## 仓库结构

```
Git 仓库根: D:\Xuexi\MultiAgentDesign  (remote: github.com/AllenTango/multi-agent-design)
                                    │
                     ┌──────────────┴──────────────┐
                     │  ai-zhishiku/                │  ← 子项目目录
                     │  └── .github/workflows/      │  ← 仅作本地参考/版本管理
                     │                              │
                     │  D:\Xuexi\MultiAgentDesign    │
                     │  └── .github/workflows/       │  ← ✅ 实际生效的位置
```

## 核心规则

**GitHub Actions 只加载仓库根目录下的 `.github/workflows/` 文件。**

一个仓库可以有多个 action 文件（例如 `daily-collect.yml` + `deploy.yml`），但它们**全部必须**在仓库根目录的 `.github/workflows/` 下。子目录内的 `.github/workflows/` 被 GitHub 完全忽略。

## 为什么项目内保留了一份？

两份 `daily-collect.yml`，分工不同：

| 位置 | 用途 | 是否生效 |
|------|------|---------|
| `MultiAgentDesign/.github/workflows/daily-collect.yml` | **实际执行** | ✅ 是 |
| `ai-zhishiku/.github/workflows/daily-collect.yml` | **本地参考/版本追踪** | ❌ 否 |

项目内保留副本的好处：
- 随项目代码一同版本管理，便于查看和修改历史
- 作为子项目的独立文档，说明其 CI 配置意图
- 方便在子项目层面进行 code review

## 调整要点汇总

| 配置项 | 子项目内的副本 | 仓库根的实际文件 |
|--------|---------------|-----------------|
| 是否被 GitHub 加载 | ❌ | ✅ |
| 文件头部注释 | 标注了"仅作参考" | 无额外注释 |
| `working-directory` | `ai-zhishiku` | `ai-zhishiku` |
| `cache-dependency-path` | `ai-zhishiku/requirements.txt` | `ai-zhishiku/requirements.txt` |
| commit 路径 | `ai-zhishiku/knowledge/` | `ai-zhishiku/knowledge/` |

## 全流程覆盖

workflow 运行 `python pipeline/pipeline.py`，内部包含采集和 LLM 分析全流程：

| 步骤 | 说明 |
|------|------|
| Step 1 采集 | GitHub Search API + RSS 源抓取 |
| Step 2 分析 | LLM 生成中文摘要 / 标签 / 评分 |
| Step 3 整理 | 去重 + 格式标准化 |
| Step 4 保存 | 写入 knowledge/articles/ |

LLM 密钥通过 `secrets` 注入 → 写入 `ai-zhishiku/.env` → `pipeline.py` 通过 `find_dotenv()` 加载。

## 本地备选方案

当 GitHub Actions 不可用时，使用 `scheduler/` 下的本地脚本（详见 `local-scheduler-design.md`）。

## 注意事项

1. `working-directory: ai-zhishiku` 仅影响 `run` 步骤，不影响 `uses` 和 `git` 命令
2. `git` 命令路径始终相对于仓库根，不受 `working-directory` 影响
3. 修改 workflow 时建议同步更新两处文件，或直接编辑仓库根目录版本
4. 仓库根目录不要添加 `.gitignore` 忽略 `.github/workflows/` 中的文件
