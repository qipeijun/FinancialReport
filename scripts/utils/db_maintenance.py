#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库维护工具

功能：
- 索引优化和重建
- 数据库清理和碎片整理
- 健康检查和诊断
- 数据归档和清理
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import argparse

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import get_logger
from scripts.utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_statistics
)

logger = get_logger('db_maintenance')


class DatabaseMaintenance:
    """数据库维护工具"""

    def __init__(self, db_path: Path):
        """
        初始化数据库维护工具

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    def optimize_indexes(self, rebuild: bool = False):
        """
        优化索引

        Args:
            rebuild: 是否重建所有索引
        """
        print_header("📊 索引优化")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if rebuild:
                print_info("正在重建索引...")

                # 1. 删除冗余索引
                redundant_indexes = [
                    'idx_articles_date_created',
                    'idx_articles_date_published',
                    'idx_articles_source_date',
                ]

                for idx_name in redundant_indexes:
                    try:
                        cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")
                        logger.info(f"删除冗余索引: {idx_name}")
                    except sqlite3.Error as e:
                        logger.warning(f"删除索引失败 {idx_name}: {e}")

                # 2. 创建优化的复合索引
                optimized_indexes = [
                    # 日期 + 来源 + 发布时间（覆盖80%查询）
                    """
                    CREATE INDEX IF NOT EXISTS idx_date_source_published
                    ON news_articles(collection_date, source_id, published DESC)
                    """,

                    # 来源 + 日期（反向查询）
                    """
                    CREATE INDEX IF NOT EXISTS idx_source_date
                    ON news_articles(source_id, collection_date DESC)
                    """,

                    # AI分析专用索引（仅包含有内容的文章）
                    """
                    CREATE INDEX IF NOT EXISTS idx_analysis_ready
                    ON news_articles(collection_date, published DESC)
                    WHERE (summary IS NOT NULL AND summary != '')
                       OR (content IS NOT NULL AND content != '')
                    """,
                ]

                for sql in optimized_indexes:
                    try:
                        cursor.execute(sql)
                        logger.info(f"创建索引成功")
                    except sqlite3.Error as e:
                        logger.error(f"创建索引失败: {e}")

                conn.commit()
                print_success("✓ 索引重建完成")

            # 3. 更新统计信息
            print_info("更新统计信息...")
            cursor.execute("ANALYZE")
            conn.commit()
            print_success("✓ 统计信息已更新")

            # 4. 优化查询计划
            print_info("优化查询计划...")
            cursor.execute("PRAGMA optimize")
            conn.commit()
            print_success("✓ 查询计划已优化")

        logger.info("索引优化完成")

    def vacuum(self):
        """执行VACUUM操作（清理碎片、回收空间）"""
        print_header("🧹 数据库清理")

        # 获取优化前大小
        size_before = self.db_path.stat().st_size / (1024 * 1024)  # MB
        print_info(f"当前数据库大小: {size_before:.2f} MB")

        print_info("正在执行 VACUUM（可能需要几分钟）...")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("VACUUM")

        # 获取优化后大小
        size_after = self.db_path.stat().st_size / (1024 * 1024)
        saved = size_before - size_after

        print_success(f"✓ VACUUM 完成")
        print_statistics({
            '优化前': f'{size_before:.2f} MB',
            '优化后': f'{size_after:.2f} MB',
            '节省空间': f'{saved:.2f} MB ({saved/size_before*100:.1f}%)'
        })

        logger.info(f"VACUUM完成，节省 {saved:.2f} MB")

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态报告
        """
        print_header("🏥 数据库健康检查")

        health = {
            'status': 'healthy',
            'checks': {},
            'warnings': [],
            'errors': []
        }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. 完整性检查
            print_info("检查数据完整性...")
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]

            if integrity_result == 'ok':
                health['checks']['integrity'] = 'ok'
                print_success("✓ 数据完整性正常")
            else:
                health['status'] = 'error'
                health['errors'].append(f'完整性检查失败: {integrity_result}')
                print_error(f"✗ 数据完整性异常: {integrity_result}")

            # 2. 碎片检查
            print_info("检查碎片率...")
            cursor.execute("PRAGMA freelist_count")
            fragmentation = cursor.fetchone()[0]
            health['checks']['fragmentation_pages'] = fragmentation

            if fragmentation > 1000:
                health['warnings'].append(f'碎片较多: {fragmentation} 页，建议执行 VACUUM')
                print_warning(f"⚠ 碎片页数: {fragmentation}（建议清理）")
            else:
                print_success(f"✓ 碎片页数: {fragmentation}（正常）")

            # 3. 索引检查
            print_info("检查索引...")
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='index' AND tbl_name='news_articles'
            """)
            index_count = cursor.fetchone()[0]
            health['checks']['index_count'] = index_count

            # 合理范围：4-6个索引
            if index_count < 4:
                health['warnings'].append(f'索引数量偏少: {index_count}')
                print_warning(f"⚠ 索引数量: {index_count}（偏少）")
            elif index_count > 8:
                health['warnings'].append(f'索引数量过多: {index_count}，可能影响写入性能')
                print_warning(f"⚠ 索引数量: {index_count}（过多）")
            else:
                print_success(f"✓ 索引数量: {index_count}（正常）")

            # 4. 统计信息检查
            print_info("检查统计信息...")
            cursor.execute("SELECT COUNT(*) FROM sqlite_stat1")
            stats_count = cursor.fetchone()[0]
            health['checks']['statistics_tables'] = stats_count

            if stats_count == 0:
                health['warnings'].append('缺少统计信息，建议执行 ANALYZE')
                print_warning("⚠ 缺少统计信息")
            else:
                print_success(f"✓ 统计信息: {stats_count} 个表")

            # 5. 数据量检查
            print_info("检查数据量...")
            cursor.execute("SELECT COUNT(*) FROM news_articles")
            article_count = cursor.fetchone()[0]
            health['checks']['article_count'] = article_count
            print_info(f"文章总数: {article_count}")

            # 6. 数据库大小
            db_size_mb = self.db_path.stat().st_size / (1024 * 1024)
            health['checks']['db_size_mb'] = round(db_size_mb, 2)
            print_info(f"数据库大小: {db_size_mb:.2f} MB")

        # 总结
        if health['errors']:
            health['status'] = 'error'
            print_error(f"\n❌ 健康检查发现 {len(health['errors'])} 个错误")
        elif health['warnings']:
            health['status'] = 'warning'
            print_warning(f"\n⚠️  健康检查发现 {len(health['warnings'])} 个警告")
        else:
            print_success("\n✅ 数据库健康状况良好")

        return health

    def cleanup_old_data(self, days_to_keep: int = 90, dry_run: bool = True):
        """
        清理旧数据

        Args:
            days_to_keep: 保留最近N天的数据
            dry_run: 是否为模拟运行（不实际删除）
        """
        print_header(f"🗑️  数据清理（保留 {days_to_keep} 天）")

        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        print_info(f"截止日期: {cutoff_date}")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 查询将被删除的数据量
            cursor.execute("""
                SELECT COUNT(*) FROM news_articles
                WHERE collection_date < ?
            """, (cutoff_date,))
            to_delete_count = cursor.fetchone()[0]

            if to_delete_count == 0:
                print_info("没有需要清理的数据")
                return

            print_warning(f"将删除 {to_delete_count} 条旧数据")

            if dry_run:
                print_info("🔍 模拟运行模式（不会实际删除）")
                print_info("如需执行删除，请使用 --no-dry-run 参数")
            else:
                # 实际删除
                cursor.execute("""
                    DELETE FROM news_articles
                    WHERE collection_date < ?
                """, (cutoff_date,))

                deleted = cursor.rowcount
                conn.commit()

                print_success(f"✓ 已删除 {deleted} 条数据")
                logger.info(f"清理了 {deleted} 条旧数据（{cutoff_date}之前）")

    def full_maintenance(self):
        """执行完整维护流程"""
        print_header("🔧 执行完整数据库维护")

        # 1. 健康检查
        health = self.health_check()

        # 2. 根据健康状况决定维护策略
        if health['checks'].get('fragmentation_pages', 0) > 1000:
            self.vacuum()

        if health['checks'].get('statistics_tables', 0) == 0:
            self.optimize_indexes(rebuild=False)

        # 3. 最终优化
        print_header("🎯 最终优化")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA optimize")
        print_success("✓ 数据库维护完成")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库维护工具')
    parser.add_argument(
        '--db-path',
        type=str,
        default='data/news_data.db',
        help='数据库文件路径'
    )
    parser.add_argument(
        '--optimize',
        action='store_true',
        help='执行完整优化'
    )
    parser.add_argument(
        '--rebuild-indexes',
        action='store_true',
        help='重建索引'
    )
    parser.add_argument(
        '--vacuum',
        action='store_true',
        help='执行VACUUM'
    )
    parser.add_argument(
        '--health-check',
        action='store_true',
        help='健康检查'
    )
    parser.add_argument(
        '--cleanup',
        type=int,
        metavar='DAYS',
        help='清理N天之前的数据'
    )
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='实际执行删除（与--cleanup配合使用）'
    )

    args = parser.parse_args()

    # 构建数据库路径
    db_path = PROJECT_ROOT / args.db_path

    try:
        maintenance = DatabaseMaintenance(db_path)

        if args.optimize:
            maintenance.full_maintenance()
        elif args.rebuild_indexes:
            maintenance.optimize_indexes(rebuild=True)
        elif args.vacuum:
            maintenance.vacuum()
        elif args.health_check:
            maintenance.health_check()
        elif args.cleanup:
            maintenance.cleanup_old_data(
                days_to_keep=args.cleanup,
                dry_run=not args.no_dry_run
            )
        else:
            # 默认：健康检查
            maintenance.health_check()

    except Exception as e:
        print_error(f"执行失败: {e}")
        logger.error(f"数据库维护失败", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
