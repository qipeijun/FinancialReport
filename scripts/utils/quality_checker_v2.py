#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
增强版报告质量检查器 v2.0

核心升级:
1. 集成事实核查 - 验证所有可验证断言
2. 多维度评分 - 准确性(60%) + 时效性(20%) + 可靠性(20%)
3. 严格约束检查 - 自动检测AI编造内容
4. 实时数据验证 - 要求报告基于实时数据

目标: 杜绝AI幻觉,提升报告可信度
"""

import re
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _realtime_claims(claims: Optional[List]) -> Optional[List]:
    if claims is None:
        return None
    return [c for c in claims if getattr(c, 'scope', None) is None or getattr(c, 'scope').value == '实时行情断言']


def _news_fact_claims(claims: Optional[List]) -> Optional[List]:
    if claims is None:
        return None
    return [c for c in claims if getattr(c, 'scope', None) and getattr(c, 'scope').value == '新闻事实断言']


def _section_before_stock_table(report_text: str) -> str:
    marker = report_text.find('## 股票推荐评分')
    if marker == -1:
        return report_text
    return report_text[:marker]


def _extract_strong_phrases(report_text: str) -> List[str]:
    phrases = ['绝佳窗口', '十倍速', '不可逆', '极大概率', '极端结构主义配置哲学']
    return [phrase for phrase in phrases if phrase in report_text]


def _find_unsupported_stock_mentions(report_text: str, stock_recommendations: Optional[List[Dict]]) -> List[str]:
    if not stock_recommendations:
        return []
    recommendation_names = {str(item.get('name') or '').strip() for item in stock_recommendations}
    recommendation_names.discard('')
    recommendation_symbols = {str(item.get('symbol') or '').strip() for item in stock_recommendations}
    recommendation_symbols.discard('')
    narrative_text = _section_before_stock_table(report_text)

    unsupported = []
    for match in re.findall(r'\b(?:sh|sz)\d{6}\b', narrative_text):
        if match not in recommendation_symbols:
            unsupported.append(match)
    for match in re.finditer(r'（([A-Za-z0-9]{6,8})）', narrative_text):
        symbol = match.group(1).lower()
        if symbol not in recommendation_symbols:
            unsupported.append(symbol)

    recommendation_section_keywords = ('推荐摘要', '投资组合建议', '建议', '重点标的', '核心持仓')
    if any(keyword in narrative_text for keyword in recommendation_section_keywords):
        known_company_names = re.findall(r'[\u4e00-\u9fa5]{2,8}', narrative_text)
        for name in known_company_names:
            if name in {'市场概况', '投资主题', '风险提示', '操作策略', '高置信主题', '观察主题', '结构化推荐摘要'}:
                continue
            if name in recommendation_names:
                continue
            if name.endswith('指数') or name.endswith('黄金') or name.endswith('人民币'):
                continue
            if '新闻' in name:
                continue
            if any(name in rec for rec in recommendation_names):
                continue
        # 这里不对中文公司名做宽松猜测，避免误伤；代码级别不一致已经足够拦截主要问题。
    return sorted(set(unsupported))


def _high_confidence_topics(judgment_candidates: Optional[List[Dict]]) -> set[str]:
    if not judgment_candidates:
        return set()
    return {
        str(item.get('topic') or '').strip()
        for item in judgment_candidates
        if bool(item.get('high_confidence_topic')) and str(item.get('topic') or '').strip()
    }


def _extract_topic_headers(report_text: str) -> List[str]:
    topic_section_match = re.search(r'##\s+.*投资主题(.*?)(?:\n##\s+|\Z)', report_text, flags=re.S)
    if not topic_section_match:
        return []
    section = topic_section_match.group(1)
    return [
        match.group(1).strip()
        for match in re.finditer(r'###\s+([^\n]+)', section)
        if match.group(1).strip()
    ]


def _extract_recommendation_section(report_text: str) -> str:
    match = re.search(r'##\s+.*建议(.*?)(?:\n##\s+|\Z)', report_text, flags=re.S)
    return match.group(1) if match else ''


def _extract_recommendation_blocks(recommendation_section: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []
    for raw_line in recommendation_section.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current:
                current.append('')
            continue
        if re.match(r'^\s*[-*]\s+', line):
            if current:
                blocks.append('\n'.join(current).strip())
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        blocks.append('\n'.join(current).strip())
    return blocks


def _watchlist_promotion_issues(report_text: str, stock_recommendations: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not stock_recommendations:
        return []
    recommendation_section = _extract_recommendation_section(report_text)
    if not recommendation_section:
        return []
    strong_action_words = ('核心配置', '重点配置', '直接买入', '可执行买点', '立即加仓', '核心受益')
    recommendation_blocks = _extract_recommendation_blocks(recommendation_section)
    issues = []
    for item in stock_recommendations:
        name = str(item.get('name') or '').strip()
        symbol = str(item.get('symbol') or '').strip()
        if not name and not symbol:
            continue
        if item.get('actionability_passed'):
            continue
        matched_blocks = [
            block for block in recommendation_blocks
            if (name and name in block) or (symbol and symbol in block)
        ]
        if any(word in block for block in matched_blocks for word in strong_action_words):
                issues.append(f"❌ {name or symbol} 属于观察/非可行动层级，却在建议段落被写成明确动作建议")
    return issues


def _has_verification_boundary_overclaim(report_text: str, realtime_claims: Optional[List], news_claims: Optional[List]) -> bool:
    narrative = report_text
    overclaim_phrases = ('整份报告已验证', '整篇报告已验证', '整份thesis已验证', '整篇thesis已验证', '整份报告高可信已验证')
    if not any(phrase in narrative for phrase in overclaim_phrases):
        return False
    realtime_total = len(realtime_claims) if realtime_claims is not None else 0
    news_total = len(news_claims) if news_claims is not None else 0
    return realtime_total + news_total <= 4


def _data_integrity_statement_passed(report_text: str, data_quality_stats: Optional[Dict[str, Any]]) -> bool:
    if not data_quality_stats:
        return True
    full_ratio = float((data_quality_stats.get('ratios') or {}).get('full') or 0.0)
    full_count = int((data_quality_stats.get('counts') or {}).get('full') or 0)
    partial_count = int((data_quality_stats.get('counts') or {}).get('partial') or 0)
    summary_only_count = int((data_quality_stats.get('counts') or {}).get('summary_only') or 0)

    impossible_claim = re.search(r'100(?:\.0+)?%[^。\n]{0,12}(?:文章)?包含完整内容', report_text)
    if impossible_claim and full_ratio < 99.95:
        return False

    required_fragments = [
        f"完整正文 {full_count}",
        f"部分正文 {partial_count}",
        f"仅摘要 {summary_only_count}",
    ]
    if '数据质量说明' in report_text or '数据质量分布' in report_text:
        return all(fragment in report_text for fragment in required_fragments)
    return True


def _parse_quality_time(value: str) -> Optional[datetime]:
    normalized = str(value or '').strip().replace('T', ' ')
    if not normalized:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _extract_report_update_time(report_text: str) -> Optional[datetime]:
    match = re.search(
        r'(?:更新时间|数据时效).*?(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)',
        report_text,
    )
    if not match:
        return None
    return _parse_quality_time(match.group(1))


def _timeliness_score(data_age_hours: Optional[float], warnings: List[str]) -> int:
    if data_age_hours is None:
        return 10
    if data_age_hours < 1:
        return 20
    if data_age_hours < 4:
        return 15
    if data_age_hours < 24:
        warnings.append(f"⚠️ 数据更新于{data_age_hours:.1f}小时前,时效性一般")
        return 10
    warnings.append(f"⚠️ 数据更新于{data_age_hours:.1f}小时前,时效性较差")
    return 5


def check_report_quality_v2(
    report_text: str,
    claims: Optional[List] = None,
    realtime_data: Optional[Dict] = None,
    report_mode: str = 'markdown-report',
    stock_recommendations: Optional[List[Dict[str, Any]]] = None,
    judgment_candidates: Optional[List[Dict[str, Any]]] = None,
    data_quality_stats: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    增强版质量检查 (集成事实核查)

    评分维度:
    1. 准确性(60分) - 基于事实核查通过率
    2. 时效性(20分) - 数据新鲜度
    3. 可靠性(20分) - 来源标注完整性

    Args:
        report_text: 报告文本
        claims: 事实核查结果(来自FactChecker)
        realtime_data: 实时数据(用于验证时效性)

    Returns:
        {
            'score': 总分(0-100),
            'passed': 是否通过(>=80),
            'accuracy_score': 准确性得分,
            'timeliness_score': 时效性得分,
            'reliability_score': 可靠性得分,
            'issues': 问题列表,
            'warnings': 警告列表
        }
    """
    score = 0
    issues = []
    warnings = []
    accuracy_score = 0
    timeliness_score = 0
    reliability_score = 0
    claim_coverage_score = 0
    narrative_consistency_passed = True
    data_integrity_statement_passed = _data_integrity_statement_passed(report_text, data_quality_stats)
    watchlist_promoted_in_narrative_count = 0
    verification_boundary_overclaim_count = 0
    time_source = None
    source_annotation_missing = False

    # ============================================================
    # 1. 准确性评分 (60分) - 核心指标
    # ============================================================
    realtime_claims = _realtime_claims(claims)
    news_claims = _news_fact_claims(claims)

    if realtime_claims is not None:
        verified_count = sum(1 for c in realtime_claims if c.verified)
        total_count = len(realtime_claims)
        error_count = sum(1 for c in realtime_claims if c.error)

        if total_count > 0:
            accuracy_rate = verified_count / total_count
            accuracy_score = accuracy_rate * 60

            # 记录准确性情况
            if accuracy_rate < 0.5:
                issues.append(f"❌ 准确性严重不足: 仅{accuracy_rate:.0%}的断言得到验证 ({verified_count}/{total_count})")
            elif accuracy_rate < 0.7:
                warnings.append(f"⚠️ 准确性偏低: {accuracy_rate:.0%}的断言得到验证 ({verified_count}/{total_count})")
            else:
                logger.info(f"准确性良好: {accuracy_rate:.0%} ({verified_count}/{total_count})")

            # 错误惩罚
            if error_count > 0:
                penalty = min(error_count * 10, 30)
                accuracy_score = max(0, accuracy_score - penalty)
                issues.append(f"❌ 检测到 {error_count} 个错误或违规断言,扣分 {penalty}")
        else:
            logger.info("事实核查已执行，但报告中未提取到可验证断言")
            warnings.append("⚠️ 未提取到可验证的具体断言,准确性按中性评分处理")
            accuracy_score = 45
    else:
        warnings.append("⚠️ 未进行事实核查,准确性无法保证")
        accuracy_score = 30  # 给基础分

    score += accuracy_score

    # ============================================================
    # 1.5 断言覆盖度评分 (附加门槛，不单独计入总分)
    # ============================================================
    total_realtime_claims = len(realtime_claims) if realtime_claims is not None else 0
    total_news_claims = len(news_claims) if news_claims is not None else 0
    narrative_body = _section_before_stock_table(report_text)
    narrative_length = len(narrative_body)
    if total_realtime_claims + total_news_claims >= 6:
        claim_coverage_score = 20
    elif total_realtime_claims + total_news_claims >= 4:
        claim_coverage_score = 15
    elif total_realtime_claims + total_news_claims >= 2:
        claim_coverage_score = 10
    else:
        claim_coverage_score = 5 if narrative_length < 1800 else 0
    if narrative_length > 2500 and total_realtime_claims + total_news_claims < 3:
        issues.append("❌ 报告篇幅较长，但可验证断言覆盖过少")

    # ============================================================
    # 2. 时效性评分 (20分)
    # ============================================================
    has_source_annotation = '数据来源' in report_text or '来源：' in report_text
    has_time_annotation = '更新时间' in report_text or '数据时效' in report_text
    source_annotation_missing = not has_source_annotation
    report_update_time = _extract_report_update_time(report_text)
    system_update_time = _parse_quality_time((realtime_data or {}).get('timestamp'))
    has_realtime_data = bool(report_update_time or system_update_time)
    data_age_hours = None

    if report_update_time and system_update_time:
        if abs((system_update_time - report_update_time).total_seconds()) > 3600:
            warnings.append("⚠️ 报告更新时间与系统实时数据时间不一致,已按更保守时间计算时效性")
        update_time = min(report_update_time, system_update_time)
        time_source = 'report_text' if update_time == report_update_time else 'system_realtime_data'
        data_age_hours = (datetime.now() - update_time).total_seconds() / 3600
        timeliness_score = _timeliness_score(data_age_hours, warnings)
    elif report_update_time:
        time_source = 'report_text'
        data_age_hours = (datetime.now() - report_update_time).total_seconds() / 3600
        timeliness_score = _timeliness_score(data_age_hours, warnings)
    elif system_update_time:
        time_source = 'system_realtime_data'
        data_age_hours = (datetime.now() - system_update_time).total_seconds() / 3600
        timeliness_score = _timeliness_score(data_age_hours, warnings)
        if not has_time_annotation:
            warnings.append("⚠️ 报告中缺少实时数据更新时间标注,已按系统注入时间计算时效性")
    else:
        issues.append("❌ 缺少实时数据注入,报告时效性差")
        timeliness_score = 0

    if has_realtime_data and not has_source_annotation:
        warnings.append("⚠️ 报告中缺少实时数据来源标注")
    if data_age_hours is not None and data_age_hours >= 24:
        issues.append("❌ 实时数据更新时间超过24小时,不满足发布时效要求")

    score += timeliness_score

    # ============================================================
    # 3. 可靠性评分 (20分) - 来源标注
    # ============================================================
    # 检查引用来源
    citations = re.findall(r'【新闻\d+】', report_text)
    citation_count = len(citations)
    judgment_cards_count = len(re.findall(r'^###\s+\d+\.', report_text, flags=re.MULTILINE))

    # 计算可靠性得分
    if report_mode == 'judgment-cards' and judgment_cards_count > 0:
        reliability_score = min(20, 8 + judgment_cards_count * 3)
        if '观察项' not in report_text:
            warnings.append("⚠️ 缺少观察项章节，判断边界可能不够清晰")
    elif citation_count >= 15 and has_source_annotation:
        reliability_score = 20
    elif citation_count >= 15:
        reliability_score = 15
    elif citation_count >= 10 and has_source_annotation:
        reliability_score = 15
    elif citation_count >= 10:
        reliability_score = 10
    elif citation_count >= 5 or has_source_annotation:
        reliability_score = 10
        if citation_count < 15:
            warnings.append(f"⚠️ 引用来源偏少 ({citation_count}处),建议增加到15处以上")
    else:
        reliability_score = 5
        issues.append(f"❌ 引用来源严重不足 ({citation_count}处),缺乏可信度")

    score += reliability_score

    # ============================================================
    # 4. 禁止编造内容检查 (严重违规 - 直接扣分)
    # ============================================================
    fabrication_detected = False

    # 检测1: 目标涨幅 (最严重违规)
    target_gains = re.findall(r'目标涨幅\s*[:：]?\s*(\d+\.?\d*)\s*%', report_text)
    if target_gains:
        score -= 30  # 严重扣分
        fabrication_detected = True
        issues.append(f"❌❌❌ 严重违规: AI编造目标涨幅 ({', '.join(target_gains)}%),明确禁止!")

    # 检测2: 未来具体价格预测
    target_prices = re.findall(r'目标价(?:格)?\s*[:：]?\s*([¥$]\d+\.?\d*)', report_text)
    if target_prices:
        score -= 20
        fabrication_detected = True
        issues.append(f"❌❌ 违规: AI编造目标价格 ({', '.join(target_prices)}),禁止!")

    # 检测3: 编造的未来业绩预测
    future_predictions = re.findall(r'预计.*?(?:增长|下降)\s*(\d+\.?\d*)\s*%', report_text)
    if len(future_predictions) > 3:
        warnings.append(f"⚠️ 检测到多处未来预测 ({len(future_predictions)}处),请确认是否有依据")

    # 检测4: 无依据的具体断言
    if 'N/A' in report_text or '待定' in report_text:
        score -= 10
        issues.append("❌ 检测到N/A或待定占位符,未填写完整")

    strong_phrases = _extract_strong_phrases(report_text)
    if strong_phrases:
        actionable_count = len((stock_recommendations or []))
        high_confidence_count = len(_high_confidence_topics(judgment_candidates))
        if not actionable_count or high_confidence_count == 0:
            score -= min(15, len(strong_phrases) * 5)
            issues.append(f"❌ 存在过强措辞但缺少对应高置信证据: {', '.join(strong_phrases)}")
        else:
            warnings.append(f"⚠️ 检测到较强措辞: {', '.join(strong_phrases)}")

    # ============================================================
    # 5. 基础结构检查 (额外加分项)
    # ============================================================
    required_sections = (
        ["判断卡片", "观察项"]
        if report_mode == 'judgment-cards'
        else ["市场概况", "投资主题", "风险", "建议"]
    )
    missing_sections = [s for s in required_sections if s not in report_text]

    if missing_sections:
        warnings.append(f"⚠️ 缺少章节: {', '.join(missing_sections)}")
        score -= len(missing_sections) * 5

    # ============================================================
    # 5.5 一致性检查
    # ============================================================
    unsupported_stock_mentions = _find_unsupported_stock_mentions(report_text, stock_recommendations)
    if unsupported_stock_mentions:
        narrative_consistency_passed = False
        issues.append(f"❌ 正文出现结构化推荐层未支持的股票代码: {', '.join(unsupported_stock_mentions)}")

    watchlist_promotion_issues = _watchlist_promotion_issues(report_text, stock_recommendations)
    if watchlist_promotion_issues:
        narrative_consistency_passed = False
        watchlist_promoted_in_narrative_count = len(watchlist_promotion_issues)
        issues.extend(watchlist_promotion_issues)

    high_confidence_topics = _high_confidence_topics(judgment_candidates)
    if high_confidence_topics:
        mentioned_topics = set(_extract_topic_headers(report_text))
        unsupported_topics = {
            topic for topic in mentioned_topics
            if topic not in {'高置信主题', '观察主题', '高置信主题：', '观察主题：'}
            and '观察' not in topic
            and topic not in high_confidence_topics
        }
        if unsupported_topics:
            narrative_consistency_passed = False
            issues.append(f"❌ 正文出现未进入高置信候选的主题标题: {', '.join(sorted(unsupported_topics))}")

    if not data_integrity_statement_passed:
        issues.append("❌ 数据质量说明与真实文章分布不一致")

    if _has_verification_boundary_overclaim(report_text, realtime_claims, news_claims):
        verification_boundary_overclaim_count = 1
        narrative_consistency_passed = False
        issues.append("❌ 把局部已验证断言扩写成整份报告已验证，超出了事实核查边界")

    # ============================================================
    # 6. 确保得分在合理范围
    # ============================================================
    score = max(0, min(100, score))

    # ============================================================
    # 7. 判断是否通过
    # ============================================================
    # 通过标准: 总分>=80 且 无严重问题 且 未检测到编造内容
    passed = (
        score >= 80
        and len(issues) == 0
        and not fabrication_detected
        and claim_coverage_score >= 10
        and narrative_consistency_passed
        and data_integrity_statement_passed
    )

    # ============================================================
    # 8. 返回结果
    # ============================================================
    return {
        'score': round(score, 1),
        'passed': passed,
        'accuracy_score': round(accuracy_score, 1),
        'timeliness_score': round(timeliness_score, 1),
        'reliability_score': round(reliability_score, 1),
        'claim_coverage_score': claim_coverage_score,
        'time_source': time_source,
        'source_annotation_missing': source_annotation_missing,
        'narrative_consistency_passed': narrative_consistency_passed,
        'data_integrity_statement_passed': data_integrity_statement_passed,
        'issues': issues,
        'warnings': warnings,
        'stats': {
            'has_realtime_data': has_realtime_data,
            'data_age_hours': data_age_hours,
            'time_source': time_source,
            'source_annotation_missing': source_annotation_missing,
            'claim_coverage_score': claim_coverage_score,
            'citation_count': citation_count,
            'verified_claims': sum(1 for c in realtime_claims if c.verified) if realtime_claims is not None else 0,
            'total_claims': len(realtime_claims) if realtime_claims is not None else 0,
            'realtime_verified_claims': sum(1 for c in realtime_claims if c.verified) if realtime_claims is not None else 0,
            'realtime_total_claims': len(realtime_claims) if realtime_claims is not None else 0,
            'news_fact_claims': len(news_claims) if news_claims is not None else 0,
            'analytical_judgment_count': 0,
            'fabrication_detected': fabrication_detected,
            'watchlist_promoted_in_narrative_count': watchlist_promoted_in_narrative_count,
            'verification_boundary_overclaim_count': verification_boundary_overclaim_count,
        },
        'timestamp': datetime.now().isoformat()
    }


