# AI 知识库 · 编码规范 v0.2

## 要做什么
- Python 用 black 格式化，行长度 150
- TypeScript strict mode（`strict: true`）
- 所有公开函数必须有文档
  - Python：Google 风格 docstring（中文）
  - TypeScript：TSdoc 风格（中文说明，代码示例保留英文）

## 不做什么
- 不用任何魔法字符串
  - 业务枚举值（如 `pending_review`）→ Python `Enum` / TypeScript `const enum`
  - 重复出现 ≥2 次的字符串 → 提取为 `const`
  - 独立使用一次的字符串不强制提取
- 不允许 TODO 提交到 main
  - 格式：`TODO(high): ...` 允许，`TODO(low): ...` 或无标注的 `TODO` 拒绝
  - 执行：pre-commit hook 拦截

## 边界 & 验收
- 单测覆盖率 ≥ 80%（行覆盖率，整体项目）
- CI 验证规范文件变更

## 怎么验证
- pre-commit hook（commit 时）：black + ruff + pytest（abort on fail）
- GitHub Actions CI（push + PR + 定时）：
  - 每日：lint + test
  - 每周：lint + test + coverage 全量报告

## 工具链选型

| 语言 | Formatter | Linter | 测试 | 覆盖率 |
|---|---|---|---|---|
| Python | black | ruff（lint + import 排序） | pytest | coverage.py |
| TypeScript | Prettier | ESLint + eslint-plugin-tsdoc | Vitest | Vitest 内置 v8 |

## 配置要点
- black：`--line-length 150`（需显式配置，与 ruff 统一）
- ruff：`--select I`（isort）+ `--line-length 150` + `--target-version py312`
- ruff isort profile：`black`（与 formatter 兼容）
- pre-commit：black + ruff + pytest，fail-fast abort
- TypeScript：`tsconfig.json` → `strict: true`
- Vitest coverage：`provider: 'v8'`

## 规范管理
- 版本化：`coding-standards.md` 随项目迭代更新
- CI 验证：workflow 检查规范文件变更
- 决策人：单人决策（确保变更高效）
