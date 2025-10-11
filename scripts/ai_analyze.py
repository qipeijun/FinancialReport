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
import sys
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
    parser.add_argument('--max-articles', type=int, help='可选：对参与分析的文章再控量（优先级高于 --limit）')
    parser.add_argument('--filter-source', type=str, help='仅分析指定来源（逗号分隔）')
    parser.add_argument('--filter-keyword', type=str, help='仅分析标题/摘要包含关键词的文章（逗号分隔，OR语义）')
    parser.add_argument('--order', choices=['asc', 'desc'], default='desc', help='排序方向，基于 published 优先、否则 created_at')
    parser.add_argument('--output-json', type=str, help='可选：将结果（summary+文章元数据）导出为 JSON 文件')
    parser.add_argument('--max-chars', type=int, default=500000, help='传入模型的最大字符数上限，用于控制成本，0 表示不限制')
    parser.add_argument('--api-key', type=str, help='可选：显式传入 Gemini API Key（默认从配置/环境读取）')
    parser.add_argument('--config', type=str, help='可选：配置文件路径（默认 config/config.yml）')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='summary', help='选择分析字段：summary(摘要优先，默认)、content(正文优先)、auto(智能选择)')
    parser.add_argument('--model', type=str, help='可选：指定 Gemini 模型（如 gemini-2.5-pro），不指定则按优先级自动选择')
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
    """简单字符级分块（近似 500-1500 tokens）。可替换成更智能的语义切分。"""
    if not text:
        return []
    if max_chars <= 0:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        # 尝试在段落边界截断
        boundary = text.rfind('\n\n', start, end)
        if boundary == -1 or boundary <= start + int(max_chars * 0.5):
            boundary = end
        chunks.append(text[start:boundary])
        start = boundary
    return chunks


def build_corpus(articles: List[Dict[str, Any]], max_chars: int, per_chunk_chars: int = 3000, content_field: str = 'auto') -> Tuple[List[Tuple[Dict[str, Any], List[str]]], int]:
    """构造分块语料：返回 [(article_meta, [chunks...])...] 与原始总长度。"""
    pairs: List[Tuple[Dict[str, Any], List[str]]] = []
    total_len = 0
    for a in articles:
        if content_field == 'summary':
            body = a.get('summary') or a.get('content') or ''
        elif content_field == 'content':
            body = a.get('content') or a.get('summary') or ''
        else:  # auto - 智能选择
            summary = a.get('summary', '')
            content = a.get('content', '')
            # 如果content太长（>5000字符），优先使用summary
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

    # 上限控制（粗略按字符裁剪）：仅在 max_chars > 0 时生效
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

