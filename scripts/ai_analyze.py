#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析脚本（基于数据库）

功能：
- 从 `data/news_data.db` 读取指定日期范围内的文章
- 语料构造优先使用 `content`（正文），为空则回退 `summary`
- 调用 Gemini 模型生成 Markdown 分析（多模型兜底）
- 将报告保存到 `docs/archive/YYYY-MM/YYYY-MM-DD/reports/` 下
- 可选导出 JSON（包含 summary 与文章元数据）

示例：
  - 分析当天：
      python3 scripts/ai_analyze.py
  - 指定日期：
      python3 scripts/ai_analyze.py --date 2025-09-29
  - 指定范围并导出 JSON：
      python3 scripts/ai_analyze.py --start 2025-09-28 --end 2025-09-29 --output-json /tmp/analysis.json
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

try:
    import google.generativeai as genai
except Exception:  # 允许环境缺失时先行提示
    genai = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='从数据库读取新闻并调用 Gemini 生成分析报告')
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定单日（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--limit', type=int, default=0, help='最多读取多少条记录（0表示不限制）')
    parser.add_argument('--order', choices=['asc', 'desc'], default='desc', help='排序方向，基于 published 优先、否则 created_at')
    parser.add_argument('--output-json', type=str, help='可选：将结果（summary+文章元数据）导出为 JSON 文件')
    parser.add_argument('--max-chars', type=int, default=200000, help='传入模型的最大字符数上限，用于控制成本，0 表示不限制')
    parser.add_argument('--api-key', type=str, help='可选：显式传入 Gemini API Key（默认从配置/环境读取）')
    parser.add_argument('--config', type=str, help='可选：配置文件路径（默认 config/config.yml）')
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


def build_corpus(articles: List[Dict[str, Any]], max_chars: int) -> Tuple[str, int]:
    """构造传给模型的语料，优先 content 回退 summary，并控制最大长度。
    返回 (裁剪后的文本, 原始长度)。
    """
    parts: List[str] = []
    for a in articles:
        body = a.get('content') or a.get('summary') or ''
        title = a.get('title') or ''
        source = a.get('source') or ''
        published = a.get('published') or ''
        link = a.get('link') or ''
        parts.append(f"【{title}】\n来源: {source} | 时间: {published}\n链接: {link}\n{body}\n\n")

    text_full = ''.join(parts)
    if max_chars and max_chars > 0 and len(text_full) > max_chars:
        return text_full[:max_chars], len(text_full)
    return text_full, len(text_full)


def call_gemini(api_key: str, content: str) -> str:
    """按优先级尝试多个模型，返回 Markdown 文本。"""
    if genai is None:
        raise SystemExit('未安装 google-generativeai，请先安装或在环境中提供。')

    model_names = [
        'models/gemini-2.5-pro',
        'models/gemini-2.5-flash',
        'models/gemini-2.0-flash',
        'models/gemini-pro-latest'
    ]

    genai.configure(api_key=api_key)
    print(f'🤖 正在生成报告（输入长度 {len(content)} 字符）')

    # 读取提示词（固定使用专业版）
    prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
    if not prompt_path.exists():
        raise SystemExit(f'提示词文件不存在: {prompt_path}')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    last_error: Optional[Exception] = None
    for model_name in model_names:
        try:
            print(f'→ 尝试模型: {model_name}')
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content([system_prompt, content])
            print(f'✅ 模型成功: {model_name}')
            return resp.text
        except Exception as e:  # 尝试下一个
            last_error = e
            continue

    raise RuntimeError(f'所有模型调用失败，最后错误：{last_error}')


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
    print(f"✅ 报告已保存到: {report_file}")
    return report_file


def write_json(path: Path, summary_md: str, articles: List[Dict[str, Any]]):
    data = {
        'summary_markdown': summary_md,
        'articles': articles
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'✅ 已导出 JSON: {path}')


def main():
    args = parse_args()
    start, end = resolve_date_range(args)
    print(f'🚀 开始 AI 分析：日期范围 {start} → {end}')

    # 解析配置文件，优先顺序：config.yml > --api-key > 环境变量
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    api_key: Optional[str] = None
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            # 常见层级兼容：api_keys.gemini 或 gemini.api_key
            api_key = (
                (cfg.get('api_keys') or {}).get('gemini')
                or (cfg.get('gemini') or {}).get('api_key')
            )
            print(f'🔧 使用配置文件：{config_path}')
        except Exception as e:
            print(f'⚠️ 读取配置失败（{config_path}）：{e}，将尝试使用命令行或环境变量。')
    else:
        print(f'⚠️ 未找到配置文件：{config_path}，将尝试使用命令行或环境变量。')

    if not api_key:
        api_key = args.api_key or os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise SystemExit("未在配置/参数/环境中找到 Gemini API Key。可在 config.yml 的 api_keys.gemini 或 gemini.api_key 配置，或使用 --api-key / GEMINI_API_KEY。")

    conn = open_connection(DB_PATH)
    try:
        rows = query_articles(conn, start, end, args.order, args.limit)
    finally:
        conn.close()

    if not rows:
        print('（无结果）未找到指定日期范围的文章，终止分析。')
        return
    print(f'📥 已读取文章：{len(rows)} 条')

    corpus, total_len = build_corpus(rows, args.max_chars)
    print(f'🔎 语料长度: {len(corpus)} 字符（原始 {total_len}，max={args.max_chars}）')
    if args.max_chars and args.max_chars > 0 and total_len > args.max_chars:
        print(f'✂️ 语料已按上限截断：{total_len} → {len(corpus)}')

    try:
        summary_md = call_gemini(api_key, corpus)
    except Exception as e:
        print(f'❌ 模型调用失败: {e}')
        return

    # 保存 Markdown 报告（按 end 日期命名，更贴近日报语义）
    saved_path = save_markdown(end, summary_md)

    # 可选导出 JSON
    if args.output_json:
        out_path = Path(args.output_json)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        write_json(out_path, summary_md, rows)

    print('🎉 分析完成。')


if __name__ == '__main__':
    main()