def print_quality_report_v2(quality_result: Dict, verbose: bool = True):
    """
    打印增强版质量检查报告

    Args:
        quality_result: check_report_quality_v2的返回结果
        verbose: 是否显示详细信息
    """
    print("\n" + "="*70)
    print("📊 报告质量检查结果 (v2.0 - 集成事实核查)")
    print("="*70)

    # 总分
    score = quality_result['score']
    if score >= 90:
        score_emoji = "🌟"
        score_desc = "优秀"
    elif score >= 80:
        score_emoji = "✅"
        score_desc = "良好"
    elif score >= 70:
        score_emoji = "👍"
        score_desc = "合格"
    elif score >= 60:
        score_emoji = "⚠️"
        score_desc = "待改进"
    else:
        score_emoji = "❌"
        score_desc = "不合格"

    print(f"\n{score_emoji} 总体评分: {score}/100 ({score_desc})")

    # 分项得分
    if verbose:
        print(f"\n📈 分项评分:")
        print(f"  • 准确性: {quality_result['accuracy_score']:.1f}/60 (基于事实核查)")
        print(f"  • 时效性: {quality_result['timeliness_score']:.1f}/20 (数据新鲜度)")
        print(f"  • 可靠性: {quality_result['reliability_score']:.1f}/20 (来源标注)")
        print(f"  • 断言覆盖: {quality_result.get('claim_coverage_score', 0)}/20 (非总分门槛)")

    # 严重问题
    if quality_result['issues']:
        print(f"\n❌ 严重问题 ({len(quality_result['issues'])}个):")
        for issue in quality_result['issues']:
            print(f"  {issue}")

    # 警告
    if quality_result['warnings']:
        print(f"\n⚠️ 警告 ({len(quality_result['warnings'])}个):")
        for warning in quality_result['warnings']:
            print(f"  {warning}")

    # 统计信息
    if verbose:
        stats = quality_result['stats']
        print(f"\n📊 统计数据:")
        print(f"  • 实时数据: {'是' if stats.get('has_realtime_data') else '否'}")
        if stats.get('data_age_hours') is not None:
            print(f"  • 数据时效: {stats['data_age_hours']:.1f} 小时前")
        print(f"  • 引用来源: {stats.get('citation_count', 0)}处")
        print(f"  • 验证断言: {stats.get('verified_claims', 0)}/{stats.get('total_claims', 0)}")
        print(f"  • 新闻数值断言: {stats.get('news_fact_claims', 0)}")
        if stats.get('fabrication_detected'):
            print(f"  • ⚠️ 检测到编造内容")
        print(f"  • 叙事一致性: {'通过' if quality_result.get('narrative_consistency_passed', True) else '失败'}")
        print(f"  • 数据质量说明: {'通过' if quality_result.get('data_integrity_statement_passed', True) else '失败'}")

    # 最终判断
    print(f"\n{'='*70}")
    if quality_result['passed']:
        print("✅ 质量检查通过,可以发布")
    else:
        print("❌ 质量检查未通过,建议优化后再发布")
        print("\n改进建议:")
        print("  1. 确保所有断言基于实时数据")
        print("  2. 删除所有编造的目标涨幅/价格")
        print("  3. 增加引用来源标注(【新闻X】)")
        print("  4. 在报告中标注数据来源和更新时间")

    print("="*70 + "\n")


