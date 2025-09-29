#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按时间范围查询 data/news_data.db 中的新闻数据（默认查询当天）。

示例：
  - 查询当天：
      python3 scripts/query_news_by_date.py
  - 指定日期：
      python3 scripts/query_news_by_date.py --date 2025-09-29
  - 指定范围：
      python3 scripts/query_news_by_date.py --start 2025-09-28 --end 2025-09-29
  - 过滤来源：
      python3 scripts/query_news_by_date.py --source 华尔街见闻 --limit 20
  - 关键字搜索（标题/摘要）：
      python3 scripts/query_news_by_date.py --keyword 人工智能
  - 输出格式：
      python3 scripts/query_news_by_date.py --format table   # 默认
      python3 scripts/query_news_by_date.py --format json
      python3 scripts/query_news_by_date.py --format csv --output /tmp/news.csv
"""

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='按时间范围查询新闻数据库（默认当天）')
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定某天（YYYY-MM-DD），等价于 --start=day --end=day')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--source', type=str, help='按来源名称过滤（如：华尔街见闻）')
    parser.add_argument('--keyword', type=str, help='关键字搜索标题与摘要（LIKE 模糊匹配）')
    parser.add_argument('--format', choices=['table', 'json', 'csv'], default='table', help='输出格式')
    parser.add_argument('--limit', type=int, default=100, help='最多返回多少条记录（0表示不限制）')
    parser.add_argument('--output', type=str, help='当格式为csv或json时，输出到该文件路径')
    parser.add_argument('--order', choices=['asc', 'desc'], default='desc', help='按发布时间或创建时间排序方向')
    return parser.parse_args()


def validate_date(date_str: str) -> str:
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise SystemExit(f'无效日期格式: {date_str}，应为 YYYY-MM-DD')


def resolve_date_range(args: argparse.Namespace) -> (str, str):
    today = datetime.now().strftime('%Y-%m-%d')
    if args.date:
        day = validate_date(args.date)
        return day, day
    start = validate_date(args.start) if args.start else today
    end = validate_date(args.end) if args.end else today
    if start > end:
        raise SystemExit(f'开始日期不得晚于结束日期: {start} > {end}')
    return start, end


def open_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f'数据库不存在: {db_path}')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def build_query(source: Optional[str], keyword: Optional[str], order: str, limit: int) -> (str, list):
    sql = [
        'SELECT a.id, a.collection_date, a.title, a.link, a.published, a.summary, s.source_name',
        'FROM news_articles a',
        'JOIN rss_sources s ON a.source_id = s.id',
        'WHERE a.collection_date BETWEEN ? AND ?'
    ]
    params: List[Any] = []
    # start, end will be appended by caller first
    if source:
        sql.append('AND s.source_name = ?')
        params.append(source)
    if keyword:
        sql.append('AND (a.title LIKE ? OR a.summary LIKE ?)')
        like = f'%{keyword}%'
        params.extend([like, like])

    # Order by: prefer published if present, fallback created_at
    order_dir = 'DESC' if order.lower() == 'desc' else 'ASC'
    sql.append('ORDER BY COALESCE(a.published, a.created_at) ' + order_dir)

    if limit and limit > 0:
        sql.append('LIMIT ?')
        params.append(limit)

    return '\n'.join(sql), params


def query_articles(conn: sqlite3.Connection, start: str, end: str, source: Optional[str], keyword: Optional[str], order: str, limit: int) -> List[Dict[str, Any]]:
    sql, params_tail = build_query(source, keyword, order, limit)
    params = [start, end] + params_tail
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append({
            'id': r['id'],
            'collection_date': r['collection_date'],
            'title': r['title'],
            'link': r['link'],
            'source': r['source_name'],
            'published': r['published'],
            'summary': r['summary']
        })
    return results


def print_table(rows: List[Dict[str, Any]]):
    if not rows:
        print('（无结果）')
        return
    # Minimal pretty table without external deps
    headers = ['collection_date', 'source', 'title', 'published']
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row.get(h, '') or '')))
    sep = ' | '
    header_line = sep.join(h.ljust(widths[h]) for h in headers)
    divider = '-+-'.join('-' * widths[h] for h in headers)
    print(header_line)
    print(divider)
    for row in rows:
        line = sep.join(str(row.get(h, '') or '').ljust(widths[h]) for h in headers)
        print(line)


def write_csv(rows: List[Dict[str, Any]], path: Path):
    fieldnames = ['id', 'collection_date', 'source', 'title', 'published', 'link', 'summary']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f'✅ 已导出 CSV: {path}')


def write_json(rows: List[Dict[str, Any]], path: Path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f'✅ 已导出 JSON: {path}')


def main():
    args = parse_args()
    start, end = resolve_date_range(args)

    conn = open_connection(DB_PATH)
    try:
        rows = query_articles(conn, start, end, args.source, args.keyword, args.order, args.limit)
    finally:
        conn.close()

    if args.format == 'table':
        print_table(rows)
    elif args.format == 'csv':
        if not args.output:
            raise SystemExit('CSV 输出需要 --output 指定文件路径')
        write_csv(rows, Path(args.output))
    elif args.format == 'json':
        if args.output:
            write_json(rows, Path(args.output))
        else:
            print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


