# HEARTBEAT.md - 定时任务

_小芽会在心跳时检查这些任务。_

## 📡 每日简报推送

每天 **早上 9:00** 通过 cron 推送简报到 QQ。

### 推送机制

- **触发方式**: 系统 cron（`scheduler/daily_digest_cron.sh`）
- **推送时间**: 每天 09:00
- **判断逻辑**: 检查 `knowledge/articles/` 是否有当天新条目（`YYYYMMDD-*.json`）
- **渠道**: OpenClaw QQBot（`channels=["openclaw"]`）

### 推送脚本

```bash
# 手动触发推送
bash scheduler/daily_digest_cron.sh

# 或直接运行 Python
python3 scripts/daily_digest.py --force
```

### 日志

- 路径: `logs/daily_digest.log`
- 保留: 30 天

### 注意事项

- cron 负责定时，小芽的心跳仅做辅助检查
- 如果当天没有新条目，脚本会自动跳过不推送
- 推送成功后会在日志中记录 message_id

