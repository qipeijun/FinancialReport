#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析公共模块

提取ai_analyze.py和ai_analyze_deepseek.py的公共逻辑，避免代码重复
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pytz

from utils.print_utils import (
    print_success, print_warning, print_info
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def validate_date(date_str: str) -> str:
    """验证日期格式"""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise SystemExit(f'无效日期格式: {date_str}，应为 YYYY-MM-DD')


def open_connection(db_path: Path) -> sqlite3.Connection:
    """打开数据库连接"""
    if not db_path.exists():
        raise SystemExit(f'数据库不存在: {db_path}')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def build_query(order: str, limit: int) -> Tuple[str, List[Any]]:
    """构建SQL查询"""
    sql = [
        'SELECT a.id, a.collection_date, a.title, a.link, a.published, a.summary, a.content, s.source_name',
        'FROM news_articles a',
        'JOIN rss_sources s ON a.source_id = s.id',
        'WHERE a.collection_date BETWEEN ? AND ?'
    ]
    params: List[Any] = []

    order_dir = 'DESC' if order.lower() == 'desc' else 'ASC'
    sql.append('ORDER BY COALESCE(a.published, a.created_at) ' + order_dir)

    if limit and limit > 0:
        sql.append('LIMIT ?')
        params.append(limit)

    return '\n'.join(sql), params


def query_articles(conn: sqlite3.Connection, start: str, end: str, order: str, limit: int) -> List[Dict[str, Any]]:
    """查询文章"""
    sql, tail = build_query(order, limit)
    params = [start, end] + tail
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
            'summary': r['summary'],
            'content': r['content']
        })
    return results


def chunk_text(text: str, max_chars: int = 4000) -> List[str]:
    """文本分块"""
    if not text:
        return []
    if max_chars <= 0:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        boundary = text.rfind('\n\n', start, end)
        if boundary == -1 or boundary <= start + int(max_chars * 0.5):
            boundary = end
        chunks.append(text[start:boundary])
        start = boundary
    return chunks


def build_corpus(articles: List[Dict[str, Any]], max_chars: int, per_chunk_chars: int = 3000, content_field: str = 'auto') -> Tuple[List[Tuple[Dict[str, Any], List[str]]], int]:
    """构造分块语料"""
    pairs: List[Tuple[Dict[str, Any], List[str]]] = []
    total_len = 0
    for a in articles:
        if content_field == 'summary':
            body = a.get('summary') or a.get('content') or ''
        elif content_field == 'content':
            body = a.get('content') or a.get('summary') or ''
        else:  # auto
            summary = a.get('summary', '')
            content = a.get('content', '')
            if len(content) > 5000 and summary:
                body = summary
            else:
                body = content or summary or ''

        title = a.get('title') or ''
        source = a.get('source') or ''
        published = a.get('published') or ''
        link = a.get('link') or ''
        header = f"【{title}】\n来源: {source} | 时间: {published}\n链接: {link}\n"
        text = header + body
        total_len += len(text)
        chunks = chunk_text(text, per_chunk_chars)
        pairs.append((a, chunks))

    if max_chars and max_chars > 0:
        acc = 0
        trimmed: List[Tuple[Dict[str, Any], List[str]]] = []
        for meta, chunks in pairs:
            kept: List[str] = []
            for c in chunks:
                if acc + len(c) <= max_chars:
                    kept.append(c)
                    acc += len(c)
                else:
                    break
            if kept:
                trimmed.append((meta, kept))
            if acc >= max_chars:
                break
        return trimmed, total_len
    return pairs, total_len


def _normalize_source_name(name: str) -> str:
    """规范化来源名称"""
    if not name:
        return '未知来源'
    name = name.strip()
    mapping = {
        '东方财富网': '东方财富',
        '国家统计局-最新发布': '国家统计局',
        '中新社': '中新网',
        '中国新闻网': '中新网',
        'Wall Street CN': '华尔街见闻',
        'WallstreetCN': '华尔街见闻',
    }
    return mapping.get(name, name)


def build_source_stats_block(selected: List[Dict[str, Any]], content_field: str, start: str, end: str) -> str:
    """构建数据统计信息块"""
    tracked = ['华尔街见闻', '36氪', '东方财富', '国家统计局', '中新网']
    counters: Dict[str, int] = {k: 0 for k in tracked}
    other_count = 0

    for article in selected:
        raw = (article.get('source') or '').strip()
        norm = _normalize_source_name(raw)
        if norm in counters:
            counters[norm] += 1
        else:
            other_count += 1

    total_articles = len(selected)
    content_articles = sum(1 for a in selected if a.get('content'))
    content_ratio = (content_articles / total_articles * 100) if total_articles > 0 else 0

    stats_info = f"""
=== 数据统计信息 ===
分析日期范围: {start} 至 {end}
处理文章总数: {total_articles}篇
内容类型: {content_field}
数据完整性: {content_ratio:.1f}%的文章包含完整内容

新闻源统计:
本次分析基于以下新闻源：
"""
    for k in tracked:
        stats_info += f"- {k}：{counters[k]}篇\n"
    stats_info += f"- 其他来源：{other_count}篇\n\n"
    stats_info += f"总计: {total_articles}篇新闻文章\n"
    return stats_info


