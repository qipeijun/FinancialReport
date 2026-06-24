#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一报告生成引擎

核心功能:
1. 文章查询和过滤
2. 质量筛选和去重
3. 语料构建
4. AI报告生成（支持多个提供商）
5. 质量检查和自动重试
6. 报告保存和元数据记录

使用示例:
    from utils.report_generator import ReportGenerator
    from utils.providers import DeepSeekProvider

    generator = ReportGenerator(
        provider=DeepSeekProvider(api_key='your-key'),
        enable_verification=True
    )

    result = generator.generate(
        date='2026-01-07',
        quality_check=True,
        max_retries=3
    )
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.ai_analyzer_common import (
    resolve_date_range, open_connection, query_articles,
    filter_articles, build_corpus, build_source_stats_block,
    save_markdown, save_metadata, write_json
)
from scripts.utils.quality_filter import filter_and_rank_articles
from scripts.utils.quality_checker import (
    check_report_quality, generate_quality_feedback,
    print_quality_summary, add_quality_warning
)
from scripts.utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_step, print_statistics
)
from scripts.utils.providers import BaseProvider

# 验证系统模块（可选）
try:
    from scripts.utils.realtime_data_fetcher import RealtimeDataFetcher
    from scripts.utils.fact_checker import FactChecker
    from scripts.utils.quality_checker_v2 import check_report_quality_v2, print_quality_report_v2
    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False


