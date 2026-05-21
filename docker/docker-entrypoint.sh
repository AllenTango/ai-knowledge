#!/bin/bash
set -euo pipefail

MODE="${1:-cron}"

case "$MODE" in
    cron)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动定时调度服务（supercronic）..."
        exec supercronic /app/docker/crontab.txt
        ;;

    mcp)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动 MCP HTTP API 服务..."
        exec python3 /app/scripts/mcp_http_server.py
        ;;

    pipeline)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 手动执行流水线..."
        exec python3 /app/pipeline/pipeline.py --sources "${SOURCES:-github,rss}" --limit "${LIMIT:-20}" --verbose
        ;;

    digest)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 手动执行每日简报..."
        exec python3 /app/daily_digest.py --channels "${CHANNELS:-telegram}" --top-n "${TOP_N:-5}" --verbose
        ;;

    *)
        echo "用法: $0 {cron|mcp|pipeline|digest}"
        echo "  cron     - 启动定时调度服务（supercronic）"
        echo "  mcp      - 启动 MCP HTTP API 服务（端口 8080）"
        echo "  pipeline - 手动执行一次采集流水线"
        echo "  digest   - 手动执行一次每日简报"
        exit 1
        ;;
esac
