#!/bin/bash
# =============================================================================
# 知识库自动化采集 —— Linux/Mac 本地定时任务脚本
#
# 用法:
#   ./run_pipeline.sh                  # 默认采集 github+rss, limit 20
#   ./run_pipeline.sh --limit 5        # 自定义 limit
#   ./run_pipeline.sh --sources github # 仅采集 GitHub
#
# 日志:
#   logs/collect_YYYY-MM-DD_HHMMSS.log (单次执行日志)
#   logs/collect_history.log            (汇总历史日志)
#   自动清理 30 天前的日志文件
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

SOURCES="${SOURCES:-github,rss}"
LIMIT="${LIMIT:-20}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$LOG_DIR"

TIMESTAMP=$(date -u +"%Y-%m-%d_%H%M%S")
LOG_FILE="$LOG_DIR/collect_${TIMESTAMP}.log"
HISTORY_LOG="$LOG_DIR/collect_history.log"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

cleanup_old_logs() {
    log "清理 ${RETENTION_DAYS} 天前的日志..."
    find "$LOG_DIR" -name "collect_*.log" -type f -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
}

run_pipeline() {
    log "========== 知识库采集开始 =========="

    cd "$PROJECT_DIR"

    log "参数: sources=$SOURCES, limit=$LIMIT"

    START_TIME=$(date +%s)

    PYTHONPATH=. python3 pipeline/pipeline.py \
        --sources "$SOURCES" \
        --limit "$LIMIT" \
        --verbose \
        2>&1 | tee -a "$LOG_FILE"

    EXIT_CODE=${PIPESTATUS[0]}
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    if [ "$EXIT_CODE" -eq 0 ]; then
        log "采集成功，耗时 ${DURATION}s"
    else
        log "采集失败，退出码: $EXIT_CODE，耗时 ${DURATION}s"
    fi

    log "========== 采集结束 =========="

    return $EXIT_CODE
}

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --sources) SOURCES="$2"; shift 2 ;;
            --limit)   LIMIT="$2";   shift 2 ;;
            *)         shift ;;
        esac
    done

    run_pipeline
    RESULT=$?

    cat "$LOG_FILE" >> "$HISTORY_LOG"
    echo "" >> "$HISTORY_LOG"

    cleanup_old_logs

    exit $RESULT
}

main "$@"
