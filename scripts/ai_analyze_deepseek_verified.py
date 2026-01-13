#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI分析脚本 - DeepSeek完整验证版

核心功能:
1. 从数据库读取新闻
2. 获取实时市场数据
3. 调用DeepSeek生成报告
4. 事实核查验证
5. 质量评分
6. 自动重试(不达标)
7. 保存验证报告

使用方法:
    python3 scripts/ai_analyze_deepseek_verified.py --date 2026-01-07
    python3 scripts/ai_analyze_deepseek_verified.py --date 2026-01-07 --skip-verification
    python3 scripts/ai_analyze_deepseek_verified.py --date 2026-01-07 --min-score 90 --max-retries 5
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.report_generator import ReportGenerator
from scripts.utils.providers import DeepSeekProvider
from scripts.utils.print_utils import print_error


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='生成带实时数据验证的AI财经分析报告（DeepSeek）')
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定单日（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--limit', type=int, default=0, help='最多读取多少条记录')
    parser.add_argument('--max-articles', type=int, help='参与分析的文章数量上限')
    parser.add_argument('--filter-source', type=str, help='仅分析指定来源（逗号分隔）')
    parser.add_argument('--filter-keyword', type=str, help='关键词过滤（逗号分隔）')
    parser.add_argument('--api-key', type=str, help='DeepSeek API Key')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--model', type=str, default='deepseek-chat', help='DeepSeek模型名称')
    parser.add_argument('--base-url', type=str, default='https://api.deepseek.com', help='DeepSeek API Base URL')
    parser.add_argument('--prompt', choices=['safe', 'pro', 'pro_v2'], default='pro_v2', help='提示词版本')
    parser.add_argument('--skip-verification', action='store_true', help='跳过事实验证(测试用)')
    parser.add_argument('--max-retries', type=int, default=3, help='质量不达标时的最大重试次数')
    parser.add_argument('--min-score', type=int, default=80, help='最低质量评分(0-100)')
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--verbose', action='store_true', help='详细日志')
    return parser.parse_args()


def load_api_key(args: argparse.Namespace) -> str:
    """加载DeepSeek API Key"""
    import yaml

    # 1. 命令行参数
    if args.api_key:
        return args.api_key

    # 2. 环境变量
    env_key = os.getenv('DEEPSEEK_API_KEY')
    if env_key:
        return env_key

    # 3. 配置文件
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            api_key = (cfg.get('api_keys') or {}).get('deepseek') or (cfg.get('deepseek') or {}).get('api_key')
            if api_key:
                return api_key
        except Exception:
            pass

    raise SystemExit(
        "未找到 DeepSeek API Key。请使用以下任一方式配置:\n"
        "  1. 环境变量: export DEEPSEEK_API_KEY='your-key'\n"
        "  2. 配置文件: config/config.yml 中的 api_keys.deepseek\n"
        "  3. 命令行参数: --api-key 'your-key'"
    )


def main():
    """主函数"""
    args = parse_args()

    # 加载API Key
    api_key = load_api_key(args)

    # 创建DeepSeek提供商
    provider = DeepSeekProvider(
        api_key=api_key,
        base_url=args.base_url,
        model=args.model
    )

    # 创建报告生成器（启用完整验证）
    generator = ReportGenerator(
        provider=provider,
        enable_verification=not args.skip_verification
    )

    # 生成报告
    try:
        result = generator.generate(
            date=args.date,
            start=args.start,
            end=args.end,
            limit=args.limit,
            max_articles=args.max_articles,
            filter_source=args.filter_source,
            filter_keyword=args.filter_keyword,
            quality_check=True,  # 默认启用质量检查
            max_retries=args.max_retries,
            min_score=args.min_score,
            prompt_version=args.prompt,  # DeepSeek支持safe/pro
            output_json=args.output,
            model=args.model
        )

        if not result['success']:
            print_error(f"报告生成失败: {result.get('error', '未知错误')}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)
    except Exception as e:
        print_error(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
