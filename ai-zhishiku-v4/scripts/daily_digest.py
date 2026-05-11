#!/usr/bin/env python3
"""每日知识简报推送脚本

用法:
    python scripts/daily_digest.py              # 推送今天简报
    python scripts/daily_digest.py --date 20260511  # 推送指定日期
    python scripts/daily_digest.py --dry-run       # 仅显示，不发送
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# 静默日志
logging.basicConfig(level=logging.WARNING)


def should_push_now() -> bool:
    """判断当前是否在推送时间窗口内。
    
    推送窗口: 09:00-10:00 和 21:00-22:00
    """
    hour = datetime.now().hour
    return hour in (9, 21)


async def push_digest(date: str | None = None, dry_run: bool = False) -> bool:
    """推送简报。
    
    Args:
        date: 日期字符串，格式 YYYYMMDD，默认今天
        dry_run: True 则只打印不发送
    
    Returns:
        是否推送成功
    """
    from distribution.publisher import publish_daily_digest
    
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    
    print(f"📡 准备推送 {date} 简报...")
    
    if dry_run:
        from distribution.formatter import generate_daily_digest
        digest = generate_daily_digest("knowledge/articles", date, 5)
        print("\n=== 简报预览 ===")
        print(digest["telegram"][:500] + "..." if len(digest["telegram"]) > 500 else digest["telegram"])
        print("=== 预览结束 ===\n")
        return True
    
    results = await publish_daily_digest(
        knowledge_dir="knowledge/articles",
        date=date,
        top_n=5,
        channels=["openclaw"]
    )
    
    all_success = True
    for r in results:
        if r.success:
            print(f"✅ {r.channel}: message_id={r.message_id}")
        else:
            print(f"❌ {r.channel}: error={r.error}")
            all_success = False
    
    return all_success


async def main():
    parser = argparse.ArgumentParser(description="每日知识简报推送")
    parser.add_argument("--date", help="日期 YYYYMMDD，默认今天")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不发送")
    parser.add_argument("--force", action="store_true", help="无视时间窗口强制推送")
    args = parser.parse_args()
    
    if not args.force and not should_push_now():
        hour = datetime.now().hour
        print(f"⏰ 当前时间 ({hour}:00) 不在推送窗口内 (09:00-10:00, 21:00-22:00)")
        print("   使用 --force 强制推送，或等待到了窗口时间再试")
        sys.exit(0)
    
    success = await push_digest(args.date, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