class ReportGenerator:
    """统一报告生成引擎"""

    def __init__(
        self,
        provider: BaseProvider,
        db_path: Optional[Path] = None,
        enable_verification: bool = False,
        **config
    ):
        """
        初始化报告生成器

        Args:
            provider: AI模型提供商实例
            db_path: 数据库路径（默认为项目根目录/data/news_data.db）
            enable_verification: 是否启用验证系统（实时数据+事实核查+高级质量评分）
            **config: 其他配置参数
        """
        self.provider = provider
        self.db_path = db_path or (PROJECT_ROOT / 'data' / 'news_data.db')
        self.enable_verification = enable_verification
        self.config = config

        if enable_verification and not VERIFICATION_AVAILABLE:
            print_warning('验证系统模块未找到，已禁用验证功能')
            self.enable_verification = False

    def load_prompt(self, prompt_version: str = 'pro_v2') -> str:
        """
        加载提示词模板

        Args:
            prompt_version: 提示词版本
                - 'pro_v2': 专业版v2（带实时数据注入）
                - 'pro': 专业版
                - 'safe': 安全版

        Returns:
            str: 提示词内容
        """
        prompt_files = {
            'pro_v2': 'financial_analysis_prompt_pro_v2.md',
            'pro': 'financial_analysis_prompt_pro.md',
            'safe': 'financial_analysis_prompt_safe.md'
        }

        prompt_file = prompt_files.get(prompt_version, prompt_files['pro'])
        prompt_path = PROJECT_ROOT / 'task' / prompt_file

        if not prompt_path.exists():
            # 回退到专业版
            print_warning(f'提示词 {prompt_file} 不存在，回退到 pro 版本')
            prompt_path = PROJECT_ROOT / 'task' / 'financial_analysis_prompt_pro.md'

        if not prompt_path.exists():
            raise FileNotFoundError(f'提示词文件不存在: {prompt_path}')

        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def fetch_realtime_data(self) -> Optional[Dict[str, Any]]:
        """获取实时市场数据（如果启用验证）"""
        if not self.enable_verification:
            return None

        try:
            print_progress('获取实时市场数据...')
            fetcher = RealtimeDataFetcher()
            data = fetcher.fetch_all()
            print_success(f'✓ 获取成功: {len(data)} 类数据')
            return data
        except Exception as e:
            print_warning(f'实时数据获取失败: {e}')
            return None

    def generate_with_quality_check(
        self,
        prompt: str,
        content: str,
        quality_check: bool = False,
        max_retries: int = 0,
        min_score: int = 80,
        **kwargs
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """
        生成报告并进行质量检查

        Args:
            prompt: 系统提示词
            content: 用户输入内容
            quality_check: 是否启用质量检查
            max_retries: 质量不达标时的最大重试次数
            min_score: 最低质量评分
            **kwargs: 传递给provider的其他参数

        Returns:
            Tuple[str, Dict, Dict]: (报告文本, 使用统计, 质量检查结果)
        """
        quality_checker = check_report_quality_v2 if self.enable_verification else check_report_quality

        for attempt in range(max_retries + 1):
            if attempt > 0:
                print_warning(f'\n🔄 质量不达标，第{attempt}次重试（共{max_retries}次）...\n')

            # 生成报告
            if attempt == 0:
                print_progress('调用AI模型生成投资分析报告...')

            report, usage = self.provider.generate(prompt, content, **kwargs)

            if attempt == 0:
                print_success('✓ 报告生成完成')

            # 质量检查
            if quality_check:
                print_progress('质量检查中...')
                quality_result = quality_checker(report)

                if self.enable_verification:
                    print_quality_report_v2(quality_result)
                else:
                    print_quality_summary(quality_result)

                # 判断是否通过
                passed = quality_result.get('passed', quality_result.get('score', 0) >= min_score)

                if passed:
                    print_success('✅ 质量检查通过\n')
                    return report, usage, quality_result
                else:
                    if attempt < max_retries:
                        score = quality_result.get('score', 0)
                        issues_count = len(quality_result.get('issues', []))
                        warnings_count = len(quality_result.get('warnings', []))
                        print_warning(f'⚠️ 质量评分: {score}/100 (要求≥{min_score})')
                        print_info(f'问题数量: {issues_count}个严重问题, {warnings_count}个警告')
                    else:
                        print_error(f'❌ 已达最大重试次数({max_retries}次)，使用当前版本')
                        print_warning('报告质量可能不理想，建议人工审核')
                        report = add_quality_warning(report, quality_result)
                        return report, usage, quality_result
            else:
                # 不启用质量检查，直接返回
                if attempt == 0:
                    print_info('  ℹ️ 质量检查已禁用，报告未经二次处理')
                return report, usage, {}

        # 返回最后一次的结果
        return report, usage, quality_result if quality_check else {}

    def generate(
        self,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 0,
        max_articles: Optional[int] = None,
        filter_source: Optional[str] = None,
        filter_keyword: Optional[str] = None,
        order: str = 'desc',
        max_chars: int = 500000,
        content_field: str = 'summary',
        quality_check: bool = False,
        max_retries: int = 0,
        min_score: int = 80,
        prompt_version: str = 'pro_v2' if VERIFICATION_AVAILABLE else 'pro',
        output_json: Optional[str] = None,
        **provider_kwargs
    ) -> Dict[str, Any]:
        """
        生成AI分析报告（主入口）

        Args:
            date: 单日日期（YYYY-MM-DD）
            start: 开始日期（YYYY-MM-DD）
            end: 结束日期（YYYY-MM-DD）
            limit: 最多读取多少条记录
            max_articles: 参与分析的文章数量上限
            filter_source: 仅分析指定来源（逗号分隔）
            filter_keyword: 关键词过滤（逗号分隔）
            order: 排序方向（asc/desc）
            max_chars: 传入模型的最大字符数上限
            content_field: 分析字段（summary/content/auto）
            quality_check: 是否启用质量检查
            max_retries: 质量不达标时的最大重试次数
            min_score: 最低质量评分
            prompt_version: 提示词版本
            output_json: 可选：导出JSON文件路径
            **provider_kwargs: 传递给provider的其他参数

        Returns:
            Dict: 生成结果，包含 report, metadata, quality_result
        """
        # 解析日期范围
        class Args:
            pass
        args = Args()
        args.date = date
        args.start = start
        args.end = end
        start_date, end_date = resolve_date_range(args)

        print_header(f"AI 财经分析系统（{self.provider.get_provider_name()}）")
        print_info(f"分析日期范围: {start_date} → {end_date}")
        print_info(f"字段选择模式: {content_field}")
        if self.enable_verification:
            print_info("验证系统: 已启用 ✅")
        if max_chars > 0:
            print_info(f"字符数限制: {max_chars:,}")
        if quality_check:
            print_info(f"质量检查: 已启用（最多重试{max_retries}次，最低评分{min_score}）")
        print()

        # 获取实时数据（如果启用验证）
        realtime_data = self.fetch_realtime_data()

        # 查询文章
        conn = open_connection(self.db_path)
        try:
            rows = query_articles(conn, start_date, end_date, order, limit)
        finally:
            conn.close()

        if not rows:
            print_warning('未找到指定日期范围的文章，终止分析。')
            return {'success': False, 'error': '未找到文章'}

        print_info(f'已读取文章：{len(rows):,} 条')

        # 过滤文章
        selected = filter_articles(
            rows,
            filter_source=filter_source,
            filter_keyword=filter_keyword,
            max_articles=max_articles
        )

        # 质量筛选和排序
        print_progress('质量筛选: 过滤低质量文章并智能去重...')
        selected, quality_stats = filter_and_rank_articles(selected)

        if not selected:
            print_warning('质量筛选后无文章剩余，请降低阈值或检查数据源')
            return {'success': False, 'error': '质量筛选后无文章'}

        # 构建语料
        pairs, total_len = build_corpus(selected, max_chars, per_chunk_chars=3000, content_field=content_field)
        current_len = sum(len(c) for _, chunks in pairs for c in chunks)
        usage_pct = (current_len / max_chars * 100) if max_chars and max_chars > 0 else 0
        print_info(f'语料长度: {current_len:,} 字符（原始 {total_len:,}，限制={max_chars:,}，使用率 {usage_pct:.1f}%）')
        if max_chars and max_chars > 0 and total_len > max_chars:
            print_warning(f'语料已按上限截断：{total_len:,} → {current_len:,}')

        # 构建统计信息
        stats_info = build_source_stats_block(selected, content_field, start_date, end_date)

        # 注入实时数据（如果有）
        if realtime_data:
            print_progress('注入实时市场数据到提示词...')
            realtime_block = self._format_realtime_data(realtime_data)
            stats_info = realtime_block + "\n\n" + stats_info

        joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
        full_content = stats_info + "\n\n" + joined

        # 加载提示词
        prompt = self.load_prompt(prompt_version)

        # 生成报告（集成质量检查）
        print()
        try:
            summary_md, usage, quality_result = self.generate_with_quality_check(
                prompt, full_content,
                quality_check=quality_check,
                max_retries=max_retries,
                min_score=min_score,
                **provider_kwargs
            )
        except Exception as e:
            print_error(f'报告生成失败: {e}')
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

        # 事实核查（如果启用验证）
        if self.enable_verification and realtime_data:
            print_progress('事实核查: 验证报告中的数据断言...')
            try:
                checker = FactChecker(realtime_data)
                check_result = checker.check_report(summary_md)

                # 追加核查报告
                verification_report = checker.generate_verification_report(check_result)
                summary_md += "\n\n" + verification_report
                print_success(f'✓ 事实核查完成: {check_result["stats"]["total"]} 个断言')
            except Exception as e:
                print_warning(f'事实核查失败（跳过）: {e}')

        # 保存报告
        print_progress('保存报告到文件...')
        model_suffix = self.provider.get_provider_name().lower()
        saved_path = save_markdown(end_date, summary_md, model_suffix=model_suffix)

        # 保存元数据
        meta = {
            'date_range': {'start': start_date, 'end': end_date},
            'articles_used': len(selected),
            'chunks': sum(len(ch) for _, ch in pairs),
            'model_usage': usage,
            'quality_check': quality_result if quality_result else None,
            'verification_enabled': self.enable_verification,
        }
        save_metadata(end_date, meta, model_suffix=model_suffix)

        # 可选导出JSON
        if output_json:
            out_path = Path(output_json)
            if not out_path.is_absolute():
                out_path = PROJECT_ROOT / out_path
            write_json(out_path, summary_md, rows)

        print_success('分析完成！')

        # 打印统计信息
        stats = {
            '分析日期范围': f"{start_date} → {end_date}",
            '处理文章数': len(selected),
            '语料块数': sum(len(ch) for _, ch in pairs),
            '最终字符数': f"{current_len:,}",
            '使用模型': usage.get('model', '未知'),
            'Token消耗': f"{usage.get('total_tokens', 0):,}" if usage.get('total_tokens') else '未知'
        }
        print_statistics(stats)

        return {
            'success': True,
            'report_path': str(saved_path),
            'report_text': summary_md,
            'metadata': meta,
            'quality_result': quality_result
        }

    def _format_realtime_data(self, realtime_data: Dict[str, Any]) -> str:
        """格式化实时数据为Markdown块"""
        lines = ["## 📊 实时市场数据", ""]

        for key, value in realtime_data.items():
            if isinstance(value, dict):
                lines.append(f"### {key}")
                for k, v in value.items():
                    lines.append(f"- **{k}**: {v}")
                lines.append("")
            else:
                lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)
