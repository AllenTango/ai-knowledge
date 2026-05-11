#!/bin/bash

echo "=== V4 完整性检查 ==="
echo ""
echo "--- V1 基础（.opencode/agents 在 v1-skeleton 或 v2-automation 中） ---"
for f in AGENTS.md; do
    [ -f "$f" ] && echo "  [OK] $f" || echo "  [!!] $f (缺失)"
done

echo ""
echo "--- V2 自动化（pipeline 继承自 V3，V4 重写为 LangGraph 薄封装） ---"
for f in pipeline/pipeline.py; do
    [ -f "$f" ] && echo "  [OK] $f" || echo "  [!!] $f (缺失)"
done

echo ""
echo "--- V3 多 Agent（workflows + patterns + tests，V4 从 v3-multi-agent 拷贝继承） ---"
for f in workflows/graph.py workflows/nodes.py workflows/state.py scripts/model_client.py patterns/router.py patterns/supervisor.py; do
    [ -f "$f" ] && echo "  [OK] $f" || echo "  [!!] $f (缺失)"
done

echo ""
echo "--- V4 部署（分发 + Bot + 容器化） ---"
for f in Dockerfile docker-compose.yml bot/knowledge_bot.py distribution/formatter.py distribution/publisher.py daily_digest.py .openclaw/AGENTS.md .openclaw/SOUL.md .openclaw/knowledge-recommend/SKILL.md; do
    [ -f "$f" ] && echo "  [OK] $f" || echo "  [!!] $f (缺失)"
done
