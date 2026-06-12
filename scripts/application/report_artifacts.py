#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告证据、审计和渲染辅助函数。

这些函数不持有 ReportGenerator 状态，集中在这里以保持主生成器只负责流程编排。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from scripts.domain.cross_verification import (
    CROSS_STATUS_CONFIRMED,
    CROSS_STATUS_CONFLICTED,
    MAJOR_NEGATIVE_KEYWORDS,
    MAJOR_POSITIVE_KEYWORDS,
)


def quality_metadata_fields(quality_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = quality_result or {}
    stats = payload.get('stats') or {}
    return {'quality_score': payload.get('score'), 'quality_stats': payload.get('stats'), 'quality_issues': payload.get('issues'), 'quality_warnings': payload.get('warnings'), 'time_source': payload.get('time_source') or stats.get('time_source'), 'source_annotation_missing': payload.get('source_annotation_missing') if 'source_annotation_missing' in payload else stats.get('source_annotation_missing'), 'claim_coverage_score': payload.get('claim_coverage_score') if 'claim_coverage_score' in payload else stats.get('claim_coverage_score')}


def realtime_source_annotation(realtime_data: Optional[Dict[str, Any]]) -> str:
    if not realtime_data:
        return ''
    timestamp = realtime_data.get('timestamp')
    if not timestamp:
        return ''
    return f'## 📊 实时数据来源\n\n- 数据来源: Yahoo Finance、Gold-API、Frankfurter\n- 更新时间: {timestamp}\n'


def attach_realtime_source_annotation(report_text: str, realtime_data: Optional[Dict[str, Any]]) -> str:
    """把确定性的实时数据来源写入报告文本，避免模型自由生成来源口径。"""
    annotation = realtime_source_annotation(realtime_data)
    if not annotation or '## 📊 实时数据来源' in report_text:
        return report_text
    return f'{report_text.rstrip()}\n\n{annotation}'


def build_source_reference_payload(selected: list) -> Dict[str, Any]:
    """构建真实新闻引用索引，只暴露可回溯的 article_id。"""
    articles = []
    for article in selected:
        article_id = article.get('id')
        if article_id is None:
            continue
        articles.append({'article_id': article_id, 'source': article.get('source'), 'title': article.get('title'), 'published': article.get('published') or article.get('collection_date'), 'source_tier': article.get('source_tier')})
    return {'required': True, 'article_ids': [item['article_id'] for item in articles], 'articles': articles}


def build_source_reference_prompt(selected: list, limit: int=30) -> str:
    refs = build_source_reference_payload(selected)['articles']
    lines = ['=== 新闻引用索引（必须使用真实 article_id） ===', '- 重要新闻事实只能标注为【新闻<article_id>】，例如【新闻4885】。', '- 禁止使用【新闻X】、【新闻1】这类占位或序号引用，除非 1 本身就是下列真实 article_id。']
    for item in refs[:limit]:
        title = str(item.get('title') or '').replace('\n', ' ')[:90]
        lines.append(f'- 【新闻{item.get('article_id')}】 {item.get('source') or '未知来源'} | {item.get('published') or '未知时间'} | {title}')
    return '\n'.join(lines)


def build_coverage_matrix(selected: list, *, market: str, realtime_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """统计中美报告的主题覆盖，供 prompt 与验收判断报告边界。"""
    category_rules = {'macro_liquidity': ('宏观', '流动性', '利率', '美联储', 'Fed', '债市'), 'policy_regulation': ('政策', '监管', '证监会', 'SEC', '关税', '财政'), 'company_earnings': ('财报', '公司经营', '盈利', '业绩', 'guidance', 'earnings'), 'industry_theme': ('科技', '产业', 'AI', '半导体', '能源', '消费'), 'risk_event': ('风险', '地缘', '冲突', '诉讼', '调查', '危机')}
    buckets: Dict[str, Dict[str, Any]] = {key: {'article_count': 0, 'source_count': 0, 'status': 'missing'} for key in category_rules}
    source_sets: Dict[str, set[str]] = {key: set() for key in category_rules}
    for article in selected:
        text = ' '.join((str(article.get(field) or '') for field in ('primary_topic', 'title', 'summary')))
        source = str(article.get('source') or '')
        for key, cues in category_rules.items():
            if any((cue in text for cue in cues)):
                buckets[key]['article_count'] += 1
                if source:
                    source_sets[key].add(source)
    for key, bucket in buckets.items():
        bucket['source_count'] = len(source_sets[key])
        if bucket['article_count'] >= 2 and bucket['source_count'] >= 2:
            bucket['status'] = 'sufficient'
        elif bucket['article_count'] >= 1:
            bucket['status'] = 'partial'
    realtime_available = bool(realtime_data and realtime_data.get('stocks'))
    buckets['realtime_market'] = {'article_count': 0, 'source_count': 1 if realtime_available else 0, 'status': 'sufficient' if realtime_available else 'missing'}
    return {'required': True, 'market': market, 'categories': buckets, 'coverage_gaps': [key for key, bucket in buckets.items() if bucket.get('status') != 'sufficient']}


def build_coverage_prompt(coverage_matrix: Dict[str, Any]) -> str:
    categories = coverage_matrix.get('categories') or {}
    lines = ['=== 覆盖矩阵约束 ===']
    for key, bucket in categories.items():
        lines.append(f'- {key}: status={bucket.get('status')}, articles={bucket.get('article_count')}, sources={bucket.get('source_count')}')
    gaps = coverage_matrix.get('coverage_gaps') or []
    if gaps:
        lines.append('- 覆盖不足的板块只能写观察或证据缺口，禁止写成完整市场结论: ' + ', '.join(gaps))
    return '\n'.join(lines)


def distribution(counter: Counter, total: int) -> List[Dict[str, Any]]:
    rows = []
    for name, count in counter.most_common():
        rows.append({'name': name, 'count': count, 'share': count / total if total else 0.0})
    return rows


def explicit_article_entities(article: Dict[str, Any]) -> List[str]:
    entities: List[str] = []
    scalar_fields = ('company', 'company_name', 'ticker', 'symbol')
    list_fields = ('companies', 'tickers', 'symbols', 'related_symbols', 'stock_symbols')
    for field in scalar_fields:
        value = article.get(field)
        if value:
            entities.append(str(value).strip())
    for field in list_fields:
        value = article.get(field)
        if isinstance(value, list):
            entities.extend((str(item).strip() for item in value if item))
        elif isinstance(value, str) and value.strip():
            entities.extend((item.strip() for item in re.split('[,，;；\\s]+', value) if item.strip()))
    return [item for item in entities if item]


def build_evidence_diversity(selected: list, *, market: str) -> Dict[str, Any]:
    """统计来源、主题和显式标的集中度，避免单一依据带偏报告。"""
    total = len(selected)
    source_counter: Counter = Counter()
    topic_counter: Counter = Counter()
    entity_counter: Counter = Counter()
    source_tier_counter: Counter = Counter()
    source_tier_known_count = 0
    mainstream_or_better_count = 0
    aggregator_count = 0
    original_source_known_count = 0
    original_source_count = 0
    for article in selected:
        source = str(article.get('source') or '未知来源').strip() or '未知来源'
        topic = str(article.get('primary_topic') or '未分类').strip() or '未分类'
        source_tier = str(article.get('source_tier') or 'unknown').strip() or 'unknown'
        source_counter[source] += 1
        topic_counter[topic] += 1
        source_tier_counter[source_tier] += 1
        if source_tier != 'unknown':
            source_tier_known_count += 1
            if source_tier in {'official', 'mainstream'}:
                mainstream_or_better_count += 1
            if source_tier == 'aggregator':
                aggregator_count += 1
        original_value = article.get('is_original_source')
        if original_value is not None and original_value != '':
            original_source_known_count += 1
            if str(original_value).lower() in {'1', 'true', 'yes'}:
                original_source_count += 1
        for entity in explicit_article_entities(article):
            entity_counter[entity] += 1

    def max_share(counter: Counter, denominator: int) -> float:
        return counter.most_common(1)[0][1] / denominator if counter and denominator else 0.0
    source_count = len(source_counter)
    topic_count = len(topic_counter)
    entity_total = sum(entity_counter.values())
    flags: List[str] = []
    if total >= 8 and source_count < 3:
        flags.append('insufficient_source_diversity')
    if total >= 8 and max_share(source_counter, total) > 0.6:
        flags.append('source_concentration')
    if total >= 8 and max_share(topic_counter, total) > 0.7:
        flags.append('topic_concentration')
    if entity_total >= 3 and max_share(entity_counter, entity_total) > 0.6:
        flags.append('entity_concentration')
    if total >= 8 and source_tier_known_count >= total * 0.8 and (mainstream_or_better_count < 2):
        flags.append('insufficient_mainstream_sources')
    if total >= 8 and (aggregator_count / source_tier_known_count if source_tier_known_count else 0.0) > 0.5:
        flags.append('aggregator_concentration')
    if total >= 8 and original_source_known_count >= total * 0.8 and (original_source_count == 0):
        flags.append('no_original_sources')
    return {'required': True, 'market': market, 'total_articles': total, 'source_count': source_count, 'topic_count': topic_count, 'explicit_entity_count': len(entity_counter), 'explicit_entity_observation_count': entity_total, 'source_tier_known_count': source_tier_known_count, 'mainstream_or_better_count': mainstream_or_better_count, 'aggregator_count': aggregator_count, 'original_source_known_count': original_source_known_count, 'original_source_count': original_source_count, 'max_source_share': max_share(source_counter, total), 'max_topic_share': max_share(topic_counter, total), 'max_entity_share': max_share(entity_counter, entity_total), 'max_aggregator_share': aggregator_count / source_tier_known_count if source_tier_known_count else 0.0, 'original_source_share': original_source_count / original_source_known_count if original_source_known_count else None, 'source_distribution': distribution(source_counter, total), 'topic_distribution': distribution(topic_counter, total), 'entity_distribution': distribution(entity_counter, entity_total), 'source_tier_distribution': distribution(source_tier_counter, total), 'concentration_flags': flags, 'passed': not flags}


def build_diversity_prompt(evidence_diversity: Dict[str, Any]) -> str:
    lines = ['=== 证据多样性约束 ===']
    lines.append(f'- sources={evidence_diversity.get('source_count')}, topics={evidence_diversity.get('topic_count')}, max_source_share={evidence_diversity.get('max_source_share', 0):.0%}, max_topic_share={evidence_diversity.get('max_topic_share', 0):.0%}, aggregator_share={evidence_diversity.get('max_aggregator_share', 0):.0%}')
    flags = evidence_diversity.get('concentration_flags') or []
    if flags:
        lines.append('- 证据集中度偏高，只能写成样本偏置/观察结论，禁止把集中样本扩写成市场整体信号: ' + ', '.join(flags))
    return '\n'.join(lines)


def keyword_hits(text: str, keywords: List[str]) -> List[str]:
    lowered = text.lower()
    return sorted({keyword for keyword in keywords if keyword.lower() in lowered})


def build_counter_evidence_ledger(selected: list, judgment_candidates: list, *, market: str) -> Dict[str, Any]:
    """记录每个主题候选是否检查过反证/风险证据。"""
    article_map = {article.get('id'): article for article in selected if article.get('id') is not None}
    topic_rows: List[Dict[str, Any]] = []
    for item in judgment_candidates:
        topic = str(item.get('topic') or '')
        candidate_articles = item.get('articles') or []
        article_ids = [article.get('id') for article in candidate_articles if article.get('id') is not None]
        relevant = [article_map[article_id] for article_id in article_ids if article_id in article_map]
        supporting_ids: List[Any] = []
        counter_ids: List[Any] = []
        positive_hits: List[str] = []
        negative_hits: List[str] = []
        for article in relevant:
            text = ' '.join((str(article.get(field) or '') for field in ('title', 'summary', 'content')))
            pos = keyword_hits(text, MAJOR_POSITIVE_KEYWORDS)
            neg = keyword_hits(text, MAJOR_NEGATIVE_KEYWORDS)
            positive_hits.extend(pos)
            negative_hits.extend(neg)
            if topic == '风险事件':
                if neg:
                    supporting_ids.append(article.get('id'))
                if pos:
                    counter_ids.append(article.get('id'))
            else:
                if pos:
                    supporting_ids.append(article.get('id'))
                if neg:
                    counter_ids.append(article.get('id'))
        supporting_ids = sorted(set(supporting_ids))
        counter_ids = sorted(set(counter_ids))
        status = 'balanced'
        if counter_ids and supporting_ids:
            status = 'mixed'
        elif counter_ids:
            status = 'counter_only'
        elif supporting_ids:
            status = 'support_only'
        topic_rows.append({'topic': topic, 'market': market, 'high_confidence_topic': bool(item.get('high_confidence_topic')), 'evidence_article_ids': article_ids, 'supporting_article_ids': supporting_ids, 'counter_article_ids': counter_ids, 'counter_evidence_count': len(counter_ids), 'positive_keywords': sorted(set(positive_hits)), 'negative_keywords': sorted(set(negative_hits)), 'status': status})
    topics_with_counter = [row for row in topic_rows if row.get('high_confidence_topic') and row.get('counter_evidence_count', 0) > 0]
    return {'required': True, 'market': market, 'topics': topic_rows, 'summary': {'topic_count': len(topic_rows), 'topics_with_counter_evidence': len(topics_with_counter), 'high_confidence_topics_with_counter_evidence': len(topics_with_counter)}, 'passed': len(topics_with_counter) == 0}


def build_counter_evidence_prompt(counter_evidence_ledger: Dict[str, Any]) -> str:
    lines = ['=== 反证/冲突证据约束 ===']
    rows = counter_evidence_ledger.get('topics') or []
    for row in rows:
        if row.get('counter_evidence_count', 0) <= 0:
            continue
        lines.append(f'- {row.get('topic')}: counter_articles={row.get('counter_article_ids')}, negative_keywords={row.get('negative_keywords')}')
    if (counter_evidence_ledger.get('summary') or {}).get('high_confidence_topics_with_counter_evidence', 0):
        lines.append('- 高置信主题存在反证时，正文必须显式写出反证/风险边界，禁止单边强化结论。')
    return '\n'.join(lines)


def prepend_trust_card(report_text: str, meta: Dict[str, Any]) -> str:
    """在报告标题之后插入可信度摘要卡（代码拼接，不经过 AI）。

        数据全部来自 meta dict，分层展示：
        - 第一行：总评（质量检查通过/未通过 + 评分）
        - 常驻字段：事实核查、交叉验真
        - 仅在异常时展示：实时行情降级、覆盖缺口
        """
    quality = meta.get('quality_check') or {}
    stats = quality.get('stats') or {}
    cv = meta.get('cross_verification') or {}
    cv_summary = cv.get('summary') or {}
    coverage = meta.get('coverage_matrix') or {}
    gaps = coverage.get('coverage_gaps') or []
    degraded = meta.get('live_data_degraded', False)
    score = quality.get('score')
    passed = quality.get('passed')
    verified = stats.get('verified_claims')
    total = stats.get('total_claims')
    cv_confirmed = cv_summary.get('stocks_confirmed')
    cv_weak = cv_summary.get('stocks_weak')
    if passed is True and score is not None:
        status_line = f'🟢 **质量检查通过** · 评分 {score}/100'
    elif passed is False:
        status_line = f'🔴 **质量检查未通过** · 评分 {score or '?'}/100'
    else:
        status_line = '⚪ **未运行质量检查**'
    lines = ['> 📋 **可信度摘要** · 系统根据实际数据源状态自动生成', '', status_line, '', '| 维度 | 状态 |', '|------|------|']
    if verified is not None and total is not None:
        lines.append(f'| 事实核查 | {verified}/{total} 断言通过验证 |')
    elif verified is not None:
        lines.append(f'| 事实核查 | {verified} 断言已验证 |')
    if cv_confirmed is not None:
        parts = [f'{cv_confirmed} confirmed']
        if cv_weak is not None:
            parts.append(f'{cv_weak} weak')
        lines.append(f'| 交叉验真 | 标的 {' / '.join(parts)} |')
    if gaps:
        lines.append(f'| 覆盖缺口 | {', '.join(gaps[:4])} |')
    lines.append('')
    if degraded:
        lines.append('⚠️ 实时行情数据降级，价格相关结论依赖新闻与本地快照，不反映盘中最新价')
        lines.append('')
    lines.append('---')
    card = '\n'.join(lines)
    title_match = __import__('re').search('^# .+$', report_text or '', __import__('re').MULTILINE)
    if title_match:
        pos = title_match.end()
        return report_text[:pos] + '\n\n' + card + '\n' + report_text[pos:].lstrip('\n')
    return card + '\n' + (report_text or '')


def build_evidence_audit_markdown(*, source_references: Dict[str, Any], coverage_matrix: Dict[str, Any], evidence_diversity: Dict[str, Any], counter_evidence_ledger: Dict[str, Any], quality_result: Optional[Dict[str, Any]]=None, candidate_evidence_audit: Optional[Dict[str, Any]]=None, scoring_calibration: Optional[Dict[str, Any]]=None) -> str:
    """生成确定性审计附录；它只暴露证据状态，不参与模型正文生成。"""
    quality = quality_result or {}
    coverage_gaps = coverage_matrix.get('coverage_gaps') or []
    diversity_flags = evidence_diversity.get('concentration_flags') or []
    counter_summary = counter_evidence_ledger.get('summary') or {}
    article_count = len(source_references.get('articles') or [])
    candidate_audit = candidate_evidence_audit or {}
    relevance_counts = candidate_audit.get('status_counts') or {}
    calibration = scoring_calibration or {}
    lines = ['## 证据审计摘要', '', f'- 新闻引用索引: {article_count} 篇可回溯文章', f'- 覆盖缺口: {(', '.join(coverage_gaps) if coverage_gaps else '无')}', f'- 来源/主题集中度风险: {(', '.join(diversity_flags) if diversity_flags else '无')}', f'- 高置信主题反证数: {counter_summary.get('high_confidence_topics_with_counter_evidence', 0)}', f'- 个股证据相关性: 实质证据 {relevance_counts.get('direct_material_news', 0)} / 主题代理 {relevance_counts.get('theme_proxy', 0)} / 误命中过滤 {len(candidate_audit.get('rejected_false_positive_mentions') or [])}', f'- 历史方向校准: {(', '.join(calibration.get('status_counts', {}).keys()) if calibration.get('status_counts') else '样本不足')}', f'- 质量门禁: {('通过' if quality.get('passed') else '未通过')} / 分数 {quality.get('score', '未知')}']
    return '\n'.join(lines)


def build_candidate_evidence_audit(*, candidate_stocks: list, stock_payload: Dict[str, Any], rejected_false_positive_mentions: Optional[List[Dict[str, Any]]]=None) -> Dict[str, Any]:
    """汇总候选股证据相关性，供 acceptance 和人工审计复核。"""
    recommendations = (stock_payload or {}).get('recommendations') or []
    status_counts: Dict[str, int] = {}
    rows = []
    for item in recommendations:
        status = item.get('evidence_relevance_status') or 'unknown'
        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append({'symbol': item.get('symbol'), 'name': item.get('name'), 'source_type': item.get('source_type'), 'evidence_relevance_status': status, 'evidence_relevance_reasons': item.get('evidence_relevance_reasons') or [], 'evidence_article_ids': item.get('evidence_article_ids') or [], 'actionability_passed': item.get('actionability_passed') is True})
    return {'required': True, 'candidate_count': len(candidate_stocks or []), 'recommendation_count': len(recommendations), 'status_counts': status_counts, 'candidates': rows, 'rejected_false_positive_mentions': rejected_false_positive_mentions or []}


def build_scoring_calibration(stock_payload: Dict[str, Any]) -> Dict[str, Any]:
    """汇总每条推荐的历史校准状态；不把未校准分数包装成方向结论。"""
    recommendations = (stock_payload or {}).get('recommendations') or []
    status_counts: Dict[str, int] = {}
    rows = []
    for item in recommendations:
        status = item.get('historical_calibration_status') or '样本不足'
        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append({'symbol': item.get('symbol'), 'name': item.get('name'), 'grade': item.get('grade'), 'historical_calibration_status': status, 'historical_forward_stats': item.get('historical_forward_stats') or {}})
    return {'required': True, 'status_counts': status_counts, 'items': rows}


def build_prompt_signal_context(judgment_candidates: list, stock_payload: Dict[str, Any], data_quality_stats: Dict[str, Any], cross_verification_result: Dict[str, Any] | None=None) -> str:
    """把结构化主题、推荐和数据质量约束显式注入给 markdown-report。"""
    high_confidence = [item for item in judgment_candidates if bool(item.get('high_confidence_topic'))]
    watch_topics = [item for item in judgment_candidates if not bool(item.get('high_confidence_topic'))][:4]
    recommendations = stock_payload.get('recommendations') or []
    actionable = stock_payload.get('decision_views', {}).get('actionable_candidates') or []
    watchlist = stock_payload.get('decision_views', {}).get('conditional_watchlist') or []
    stale = stock_payload.get('decision_views', {}).get('stale_or_rejected') or []
    counts = data_quality_stats.get('counts') or {}
    ratios = data_quality_stats.get('ratios') or {}
    lines = ['=== 高信号输出约束 ===', f'- 高置信主题数量: {len(high_confidence)}', f'- 观察主题数量: {len(watch_topics)}', f'- 结构化推荐数量: {len(recommendations)}', f'- 可行动推荐数量: {len(actionable)}', f'- 观察清单数量: {len(watchlist)}', f'- 拒绝/拥挤清单数量: {len(stale)}', f'- 数据质量: 完整正文 {counts.get('full', 0)}篇({ratios.get('full', 0.0):.1f}%), 部分正文 {counts.get('partial', 0)}篇({ratios.get('partial', 0.0):.1f}%), 仅摘要 {counts.get('summary_only', 0)}篇({ratios.get('summary_only', 0.0):.1f}%)', '- 正文只能使用下列主题和标的，禁止自行扩写新的股票池、行业配比或宏大资产配置口号。', '- 事实核查只覆盖实时数值与部分新闻事实；不得把“已验证的实时断言”扩写成“整份报告已证实”或“整篇 thesis 已验证”。', '- 只有 actionable_candidates 可以写成“可行动标的”；conditional_watchlist 只能写成“继续观察”，stale_or_rejected 只能写成风险或等待项。']
    if high_confidence:
        lines.append('- 可写成高置信主题:')
        for item in high_confidence[:3]:
            lines.append(f'  * {item.get('topic')}: topic_article_count={item.get('topic_article_count', 0)}, independent_evidence_count={item.get('independent_evidence_count', 0)}, source_tier_max={item.get('source_tier_max')}')
    else:
        lines.append('- 当前没有可写成高置信结论的主题，正文必须以观察项为主。')
    if watch_topics:
        lines.append('- 仅允许写成观察项的主题:')
        for item in watch_topics:
            lines.append(f'  * {item.get('topic')}: topic_article_count={item.get('topic_article_count', 0)}, independent_evidence_count={item.get('independent_evidence_count', 0)}')
    if recommendations:
        lines.append('- 允许在正文中提到的结构化标的:')
        for item in recommendations[:8]:
            lines.append(f'  * {item.get('symbol')} {item.get('name')} / {item.get('grade')} / source_type={item.get('source_type')} / grade_caps={','.join(item.get('grade_caps') or ['none'])} / actionable={('yes' if item.get('actionability_passed') else 'no')}')
    else:
        lines.append('- 当前没有满足规则门槛的结构化股票推荐，正文不得写具体股票推荐。')
    if len(actionable) <= 1:
        lines.append('- 由于可行动推荐少于等于1个，正文不得写成多只核心持仓组合。')
    if not high_confidence and (not actionable):
        lines.append('- 若主题与推荐都偏弱，正文必须退化为“观察清单 + 风险 + 验证点”。')
    if cross_verification_result:
        cv = cross_verification_result
        cv_summary = cv.get('summary', {})
        lines.append('')
        lines.append('=== 交叉验真约束 ===')
        lines.append(f'- 主题交叉验真: {cv_summary.get('topics_confirmed', 0)} confirmed, {cv_summary.get('topics_weak', 0)} weak, {cv_summary.get('topics_conflicted', 0)} conflicted')
        lines.append(f'- 标的交叉验真: {cv_summary.get('stocks_confirmed', 0)} confirmed, {cv_summary.get('stocks_weak', 0)} weak, {cv_summary.get('stocks_conflicted', 0)} conflicted')
        conflicted_topics = [tc.get('topic', '') for tc in cv.get('topic_checks', []) if tc.get('status') == CROSS_STATUS_CONFLICTED]
        if conflicted_topics:
            lines.append(f"- 冲突主题: {', '.join(conflicted_topics[:3])} -- 正文必须标注为'证据矛盾，待进一步确认'")
        conflicted_stocks = [sc.get('symbol', '') for sc in cv.get('stock_checks', []) if sc.get('status') == CROSS_STATUS_CONFLICTED]
        if conflicted_stocks:
            lines.append(f"- 冲突标的: {', '.join(conflicted_stocks[:5])} -- 禁止写成'可行动'，必须注明正反证据并存")
        lines.append("- 正文中只有 cross_verification_status=confirmed 的标的才能写成'已验证''强确认'")
        lines.append("- weak/conflicted 标的禁止使用'多来源验证''确定性高''可行动'等表述")
    return '\n'.join(lines)


def render_structured_recommendation_summary(
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

    lines = ['## 📌 结构化推荐摘要', '', '### 高置信主题']
    if high_confidence:
        for item in high_confidence[:3]:
            lines.append(
                f"- **{item.get('topic')}**："
                f"{item.get('topic_article_count', 0)}篇主题文章，"
                f"独立证据 {item.get('independent_evidence_count', 0)} 条。"
            )
    else:
        lines.append('- 当前没有足够证据支撑的高置信主题，建议以观察项为主。')

    lines.extend(['', '### 建议与观察'])
    if actionable:
        lines.append('- **可行动标的**:')
        for item in actionable[:3]:
            lines.append(
                f"  - {item.get('name')}（{item.get('symbol')}，"
                f"{item.get('grade')}，总分 {item.get('total_score')}）"
            )
    else:
        lines.append('- **无新增高信号标的**：当前没有满足高信号门槛的可行动标的。')

    if watchlist:
        lines.append('- **继续观察**:')
        for item in watchlist[:5]:
            lines.append(
                f"  - {item.get('name')}（{item.get('symbol')}，{item.get('grade')}）"
            )

    if stale:
        lines.append('- **拥挤或后手机会**:')
        for item in stale[:3]:
            lines.append(
                f"  - {item.get('name')}（{item.get('symbol')}，{item.get('grade')}）"
            )

    if watch_topics:
        lines.extend(['', '### 主题观察清单'])
        for item in watch_topics[:4]:
            lines.append(f"- {item.get('topic')}：证据密度不足以形成高置信结论，暂列观察。")

    if cross_verification_result:
        cv_stocks = cross_verification_result.get('stock_checks', [])
        confirmed = [s for s in cv_stocks if s.get('status') == CROSS_STATUS_CONFIRMED]
        conflicted = [s for s in cv_stocks if s.get('status') == CROSS_STATUS_CONFLICTED]
        if confirmed or conflicted:
            lines.extend(['', '### 交叉验真信号'])
            if confirmed:
                lines.append('- **多来源确认**:')
                for sc in confirmed[:3]:
                    lines.append(
                        f"  - {sc.get('name')}（{sc.get('symbol')}）："
                        f"{sc.get('independent_source_count')} 个独立来源，证据新鲜"
                    )
            if conflicted:
                lines.append('- **信号冲突**:')
                for sc in conflicted[:3]:
                    lines.append(
                        f"  - {sc.get('name')}（{sc.get('symbol')}）："
                        f"{sc.get('conflict_detail') or '正反证据并存'}"
                    )

    return '\n'.join(lines)


def serialize_selected_articles(selected: list) -> list:
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


def build_enhanced_context_payload(
    *,
    selected: list,
    judgment_candidates: list,
    candidate_stocks: list,
    stock_payload: Optional[Dict[str, Any]],
    analysis_mode: str,
    date_range: Dict[str, str],
    market: str = 'CN',
    cross_verification_result: Dict[str, Any] | None = None,
    source_references: Optional[Dict[str, Any]] = None,
    claim_ledger: Optional[Dict[str, Any]] = None,
    coverage_matrix: Optional[Dict[str, Any]] = None,
    evidence_diversity: Optional[Dict[str, Any]] = None,
    counter_evidence_ledger: Optional[Dict[str, Any]] = None,
    candidate_evidence_audit: Optional[Dict[str, Any]] = None,
    scoring_calibration: Optional[Dict[str, Any]] = None,
    rejected_false_positive_mentions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构建增强特征归档，供次日回看与后续时序统计。"""
    return {
        'analysis_mode': analysis_mode,
        'market': market,
        'date_range': date_range,
        'selected_articles': serialize_selected_articles(selected),
        'judgment_candidates': judgment_candidates,
        'candidate_stocks': [item.to_dict() for item in candidate_stocks],
        'stock_recommendations': (stock_payload or {}).get('recommendations') or [],
        'decision_views': (stock_payload or {}).get('decision_views') or {},
        'score_distribution': (stock_payload or {}).get('score_distribution') or {},
        'scoring_config': (stock_payload or {}).get('scoring_config') or {},
        'cross_verification': cross_verification_result if cross_verification_result else {},
        'source_references': source_references or {},
        'claim_ledger': claim_ledger or {},
        'coverage_matrix': coverage_matrix or {},
        'evidence_diversity': evidence_diversity or {},
        'counter_evidence_ledger': counter_evidence_ledger or {},
        'candidate_evidence_audit': candidate_evidence_audit or {},
        'scoring_calibration': scoring_calibration or {},
        'rejected_false_positive_mentions': rejected_false_positive_mentions or [],
    }


def build_evidence_audit_payload(
    *,
    analysis_mode: str,
    market: str,
    date_range: Dict[str, str],
    source_references: Dict[str, Any],
    claim_ledger: Dict[str, Any],
    coverage_matrix: Dict[str, Any],
    evidence_diversity: Dict[str, Any],
    counter_evidence_ledger: Dict[str, Any],
    cross_verification_result: Dict[str, Any] | None = None,
    stock_payload: Optional[Dict[str, Any]] = None,
    quality_result: Optional[Dict[str, Any]] = None,
    candidate_evidence_audit: Optional[Dict[str, Any]] = None,
    scoring_calibration: Optional[Dict[str, Any]] = None,
    rejected_false_positive_mentions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """集中落盘可信度证据，便于人工审计和自动化回放。"""
    return {
        'required': True,
        'analysis_mode': analysis_mode,
        'market': market,
        'date_range': date_range,
        'source_references': source_references,
        'claim_ledger': claim_ledger,
        'coverage_matrix': coverage_matrix,
        'evidence_diversity': evidence_diversity,
        'counter_evidence_ledger': counter_evidence_ledger,
        'cross_verification': cross_verification_result or {},
        'decision_views': (stock_payload or {}).get('decision_views') or {},
        'stock_recommendations': (stock_payload or {}).get('recommendations') or [],
        'quality_check': quality_result or {},
        'candidate_evidence_audit': candidate_evidence_audit or {},
        'scoring_calibration': scoring_calibration or {},
        'rejected_false_positive_mentions': rejected_false_positive_mentions or [],
    }


def format_realtime_data(realtime_data: Dict[str, Any]) -> str:
    """格式化实时数据为Markdown块"""
    prompt_block = realtime_data.get('prompt')
    if isinstance(prompt_block, str) and prompt_block.strip():
        return prompt_block.strip()
    lines = ['## 📊 实时市场数据', '']
    for key, value in realtime_data.items():
        if isinstance(value, dict):
            lines.append(f'### {key}')
            for k, v in value.items():
                lines.append(f'- **{k}**: {v}')
            lines.append('')
        else:
            lines.append(f'- **{key}**: {value}')
    return '\n'.join(lines)