def compare_quality_scores(old_score: Dict, new_score: Dict) -> str:
    """
    对比优化前后的质量评分

    Args:
        old_score: 旧版评分结果
        new_score: 新版评分结果

    Returns:
        对比报告文本
    """
    comparison = "\n## 📊 质量评分对比\n\n"
    comparison += "| 维度 | 优化前 | 优化后 | 提升 |\n"
    comparison += "|------|--------|--------|------|\n"

    old_total = old_score.get('score', 0)
    new_total = new_score.get('score', 0)
    improvement = new_total - old_total

    comparison += f"| **总分** | {old_total:.1f} | {new_total:.1f} | "
    comparison += f"**{improvement:+.1f}** |\n"

    # 如果新版有分项得分
    if 'accuracy_score' in new_score:
        comparison += f"| 准确性(/60) | - | {new_score['accuracy_score']:.1f} | 新增 |\n"
        comparison += f"| 时效性(/20) | - | {new_score['timeliness_score']:.1f} | 新增 |\n"
        comparison += f"| 可靠性(/20) | - | {new_score['reliability_score']:.1f} | 新增 |\n"

    # 统计对比
    old_issues = len(old_score.get('issues', []))
    new_issues = len(new_score.get('issues', []))

    comparison += f"\n**问题数对比**: {old_issues} → {new_issues} "
    comparison += f"({'减少' if new_issues < old_issues else '增加'} {abs(new_issues - old_issues)})\n"

    return comparison