def call_gemini(api_key: str, content: str, preferred_model: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """按优先级尝试多个模型，返回 Markdown 文本。"""
    if genai is None:
        raise SystemExit('未安装 google-generativeai，请先安装或在环境中提供。')

    # 如果指定了模型，只尝试该模型
    if preferred_model:
        model_names = [f'models/{preferred_model}' if not preferred_model.startswith('models/') else preferred_model]
        print_info(f'使用指定模型: {model_names[0]}')
    else:
        # 默认按优先级尝试
        model_names = [
            'models/gemini-2.5-pro',
            'models/gemini-2.5-flash',
            'models/gemini-2.0-flash',
            'models/gemini-pro-latest'
        ]
        print_info('按优先级尝试模型: 2.5-pro → 2.5-flash → 2.0-flash → pro-latest')

    genai.configure(api_key=api_key)
    print_progress(f'正在生成报告（输入长度 {len(content):,} 字符）')

    # 读取提示词（固定使用专业版）
    prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
    if not prompt_path.exists():
        raise SystemExit(f'提示词文件不存在: {prompt_path}')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    
    # 替换模型占位符（在实际调用前会被替换为真实模型名）
    # 注意：这里先用占位符，成功调用后再替换
    system_prompt_template = system_prompt

    last_error: Optional[Exception] = None
    for i, model_name in enumerate(model_names, 1):
        try:
            print_step(i, len(model_names), f'尝试模型: {model_name}')
            
            # 为每个模型替换占位符
            system_prompt = system_prompt_template.replace('[使用的具体模型名称]', model_name.replace('models/', ''))
            
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content([system_prompt, content])
            print_success(f'模型调用成功: {model_name}')
            usage = {'model': model_name}
            try:
                if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                    usage_metadata = resp.usage_metadata
                    usage['prompt_tokens'] = getattr(usage_metadata, 'prompt_token_count', 0)
                    usage['candidates_tokens'] = getattr(usage_metadata, 'candidates_token_count', 0)
                    usage['total_tokens'] = getattr(usage_metadata, 'total_token_count', 0)
            except Exception:
                pass  # 静默失败，至少保证model字段存在
            return resp.text, usage
        except Exception as e:  # 尝试下一个
            last_error = e
            continue

    raise RuntimeError(f'所有模型调用失败，最后错误：{last_error}')


def save_markdown(date_str: str, markdown_text: str) -> Path:
    year_month = date_str[:7]
    report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(pytz.timezone('Asia/Shanghai'))
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    # 根据小时判断 AM/PM
    period = 'AM' if now.hour < 12 else 'PM'
    header = f"# 📅 {date_str} 财经分析报告\n\n> 📅 生成时间: {now_str} (北京时间)\n\n"
    content = header + (markdown_text or '').strip() + '\n'
    report_file = report_dir / f"📅 {date_str}_{period} 财经分析报告_gemini.md"
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

    print_header("AI 财经分析系统")
    print_info(f"分析日期范围: {start} → {end}")
    print_info(f"字段选择模式: {args.content_field}")
    if args.max_chars > 0:
        print_info(f"字符数限制: {args.max_chars:,}")
    print()

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
            print_success(f'使用配置文件：{config_path}')
        except Exception as e:
            print_warning(f'读取配置失败（{config_path}）：{e}，将尝试使用命令行或环境变量。')
    else:
        print_warning(f'未找到配置文件：{config_path}，将尝试使用命令行或环境变量。')

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
        print_warning('未找到指定日期范围的文章，终止分析。')
        return
    print_info(f'已读取文章：{len(rows):,} 条')

    # 过滤来源与关键词（可控量）
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

    # 构建规范化的新闻源统计信息
    stats_info = build_source_stats_block(selected, args.content_field, start, end)

    # 简单 RAG：将分块串接一次性生成（可升级为先召回再生成）
    joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
    full_content = stats_info + "\n\n" + joined

    try:
        summary_md, usage = call_gemini(api_key, full_content, preferred_model=args.model)
    except Exception as e:
        print_error(f'模型调用失败: {e}')
        return

    # 保存 Markdown 报告（按 end 日期命名，更贴近日报语义）
    saved_path = save_markdown(end, summary_md)
    # 元数据持久化
    meta = {
        'date_range': {'start': start, 'end': end},
        'articles_used': len(selected),
        'chunks': sum(len(ch) for _, ch in pairs),
        'model_usage': usage,
#         'prompt_file': str((PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md').resolve())
    }
    save_metadata(end, meta)

    # 可选导出 JSON
    if args.output_json:
        out_path = Path(args.output_json)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        write_json(out_path, summary_md, rows)

    print_success('分析完成！')

    # 打印统计信息
    stats = {
        '分析日期范围': f"{start} → {end}",
        '处理文章数': len(selected),
        '语料块数': sum(len(ch) for _, ch in pairs),
        '最终字符数': f"{current_len:,}",
        '使用模型': usage.get('model', '未知'),
        'Token消耗': f"{usage.get('total_tokens', 0):,}" if usage.get('total_tokens') else '未知'
    }
    print_statistics(stats)


if __name__ == '__main__':
    main()


