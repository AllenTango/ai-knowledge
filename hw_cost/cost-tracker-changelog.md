# CostTracker 功能调整记录

## 调整时间

2026-05-10

## 调整内容

### 1. 新增 CostTracker 类

在 `pipeline/model_client.py` 中添加了 `CostTracker` 类，功能：

| 方法 | 说明 |
|------|------|
| `record(usage, provider)` | 记录 LLM 调用的 token 消耗 |
| `estimated_cost(provider)` | 返回指定提供商的估算成本（元） |
| `report(provider)` | 打印成本报告（请求次数、tokens、成本） |

### 2. 国产模型价格表

价格单位：元/百万 tokens

| 提供商 | 输入价格 | 输出价格 |
|--------|---------|---------|
| deepseek | ¥1 | ¥2 |
| qwen | ¥4 | ¥12 |
| openai | ¥150 | ¥600 |

### 3. chat() 自动 record

在 `OpenAICompatibleProvider.chat()` 方法中，每次 API 调用成功后自动调用 `tracker.record()`。

### 4. Pipeline 集成

在 `pipeline/pipeline.py` 的 `main()` 函数末尾，非 dry_run 模式下自动调用 `tracker.report()` 输出成本报告。

### 5. 多模型轮询支持（2026-05-10 新增）

**新增功能**：支持一次 Pipeline 中使用多个 LLM 模型，按轮询策略分配任务。

#### 支持方式

| 方式 | 配置方法 | 示例 |
|------|---------|------|
| **环境变量** | `LLM_PROVIDER=deepseek,minimax` | 自动从 .env 读取多提供商 |
| **命令行参数** | `--providers deepseek,qwen` | 显式指定提供商 |
| **自动检测** | 不指定时自动检测已配置的 API Key | fallback 方案 |

#### 配置示例

```bash
# pipeline/.env - 方式1: 逗号分隔
LLM_PROVIDER=deepseek,minimax
DEEPSEEK_API_KEY=sk-xxx
MINIMAX_API_KEY=sk-yyy

# 或 pipeline/.env - 方式2: 仅指定默认，Qwen Key 存在时自动启用
LLM_PROVIDER=deepseek
DASHSCOPE_API_KEY=sk-yyy
```

#### 使用示例

```bash
# 使用单个模型（默认）
python pipeline/pipeline.py --sources github --limit 5

# 使用单个指定模型
python pipeline/pipeline.py --sources github --limit 5 --providers deepseek

# 使用多个模型轮询
python pipeline/pipeline.py --sources github --limit 5 --providers deepseek,qwen

# 从 LLM_PROVIDER 读取多提供商（需在 .env 中配置）
python pipeline/pipeline.py --sources github --limit 5
```

#### 输出示例

```
[INFO] 从 LLM_PROVIDER 环境变量读取多提供商: ['deepseek', 'minimax']
[INFO] 使用提供商: ['deepseek', 'minimax']
[INFO] 分析进度: 1/5 [deepseek]
[INFO] 分析进度: 2/5 [minimax]
...
[INFO] 分析阶段完成，共处理 5 条
[INFO] 模型使用统计: {'deepseek': 3, 'minimax': 2}
```

#### 文章字段

每篇分析后的文章会增加 `model_provider` 字段，记录使用了哪个模型。

## 调整原因

1. **成本可视化的需求**：每次 LLM 调用消耗的 tokens 和成本需要可追溯
2. **多提供商支持**：需要支持国产模型（deepseek、qwen）的不同定价策略
3. **国产化替代**：原有的 `MODEL_PRICES` 是美元定价，新增 `CHINA_MODEL_PRICES` 支持人民币定价
4. **自动化输出**：Pipeline 结束后自动输出成本报告，无需手动查询
5. **多模型轮询**：支持灵活切换和组合使用多个 LLM，提高可用性和成本优化

## 其他脚本检查

