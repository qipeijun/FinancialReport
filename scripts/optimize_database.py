#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库索引优化脚本

功能：
1. 添加复合索引，优化常用查询
2. 分析并优化数据库结构
3. 配置FTS5全文检索同步
4. 清理和维护数据库

使用：
    python scripts/optimize_database.py              # 优化默认数据库
    python scripts/optimize_database.py --analyze    # 分析查询性能
    python scripts/optimize_database.py --vacuum     # 清理压缩数据库
"""

import sqlite3
import argparse
from pathlib import Path
from typing import List, Tuple
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def print_step(text: str):
    """打印步骤"""
    print(f"\n📍 {text}")


def print_success(text: str):
    """打印成功"""
    print(f"✅ {text}")


def print_info(text: str):
    """打印信息"""
    print(f"ℹ️  {text}")


def print_warning(text: str):
    """打印警告"""
    print(f"⚠️  {text}")


def check_existing_indexes(conn: sqlite3.Connection) -> dict:
    """
    检查现有索引
    
    Returns:
        {table_name: [(index_name, index_sql), ...]}
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, tbl_name, sql 
        FROM sqlite_master 
        WHERE type='index' AND sql IS NOT NULL
        ORDER BY tbl_name, name
    """)
    
    indexes = {}
    for row in cursor.fetchall():
        index_name, table_name, sql = row
        if table_name not in indexes:
            indexes[table_name] = []
        indexes[table_name].append((index_name, sql))
    
    return indexes


def add_composite_indexes(conn: sqlite3.Connection, dry_run: bool = False):
    """
    添加复合索引
    
    复合索引设计原则：
    1. 左前缀原则：最常用于WHERE的字段放左边
    2. 等值优先：等值查询>范围查询
    3. 区分度高：区分度高的字段优先
    """
    
    print_step("添加复合索引")
    
    # 复合索引列表
    indexes = [
        # 1. 日期范围查询 + 发布时间排序（最常用）
        {
            'name': 'idx_articles_date_published',
            'table': 'news_articles',
            'columns': '(collection_date, published)',
            'desc': '优化日期范围查询并按发布时间排序'
        },
        
        # 2. 日期范围查询 + 创建时间排序（备用排序）
        {
            'name': 'idx_articles_date_created',
            'table': 'news_articles',
            'columns': '(collection_date, created_at)',
            'desc': '优化日期范围查询并按创建时间排序'
        },
        
        # 3. 来源 + 日期组合查询
        {
            'name': 'idx_articles_source_date',
            'table': 'news_articles',
            'columns': '(source_id, collection_date)',
            'desc': '优化按来源筛选的日期范围查询'
        },
        
        # 4. 来源 + 发布时间（来源分析）
        {
            'name': 'idx_articles_source_published',
            'table': 'news_articles',
            'columns': '(source_id, published)',
            'desc': '优化按来源的时间序列查询'
        },
    ]
    
    cursor = conn.cursor()
    created_count = 0
    skipped_count = 0
    
    for idx in indexes:
        try:
            # 检查索引是否已存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx['name'],)
            )
            
            if cursor.fetchone():
                print_info(f"  跳过（已存在）: {idx['name']}")
                skipped_count += 1
                continue
            
            # 创建索引
            sql = f"CREATE INDEX IF NOT EXISTS {idx['name']} ON {idx['table']} {idx['columns']}"
            
            if dry_run:
                print_info(f"  [模拟] {sql}")
                print_info(f"           说明: {idx['desc']}")
            else:
                cursor.execute(sql)
                print_success(f"  已创建: {idx['name']}")
                print_info(f"           说明: {idx['desc']}")
            
            created_count += 1
            
        except sqlite3.Error as e:
            print_warning(f"  创建失败: {idx['name']} - {e}")
    
    if not dry_run:
        conn.commit()
    
    print()
    print_success(f"复合索引优化完成：新增 {created_count} 个，跳过 {skipped_count} 个")


def setup_fts5_triggers(conn: sqlite3.Connection, dry_run: bool = False):
    """
    配置FTS5全文检索自动同步触发器
    
    触发器确保：
    1. 插入新文章时自动添加到FTS5索引
    2. 更新文章时自动更新FTS5索引
    3. 删除文章时自动从FTS5索引移除
    """
    
    print_step("配置FTS5全文检索同步")
    
    # 检查FTS5表是否存在
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='news_articles_fts'
    """)
    
    if not cursor.fetchone():
        print_info("  FTS5表不存在，跳过触发器配置")
        return
    
    triggers = [
        # INSERT触发器
        {
            'name': 'news_articles_fts_insert',
            'sql': '''
                CREATE TRIGGER IF NOT EXISTS news_articles_fts_insert AFTER INSERT ON news_articles
                BEGIN
                    INSERT INTO news_articles_fts(rowid, title, summary, content)
                    VALUES (new.id, new.title, new.summary, new.content);
                END
            ''',
            'desc': '插入新文章时自动添加到全文索引'
        },
        
        # UPDATE触发器
        {
            'name': 'news_articles_fts_update',
            'sql': '''
                CREATE TRIGGER IF NOT EXISTS news_articles_fts_update AFTER UPDATE ON news_articles
                BEGIN
                    UPDATE news_articles_fts 
                    SET title=new.title, summary=new.summary, content=new.content
                    WHERE rowid=new.id;
                END
            ''',
            'desc': '更新文章时自动更新全文索引'
        },
        
        # DELETE触发器
        {
            'name': 'news_articles_fts_delete',
            'sql': '''
                CREATE TRIGGER IF NOT EXISTS news_articles_fts_delete AFTER DELETE ON news_articles
                BEGIN
                    DELETE FROM news_articles_fts WHERE rowid=old.id;
                END
            ''',
            'desc': '删除文章时自动从全文索引移除'
        },
    ]
    
    created_count = 0
    
    for trigger in triggers:
        try:
            # 检查触发器是否已存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger['name'],)
            )
            
            if cursor.fetchone():
                print_info(f"  跳过（已存在）: {trigger['name']}")
                continue
            
            if dry_run:
                print_info(f"  [模拟] 创建触发器: {trigger['name']}")
                print_info(f"         说明: {trigger['desc']}")
            else:
                cursor.execute(trigger['sql'])
                print_success(f"  已创建: {trigger['name']}")
                print_info(f"           说明: {trigger['desc']}")
            
            created_count += 1
            
        except sqlite3.Error as e:
            print_warning(f"  创建失败: {trigger['name']} - {e}")
    
    if not dry_run:
        conn.commit()
    
    print()
    print_success(f"FTS5触发器配置完成：新增 {created_count} 个")


