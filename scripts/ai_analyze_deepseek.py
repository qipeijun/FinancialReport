#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析脚本（DeepSeek版本）- 重构版

功能：
- 从 `data/news_data.db` 读取指定日期范围内的文章
- 调用 DeepSeek 模型生成 Markdown 分析
- 将报告保存到 `docs/archive/YYYY-MM/YYYY-MM-DD/reports/` 下

示例：
      python3 scripts/ai_analyze_deepseek.py
  python3 scripts/ai_analyze_deepseek.py --date 2025-10-11
  python3 scripts/ai_analyze_deepseek.py --start 2025-10-10 --end 2025-10-11
"""

import argparse
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import yaml

# 导入公共模块
from utils.ai_analyzer_common import *
from utils.quality_filter import filter_and_rank_articles
from utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_step, print_statistics
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='从数据库读取新闻并调用 DeepSeek 生成分析报告')
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定单日（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD），默认为当天')
    parser.add_argument('--limit', type=int, default=0, help='最多读取多少条记录（0表示不限制）')
    parser.add_argument('--max-articles', type=int, help='可选：对参与分析的文章再控量')
    parser.add_argument('--filter-source', type=str, help='仅分析指定来源（逗号分隔）')
    parser.add_argument('--filter-keyword', type=str, help='仅分析标题/摘要包含关键词的文章（逗号分隔）')
    parser.add_argument('--order', choices=['asc', 'desc'], default='desc', help='排序方向')
    parser.add_argument('--output-json', type=str, help='可选：将结果导出为 JSON 文件')
    parser.add_argument('--max-chars', type=int, default=500000, help='传入模型的最大字符数上限')
    parser.add_argument('--api-key', type=str, help='可选：显式传入 DeepSeek API Key')
    parser.add_argument('--config', type=str, help='可选：配置文件路径（默认 config/config.yml）')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='summary',
                        help='选择分析字段：summary(摘要优先)、content(正文优先)、auto(智能选择)')
    parser.add_argument('--model', type=str, default='deepseek-chat', help='DeepSeek 模型名称')
    parser.add_argument('--base-url', type=str, default='https://api.deepseek.com', help='DeepSeek API Base URL')
    parser.add_argument('--prompt', choices=['safe', 'pro'], default='pro',
                        help='提示词版本：safe(安全版) 或 pro(专业版)')
    return parser.parse_args()


def load_api_key(args: argparse.Namespace) -> str:
    """加载DeepSeek API Key"""
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    api_key: Optional[str] = None
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            api_key = (
                (cfg.get('api_keys') or {}).get('deepseek')
                or (cfg.get('deepseek') or {}).get('api_key')
            )
            if api_key:
                print_success(f'使用配置文件：{config_path}')
        except Exception as e:
            print_warning(f'读取配置失败（{config_path}）：{e}')
    
    if not api_key:
        api_key = args.api_key
    
    if not api_key:
        raise SystemExit("未找到 DeepSeek API Key。请在 config.yml 配置或使用 --api-key")
    
    return api_key


def call_deepseek(api_key: str, base_url: str, model_name: str, content: str, prompt_version: str = 'pro') -> Tuple[str, Dict[str, Any]]:
    """调用DeepSeek模型生成分析"""
    if OpenAI is None:
        raise SystemExit('未安装 openai，请先安装。')

    print_progress(f'正在生成报告（输入长度 {len(content):,} 字符）')

    # 根据版本选择提示词
    if prompt_version == 'safe':
        prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_safe.md'
        if not prompt_path.exists():
            print_warning('安全版提示词不存在，回退到专业版')
            prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
    else:
        prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'

    if not prompt_path.exists():
        raise SystemExit(f'提示词文件不存在: {prompt_path}')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    print_info(f'使用提示词版本: {prompt_version} ({prompt_path.name})')
    
    # 替换模型占位符
    system_prompt = system_prompt.replace('[使用的具体模型名称]', model_name)

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
        
        usage = {'model': getattr(resp, 'model', model_name)}
        try:
            if hasattr(resp, 'usage') and resp.usage:
                usage['prompt_tokens'] = getattr(resp.usage, 'prompt_tokens', 0)
                usage['completion_tokens'] = getattr(resp.usage, 'completion_tokens', 0)
                usage['total_tokens'] = getattr(resp.usage, 'total_tokens', 0)
        except Exception:
            pass
        
        text = resp.choices[0].message.content if resp and resp.choices else ''
        return text, usage
    except Exception as e:
        raise RuntimeError(f'DeepSeek 模型调用失败：{e}')


def main():
    """主函数"""
    args = parse_args()
    start, end = resolve_date_range(args)

    print_header("AI 财经分析系统（DeepSeek）")
    print_info(f"分析日期范围: {start} → {end}")
    print_info(f"字段选择模式: {args.content_field}")
    print_info(f"提示词版本: {args.prompt}")
    if args.max_chars > 0:
        print_info(f"字符数限制: {args.max_chars:,}")
    print()

    # 加载API Key
    api_key = load_api_key(args)

    # 查询文章
    conn = open_connection(DB_PATH)
    try:
        rows = query_articles(conn, start, end, args.order, args.limit)
    finally:
        conn.close()

    if not rows:
        print_warning('未找到指定日期范围的文章，终止分析。')
        return
    print_info(f'已读取文章：{len(rows):,} 条')

    # 过滤文章
    selected = filter_articles(
        rows,
        filter_source=args.filter_source,
        filter_keyword=args.filter_keyword,
        max_articles=args.max_articles
    )
    
    # 质量筛选和排序（新增）
    print_progress('质量筛选: 过滤低质量文章并智能去重...')
    selected, quality_stats = filter_and_rank_articles(
        selected
        # 所有参数都从 config/quality_filter_config.yml 读取
        # 可通过修改配置文件来调整质量阈值、去重参数等
    )
    
    if not selected:
        print_warning('质量筛选后无文章剩余，请降低阈值或检查数据源')
        return

    # 构建语料
    pairs, total_len = build_corpus(selected, args.max_chars, per_chunk_chars=3000, content_field=args.content_field)
    current_len = sum(len(c) for _, chunks in pairs for c in chunks)
    print_info(f'语料长度: {current_len:,} 字符（原始 {total_len:,}，限制={args.max_chars:,}）')
    if args.max_chars and args.max_chars > 0 and total_len > args.max_chars:
        print_warning(f'语料已按上限截断：{total_len:,} → {current_len:,}')

    # 构建统计信息
    stats_info = build_source_stats_block(selected, args.content_field, start, end)
    joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
    full_content = stats_info + "\n\n" + joined

    # 调用DeepSeek生成报告
    try:
        summary_md, usage = call_deepseek(api_key, args.base_url, args.model, full_content, args.prompt)
    except Exception as e:
        print_error(f'模型调用失败: {e}')
        return

    # 保存报告
    saved_path = save_markdown(end, summary_md, model_suffix='deepseek')
    
    # 保存元数据
    meta = {
        'date_range': {'start': start, 'end': end},
        'articles_used': len(selected),
        'chunks': sum(len(ch) for _, ch in pairs),
        'model_usage': usage,
    }
    save_metadata(end, meta)

    # 可选导出JSON
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
        '使用模型': usage.get('model', args.model),
        'Token消耗': f"{usage.get('total_tokens', 0):,}" if usage.get('total_tokens') else '未知'
    }
    print_statistics(stats)


if __name__ == '__main__':
    main()
