# Skill 机制问答

## 问题1：description 字段如何触发语义匹配？

**工作原理**：

description 字段用于**语义匹配**（Semantic Matching），当用户提出需求时，OpenCode 系统会将用户的自然语言描述与所有已加载 Skill 的 description 进行语义相似度计算，选择最匹配的一个。

**匹配流程**：
1. 用户输入需求（如"帮我抓取 GitHub 热门项目"）
2. 系统提取用户意图的语义向量
3. 与各 Skill description 的语义向量进行相似度计算
4. 选取相似度最高的 Skill 作为执行方案

**设计建议**：
- description 应描述**使用场景**，而非具体操作步骤
- 使用领域术语（如"采集 GitHub 热门开源项目"而非"抓取网页"）
- 包含关键词以提高检索命中概率

---

## 问题2：allowed-tools 是硬性限制还是建议？

**性质**：allowed-tools 是**硬性限制**，非建议。

**机制**：
1. 加载 Skill 时，系统解析 YAML frontmatter 中的 allowed-tools 列表
2. Skill 执行时，Agent 的工具权限被限制为该列表中的工具
3. 若 Agent 尝试使用未授权工具，操作将被阻止或报错

**示例**：

```yaml
allowed-tools:
  - Read
  - Glob
  - WebFetch
```

若 Agent 尝试执行 `Write` 或 `Bash`，系统将拒绝该操作。

**设计建议**：
- 仅列出该 Skill 必须使用的工具，遵循最小权限原则
- 若某工具为可选，应在 Skill 文档正文中说明

---

## 总结

| 字段 | 作用 | 性质 |
|------|------|------|
| description | 语义匹配触发器 | 建议（影响匹配精度） |
| allowed-tools | 工具权限白名单 | 硬性限制（强制生效） |