def analyze_database(conn: sqlite3.Connection):
    """
    分析数据库统计信息
    
    SQLite ANALYZE命令：
    - 收集表和索引的统计信息
    - 帮助查询优化器选择最佳执行计划
    - 建议定期运行（特别是数据量变化大时）
    """
    
    print_step("分析数据库统计信息")
    
    cursor = conn.cursor()
    
    try:
        # 收集统计信息
        cursor.execute("ANALYZE")
        conn.commit()
        print_success("数据库统计信息已更新")
        
        # 显示统计信息
        cursor.execute("SELECT * FROM sqlite_stat1 ORDER BY tbl, idx")
        stats = cursor.fetchall()
        
        if stats:
            print()
            print_info("索引使用统计：")
            print(f"  {'表名':<30} {'索引名':<40} {'统计信息'}")
            print(f"  {'-'*30} {'-'*40} {'-'*20}")
            for row in stats:
                tbl, idx, stat = row
                print(f"  {tbl:<30} {idx or '(无索引)':<40} {stat}")
        
    except sqlite3.Error as e:
        print_warning(f"分析失败: {e}")


def vacuum_database(conn: sqlite3.Connection):
    """
    清理压缩数据库
    
    VACUUM命令：
    - 重建数据库文件，回收空闲空间
    - 优化数据库结构
    - 可能会缩小数据库文件大小
    
    注意：VACUUM会锁定整个数据库，耗时较长
    """
    
    print_step("清理压缩数据库")
    print_warning("此操作会锁定数据库，请确保没有其他程序正在使用")
    
    cursor = conn.cursor()
    
    try:
        # 获取当前大小
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        size_before = cursor.fetchone()[0]
        
        # 执行VACUUM
        cursor.execute("VACUUM")
        
        # 获取新大小
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        size_after = cursor.fetchone()[0]
        
        saved = size_before - size_after
        saved_mb = saved / (1024 * 1024)
        
        print_success(f"数据库已清理压缩")
        print_info(f"  原大小: {size_before / (1024 * 1024):.2f} MB")
        print_info(f"  新大小: {size_after / (1024 * 1024):.2f} MB")
        print_info(f"  节省空间: {saved_mb:.2f} MB ({saved / size_before * 100:.1f}%)")
        
    except sqlite3.Error as e:
        print_warning(f"清理失败: {e}")


