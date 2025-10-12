#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析脚本（Gemini版本）- 重构版

功能：
- 从 `data/news_data.db` 读取指定日期范围内的文章
- 调用 Gemini 模型生成 Markdown 分析
- 自动添加实时股票数据
- 将报告保存到 `docs/archive/YYYY-MM/YYYY-MM-DD/reports/` 下

示例：
      python3 scripts/ai_analyze.py
  python3 scripts/ai_analyze.py --date 2025-10-11
  python3 scripts/ai_analyze.py --start 2025-10-10 --end 2025-10-11
"""

import argparse
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import yaml

# 导入公共模块
from utils.ai_analyzer_common import *
# from utils.data_enrichment import DataEnricher  # 已禁用数据增强功能
from utils.quality_filter import filter_and_rank_articles
from utils.quality_checker import (
    check_report_quality, generate_quality_feedback, 
    print_quality_report, print_quality_summary, add_quality_warning
)
from utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_step, print_statistics
)

try:
    import google.generativeai as genai
except Exception:
    genai = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='从数据库读取新闻并调用 Gemini 生成分析报告')
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
    parser.add_argument('--api-key', type=str, help='可选：显式传入 Gemini API Key')
    parser.add_argument('--config', type=str, help='可选：配置文件路径（默认 config/config.yml）')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='summary', 
                        help='选择分析字段：summary(摘要优先)、content(正文优先)、auto(智能选择)')
    parser.add_argument('--model', type=str, help='可选：指定 Gemini 模型（如 gemini-2.5-pro）')
    parser.add_argument('--quality-check', action='store_true', default=False,
                        help='启用质量检查（默认关闭），自动检测报告质量并重试')
    parser.add_argument('--max-retries', type=int, default=0,
                        help='质量检查不通过时的最大重试次数（默认0次，即不重试）')
    return parser.parse_args()


def load_api_key(args: argparse.Namespace) -> str:
    """加载Gemini API Key（优先级：命令行 > 环境变量 > 配置文件）"""
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    api_key: Optional[str] = None
    
    # 1. 尝试从命令行参数读取
    if args.api_key:
        api_key = args.api_key
        print_success('使用命令行参数提供的 API Key')
        return api_key
    
    # 2. 尝试从环境变量读取
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        api_key = env_key
        print_success('使用环境变量 GEMINI_API_KEY')
        return api_key
    
    # 3. 尝试从配置文件读取
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            api_key = (
                (cfg.get('api_keys') or {}).get('gemini')
                or (cfg.get('gemini') or {}).get('api_key')
            )
            if api_key:
                print_success(f'使用配置文件：{config_path}')
                return api_key
        except Exception as e:
            print_warning(f'读取配置失败（{config_path}）：{e}')
    
    # 4. 都没找到，报错
    raise SystemExit(
        "未找到 Gemini API Key。请使用以下任一方式配置：\n"
        "  1. 环境变量：export GEMINI_API_KEY='your-key'\n"
        "  2. 配置文件：config/config.yml 中的 api_keys.gemini\n"
        "  3. 命令行参数：--api-key 'your-key'"
    )


def call_gemini(api_key: str, content: str, preferred_model: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """调用Gemini模型生成分析"""
    if genai is None:
        raise SystemExit('未安装 google-generativeai，请先安装。')

    # 选择模型
    if preferred_model:
        model_names = [f'models/{preferred_model}' if not preferred_model.startswith('models/') else preferred_model]
        print_info(f'使用指定模型: {model_names[0]}')
    else:
        model_names = [
            'models/gemini-2.5-pro',
            'models/gemini-2.5-flash',
            'models/gemini-2.0-flash',
            'models/gemini-pro-latest'
        ]
        print_info('按优先级尝试模型: 2.5-pro → 2.5-flash → 2.0-flash → pro-latest')

    genai.configure(api_key=api_key)
    print_progress(f'正在生成报告（输入长度 {len(content):,} 字符）')

    # 读取提示词
    prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
    if not prompt_path.exists():
        raise SystemExit(f'提示词文件不存在: {prompt_path}')
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt_template = f.read()
    
    # 尝试多个模型
    last_error: Optional[Exception] = None
    for i, model_name in enumerate(model_names, 1):
        try:
            print_step(i, len(model_names), f'尝试模型: {model_name}')
            
            # 替换模型占位符
            system_prompt = system_prompt_template.replace(
                '[使用的具体模型名称]', 
                model_name.replace('models/', '')
            )
            
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
                pass
            
            return resp.text, usage
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f'所有模型调用失败，最后错误：{last_error}')


# 数据增强功能已禁用（用户不需要此功能）
# def enhance_with_realtime_data(api_key: str, report_text: str) -> str:
#     """使用AI增强报告，添加实时股票数据"""
#     try:
#         genai.configure(api_key=api_key)
#         # 注意：如果将来需要重新启用，需要将 'gemini-pro' 改为 'gemini-2.0-flash-exp' 或其他可用模型
#         client = genai.GenerativeModel('gemini-pro')
#         enricher = DataEnricher(ai_client=client)
#         enhanced_report = enricher.enrich_report(report_text)
#         print_success('数据增强完成')
#         return enhanced_report
#     except Exception as e:
#         print_warning(f'数据增强失败（跳过）: {e}')
#         return report_text


def generate_report_with_quality_check(api_key: str, selected: list, args: argparse.Namespace, 
                                       full_content: str = None) -> Tuple[str, Dict, Dict]:
    """
    生成报告并进行质量检查（全自动模式）
    
    Args:
        api_key: Gemini API Key
        selected: 文章列表
        args: 命令行参数
        full_content: 如果是单阶段模式，传入完整语料
        
    Returns:
        (报告文本, 使用统计, 质量检查结果)
    """
    max_retries = args.max_retries
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print_warning(f'\n🔄 质量不达标，第{attempt}次重试（共{max_retries}次）...\n')
        
        # 生成报告
        if attempt == 0:
            print_progress('调用Gemini模型生成投资分析报告...')
        
        report, usage = call_gemini(api_key, full_content, preferred_model=args.model)
        
        if attempt == 0:
            print_success('✓ 报告生成完成')
        
        # 质量检查
        if args.quality_check:
            print_progress('质量检查中...')
            quality_result = check_report_quality(report)
            print_quality_summary(quality_result)
            
            if quality_result['passed']:
                print_success('✅ 质量检查通过\n')
                return report, usage, quality_result
            else:
                if attempt < max_retries:
                    # 生成改进建议
                    feedback = generate_quality_feedback(quality_result)
                    print_warning(f'⚠️ 质量评分: {quality_result["score"]}/100')
                    print_info(f'问题数量: {len(quality_result["issues"])}个严重问题, {len(quality_result["warnings"])}个警告')
                    # 注: 改进建议不会自动添加到提示词中，而是用于下一次重试时的参考
                else:
                    print_error(f'❌ 已达最大重试次数({max_retries}次)，使用当前版本')
                    print_warning('报告质量可能不理想，建议人工审核')
                    # 在报告开头添加质量警告
                    report = add_quality_warning(report, quality_result)
                    return report, usage, quality_result
        else:
            # 不启用质量检查，直接返回原始报告（零干预）
            if attempt == 0:
                print_info('  ℹ️ 质量检查已禁用，报告未经二次处理')
            return report, usage, {}
    
    # 理论上不会到达这里（质量检查循环结束仍未通过）
    # 返回最后一次的结果
    return report, usage, quality_result if args.quality_check else {}


def main():
    """主函数"""
    args = parse_args()
    start, end = resolve_date_range(args)

    print_header("AI 财经分析系统（Gemini）")
    print_info(f"分析日期范围: {start} → {end}")
    print_info(f"字段选择模式: {args.content_field}")
    if args.max_chars > 0:
        print_info(f"字符数限制: {args.max_chars:,}")
    
    # 显示启用的功能
    features = []
    if args.quality_check:
        features.append(f"质量检查(最多重试{args.max_retries}次)")
    if features:
        print_info(f"启用功能: {', '.join(features)}")
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

    # 生成报告（集成质量检查）
    print()
    try:
        summary_md, usage, quality_result = generate_report_with_quality_check(
            api_key, selected, args, full_content
        )
    except Exception as e:
        print_error(f'报告生成失败: {e}')
        import traceback
        traceback.print_exc()
        return

    # 数据增强：添加实时股票数据（已禁用，用户不需要此功能）
    # print_progress('数据增强: 为报告添加实时股票数据...')
    # summary_md = enhance_with_realtime_data(api_key, summary_md)

    # 保存报告
    print_progress('保存报告到文件...')
    saved_path = save_markdown(end, summary_md, model_suffix='gemini')
    
    # 保存元数据
    meta = {
        'date_range': {'start': start, 'end': end},
        'articles_used': len(selected),
        'chunks': sum(len(ch) for _, ch in pairs),
        'model_usage': usage,
        'quality_check': quality_result if quality_result else None,
    }
    save_metadata(end, meta, model_suffix='gemini')

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
        '使用模型': usage.get('model', '未知'),
        'Token消耗': f"{usage.get('total_tokens', 0):,}" if usage.get('total_tokens') else '未知'
    }
    print_statistics(stats)


if __name__ == '__main__':
    main()
