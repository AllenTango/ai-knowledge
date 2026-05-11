# Scheduler 目录

定时任务脚本存放目录。

## 📋 当前任务

### daily_digest_cron.sh

每日知识简报推送脚本。

| 项目 | 说明 |
|------|------|
| 执行时间 | 每天 09:00 |
| 触发方式 | 系统 cron |
| 检查条件 | `knowledge/articles/` 当天是否有新条目 |
| 推送渠道 | QQ（通过 OpenClaw QQBot） |
| 日志位置 | `logs/daily_digest.log` |

### 添加/删除 cron

```bash
# 查看当前 cron
crontab -l

# 编辑 cron
crontab -e

# 手动执行测试
bash scheduler/daily_digest_cron.sh
```

### 日志管理

- 日志文件: `logs/daily_digest.log`
- 自动清理: 保留最近 30 天
