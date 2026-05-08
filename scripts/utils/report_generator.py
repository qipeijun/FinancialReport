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
import json
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
    check_report_quality,
    print_quality_summary, add_quality_warning
)
from scripts.utils.investment_signal import (
    build_judgment_candidates,
    build_judgment_prompt_context,
    build_retry_feedback,
    enforce_judgment_rules,
    extract_json_payload,
    render_judgment_markdown,
)
from scripts.utils.stock_recommendation import (
    SecurityMasterProvider,
    PriceHistoryProvider,
    ValuationProvider,
    RecommendationScorer,
    render_stock_recommendation_markdown,
)
from scripts.utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_progress, print_statistics,
    configure_dashboard, start_stage, update_stage, finish_stage,
    note_event, heartbeat,
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

        self.security_master_provider = SecurityMasterProvider()
        self.price_history_provider = PriceHistoryProvider()
        self.valuation_provider = ValuationProvider(self.security_master_provider)

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
            'judgment_cards': 'judgment_cards_prompt.md',
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
            available_kinds = sum(
                1 for key in ('stocks', 'gold', 'forex')
                if data.get(key)
            )
            if available_kinds == 0:
                print_warning('实时行情接口当前均不可用，将继续生成报告，但不注入实时价格数据')
                return None
            else:
                print_success(f'✓ 获取成功: {available_kinds} 类实时数据')
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
        realtime_data: Optional[Dict[str, Any]] = None,
        report_mode: str = 'markdown-report',
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
                note_event(f'第 {attempt} 次质量重试')

            # 生成报告
            if attempt == 0:
                start_stage('调用 AI 模型', step=4, total=6, detail='整理提示词并发起模型请求')
                print_progress('调用AI模型生成投资分析报告...')
            else:
                start_stage('调用 AI 模型', step=4, total=6, detail=f'准备第 {attempt + 1} 次模型重试')

            ai_frames = ('[生成中]', '[组织结构]', '[等待返回]', '[整理输出]')
            ai_details = ('整理摘要结构', '等待模型返回', '校对生成片段')
            with heartbeat('AI 报告生成', interval_seconds=6.0, frames=ai_frames, details=ai_details):
                report, usage = self.provider.generate(prompt, content, **kwargs)

            if attempt == 0:
                print_success('✓ 报告生成完成')
            finish_stage('AI 生成完成', duration=True)

            # 质量检查
            if quality_check:
                start_stage('事实核查 / 质量检查', step=5, total=6, detail=f'执行第 {attempt + 1} 次质量检查')
                print_progress('质量检查中...')
                if self.enable_verification:
                    update_stage('抽取并验证实时数值断言')
                    verified_claims, _ = self._run_fact_check(report, realtime_data)
                    note_event(f'已验证 {len(verified_claims)} 个断言')
                    update_stage('计算验证版质量评分')
                    quality_result = quality_checker(
                        report,
                        claims=verified_claims,
                        realtime_data=realtime_data,
                        report_mode=report_mode,
                    )
                else:
                    update_stage('计算基础质量评分')
                    quality_result = quality_checker(report)

                if self.enable_verification:
                    print_quality_report_v2(quality_result)
                else:
                    print_quality_summary(quality_result)
                finish_stage('质量检查完成', duration=True)

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
                    note_event('质量检查已禁用')
                return report, usage, {}

        # 返回最后一次的结果
        return report, usage, quality_result if quality_check else {}

    def _run_fact_check(self, report_text: str, realtime_data: Optional[Dict[str, Any]]) -> Tuple[list, str]:
        """运行事实核查并返回断言与附加报告"""
        if not (self.enable_verification and realtime_data):
            return [], ''

        checker = FactChecker()
        claims = checker.extract_claims(report_text)
        verified_claims = checker.verify_claims(claims, realtime_data)
        verification_report = checker.generate_report_annotation(verified_claims)
        return verified_claims, verification_report

    def _save_result(
        self,
        end_date: str,
        report_text: str,
        usage: Dict[str, Any],
        meta: Dict[str, Any],
        output_json: Optional[str],
        json_payload: Optional[Dict[str, Any]] = None,
        artifact_suffix: str = '',
    ) -> Path:
        """保存报告、元数据和可选JSON"""
        update_stage('写入 Markdown 报告')
        print_progress('保存报告到文件...')
        model_suffix = self.provider.get_provider_name().lower()
        saved_path = save_markdown(
            end_date,
            report_text,
            model_suffix=model_suffix,
            artifact_suffix=artifact_suffix,
        )
        note_event(f'报告已保存: {saved_path.name}')
        update_stage('写入 metadata')
        save_metadata(
            end_date,
            meta,
            model_suffix=model_suffix,
            artifact_suffix=artifact_suffix,
        )
        note_event('metadata 已保存')

        if output_json:
            update_stage('导出 JSON 结果')
            out_path = Path(output_json)
            if not out_path.is_absolute():
                out_path = PROJECT_ROOT / out_path
            payload = json_payload or {'summary_markdown': report_text, 'model_usage': usage}
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print_success(f'已导出 JSON: {out_path}')
            note_event(f'JSON 已导出: {out_path.name}')
        finish_stage('保存产物完成', duration=True)
        return saved_path

    def _generate_judgment_cards(
        self,
        *,
        start_date: str,
        end_date: str,
        selected: list,
        realtime_data: Optional[Dict[str, Any]],
        max_retries: int,
        min_score: int,
        output_json: Optional[str],
        max_theses: int,
        min_source_tier: str,
        min_independent_evidence: int,
        degrade_on_weak_evidence: bool,
        output_observation_only_when_weak: bool,
        **provider_kwargs,
    ) -> Dict[str, Any]:
        candidates = build_judgment_candidates(selected, max_candidates=max(max_theses + 3, 6))
        prompt = self.load_prompt('judgment_cards')
        base_content = build_judgment_prompt_context(candidates, bool(realtime_data), max_theses)
        retry_feedback = ''
        last_error = ''
        payload: Dict[str, Any] = {}
        rendered_md = ''
        usage: Dict[str, Any] = {}
        quality_result: Dict[str, Any] = {}
        verified_claims = []
        verification_report = ''

        for attempt in range(max_retries + 1):
            content = base_content if not retry_feedback else f"{base_content}\n\n{retry_feedback}"
            try:
                start_stage('调用 AI 模型', detail=f'生成判断卡片（第 {attempt + 1} 次）')
                with heartbeat(
                    'AI 判断卡片生成',
                    interval_seconds=6.0,
                    frames=('[构思中]', '[抽取证据]', '[组织结论]', '[等待返回]'),
                    details=('抽取候选证据', '组织判断结构', '等待模型完成'),
                ):
                    raw_text, usage = self.provider.generate(prompt, content, **provider_kwargs)
                finish_stage('判断卡片 AI 输出完成', duration=True)
                payload = extract_json_payload(raw_text)
                payload = enforce_judgment_rules(
                    payload,
                    candidates,
                    realtime_available=bool(realtime_data),
                    min_source_tier=min_source_tier,
                    min_independent_evidence=min_independent_evidence,
                    degrade_on_weak_evidence=degrade_on_weak_evidence,
                    output_observation_only_when_weak=output_observation_only_when_weak,
                    max_theses=max_theses,
                )
                rendered_md = render_judgment_markdown(payload)
                start_stage('事实核查 / 质量检查', detail='校验判断卡片内容')
                verified_claims, verification_report = self._run_fact_check(rendered_md, realtime_data)
                quality_result = check_report_quality_v2(
                    rendered_md,
                    claims=verified_claims,
                    realtime_data=realtime_data,
                    report_mode='judgment-cards',
                )
                finish_stage('判断卡片质量检查完成', duration=True)
            except Exception as exc:
                last_error = str(exc)
                quality_result = {
                    'score': 0,
                    'passed': False,
                    'issues': [f'判断卡片生成失败: {exc}'],
                    'warnings': [],
                }

            if quality_result.get('passed') and quality_result.get('score', 0) >= min_score:
                break
            if attempt < max_retries:
                retry_feedback = build_retry_feedback(quality_result)
                print_warning(f'判断卡片质量未达标，准备第 {attempt + 1} 次重试')
            else:
                print_warning('判断卡片达到最大重试次数，将使用当前版本')

        if not rendered_md:
            return {'success': False, 'error': last_error or '未生成有效判断卡片'}

        if verification_report:
            rendered_md = f"{rendered_md}\n\n{verification_report}"

        live_data_degraded = bool(self.enable_verification and realtime_data is None)
        meta = {
            'date_range': {'start': start_date, 'end': end_date},
            'articles_used': len(selected),
            'candidate_count': len(candidates),
            'model_usage': usage,
            'quality_check': quality_result,
            'verification_enabled': self.enable_verification,
            'output_mode': 'judgment-cards',
            'degraded': payload.get('degraded', False),
            'live_data_degraded': live_data_degraded,
            'thesis_count': len(payload.get('theses') or []),
            'watch_item_count': len(payload.get('watch_items') or []),
            'backtest_ready': True,
            'backtest_generated_at': datetime.now().isoformat(),
        }
        export_payload = {
            'theses': payload.get('theses') or [],
            'watch_items': payload.get('watch_items') or [],
            'confidence': [thesis.get('confidence', '中') for thesis in payload.get('theses') or []],
            'evidence_summary': payload.get('evidence_summary', ''),
            'market_scope': payload.get('market_scope', '中国与全球联动'),
            'time_horizon': payload.get('time_horizon', '1-4周'),
            'degraded': payload.get('degraded', False),
            'metadata': meta,
        }
        meta.update({
            'export_payload_refreshed': True,
        })
        saved_path = self._save_result(
            end_date,
            rendered_md,
            usage,
            meta,
            output_json,
            export_payload,
            artifact_suffix='judgment-cards',
        )

        print_success('判断卡片生成完成！')
        print_statistics({
            '分析日期范围': f"{start_date} → {end_date}",
            '处理文章数': len(selected),
            '判断卡片数': len(payload.get('theses') or []),
            '观察项数': len(payload.get('watch_items') or []),
            '使用模型': usage.get('model', '未知'),
            '降级状态': '是' if payload.get('degraded') else '否',
        })
        return {
            'success': True,
            'report_path': str(saved_path),
            'report_text': rendered_md,
            'metadata': meta,
            'quality_result': quality_result,
            'payload': export_payload,
        }

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
        mode: str = 'markdown-report',
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
            mode: 输出模式（markdown-report/judgment-cards）
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

        configure_dashboard(title='Financial Report', total_steps=6)
        print_header(f"AI 财经分析系统（{self.provider.get_provider_name()}）")
        print_info(f"分析日期范围: {start_date} → {end_date}")
        print_info(f"输出模式: {mode}")
        print_info(f"字段选择模式: {content_field}")
        if self.enable_verification:
            print_info("验证系统: 已启用 ✅")
        if max_chars > 0:
            print_info(f"字符数限制: {max_chars:,}")
        if quality_check:
            print_info(f"质量检查: 已启用（最多重试{max_retries}次，最低评分{min_score}）")
        print()

        # 获取实时数据（如果启用验证）
        start_stage('获取实时数据', step=1, total=6, detail='检查实时行情可用性')
        realtime_data = self.fetch_realtime_data()
        live_data_degraded = bool(self.enable_verification and realtime_data is None)
        finish_stage('实时数据阶段完成', duration=True)

        # 查询文章
        start_stage('查询与筛选文章', step=2, total=6, detail='读取数据库中的候选文章')
        conn = open_connection(self.db_path)
        try:
            rows = query_articles(conn, start_date, end_date, order, limit)
        finally:
            conn.close()

        if not rows:
            print_warning('未找到指定日期范围的文章，终止分析。')
            return {'success': False, 'error': '未找到文章'}

        print_info(f'已读取文章：{len(rows):,} 条')
        note_event(f'已读取 {len(rows):,} 篇文章')

        # 过滤文章
        update_stage('应用来源、关键词与数量过滤')
        selected = filter_articles(
            rows,
            filter_source=filter_source,
            filter_keyword=filter_keyword,
            max_articles=max_articles
        )

        # 质量筛选和排序
        update_stage('执行质量筛选和智能去重')
        print_progress('质量筛选: 过滤低质量文章并智能去重...')
        selected, quality_stats = filter_and_rank_articles(selected)
        note_event(f'筛选后保留 {len(selected):,} 篇文章')

        if not selected:
            print_warning('质量筛选后无文章剩余，请降低阈值或检查数据源')
            return {'success': False, 'error': '质量筛选后无文章'}
        finish_stage('文章筛选完成', duration=True)

        if mode == 'judgment-cards':
            return self._generate_judgment_cards(
                start_date=start_date,
                end_date=end_date,
                selected=selected,
                realtime_data=realtime_data,
                max_retries=max_retries,
                min_score=min_score,
                output_json=output_json,
                max_theses=int(provider_kwargs.pop('max_theses', 5)),
                min_source_tier=provider_kwargs.pop('min_source_tier', 'mainstream'),
                min_independent_evidence=int(provider_kwargs.pop('min_independent_evidence', 2)),
                degrade_on_weak_evidence=bool(provider_kwargs.pop('degrade_on_weak_evidence', True)),
                output_observation_only_when_weak=bool(provider_kwargs.pop('output_observation_only_when_weak', True)),
                **provider_kwargs,
            )

        enable_stock_scoring = bool(provider_kwargs.pop('enable_stock_scoring', True))
        max_stock_picks = int(provider_kwargs.pop('max_stock_picks', 10))
        stock_market = provider_kwargs.pop('stock_market', 'CN')

        # 构建语料
        start_stage('构建语料', step=3, total=6, detail='拼接文章语料与来源统计')
        pairs, total_len = build_corpus(selected, max_chars, per_chunk_chars=3000, content_field=content_field)
        current_len = sum(len(c) for _, chunks in pairs for c in chunks)
        usage_pct = (current_len / max_chars * 100) if max_chars and max_chars > 0 else 0
        print_info(f'语料长度: {current_len:,} 字符（原始 {total_len:,}，限制={max_chars:,}，使用率 {usage_pct:.1f}%）')
        note_event(f'语料长度 {current_len:,} 字符')
        if max_chars and max_chars > 0 and total_len > max_chars:
            print_warning(f'语料已按上限截断：{total_len:,} → {current_len:,}')

        # 构建统计信息
        stats_info = build_source_stats_block(selected, content_field, start_date, end_date)

        # 注入实时数据（如果有）
        if realtime_data:
            update_stage('注入实时市场数据到提示词')
            print_progress('注入实时市场数据到提示词...')
            realtime_block = self._format_realtime_data(realtime_data)
            stats_info = realtime_block + "\n\n" + stats_info

        joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
        full_content = stats_info + "\n\n" + joined
        finish_stage('语料构建完成', duration=True)

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
                realtime_data=realtime_data,
                report_mode='markdown-report',
                **provider_kwargs
            )
        except Exception as e:
            print_error(f'报告生成失败: {e}')
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

        # 事实核查（如果启用验证）
        verified_claims, verification_report = self._run_fact_check(summary_md, realtime_data)
        if verification_report:
            start_stage('事实核查 / 质量检查', step=5, total=6, detail='合并事实核查附注')
            summary_md += "\n\n" + verification_report
            print_success(f'✓ 事实核查完成: {len(verified_claims)} 个断言')
            finish_stage('事实核查附注已合并', duration=False)

        stock_payload = {
            'recommendations': [],
            'score_distribution': {'strong_focus': 0, 'focus': 0, 'watch': 0, 'avoid': 0},
            'scoring_config': {
                'market': stock_market,
                'style': 'balanced',
                'lookback_days': 60,
            },
        }
        if enable_stock_scoring and stock_market == 'CN':
            start_stage('事实核查 / 质量检查', step=5, total=6, detail='生成 A 股结构化推荐评分')
            print_progress('生成 A 股结构化推荐评分...')
            judgment_candidates = build_judgment_candidates(selected, max_candidates=8)
            candidate_stocks = self.security_master_provider.build_candidates(
                articles=selected,
                judgment_candidates=judgment_candidates,
                max_candidates=max_stock_picks,
            )
            scorer = RecommendationScorer(
                security_master=self.security_master_provider,
                price_history_provider=self.price_history_provider,
                valuation_provider=self.valuation_provider,
                lookback_days=60,
                style='balanced',
            )
            stock_payload = scorer.score_candidates(candidate_stocks)
            stock_section = render_stock_recommendation_markdown(
                stock_payload['recommendations'],
                scoring_config=stock_payload['scoring_config'],
            )
            summary_md = f"{summary_md.rstrip()}\n\n{stock_section}\n"
            print_success(f"✓ 已生成 {len(stock_payload['recommendations'])} 条股票评分结果")
            finish_stage('股票评分生成完成', duration=True)

        # 保存报告
        meta = {
            'date_range': {'start': start_date, 'end': end_date},
            'articles_used': len(selected),
            'chunks': sum(len(ch) for _, ch in pairs),
            'model_usage': usage,
            'quality_check': quality_result if quality_result else None,
            'verification_enabled': self.enable_verification,
            'output_mode': 'markdown-report',
            'live_data_degraded': live_data_degraded,
            'stock_recommendations': stock_payload['recommendations'],
            'score_distribution': stock_payload['score_distribution'],
            'scoring_config': stock_payload['scoring_config'],
            'backtest_ready': True,
            'backtest_generated_at': datetime.now().isoformat(),
        }
        export_payload = {
            'summary_markdown': summary_md,
            'articles': rows,
            'metadata': meta,
            'stock_recommendations': stock_payload['recommendations'],
            'score_distribution': stock_payload['score_distribution'],
            'scoring_config': stock_payload['scoring_config'],
        }
        start_stage('保存报告与元数据', step=6, total=6, detail='准备写入报告归档与 metadata')
        saved_path = self._save_result(
            end_date,
            summary_md,
            usage,
            meta,
            output_json,
            export_payload,
            artifact_suffix='markdown-report',
        )

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
        prompt_block = realtime_data.get('prompt')
        if isinstance(prompt_block, str) and prompt_block.strip():
            return prompt_block.strip()

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
