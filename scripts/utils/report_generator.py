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
    filter_articles, build_corpus, build_source_stats_block, summarize_content_quality,
    save_markdown, save_metadata, save_enhanced_context, write_json
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
from scripts.utils.cross_verification import (
    run_cross_verification,
    CROSS_STATUS_CONFIRMED,
    CROSS_STATUS_WEAK,
    CROSS_STATUS_CONFLICTED,
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


# 美股模式默认消费的新闻源（美股聚焦 + 国际财经 + 美国官方）
US_MARKET_SOURCE_NAMES = [
    'Yahoo Finance', 'MarketWatch', 'Seeking Alpha', 'CNBC Top News',
    "Investor's Business Daily",
    'FT中文网', 'Wall Street Journal', '经济学人 Economist',
    'BBC全球经济', 'CNBC', 'ZeroHedge', 'ETF Trends', 'Thomson Reuters',
    'Federal Reserve Board', '美国证监会-新闻发布',
]


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
        self.security_master_us = SecurityMasterProvider(
            config_path=PROJECT_ROOT / 'config' / 'theme_stock_map_us.json'
        )
        self.price_history_provider = PriceHistoryProvider()
        self.valuation_provider = ValuationProvider(self.security_master_provider)

    def load_prompt(self, prompt_version: str = 'pro_v2', market: str = 'CN') -> str:
        """
        加载提示词模板

        Args:
            prompt_version: 提示词版本
                - 'pro_v2': 专业版v2（带实时数据注入）
                - 'pro': 专业版
                - 'safe': 安全版
            market: 市场标识，'US' 时优先加载美股专用提示词

        Returns:
            str: 提示词内容
        """
        # 美股专用提示词
        if market == 'US' and prompt_version in ('pro_v2', 'pro', 'safe'):
            us_file = f'financial_analysis_prompt_us.md'
            us_path = PROJECT_ROOT / 'task' / us_file
            if us_path.exists():
                with open(us_path, 'r', encoding='utf-8') as f:
                    return f.read()

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

    def fetch_realtime_data(self, market: str = 'CN') -> Optional[Dict[str, Any]]:
        """获取实时市场数据（如果启用验证）"""
        if not self.enable_verification:
            return None

        try:
            print_progress('获取实时市场数据...')
            fetcher = RealtimeDataFetcher()
            data = fetcher.fetch_all(market=market)
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
        stock_recommendations: Optional[list] = None,
        judgment_candidates: Optional[list] = None,
        data_quality_stats: Optional[Dict[str, Any]] = None,
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
            report = self._attach_realtime_source_annotation(report, realtime_data)

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
                        stock_recommendations=stock_recommendations,
                        judgment_candidates=judgment_candidates,
                        data_quality_stats=data_quality_stats,
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

    @staticmethod
    def _quality_metadata_fields(quality_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = quality_result or {}
        stats = payload.get('stats') or {}
        return {
            'quality_score': payload.get('score'),
            'quality_stats': payload.get('stats'),
            'quality_issues': payload.get('issues'),
            'quality_warnings': payload.get('warnings'),
            'time_source': payload.get('time_source') or stats.get('time_source'),
            'source_annotation_missing': payload.get('source_annotation_missing') if 'source_annotation_missing' in payload else stats.get('source_annotation_missing'),
            'claim_coverage_score': payload.get('claim_coverage_score') if 'claim_coverage_score' in payload else stats.get('claim_coverage_score'),
        }

    def _run_fact_check(self, report_text: str, realtime_data: Optional[Dict[str, Any]]) -> Tuple[list, str]:
        """运行事实核查并返回断言与附加报告"""
        if not (self.enable_verification and realtime_data):
            return [], ''

        checker = FactChecker()
        claims = checker.extract_claims(report_text)
        verified_claims = checker.verify_claims(claims, realtime_data)
        verification_report = checker.generate_report_annotation(verified_claims)
        return verified_claims, verification_report

    @staticmethod
    def _realtime_source_annotation(realtime_data: Optional[Dict[str, Any]]) -> str:
        if not realtime_data:
            return ''
        timestamp = realtime_data.get('timestamp')
        if not timestamp:
            return ''
        return (
            "## 📊 实时数据来源\n\n"
            "- 数据来源: Yahoo Finance、Gold-API、Frankfurter\n"
            f"- 更新时间: {timestamp}\n"
        )

    def _attach_realtime_source_annotation(self, report_text: str, realtime_data: Optional[Dict[str, Any]]) -> str:
        """把确定性的实时数据来源写入报告文本，避免模型自由生成来源口径。"""
        annotation = self._realtime_source_annotation(realtime_data)
        if not annotation or '## 📊 实时数据来源' in report_text:
            return report_text
        return f"{report_text.rstrip()}\n\n{annotation}"

    @staticmethod
    def _build_prompt_signal_context(
        judgment_candidates: list,
        stock_payload: Dict[str, Any],
        data_quality_stats: Dict[str, Any],
        cross_verification_result: Dict[str, Any] | None = None,
    ) -> str:
        """把结构化主题、推荐和数据质量约束显式注入给 markdown-report。"""
        high_confidence = [
            item for item in judgment_candidates
            if bool(item.get('high_confidence_topic'))
        ]
        watch_topics = [
            item for item in judgment_candidates
            if not bool(item.get('high_confidence_topic'))
        ][:4]
        recommendations = stock_payload.get('recommendations') or []
        actionable = stock_payload.get('decision_views', {}).get('actionable_candidates') or []
        watchlist = stock_payload.get('decision_views', {}).get('conditional_watchlist') or []
        stale = stock_payload.get('decision_views', {}).get('stale_or_rejected') or []
        counts = data_quality_stats.get('counts') or {}
        ratios = data_quality_stats.get('ratios') or {}

        lines = [
            "=== 高信号输出约束 ===",
            f"- 高置信主题数量: {len(high_confidence)}",
            f"- 观察主题数量: {len(watch_topics)}",
            f"- 结构化推荐数量: {len(recommendations)}",
            f"- 可行动推荐数量: {len(actionable)}",
            f"- 观察清单数量: {len(watchlist)}",
            f"- 拒绝/拥挤清单数量: {len(stale)}",
            f"- 数据质量: 完整正文 {counts.get('full', 0)}篇({ratios.get('full', 0.0):.1f}%), 部分正文 {counts.get('partial', 0)}篇({ratios.get('partial', 0.0):.1f}%), 仅摘要 {counts.get('summary_only', 0)}篇({ratios.get('summary_only', 0.0):.1f}%)",
            "- 正文只能使用下列主题和标的，禁止自行扩写新的股票池、行业配比或宏大资产配置口号。",
            "- 事实核查只覆盖实时数值与部分新闻事实；不得把“已验证的实时断言”扩写成“整份报告已证实”或“整篇 thesis 已验证”。",
            "- 只有 actionable_candidates 可以写成“可行动标的”；conditional_watchlist 只能写成“继续观察”，stale_or_rejected 只能写成风险或等待项。",
        ]

        if high_confidence:
            lines.append("- 可写成高置信主题:")
            for item in high_confidence[:3]:
                lines.append(
                    f"  * {item.get('topic')}: topic_article_count={item.get('topic_article_count', 0)}, independent_evidence_count={item.get('independent_evidence_count', 0)}, source_tier_max={item.get('source_tier_max')}"
                )
        else:
            lines.append("- 当前没有可写成高置信结论的主题，正文必须以观察项为主。")

        if watch_topics:
            lines.append("- 仅允许写成观察项的主题:")
            for item in watch_topics:
                lines.append(
                    f"  * {item.get('topic')}: topic_article_count={item.get('topic_article_count', 0)}, independent_evidence_count={item.get('independent_evidence_count', 0)}"
                )

        if recommendations:
            lines.append("- 允许在正文中提到的结构化标的:")
            for item in recommendations[:8]:
                lines.append(
                    f"  * {item.get('symbol')} {item.get('name')} / {item.get('grade')} / source_type={item.get('source_type')} / grade_caps={','.join(item.get('grade_caps') or ['none'])} / actionable={'yes' if item.get('actionability_passed') else 'no'}"
                )
        else:
            lines.append("- 当前没有满足规则门槛的结构化股票推荐，正文不得写具体股票推荐。")

        if len(actionable) <= 1:
            lines.append("- 由于可行动推荐少于等于1个，正文不得写成多只核心持仓组合。")
        if not high_confidence and not actionable:
            lines.append("- 若主题与推荐都偏弱，正文必须退化为“观察清单 + 风险 + 验证点”。")

        if cross_verification_result:
            cv = cross_verification_result
            cv_summary = cv.get('summary', {})
            lines.append("")
            lines.append("=== 交叉验真约束 ===")
            lines.append(
                f"- 主题交叉验真: {cv_summary.get('topics_confirmed', 0)} confirmed, "
                f"{cv_summary.get('topics_weak', 0)} weak, "
                f"{cv_summary.get('topics_conflicted', 0)} conflicted"
            )
            lines.append(
                f"- 标的交叉验真: {cv_summary.get('stocks_confirmed', 0)} confirmed, "
                f"{cv_summary.get('stocks_weak', 0)} weak, "
                f"{cv_summary.get('stocks_conflicted', 0)} conflicted"
            )
            conflicted_topics = [
                tc.get('topic', '') for tc in cv.get('topic_checks', [])
                if tc.get('status') == CROSS_STATUS_CONFLICTED
            ]
            if conflicted_topics:
                lines.append(
                    f"- 冲突主题: {', '.join(conflicted_topics[:3])} "
                    "-- 正文必须标注为'证据矛盾，待进一步确认'"
                )
            conflicted_stocks = [
                sc.get('symbol', '') for sc in cv.get('stock_checks', [])
                if sc.get('status') == CROSS_STATUS_CONFLICTED
            ]
            if conflicted_stocks:
                lines.append(
                    f"- 冲突标的: {', '.join(conflicted_stocks[:5])} "
                    "-- 禁止写成'可行动'，必须注明正反证据并存"
                )
            lines.append("- 正文中只有 cross_verification_status=confirmed 的标的才能写成'已验证''强确认'")
            lines.append("- weak/conflicted 标的禁止使用'多来源验证''确定性高''可行动'等表述")

        return "\n".join(lines)

    @staticmethod
    def _render_structured_recommendation_summary(
        judgment_candidates: list,
        stock_payload: Dict[str, Any],
        cross_verification_result: Dict[str, Any] | None = None,
    ) -> str:
        """基于结构化真相源补一段短摘要，避免正文与评分层分裂。"""
        high_confidence = [
            item for item in judgment_candidates
            if bool(item.get('high_confidence_topic'))
        ]
        watch_topics = [
            item for item in judgment_candidates
            if not bool(item.get('high_confidence_topic'))
        ]
        actionable = stock_payload.get('decision_views', {}).get('actionable_candidates') or []
        watchlist = stock_payload.get('decision_views', {}).get('conditional_watchlist') or []
        stale = stock_payload.get('decision_views', {}).get('stale_or_rejected') or []

        lines = [
            "## 📌 结构化推荐摘要",
            "",
            "### 高置信主题",
        ]
        if high_confidence:
            for item in high_confidence[:3]:
                lines.append(
                    f"- **{item.get('topic')}**：{item.get('topic_article_count', 0)}篇主题文章，独立证据 {item.get('independent_evidence_count', 0)} 条。"
                )
        else:
            lines.append("- 当前没有足够证据支撑的高置信主题，建议以观察项为主。")

        lines.extend(["", "### 建议与观察"])
        if actionable:
            lines.append("- **可行动标的**:")
            for item in actionable[:3]:
                lines.append(
                    f"  - {item.get('name')}（{item.get('symbol')}，{item.get('grade')}，总分 {item.get('total_score')}）"
                )
        else:
            lines.append("- **无新增高信号标的**：当前没有满足高信号门槛的可行动标的。")

        if watchlist:
            lines.append("- **继续观察**:")
            for item in watchlist[:5]:
                lines.append(
                    f"  - {item.get('name')}（{item.get('symbol')}，{item.get('grade')}）"
                )

        if stale:
            lines.append("- **拥挤或后手机会**:")
            for item in stale[:3]:
                lines.append(
                    f"  - {item.get('name')}（{item.get('symbol')}，{item.get('grade')}）"
                )

        if watch_topics:
            lines.extend(["", "### 主题观察清单"])
            for item in watch_topics[:4]:
                lines.append(
                    f"- {item.get('topic')}：证据密度不足以形成高置信结论，暂列观察。"
                )

        if cross_verification_result:
            cv_stocks = cross_verification_result.get('stock_checks', [])
            confirmed = [s for s in cv_stocks if s.get('status') == CROSS_STATUS_CONFIRMED]
            conflicted = [s for s in cv_stocks if s.get('status') == CROSS_STATUS_CONFLICTED]
            if confirmed or conflicted:
                lines.extend(["", "### 交叉验真信号"])
                if confirmed:
                    lines.append("- **多来源确认**:")
                    for sc in confirmed[:3]:
                        lines.append(
                            f"  - {sc.get('name')}（{sc.get('symbol')}）："
                            f"{sc.get('independent_source_count')} 个独立来源，证据新鲜"
                        )
                if conflicted:
                    lines.append("- **信号冲突**:")
                    for sc in conflicted[:3]:
                        lines.append(
                            f"  - {sc.get('name')}（{sc.get('symbol')}）："
                            f"{sc.get('conflict_detail') or '正反证据并存'}"
                        )

        return "\n".join(lines)

    def _save_result(
        self,
        end_date: str,
        report_text: str,
        usage: Dict[str, Any],
        meta: Dict[str, Any],
        output_json: Optional[str],
        json_payload: Optional[Dict[str, Any]] = None,
        enhanced_context_payload: Optional[Dict[str, Any]] = None,
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
        if enhanced_context_payload:
            update_stage('写入增强特征归档')
            context_path = save_enhanced_context(
                end_date,
                enhanced_context_payload,
                model_suffix=model_suffix,
                artifact_suffix=artifact_suffix,
            )
            meta['enhanced_context_path'] = str(context_path)
            note_event(f'增强特征归档已保存: {context_path.name}')
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
        stock_market: str = 'CN',
        **provider_kwargs,
    ) -> Dict[str, Any]:
        active_sm = self.security_master_us if stock_market == 'US' else self.security_master_provider
        candidates = build_judgment_candidates(selected, max_candidates=max(max_theses + 3, 6))
        candidate_stocks = active_sm.build_candidates(
            articles=selected,
            judgment_candidates=candidates,
            max_candidates=max(max_theses + 3, 6),
        )
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
        meta_quality_fields = self._quality_metadata_fields(quality_result)
        meta = {
            'date_range': {'start': start_date, 'end': end_date},
            'market': stock_market,
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
        meta.update(meta_quality_fields)
        enhanced_context_payload = self._build_enhanced_context_payload(
            selected=selected,
            judgment_candidates=candidates,
            candidate_stocks=candidate_stocks,
            stock_payload=None,
            analysis_mode='judgment-cards',
            date_range=meta['date_range'],
            market=stock_market,
        )
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
            enhanced_context_payload,
            artifact_suffix=f'judgment-cards-{stock_market.lower()}',
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

        # 提前提取市场参数（后续多处使用，需 pop 避免传入 AI provider）
        stock_market = provider_kwargs.pop('stock_market', 'CN')

        # 美股模式：限定美股相关新闻源，避免 A 股/国内宏观语料污染
        if stock_market == 'US':
            if filter_source:
                user_sources = [s.strip() for s in filter_source.split(',') if s.strip()]
                valid = [s for s in user_sources if s in US_MARKET_SOURCE_NAMES]
                rejected = [s for s in user_sources if s not in US_MARKET_SOURCE_NAMES]
                if rejected:
                    print_warning(f'美股模式：以下来源不在美股 allowlist 中，已自动剔除：{", ".join(rejected)}')
                filter_source = ','.join(valid) if valid else None
            if not filter_source:
                filter_source = ','.join(US_MARKET_SOURCE_NAMES)
                print_info(f'美股模式：自动限定 {len(US_MARKET_SOURCE_NAMES)} 个美股相关新闻源')

        # 获取实时数据（如果启用验证）
        start_stage('获取实时数据', step=1, total=6, detail='检查实时行情可用性')
        realtime_data = self.fetch_realtime_data(market=stock_market)
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
                stock_market=stock_market,
                **provider_kwargs,
            )

        enable_stock_scoring = bool(provider_kwargs.pop('enable_stock_scoring', True))
        max_stock_picks = int(provider_kwargs.pop('max_stock_picks', 10))
        judgment_candidates = build_judgment_candidates(selected, max_candidates=8)
        candidate_stocks = []
        stock_payload = {
            'recommendations': [],
            'score_distribution': {'strong_focus': 0, 'focus': 0, 'watch': 0, 'avoid': 0},
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {
                'market': stock_market,
                'style': 'balanced',
                'lookback_days': 60,
            },
        }
        cv_result = None
        if enable_stock_scoring and stock_market in ('CN', 'US'):
            if stock_market == 'US':
                active_sm = self.security_master_us
                active_valuation = ValuationProvider(active_sm)
                market_label = '美股'
            else:
                active_sm = self.security_master_provider
                active_valuation = self.valuation_provider
                market_label = 'A 股'
            note_event(f'预计算 {market_label} 结构化推荐评分')
            print_progress(f'生成 {market_label} 结构化推荐评分...')
            candidate_stocks = active_sm.build_candidates(
                articles=selected,
                judgment_candidates=judgment_candidates,
                max_candidates=max_stock_picks,
            )
            scorer = RecommendationScorer(
                security_master=active_sm,
                price_history_provider=self.price_history_provider,
                valuation_provider=active_valuation,
                lookback_days=60,
                style='balanced',
                as_of_date=end_date,
                market=stock_market,
            )
            stock_payload = scorer.score_candidates(candidate_stocks)
            print_success(f"✓ 已生成 {len(stock_payload['recommendations'])} 条股票评分结果")

            # ---- 交叉验真 V1 ----
            cv_result = run_cross_verification(
                selected_articles=selected,
                judgment_candidates=judgment_candidates,
                candidate_stocks=candidate_stocks,
                stock_recommendations=stock_payload['recommendations'],
                as_of_date=end_date,
                market=stock_market,
            )
            # 将交叉验真结果注入每个推荐项的 evidence_strength
            stock_check_map = {
                sc.get('symbol'): sc for sc in cv_result.get('stock_checks', [])
            }
            for rec in stock_payload['recommendations']:
                symbol = rec.get('symbol', '')
                check = stock_check_map.get(symbol)
                evidence_strength = rec.setdefault('evidence_strength', {})
                if check:
                    evidence_strength['cross_verification_status'] = check['status']
                    evidence_strength['cross_verified_source_count'] = check['independent_source_count']
                    evidence_strength['cross_verification_reasons'] = []
                else:
                    evidence_strength['cross_verification_status'] = CROSS_STATUS_WEAK
                    evidence_strength['cross_verified_source_count'] = 0
                    evidence_strength['cross_verification_reasons'] = ['未进入交叉验真流程']

                # conflicted 标的强制不可行动
                cv_status = evidence_strength.get('cross_verification_status')
                if cv_status == CROSS_STATUS_CONFLICTED:
                    reasons = rec.setdefault('actionability_reasons', [])
                    if 'cross_verification_conflicted' not in reasons:
                        reasons.append('cross_verification_conflicted')
                    rec['actionability_passed'] = False

                # theme-only 不能 confirmed
                source_type = rec.get('source_type', '')
                direct_mentions = int(evidence_strength.get('direct_mentions', 0) or 0)
                if cv_status == CROSS_STATUS_CONFIRMED and source_type == 'theme_mapping' and direct_mentions < 1:
                    evidence_strength['cross_verification_status'] = CROSS_STATUS_WEAK
                    evidence_strength['cross_verification_reasons'] = ['theme_only_cannot_be_confirmed']

            # 重建 decision_views 三桶（因为 actionability 可能被修改）
            actionable = [r for r in stock_payload['recommendations'] if r.get('actionability_passed')]
            actionable_symbols = {r['symbol'] for r in actionable}
            stale_or_rejected = [
                r for r in stock_payload['recommendations']
                if r.get('grade') == '回避'
                or r.get('stale_opportunity_flag')
                or r.get('crowding_flag')
                or (r.get('evidence_strength') or {}).get('cross_verification_status') == CROSS_STATUS_CONFLICTED
            ]
            stale_symbols = {r['symbol'] for r in stale_or_rejected}
            conditional = [
                r for r in stock_payload['recommendations']
                if r['symbol'] not in actionable_symbols
                and r['symbol'] not in stale_symbols
            ]
            stock_payload['decision_views'] = {
                'actionable_candidates': actionable,
                'conditional_watchlist': conditional,
                'stale_or_rejected': stale_or_rejected,
            }
            print_success(
                f"✓ 交叉验真: 标的 {cv_result['summary']['stocks_confirmed']} confirmed, "
                f"{cv_result['summary']['stocks_weak']} weak, "
                f"{cv_result['summary']['stocks_conflicted']} conflicted"
            )

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
        data_quality_stats = summarize_content_quality(selected)
        stats_info = build_source_stats_block(selected, content_field, start_date, end_date)
        prompt_signal_context = self._build_prompt_signal_context(
            judgment_candidates=judgment_candidates,
            stock_payload=stock_payload,
            data_quality_stats=data_quality_stats,
            cross_verification_result=cv_result,
        )

        # 注入实时数据（如果有）
        if realtime_data:
            update_stage('注入实时市场数据到提示词')
            print_progress('注入实时市场数据到提示词...')
            realtime_block = self._format_realtime_data(realtime_data)
            stats_info = realtime_block + "\n\n" + stats_info

        joined = '\n\n'.join(c for _, chunks in pairs for c in chunks)
        full_content = stats_info + "\n\n" + prompt_signal_context + "\n\n" + joined
        finish_stage('语料构建完成', duration=True)

        # 加载提示词
        prompt = self.load_prompt(prompt_version, market=stock_market)

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
                stock_recommendations=stock_payload['recommendations'],
                judgment_candidates=judgment_candidates,
                data_quality_stats=data_quality_stats,
                **provider_kwargs
            )
        except Exception as e:
            print_error(f'报告生成失败: {e}')
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

        structured_summary = self._render_structured_recommendation_summary(
            judgment_candidates=judgment_candidates,
            stock_payload=stock_payload,
            cross_verification_result=cv_result,
        )
        summary_md = f"{summary_md.rstrip()}\n\n{structured_summary}\n"
        if stock_payload['recommendations']:
            stock_section = render_stock_recommendation_markdown(
                stock_payload['recommendations'],
                scoring_config=stock_payload['scoring_config'],
            )
            summary_md = f"{summary_md.rstrip()}\n\n{stock_section}\n"
        summary_md = self._attach_realtime_source_annotation(summary_md, realtime_data)

        # 事实核查（如果启用验证）
        verified_claims, verification_report = self._run_fact_check(summary_md, realtime_data)
        if verification_report:
            start_stage('事实核查 / 质量检查', step=5, total=6, detail='合并事实核查附注')
            summary_md += "\n\n" + verification_report
            print_success(f'✓ 事实核查完成: {len(verified_claims)} 个断言')
            finish_stage('事实核查附注已合并', duration=False)

        if self.enable_verification:
            quality_result = check_report_quality_v2(
                summary_md,
                claims=verified_claims,
                realtime_data=realtime_data,
                report_mode='markdown-report',
                stock_recommendations=stock_payload['recommendations'],
                judgment_candidates=judgment_candidates,
                data_quality_stats=data_quality_stats,
                cross_verification=cv_result if cv_result else None,
            )
            quality_result = quality_result or {}
            quality_result['stats'] = quality_result.get('stats') or {}
            quality_result['stats']['implausible_signals'] = FactChecker().collect_implausible_signals(verified_claims)

        # 保存报告
        meta_quality_fields = self._quality_metadata_fields(quality_result)
        meta = {
            'date_range': {'start': start_date, 'end': end_date},
            'market': stock_market,
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
            'decision_views': stock_payload.get('decision_views') or {},
            'judgment_candidates': judgment_candidates,
            'data_quality_stats': data_quality_stats,
            'backtest_ready': True,
            'backtest_generated_at': datetime.now().isoformat(),
            'cross_verification': cv_result if cv_result else {},
            'cross_verification_required': cv_result is not None,
        }
        meta.update(meta_quality_fields)
        enhanced_context_payload = self._build_enhanced_context_payload(
            selected=selected,
            judgment_candidates=judgment_candidates,
            candidate_stocks=candidate_stocks,
            stock_payload=stock_payload,
            analysis_mode='markdown-report',
            date_range=meta['date_range'],
            market=stock_market,
            cross_verification_result=cv_result,
        )
        export_payload = {
            'summary_markdown': summary_md,
            'articles': rows,
            'metadata': meta,
            'stock_recommendations': stock_payload['recommendations'],
            'score_distribution': stock_payload['score_distribution'],
            'scoring_config': stock_payload['scoring_config'],
            'decision_views': stock_payload.get('decision_views') or {},
            'judgment_candidates': judgment_candidates,
            'data_quality_stats': data_quality_stats,
        }
        start_stage('保存报告与元数据', step=6, total=6, detail='准备写入报告归档与 metadata')
        saved_path = self._save_result(
            end_date,
            summary_md,
            usage,
            meta,
            output_json,
            export_payload,
            enhanced_context_payload,
            artifact_suffix=f'markdown-report-{stock_market.lower()}',
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

    @staticmethod
    def _serialize_selected_articles(selected: list) -> list:
        """输出时序判断需要的最小文章特征集。"""
        fields = (
            'id', 'title', 'source', 'published', 'collection_date',
            'source_tier', 'investment_relevance', 'primary_topic',
            'content_quality_status', 'is_original_source',
        )
        result = []
        for article in selected:
            result.append({field: article.get(field) for field in fields})
        return result

    def _build_enhanced_context_payload(
        self,
        *,
        selected: list,
        judgment_candidates: list,
        candidate_stocks: list,
        stock_payload: Optional[Dict[str, Any]],
        analysis_mode: str,
        date_range: Dict[str, str],
        market: str = 'CN',
        cross_verification_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """构建增强特征归档，供次日回看与后续时序统计。"""
        return {
            'analysis_mode': analysis_mode,
            'market': market,
            'date_range': date_range,
            'selected_articles': self._serialize_selected_articles(selected),
            'judgment_candidates': judgment_candidates,
            'candidate_stocks': [item.to_dict() for item in candidate_stocks],
            'stock_recommendations': (stock_payload or {}).get('recommendations') or [],
            'decision_views': (stock_payload or {}).get('decision_views') or {},
            'score_distribution': (stock_payload or {}).get('score_distribution') or {},
            'scoring_config': (stock_payload or {}).get('scoring_config') or {},
            'cross_verification': cross_verification_result if cross_verification_result else {},
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