def save_markdown(date_str: str, markdown_text: str, model_suffix: str = 'gemini') -> Path:
    """保存Markdown报告
    
    Args:
        date_str: 日期字符串（YYYY-MM-DD）
        markdown_text: 报告内容
        model_suffix: 模型后缀（gemini/deepseek）
        
    Returns:
        报告文件路径
    """
    year_month = date_str[:7]
    report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取北京时间
    now = datetime.now(pytz.timezone('Asia/Shanghai'))
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    hour = now.hour
    
    # 根据时间段确定场次标识
    if 6 <= hour < 12:
        session = 'morning'
        session_cn = '早盘'
        session_emoji = '🌅'
    elif 12 <= hour < 18:
        session = 'afternoon'
        session_cn = '午盘'
        session_emoji = '🌆'
    elif 18 <= hour < 24:
        session = 'evening'
        session_cn = '美股'
        session_emoji = '🌙'
    else:  # 0-6点
        session = 'overnight'
        session_cn = '隔夜'
        session_emoji = '🌃'
    
    # 生成报告头部
    header = f"# 📅 {date_str} 财经分析报告 {session_emoji} {session_cn}场\n\n> 📅 生成时间: {now_str} (北京时间)\n\n"
    content = header + (markdown_text or '').strip() + '\n'
    
    # 文件名包含场次，避免覆盖
    report_file = report_dir / f"📅 {date_str} 财经分析报告_{session}_{model_suffix}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print_success(f"报告已保存到: {report_file}")
    return report_file


def save_metadata(date_str: str, meta: Dict[str, Any], model_suffix: str = ''):
    """保存元数据
    
    Args:
        date_str: 日期字符串
        meta: 元数据字典
        model_suffix: 模型后缀（如 'gemini', 'deepseek'）
    """
    year_month = date_str[:7]
    report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取北京时间，确定场次
    now = datetime.now(pytz.timezone('Asia/Shanghai'))
    hour = now.hour
    
    if 6 <= hour < 12:
        session = 'morning'
    elif 12 <= hour < 18:
        session = 'afternoon'
    elif 18 <= hour < 24:
        session = 'evening'
    else:
        session = 'overnight'
    
    # 根据模型和场次添加后缀，避免覆盖
    if model_suffix:
        meta_file = report_dir / f'analysis_meta_{session}_{model_suffix}.json'
    else:
        meta_file = report_dir / f'analysis_meta_{session}.json'
    
    # 在元数据中记录场次信息
    meta['session'] = session
    meta['session_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
    
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print_info(f'元数据已保存到: {meta_file}')


def write_json(path: Path, summary_md: str, articles: List[Dict[str, Any]]):
    """导出JSON"""
    data = {
        'summary_markdown': summary_md,
        'articles': articles
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print_success(f'已导出 JSON: {path}')


def filter_articles(articles: List[Dict[str, Any]], 
                    filter_source: Optional[str] = None,
                    filter_keyword: Optional[str] = None,
                    max_articles: Optional[int] = None) -> List[Dict[str, Any]]:
    """过滤文章"""
    selected = articles
    
    if filter_source:
        sources = {s.strip() for s in filter_source.split(',') if s.strip()}
        selected = [r for r in selected if (r.get('source') or '') in sources]
    
    if filter_keyword:
        kws = {k.strip() for k in filter_keyword.split(',') if k.strip()}
        def match_kw(r: Dict[str, Any]) -> bool:
            text = f"{r.get('title','')} {r.get('summary','')}".lower()
            return any(k.lower() in text for k in kws)
        selected = [r for r in selected if match_kw(r)]
    
    if max_articles and max_articles > 0:
        selected = selected[:max_articles]
    
    return selected


def resolve_date_range(args) -> Tuple[str, str]:
    """解析日期范围"""
    today = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
    if hasattr(args, 'date') and args.date:
        day = validate_date(args.date)
        return day, day
    start = validate_date(args.start) if args.start else today
    end = validate_date(args.end) if args.end else today
    if start > end:
        raise SystemExit(f'开始日期不得晚于结束日期: {start} > {end}')
    return start, end

