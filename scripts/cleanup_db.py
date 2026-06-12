#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库清理工具
保留最近N天的数据，删除过期数据并压缩数据库
"""

import argparse
import sys
from datetime import datetime, timedelta

try:
    from scripts.bootstrap import ensure_project_root
except ModuleNotFoundError:
    from bootstrap import ensure_project_root

project_root = ensure_project_root(__file__)

from scripts.infrastructure.db_manager import DatabaseManager
from scripts.infrastructure.logger import get_logger

logger = get_logger('db_cleanup')

def cleanup_database(days_to_keep: int = 30):
    """
    清理数据库，保留最近 days_to_keep 天的数据
    """
    # 定位数据库文件
    # 假设脚本在 scripts/ 目录下，数据库在 data/ 目录下
    db_path = project_root / "data" / "news_data.db"

    if not db_path.exists():
        print(f"数据库不存在: {db_path}")
        return

    print(f"正在连接数据库: {db_path}")
    db = DatabaseManager(db_path)

    # 计算截止日期
    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
    print(f"📅 清理策略: 保留 {days_to_keep} 天数据")
    print(f"✂️  截止日期: {cutoff_date} (早于此日期的将被删除)")

    try:
        # 1. 检查数据库状态
        total_count = db.get_row_count('news_articles')

        # 检查有多少数据需要删除
        # 注意：这里假设 collection_date 格式是 YYYY-MM-DD
        expired_count = db.get_row_count('news_articles', "collection_date < ?", (cutoff_date,))

        if expired_count == 0:
            print("✅ 没有过期数据需要清理")
            return

        print(f"📊 当前状态:")
        print(f"   - 总文章数: {total_count}")
        print(f"   - 过期文章: {expired_count}")

        # 2. 执行删除
        print(f"🗑️  正在删除过期数据...")
        # news_tags 表设置了 ON DELETE CASCADE，所以会自动清理关联标签
        deleted_rows = db.execute_update(
            "DELETE FROM news_articles WHERE collection_date < ?",
            (cutoff_date,)
        )
        print(f"✅ 已删除 {deleted_rows} 条过期记录")

        # 3. 执行 VACUUM 释放空间
        print("🧹 正在执行 VACUUM 优化数据库空间（这可能需要一点时间）...")
        original_size = db_path.stat().st_size / (1024 * 1024)
        db.vacuum()
        final_size = db_path.stat().st_size / (1024 * 1024)
        print("✅ 数据库优化完成")

        # 4. 打印结果
        print(f"📉 空间变化:")
        print(f"   - 原始大小: {original_size:.2f} MB")
        print(f"   - 当前大小: {final_size:.2f} MB")
        print(f"   - 释放空间: {original_size - final_size:.2f} MB")

    except Exception as e:
        logger.error(f"清理数据库失败: {e}")
        print(f"❌ 清理失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='数据库清理工具')
    parser.add_argument('--days', type=int, default=30, help='保留最近多少天的数据 (默认: 30)')
    args = parser.parse_args()

    cleanup_database(args.days)
