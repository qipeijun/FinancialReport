#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI分析脚本 - 集成实时数据验证版 (Gemini)

核心功能:
1. 从数据库读取新闻
2. 获取实时市场数据
3. 注入数据到AI Prompt
4. 调用Gemini生成报告
5. 事实核查验证
6. 质量评分
7. 自动重试(不达标)
8. 保存验证报告

使用方法:
    python3 scripts/ai_analyze_verified.py --date 2026-01-07
    python3 scripts/ai_analyze_verified.py --date 2026-01-07 --skip-verification
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
import yaml

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 导入公共模块
from scripts.utils.ai_analyzer_common import *
from scripts.utils.quality_filter import filter_and_rank_articles
from scripts.utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_step
)

# 导入新的验证模块
from scripts.utils.realtime_data_fetcher import RealtimeDataFetcher
from scripts.utils.fact_checker import FactChecker
from scripts.utils.quality_checker_v2 import check_report_quality_v2, print_quality_report_v2

try:
    import google.generativeai as genai
except Exception:
    genai = None

DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='生成带实时数据验证的AI财经分析报告')

    # 日期参数
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', type=str, help='指定单日（YYYY-MM-DD）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')

    # 数据筛选
    parser.add_argument('--limit', type=int, default=100, help='最多读取多少条记录')
    parser.add_argument('--max-articles', type=int, help='参与分析的文章数量上限')
    parser.add_argument('--filter-source', type=str, help='仅分析指定来源（逗号分隔）')
    parser.add_argument('--filter-keyword', type=str, help='关键词过滤（逗号分隔）')

    # API配置
    parser.add_argument('--api-key', type=str, help='Gemini API Key')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--model', type=str, help='指定Gemini模型')

    # 验证参数
    parser.add_argument('--skip-verification', action='store_true',
                       help='跳过事实验证(测试用)')
    parser.add_argument('--max-retries', type=int, default=3,
                       help='质量不达标时的最大重试次数')
    parser.add_argument('--min-score', type=int, default=80,
                       help='最低质量评分(0-100)')

    # 输出参数
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--verbose', action='store_true', help='详细日志')

    return parser.parse_args()


def load_api_key(args: argparse.Namespace) -> str:
    """加载Gemini API Key"""
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')

    # 1. 命令行参数
    if args.api_key:
        print_success('使用命令行参数提供的 API Key')
        return args.api_key

    # 2. 环境变量
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        print_success('使用环境变量 GEMINI_API_KEY')
        return env_key

    # 3. 配置文件
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            api_key = (
                (cfg.get('api_keys') or {}).get('gemini')
                or (cfg.get('gemini') or {}).get('api_key')
            )
            if api_key:
                print_success(f'使用配置文件: {config_path}')
                return api_key
        except Exception as e:
            print_warning(f'读取配置失败: {e}')

    raise SystemExit(
        "未找到 Gemini API Key。请使用以下任一方式配置:\n"
        "  1. 环境变量: export GEMINI_API_KEY='your-key'\n"
        "  2. 配置文件: config/config.yml\n"
        "  3. 命令行参数: --api-key 'your-key'"
    )


