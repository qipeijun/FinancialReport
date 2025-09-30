#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析脚本（DeepSeek 版本，基于数据库）

功能：
- 从 `data/news_data.db` 读取指定日期范围内的文章
- 语料构造优先使用 `content`（正文），为空则回退 `summary`
- 调用 DeepSeek 模型生成 Markdown 分析
- 将报告保存到 `docs/archive/YYYY-MM/YYYY-MM-DD/reports/` 下
- 可选导出 JSON（包含 summary 与文章元数据）

示例：
  - 分析当天：
      python3 scripts/ai_analyze_deepseek.py
  - 指定日期：
      python3 scripts/ai_analyze_deepseek.py --date 2025-09-29
  - 指定范围并导出 JSON：
      python3 scripts/ai_analyze_deepseek.py --start 2025-09-28 --end 2025-09-29 --output-json /tmp/analysis.json
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pytz
import yaml

from utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_step, print_statistics
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='从数据库读取新闻并调用 DeepSeek 生成分析报告')
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定单日（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--limit', type=int, default=0, help='最多读取多少条记录（0表示不限制）')
    parser.add_argument('--max-articles', type=int, help='可选：对参与分析的文章再控量（优先级高于 --limit）')
    parser.add_argument('--filter-source', type=str, help='仅分析指定来源（逗号分隔）')
    parser.add_argument('--filter-keyword', type=str, help='仅分析标题/摘要包含关键词的文章（逗号分隔，OR语义）')
    parser.add_argument('--order', choices=['asc', 'desc'], default='desc', help='排序方向，基于 published 优先、否则 created_at')
    parser.add_argument('--output-json', type=str, help='可选：将结果（summary+文章元数据）导出为 JSON 文件')
    parser.add_argument('--max-chars', type=int, default=500000, help='传入模型的最大字符数上限，用于控制成本，0 表示不限制')
    parser.add_argument('--api-key', type=str, help='可选：显式传入 DeepSeek API Key（默认仅从配置读取）')
    parser.add_argument('--config', type=str, help='可选：配置文件路径（默认 config/config.yml）')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='auto', help='选择分析字段：summary(摘要优先)、content(正文优先)、auto(智能选择)')
    parser.add_argument('--model', type=str, default='deepseek-chat', help='DeepSeek 模型名称（默认 deepseek-chat）')
    parser.add_argument('--base-url', type=str, default='https://api.deepseek.com/v3.1_terminus_expires_on_20251015', help='DeepSeek API Base URL')
    return parser.parse_args()


def validate_date(date_str: str) -> str:
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise SystemExit(f'无效日期格式: {date_str}，应为 YYYY-MM-DD')


def resolve_date_range(args: argparse.Namespace) -> Tuple[str, str]:
    today = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
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


def build_query(order: str, limit: int) -> Tuple[str, List[Any]]:
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
    pairs: List[Tuple[Dict[str, Any], List[str]]] = []
    total_len = 0
    for a in articles:
        if content_field == 'summary':
            body = a.get('summary') or a.get('content') or ''
        elif content_field == 'content':
            body = a.get('content') or a.get('summary') or ''
        else:
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


def call_deepseek(api_key: str, base_url: str, model_name: str, content: str) -> Tuple[str, Dict[str, Any]]:
    if OpenAI is None:
        raise SystemExit('未安装 openai，请先安装或在环境中提供。')

    print_progress(f'正在生成报告（输入长度 {len(content):,} 字符）')

    prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
    if not prompt_path.exists():
        raise SystemExit(f'提示词文件不存在: {prompt_path}')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        print_step(1, 1, f'调用模型: {model_name}')
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            stream=False
        )
        print_success(f'模型调用成功: {model_name}')
        usage = {}
        try:
            # OpenAI SDK usage 结构可能不同，这里做容错访问
            usage = {
                'model': getattr(resp, 'model', model_name),
                'prompt_tokens': getattr(getattr(resp, 'usage', {}), 'prompt_tokens', None) or (resp.usage.get('prompt_tokens') if isinstance(resp.usage, dict) else None),
                'completion_tokens': getattr(getattr(resp, 'usage', {}), 'completion_tokens', None) or (resp.usage.get('completion_tokens') if isinstance(resp.usage, dict) else None),
                'total_tokens': getattr(getattr(resp, 'usage', {}), 'total_tokens', None) or (resp.usage.get('total_tokens') if isinstance(resp.usage, dict) else None),
            }
        except Exception:
            pass
        text = resp.choices[0].message.content if resp and resp.choices else ''
        return text, usage
    except Exception as e:
        raise RuntimeError(f'DeepSeek 模型调用失败：{e}')


def save_markdown(date_str: str, markdown_text: str) -> Path:
    year_month = date_str[:7]
    report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    header = f"# 📅 {date_str} 财经分析报告\n\n> 📅 生成时间: {now_str} (北京时间)\n\n"
    content = header + (markdown_text or '').strip() + '\n'
    report_file = report_dir / f"📅 {date_str} 财经分析报告.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print_success(f"报告已保存到: {report_file}")
    return report_file