# ============================================================
# 使用示例和测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )

    print("="*70)
    print("增强版质量检查器 v2.0 - 功能测试")
    print("="*70)

    # 模拟报告
    test_report_bad = """
    # 财经分析报告

    ## 投资建议

    | 股票 | 目标涨幅 | 风险 |
    |------|---------|------|
    | 紫金矿业 | 25% | 中 |

    金价突破3800美元,建议关注黄金板块。
    """

    test_report_good = """
    # 财经分析报告

    ## 📊 实时市场数据

    **数据来源**: 新浪财经
    **更新时间**: 2026-01-07 15:00

    ## 市场概况

    今日A股市场活跃,紫金矿业(sh601899)现价¥15.23,涨幅+2.34%【新闻1】。
    国际金价$2650/盎司,较昨日+1.2%【新闻2】。

    ## 投资主题

    黄金板块表现强势,建议关注紫金矿业等龙头【新闻3】【新闻4】。

    ## 风险提示

    需警惕金价回调风险【新闻5】,建议设置止损【新闻6】。

    ## 操作建议

    建议逢低配置,仓位控制在30%以内【新闻7】【新闻8】【新闻9】【新闻10】。
    """

    # 模拟事实核查结果
    from dataclasses import dataclass
    from enum import Enum

    class ClaimType(Enum):
        PRICE_CHANGE = "涨跌幅"

    @dataclass
    class MockClaim:
        type: ClaimType
        content: str
        verified: bool
        confidence: float
        error: str = ""

    # 测试1: 低质量报告(有编造内容)
    print("\n【测试1】低质量报告(有目标涨幅)")
    print("-"*70)

    bad_claims = [
        MockClaim(ClaimType.PRICE_CHANGE, "目标涨幅25%", False, 0.0, "编造内容")
    ]

    bad_result = check_report_quality_v2(
        report_text=test_report_bad,
        claims=bad_claims,
        realtime_data=None
    )

    print_quality_report_v2(bad_result)

    # 测试2: 高质量报告(有实时数据)
    print("\n【测试2】高质量报告(有实时数据和事实核查)")
    print("-"*70)

    good_claims = [
        MockClaim(ClaimType.PRICE_CHANGE, "涨幅+2.34%", True, 0.98),
        MockClaim(ClaimType.PRICE_CHANGE, "金价+1.2%", True, 0.95),
    ]

    good_realtime = {
        'timestamp': '2026-01-07 15:00:00',
        'stocks': {'sh601899': {'price': 15.23, 'change_pct': 2.34}}
    }

    good_result = check_report_quality_v2(
        report_text=test_report_good,
        claims=good_claims,
        realtime_data=good_realtime
    )

    print_quality_report_v2(good_result)

    # 测试3: 对比
    print("\n【测试3】质量评分对比")
    print("-"*70)
    comparison = compare_quality_scores(bad_result, good_result)
    print(comparison)

    print("\n" + "="*70)
    print("✅ 测试完成")
    print("="*70)