def fetch_news_from_db(date: str, limit: int = 100) -> List[Dict]:
    """从数据库获取新闻"""
    import sqlite3

    if not DB_PATH.exists():
        raise SystemExit(f"数据库不存在: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT id, title, summary, content, url, source_id, published, collection_date
    FROM news_articles
    WHERE collection_date = ?
    AND content IS NOT NULL
    AND content != ''
    ORDER BY published DESC
    LIMIT ?
    """

    cursor.execute(query, (date, limit))
    rows = cursor.fetchall()
    conn.close()

    articles = []
    for row in rows:
        articles.append({
            'id': row[0],
            'title': row[1],
            'summary': row[2],
            'content': row[3],
            'url': row[4],
            'source_id': row[5],
            'published': row[6],
            'collection_date': row[7]
        })

    print_success(f"从数据库获取到 {len(articles)} 篇新闻 (日期: {date})")
    return articles


def call_gemini_with_realtime_data(
    api_key: str,
    articles: List[Dict],
    realtime_data: Dict,
    preferred_model: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    调用Gemini生成报告(注入实时数据)

    Args:
        api_key: Gemini API密钥
        articles: 新闻列表
        realtime_data: 实时数据(来自RealtimeDataFetcher)
        preferred_model: 指定模型(可选)

    Returns:
        (报告文本, 使用元数据)
    """
    if genai is None:
        raise SystemExit('未安装 google-generativeai')

    # 选择模型
    if preferred_model:
        model_names = [f'models/{preferred_model}' if not preferred_model.startswith('models/') else preferred_model]
        print_info(f'使用指定模型: {model_names[0]}')
    else:
        model_names = [
            'models/gemini-3-flash-preview',      # 🥇 最新! Gemini 3.0 Flash (2025-12发布)
            'models/gemini-3-pro-preview',         # 🥈 Gemini 3.0 Pro (2025-11发布)
            'models/gemini-2.0-flash-exp',         # 🥉 Gemini 2.0 (备用)
            'models/gemini-1.5-pro',
            'models/gemini-1.5-flash'
        ]
        print_info('按优先级尝试模型: 3.0-flash → 3.0-pro → 2.0-flash-exp → 1.5-pro → 1.5-flash')

    genai.configure(api_key=api_key)

    # 读取增强版Prompt模板
    prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro_v2.md'
    if not prompt_path.exists():
        # 回退到旧版
        prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'
        print_warning('未找到v2版Prompt,使用旧版(可能缺少严格约束)')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt_template = f.read()

    # 构建新闻内容
    news_content = "\n\n".join([
        f"【新闻{i+1}】{article['title']}\n"
        f"来源: {article['source_id']} | 发布时间: {article['published']}\n"
        f"摘要: {article.get('summary', '')}\n"
        f"正文: {article.get('content', '')[:800]}..."  # 限制长度
        for i, article in enumerate(articles[:50])  # 最多50篇
    ])

    # 组装完整Prompt
    final_prompt = f"""
{system_prompt_template}

---

{realtime_data.get('prompt', '')}

---

## 📰 今日新闻内容

{news_content}

---

**重要提醒**:
1. 所有股票推荐**必须引用上面的实时数据**(价格、涨跌幅)
2. **禁止**编造任何未在实时数据中出现的数值
3. 每个观点都要用【新闻X】标注来源
4. 在报告末尾标注"数据来源: 新浪财经 | 更新时间: {realtime_data.get('timestamp', '')}"
"""

    print_progress(f'正在生成报告 (新闻: {len(articles)}篇, 字符数: {len(final_prompt):,})')

    # 尝试多个模型
    last_error: Optional[Exception] = None
    for i, model_name in enumerate(model_names, 1):
        try:
            print_step(i, len(model_names), f'尝试模型: {model_name}')

            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(final_prompt)
            print_success(f'模型调用成功: {model_name}')

            # 提取使用信息
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
            print_warning(f'模型 {model_name} 调用失败: {e}')
            continue

    raise RuntimeError(f'所有模型调用失败,最后错误: {last_error}')


def generate_verified_report(
    api_key: str,
    date: str,
    args: argparse.Namespace
) -> Dict:
    """
    生成带验证的完整报告

    Returns:
        {
            'report': 最终报告文本,
            'quality': 质量评分结果,
            'metadata': 元数据,
            'success': 是否成功
        }
    """
    print_header(f"生成带验证的AI报告: {date}")

    # 步骤1: 获取新闻
    print_step(1, 7, "从数据库获取新闻")
    articles = fetch_news_from_db(date, limit=args.limit)

    if not articles:
        print_error("没有可用的新闻数据")
        return {'success': False, 'error': '没有新闻数据'}

    # 步骤2: 获取实时数据
    print_step(2, 7, "获取实时市场数据")
    fetcher = RealtimeDataFetcher()
    realtime_data = fetcher.fetch_all_for_articles(articles)

    print_success(f"实时数据获取完成: "
                 f"股票 {len(realtime_data.get('stocks', {}))}个, "
                 f"黄金 {'有' if realtime_data.get('gold') else '无'}, "
                 f"外汇 {len(realtime_data.get('forex', {}))}个")

    # 跳过验证(测试模式)
    if args.skip_verification:
        print_warning("⚠️ 跳过验证步骤(测试模式)")

        print_step(3, 7, "调用Gemini生成报告")
        report_text, usage = call_gemini_with_realtime_data(
            api_key, articles, realtime_data, args.model
        )

        return {
            'report': report_text,
            'quality': {'score': 0, 'passed': False},
            'usage': usage,
            'metadata': {
                'date': date,
                'llm': 'gemini',
                'articles_count': len(articles),
                'verification_skipped': True
            },
            'success': True
        }

    # 步骤3-7: 生成报告 + 验证(带重试)
    fact_checker = FactChecker(fetcher)

    for attempt in range(1, args.max_retries + 1):
        print_step(3, 7, f"生成报告 (尝试 {attempt}/{args.max_retries})")

        # 调用Gemini
        report_text, usage = call_gemini_with_realtime_data(
            api_key, articles, realtime_data, args.model
        )

        print_success(f"报告生成完成 (长度: {len(report_text):,} 字符)")

        # 步骤4: 事实核查
        print_step(4, 7, "事实核查验证")
        claims = fact_checker.extract_claims(report_text)
        print_info(f"提取到 {len(claims)} 个断言")

        verified_claims = fact_checker.verify_claims(claims, realtime_data)
        verified_count = sum(1 for c in verified_claims if c.verified)
        print_info(f"验证完成: {verified_count}/{len(claims)} 通过")

        # 步骤5: 质量评分
        print_step(5, 7, "计算质量评分")
        quality_result = check_report_quality_v2(
            report_text=report_text,
            claims=verified_claims,
            realtime_data=realtime_data
        )

        # 打印质量报告
        print_quality_report_v2(quality_result, verbose=args.verbose)

        # 步骤6: 检查是否通过
        if quality_result['passed'] and quality_result['score'] >= args.min_score:
            print_step(6, 7, "报告质量检查: ✅ 通过")

            # 追加事实核查报告
            print_step(7, 7, "追加事实核查报告")
            annotation = fact_checker.generate_report_annotation(verified_claims)
            final_report = report_text + annotation

            print_success(f"✅ 报告生成完成! (评分: {quality_result['score']}, 尝试: {attempt})")

            return {
                'report': final_report,
                'quality': quality_result,
                'usage': usage,
                'metadata': {
                    'date': date,
                    'llm': 'gemini',
                    'model': usage.get('model', ''),
                    'articles_count': len(articles),
                    'attempts': attempt,
                    'realtime_data_used': True,
                    'fact_checked': True,
                    'verified_claims': verified_count,
                    'total_claims': len(claims)
                },
                'success': True
            }
        else:
            print_warning(f"❌ 报告质量不达标 (评分: {quality_result['score']}, 要求: {args.min_score})")

            if attempt < args.max_retries:
                print_info(f"准备第 {attempt+1} 次重试...")
            else:
                print_error(f"达到最大重试次数 ({args.max_retries}),仍未通过验证")

                # 返回最后一次结果(即使不达标)
                annotation = fact_checker.generate_report_annotation(verified_claims)
                final_report = report_text + annotation

                return {
                    'report': final_report,
                    'quality': quality_result,
                    'usage': usage,
                    'metadata': {
                        'date': date,
                        'llm': 'gemini',
                        'articles_count': len(articles),
                        'attempts': attempt,
                        'failed': True
                    },
                    'success': False
                }

    return {'success': False, 'error': '未知错误'}


def save_report(report: str, date: str, metadata: Dict, output_path: Optional[str] = None):
    """保存报告到文件"""
    if output_path:
        output_file = Path(output_path)
    else:
        # 默认路径: docs/archive/YYYY-MM/YYYY-MM-DD/reports/
        year_month = date[:7]  # 2026-01
        report_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date / 'reports'
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%H%M')
        output_file = report_dir / f"📅 {date} 财经分析报告_gemini_verified_{timestamp}.md"

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 写入报告
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # 写入元数据
    metadata_file = output_file.with_suffix('.json')
    import json
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print_success(f"报告已保存: {output_file}")
    print_info(f"元数据已保存: {metadata_file}")

    return output_file


def main():
    args = parse_args()

    # 确定日期
    if args.date:
        date = args.date
    elif args.start:
        date = args.start
    else:
        date = datetime.now().strftime('%Y-%m-%d')

    print_header(f"AI财经报告生成器 (带实时数据验证)")
    print_info(f"日期: {date}")
    print_info(f"验证模式: {'关闭' if args.skip_verification else '开启'}")
    print_info(f"最大重试: {args.max_retries}")
    print_info(f"最低评分: {args.min_score}")

    try:
        # 加载API Key
        api_key = load_api_key(args)

        # 生成报告
        result = generate_verified_report(api_key, date, args)

        if not result['success']:
            print_error(f"报告生成失败: {result.get('error', '未知错误')}")
            sys.exit(1)

        # 保存报告
        output_file = save_report(
            result['report'],
            date,
            result['metadata'],
            args.output
        )

        # 打印统计
        print_header("生成统计")
        print_info(f"模型: {result['usage'].get('model', 'N/A')}")
        print_info(f"Token使用: {result['usage'].get('total_tokens', 0):,}")
        print_info(f"文章数: {result['metadata']['articles_count']}")
        print_info(f"尝试次数: {result['metadata'].get('attempts', 1)}")

        if not args.skip_verification:
            print_info(f"验证断言: {result['metadata'].get('verified_claims', 0)}/{result['metadata'].get('total_claims', 0)}")
            print_info(f"质量评分: {result['quality']['score']}/100")

        # 退出码
        sys.exit(0 if result['quality'].get('passed', False) else 1)

    except KeyboardInterrupt:
        print_warning("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print_error(f"发生错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
