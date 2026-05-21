#!/bin/bash
#===============================================================================
# 每日知识简报定时推送
#
# 使用方法:
#   添加到 crontab:  crontab -e
#   内容: 0 9 * * * /home/dev/multi-agent-design/ai-knowledge/scheduler/daily_digest_cron.sh
#
# 日志记录:
#   日志文件: logs/daily_digest.log
#   保留最近 30 天日志
#===============================================================================

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/daily_digest.log"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 记录日志
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 进入项目目录
cd "$PROJECT_DIR"

log "========== 开始推送简报 =========="

# 检查是否有新条目
TODAY=$(date +%Y%m%d)
ARTICLE_DIR="$PROJECT_DIR/knowledge/articles"
TODAY_FILES=$(find "$ARTICLE_DIR" -maxdepth 1 -name "${TODAY}-*.json" 2>/dev/null | wc -l)

if [ "$TODAY_FILES" -eq 0 ]; then
    log "今日($TODAY)暂无新知识条目，跳过推送"
    exit 0
fi

log "发现 $TODAY_FILES 条新条目，开始推送..."

# 执行推送
python3 scripts/daily_digest.py --force 2>&1 | while read line; do
    log "$line"
done

# 清理 30 天前的日志
find "$LOG_DIR" -name "daily_digest*.log" -mtime +30 -delete

log "========== 推送完成 =========="