def save_metadata(date_str: str, meta: Dict[str, Any]):
    year_month = date_str[:7]
    report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    meta_file = report_dir / 'analysis_meta.json'
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print_info(f'元数据已保存到: {meta_file}')


def write_json(path: Path, summary_md: str, articles: List[Dict[str, Any]]):
    data = {
        'summary_markdown': summary_md,
        'articles': articles
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print_success(f'已导出 JSON: {path}')


def main():
    args = parse_args()
    start, end = resolve_date_range(args)

    print_header("AI 财经分析系统（DeepSeek）")
    print_info(f"分析日期范围: {start} → {end}")
    print_info(f"字段选择模式: {args.content_field}")
    if args.max_chars > 0:
        print_info(f"字符数限制: {args.max_chars:,}")
    print()

    # 解析配置文件，优先顺序：config.yml > --api-key（不再使用环境变量）
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    api_key: Optional[str] = None
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            # 支持 api_keys.deepseek 或 deepseek.api_key
            api_key = (
                (cfg.get('api_keys') or {}).get('deepseek')
                or (cfg.get('deepseek') or {}).get('api_key')
            )
            if api_key:
                print_success(f'使用配置文件：{config_path}')
        except Exception as e:
            print_warning(f'读取配置失败（{config_path}）：{e}，将尝试使用命令行或环境变量。')
    else:
        print_warning(f'未找到配置文件：{config_path}，将尝试使用命令行或环境变量。')

    if not api_key:
        api_key = args.api_key  # 仅允许命令行覆盖，不再从环境变量读取
    if not api_key:
        raise SystemExit("未在配置或命令行参数中找到 DeepSeek API Key。请在 config.yml 的 api_keys.deepseek 或 deepseek.api_key 配置，或使用 --api-key。")

    conn = open_connection(DB_PATH)
    try:
        rows = query_articles(conn, start, end, args.order, args.limit)
    finally:
        conn.close()

    if not rows:
        print_warning('未找到指定日期范围的文章，终止分析。')
        return
    print_info(f'已读取文章：{len(rows):,} 条')

    selected = rows
    if args.filter_source:
        sources = {s.strip() for s in args.filter_source.split(',') if s.strip()}
        selected = [r for r in selected if (r.get('source') or '') in sources]
    if args.filter_keyword:
        kws = {k.strip() for k in args.filter_keyword.split(',') if k.strip()}
        def match_kw(r: Dict[str, Any]) -> bool:
            text = f"{r.get('title','')} {r.get('summary','')}".lower()
            return any(k.lower() in text for k in kws)
        selected = [r for r in selected if match_kw(r)]
    if args.max_articles and args.max_articles > 0:
        selected = selected[:args.max_articles]

    pairs, total_len = build_corpus(selected, args.max_chars, per_chunk_chars=3000, content_field=args.content_field)
    current_len = sum(len(c) for _, chunks in pairs for c in chunks)
    print_info(f'语料长度: {current_len:,} 字符（原始 {total_len:,}，限制={args.max_chars:,}）')
    if args.max_chars and args.max_chars > 0 and total_len > args.max_chars:
        print_warning(f'语料已按上限截断：{total_len:,} → {current_len:,}')

    source_stats = {}
    for article in selected:
        source = article.get('source', '未知来源')
        source_stats[source] = source_stats.get(source, 0) + 1

    total_articles = len(selected)
    content_articles = sum(1 for a in selected if a.get('content'))
    content_ratio = (content_articles / total_articles * 100) if total_articles > 0 else 0

    stats_info = f"""
=== 数据统计信息 ===
分析日期范围: {start} 至 {end}
处理文章总数: {total_articles}篇
内容类型: {args.content_field}
数据完整性: {content_ratio:.1f}%的文章包含完整内容

新闻源统计:
"""
    for source, count in sorted(source_stats.items()):
        stats_info += f"- {source}: {count}篇\n"

    stats_info += f"\n总计: {total_articles}篇新闻文章\n"

    joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
    full_content = stats_info + "\n\n" + joined

    try:
        summary_md, usage = call_deepseek(api_key, args.base_url, args.model, full_content)
    except Exception as e:
        print_error(f'模型调用失败: {e}')
        return

    saved_path = save_markdown(end, summary_md)
    meta = {
        'date_range': {'start': start, 'end': end},
        'articles_used': len(selected),
        'chunks': sum(len(ch) for _, ch in pairs),
        'model_usage': usage,
    }
    save_metadata(end, meta)

    if args.output_json:
        out_path = Path(args.output_json)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        write_json(out_path, summary_md, rows)

    print_success('分析完成！')

    stats = {
        '分析日期范围': f"{start} → {end}",
        '处理文章数': len(selected),
        '语料块数': sum(len(ch) for _, ch in pairs),
        '最终字符数': f"{current_len:,}",
        '使用模型': usage.get('model', args.model),
        'Token消耗': f"{usage.get('total_tokens', 0):,}" if usage.get('total_tokens') else '未知'
    }
    print_statistics(stats)


if __name__ == '__main__':
    main()