def show_database_info(conn: sqlite3.Connection):
    """显示数据库信息"""
    
    print_step("数据库信息")
    
    cursor = conn.cursor()
    
    # 表统计
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    
    print()
    print_info(f"数据库路径: {DB_PATH}")
    print_info(f"表数量: {len(tables)}")
    
    print()
    print("📊 表统计：")
    for table in tables:
        if table.startswith('sqlite_'):
            continue
        
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  • {table}: {count:,} 行")
    
    # 索引统计
    print()
    print("🔍 索引统计：")
    indexes = check_existing_indexes(conn)
    
    for table_name, table_indexes in sorted(indexes.items()):
        if table_name.startswith('sqlite_'):
            continue
        print(f"  • {table_name}: {len(table_indexes)} 个索引")
        for idx_name, idx_sql in table_indexes:
            print(f"    - {idx_name}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据库索引优化工具')
    parser.add_argument('--db', type=str, help='数据库路径（默认: data/news_data.db）')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际修改数据库')
    parser.add_argument('--analyze', action='store_true', help='分析数据库统计信息')
    parser.add_argument('--vacuum', action='store_true', help='清理压缩数据库')
    parser.add_argument('--info', action='store_true', help='显示数据库信息')
    parser.add_argument('--all', action='store_true', help='执行所有优化操作')
    
    args = parser.parse_args()
    
    # 确定数据库路径
    db_path = Path(args.db) if args.db else DB_PATH
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        sys.exit(1)
    
    print("="*70)
    print("        数据库索引优化工具")
    print("="*70)
    
    if args.dry_run:
        print()
        print_warning("模拟运行模式（不会实际修改数据库）")
    
    # 连接数据库
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # 显示信息
        if args.info or args.all:
            show_database_info(conn)
        
        # 添加复合索引
        if not args.info and not args.analyze and not args.vacuum:
            # 默认操作：添加索引
            add_composite_indexes(conn, args.dry_run)
            setup_fts5_triggers(conn, args.dry_run)
        
        if args.all:
            add_composite_indexes(conn, args.dry_run)
            setup_fts5_triggers(conn, args.dry_run)
        
        # 分析数据库
        if args.analyze or args.all:
            if not args.dry_run:
                analyze_database(conn)
            else:
                print_info("跳过分析（模拟运行模式）")
        
        # 清理数据库
        if args.vacuum:
            if not args.dry_run:
                vacuum_database(conn)
            else:
                print_info("跳过清理（模拟运行模式）")
        
        conn.close()
        
        print()
        print("="*70)
        print_success("数据库优化完成")
        print("="*70)
        
        if not args.dry_run:
            print()
            print_info("建议：定期运行 'python scripts/optimize_database.py --analyze' 更新统计信息")
        
    except sqlite3.Error as e:
        print(f"\n❌ 数据库错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