| 脚本 | 是否需要调整 | 说明 |
|------|:---:|------|
| `pipeline/pipeline.py` | ✅ 已完成 | 添加 tracker.report() + --providers 参数 + 多模型轮询 + LLM_PROVIDER 解析 |
| `pipeline/model_client.py` | ✅ 已完成 | 新增 CostTracker 类和 chat() 集成 |
| `mcp_knowledge_server.py` | ❌ 不需要 | MCP 服务只读知识库，不需要 LLM 调用 |
| `scheduler/run_pipeline.ps1` | ❌ 不需要 | 运行 pipeline.py，自动继承 LLM_PROVIDER 多提供商支持 |
| `scheduler/run_pipeline.sh` | ❌ 不需要 | 同上 |
| `.github/workflows/daily-collect.yml` | ❌ 不需要 | 同上，可通过 secrets 配置多个 API Key |

## 配置示例汇总

### 方式1: 仅使用单个模型（保持兼容）

```bash
# pipeline/.env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
```

### 方式2: 环境变量指定多模型

```bash
# pipeline/.env
LLM_PROVIDER=deepseek,minimax
DEEPSEEK_API_KEY=sk-xxx
MINIMAX_API_KEY=sk-yyy
```

### 方式3: 命令行指定模型

```bash
python pipeline/pipeline.py --providers deepseek,qwen --limit 10
```

### 方式4: 自动检测已配置的 Key（无 LLM_PROVIDER 逗号）

```bash
# pipeline/.env
# LLM_PROVIDER 未设置或为单个值，但配置了多个 API Key
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-yyy
OPENAI_API_KEY=sk-zzz
# → 自动使用所有已配置的模型轮询
```

## 成本对比测试记录（2026-05-10）

### 测试配置

```bash
# pipeline/.env
LLM_PROVIDER=deepseek,minimax
DEEPSEEK_API_KEY=sk-xxx
MINIMAX_API_KEY=sk-yyy

# 执行命令
python pipeline/pipeline.py --sources github --limit 2
```

### 成本对比结果

| 模型 | 请求次数 | Tokens (输入/输出) | 成本 (元) |
|------|:---:|------------------|----------:|
| DeepSeek | 1 | 372 (224/148) | ¥0.000520 |
| MiniMax | 1 | 644 (235/409) | ¥0.004325 |
| **总计** | 2 | 1,016 | **¥0.004845** |

### 价格表参考（元/百万 tokens）

| 模型 | 输入价格 | 输出价格 |
|------|---------|---------|
| DeepSeek | ¥1 | ¥2 |
| MiniMax | ¥1 | ¥10 |

### 分析

- MiniMax 输出 token 消耗较高（409 vs 148），导致成本显著增加
- 相同输入 token 数量下，成本相近；差异主要来自输出 token 量
- 实际应用中可根据任务复杂度选择合适的模型

## 成本报告存储

**当前状态**：

| 运行方式 | 成本报告输出 | 成本报告保存 |
|----------|:---:|:---:|
| `python pipeline/pipeline.py` | ✅ 控制台 | ❌ 未保存 |
| `scheduler/run_pipeline.ps1` | ✅ 控制台 | ✅ logs/collect_*.log |
| `scheduler/run_pipeline.sh` | ✅ 控制台 | ✅ logs/collect_*.log |
| GitHub Actions | ✅ 控制台 | ❌ 未保存 |

**说明**：
- Windows/Linux/macOS 定时任务脚本通过输出重定向将日志保存到 `logs/` 目录，成本报告随之保存
- 直接运行 `pipeline.py` 时成本报告仅输出到控制台，未写入文件

**当前日志文件**：
- `logs/collect_YYYY-MM-DD_HHMMSS.log` - 单次执行日志（包含成本报告）
- `logs/collect_history.log` - 历史汇总日志

**后续可选增强**：如需独立存储成本报告，可在 `pipeline.py` 中添加 FileHandler 或在 GitHub Actions 中添加日志保存步骤。

## 相关文件

| 文件 | 路径 |
|------|------|
| CostTracker 类 | `pipeline/model_client.py` |
| Pipeline 集成 | `pipeline/pipeline.py` |
| 价格配置 | `pipeline/model_client.py` 中的 `CHINA_MODEL_PRICES` |
| 全局实例 | `pipeline/model_client.py` 末尾的 `tracker = CostTracker()` |