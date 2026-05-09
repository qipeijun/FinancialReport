#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高信号投资判断辅助模块

V1 目标：
- 为新闻文章补充最小必要的投资判断标签
- 生成轻量级判断候选组
- 约束最终输出为少量判断卡片和观察项
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple


SOURCE_TIER_RANK = {
    'aggregator': 1,
    'industry': 2,
    'mainstream': 3,
    'official': 4,
}

SOURCE_TIER_LABEL = {
    'aggregator': '低优先级聚合源',
    'industry': '行业/公司信息源',
    'mainstream': '主流财经媒体',
    'official': '官方/监管',
}

TOPIC_RULES: List[Tuple[str, Dict[str, Any]]] = [
    ('政策与监管', {
        'keywords': ['监管', '政策', '发改委', '财政部', '商务部', '国务院', '证监会', 'SEC', '央行'],
        'markets': ['A股', '港股', '宏观'],
        'time_horizon': '1-4周',
    }),
    ('宏观与流动性', {
        'keywords': ['美联储', '非农', 'CPI', 'PPI', '利率', '降息', '加息', '国债', '收益率', '流动性'],
        'markets': ['美股', 'A股', '港股', '美元', '利率'],
        'time_horizon': '1-4周',
    }),
    ('汇率与大宗', {
        'keywords': ['美元', '人民币', '汇率', '黄金', '原油', '铜价', '铁矿石', '大宗'],
        'markets': ['汇率', '商品', 'A股', '港股'],
        'time_horizon': '1-3周',
    }),
    ('财报与公司经营', {
        'keywords': ['财报', '净利润', '营收', '业绩', '指引', '回购', '分红', '季度'],
        'markets': ['A股', '港股', '美股'],
        'time_horizon': '1-2周',
    }),
    ('科技与产业主题', {
        'keywords': ['AI', '芯片', '算力', '机器人', '新能源', '半导体', '云计算', '大模型'],
        'markets': ['A股', '港股', '美股'],
        'time_horizon': '2-6周',
    }),
    ('风险事件', {
        'keywords': ['冲突', '制裁', '违约', '调查', '风险', '暴跌', '停牌', '裁员'],
        'markets': ['A股', '港股', '美股', '商品'],
        'time_horizon': '1-3周',
    }),
]

HIGH_SIGNAL_KEYWORDS = [
    '政策', '监管', '美联储', '财报', '净利润', '营收', 'CPI', 'PPI', '利率', '汇率',
    '黄金', '原油', '制裁', '调查', '回购', '分红', '指引', '订单', '产能', '景气',
]

LOW_SIGNAL_KEYWORDS = [
    '热搜', '网友', '回应', '直播', '会员', '穿搭', '促销', '娱乐', '八卦', '限量发售',
]


def classify_source_tier(source_name: str, source_category: str | None = None) -> str:
    category = (source_category or '').strip()
    source = (source_name or '').strip()

    if category == '政府组织与官方数据':
        return 'official'
    if source in {'SEC', '美国证监会-新闻发布', 'Federal Reserve Board', '国家统计局-最新发布'}:
        return 'official'
    if source in {'FT中文网', 'Wall Street Journal', '经济学人 Economist', 'CNBC', 'Thomson Reuters', '华尔街见闻'}:
        return 'mainstream'
    if source in {'36氪', '东方财富网', '中新网', 'BBC全球经济'}:
        return 'mainstream'
    if source in {'百度股票焦点', 'ZeroHedge', 'ETF Trends'}:
        return 'aggregator'
    if source in {'Investing_com', 'CoinDesk'}:
        return 'industry'
    return 'mainstream'


def is_original_source(source_tier: str, source_name: str) -> int:
    if source_tier == 'official':
        return 1
    if source_name in {'Wall Street Journal', 'CNBC', 'Thomson Reuters', 'FT中文网', '经济学人 Economist'}:
        return 1
    return 0


def detect_content_quality_status(summary: str, content: str, fetched_content: bool) -> str:
    summary_len = len(summary or '')
    content_len = len(content or '')

    if fetched_content and content_len >= 800:
        return 'full'
    if fetched_content and content_len >= 180:
        return 'partial'
    if summary_len >= 80:
        return 'summary_only'
    return 'failed'


def score_investment_relevance(article: Dict[str, Any]) -> str:
    text = f"{article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}".lower()
    high_hits = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw.lower() in text)
    low_hits = sum(1 for kw in LOW_SIGNAL_KEYWORDS if kw.lower() in text)

    source_tier = article.get('source_tier', 'mainstream')
    quality_status = article.get('content_quality_status', 'summary_only')

    score = 0
    score += SOURCE_TIER_RANK.get(source_tier, 2)
    score += min(high_hits, 4)
    score -= min(low_hits, 3)
    if quality_status == 'full':
        score += 2
    elif quality_status == 'partial':
        score += 1
    elif quality_status == 'failed':
        score -= 2

    if score >= 6:
        return 'high'
    if score >= 3:
        return 'medium'
    return 'low'


def infer_topic(article: Dict[str, Any]) -> Tuple[str, List[str], str]:
    text = f"{article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}".lower()
    for topic, config in TOPIC_RULES:
        if any(keyword.lower() in text for keyword in config['keywords']):
            return topic, config['markets'], config['time_horizon']
    return '其他观察', ['A股', '港股', '美股'], '1-2周'


def extract_json_payload(text: str) -> Dict[str, Any]:
    cleaned = (text or '').strip()
    if not cleaned:
        return {}

    fenced = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', cleaned)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]

    return json.loads(cleaned)


def build_judgment_candidates(
    articles: List[Dict[str, Any]],
    max_candidates: int = 8,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    filtered = [
        a for a in articles
        if a.get('investment_relevance') in {'high', 'medium'}
        and a.get('content_quality_status') != 'failed'
    ]

    for article in filtered:
        topic, markets, horizon = infer_topic(article)
        article['primary_topic'] = topic
        article['market_scope'] = markets
        article['time_horizon'] = horizon
        grouped[topic].append(article)

    candidates: List[Dict[str, Any]] = []
    for idx, (topic, items) in enumerate(grouped.items(), start=1):
        items.sort(
            key=lambda x: (
                SOURCE_TIER_RANK.get(x.get('source_tier', 'mainstream'), 0),
                1 if x.get('investment_relevance') == 'high' else 0,
                len(x.get('content') or ''),
                len(x.get('summary') or ''),
            ),
            reverse=True,
        )
        top_items = items[:4]
        source_names = sorted({item.get('source') or '未知来源' for item in items})
        original_sources = sum(1 for item in items if item.get('is_original_source'))
        high_relevance_article_count = sum(
            1 for item in items if item.get('investment_relevance') == 'high'
        )
        candidate = {
            'candidate_id': f'C{idx:02d}',
            'topic': topic,
            'market_scope': top_items[0].get('market_scope', ['A股', '港股']),
            'time_horizon': top_items[0].get('time_horizon', '1-2周'),
            'evidence_count': len(source_names),
            'independent_evidence_count': original_sources or min(len(source_names), 1),
            'high_relevance_article_count': high_relevance_article_count,
            'source_tier_max': max(
                (item.get('source_tier', 'mainstream') for item in items),
                key=lambda tier: SOURCE_TIER_RANK.get(tier, 0),
            ),
            'original_source_count': original_sources,
            'articles': [
                {
                    'id': item.get('id'),
                    'title': item.get('title'),
                    'source': item.get('source'),
                    'summary': (item.get('summary') or '')[:180],
                    'source_tier': item.get('source_tier'),
                    'content_quality_status': item.get('content_quality_status'),
                    'published': item.get('published'),
                    'collection_date': item.get('collection_date'),
                }
                for item in top_items
            ],
            'topic_article_count': len(items),
        }
        candidate['priority_score'] = (
            SOURCE_TIER_RANK.get(candidate['source_tier_max'], 0) * 10
            + candidate['evidence_count'] * 3
            + candidate['original_source_count'] * 4
        )
        candidate['high_confidence_topic'] = (
            SOURCE_TIER_RANK.get(candidate['source_tier_max'], 0) >= SOURCE_TIER_RANK['mainstream']
            and candidate['independent_evidence_count'] >= 2
            and candidate['evidence_count'] >= 2
            and candidate['high_relevance_article_count'] >= 1
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: item['priority_score'], reverse=True)
    return candidates[:max_candidates]


def build_judgment_prompt_context(
    candidates: List[Dict[str, Any]],
    realtime_data_available: bool,
    max_theses: int,
) -> str:
    lines = [
        '你将看到一组已经过初筛的判断候选。',
        '任务是只输出少量高置信度判断卡片；证据不足的内容必须放入观察项，不得硬写结论。',
        f'最多输出 {max_theses} 条判断卡片。',
        f'实时数据状态: {"可用" if realtime_data_available else "不可用"}',
        '',
        '候选组：',
    ]

    for candidate in candidates:
        lines.append(
            f"- {candidate['candidate_id']} | 主题={candidate['topic']} | 市场={','.join(candidate['market_scope'])} | "
            f"时间维度={candidate['time_horizon']} | 来源等级={candidate['source_tier_max']} | "
            f"独立证据={candidate['independent_evidence_count']} | 来源数={candidate['evidence_count']}"
        )
        for article in candidate['articles']:
            lines.append(
                f"  * [{article['source']}/{article['source_tier']}/{article['content_quality_status']}] "
                f"{article['title']} | 摘要: {article['summary']}"
            )
        lines.append('')
    return '\n'.join(lines)


def enforce_judgment_rules(
    payload: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    *,
    realtime_available: bool,
    min_source_tier: str,
    min_independent_evidence: int,
    degrade_on_weak_evidence: bool,
    output_observation_only_when_weak: bool,
    max_theses: int,
) -> Dict[str, Any]:
    candidate_map = {candidate['candidate_id']: candidate for candidate in candidates}
    threshold_rank = SOURCE_TIER_RANK.get(min_source_tier, SOURCE_TIER_RANK['mainstream'])

    theses = payload.get('theses') or []
    watch_items = payload.get('watch_items') or []
    kept_theses = []
    degraded = payload.get('degraded', False)

    for thesis in theses[:max_theses]:
        candidate_id = thesis.get('candidate_id')
        candidate = candidate_map.get(candidate_id)
        if not candidate:
            degraded = True
            watch_items.append({
                'topic': thesis.get('hypothesis') or thesis.get('topic') or '未匹配候选',
                'reason': '模型输出未关联到有效候选，已降级为观察项',
            })
            continue

        weak_evidence = (
            SOURCE_TIER_RANK.get(candidate['source_tier_max'], 0) < threshold_rank
            or candidate['independent_evidence_count'] < min_independent_evidence
        )

        if weak_evidence and (degrade_on_weak_evidence or output_observation_only_when_weak):
            degraded = True
            watch_items.append({
                'topic': thesis.get('hypothesis') or candidate['topic'],
                'reason': thesis.get('risk') or '证据不足，降级为观察项',
                'candidate_id': candidate_id,
            })
            continue

        if not realtime_available and thesis.get('market_impact'):
            thesis['confidence'] = thesis.get('confidence') or '中'
            thesis['risk'] = f"{thesis.get('risk', '')}；缺少实时数据，市场影响仅作方向性参考".strip('；')
            degraded = True

        thesis['candidate_id'] = candidate_id
        thesis['evidence_summary'] = {
            'source_tier_max': candidate['source_tier_max'],
            'independent_evidence_count': candidate['independent_evidence_count'],
            'source_count': candidate['evidence_count'],
        }
        kept_theses.append(thesis)

    if not kept_theses and not watch_items:
        degraded = True
        watch_items.append({
            'topic': '暂无高置信度主线',
            'reason': '当前候选证据不足，建议继续观察政策、流动性和财报方向。',
        })

    payload['theses'] = kept_theses
    payload['watch_items'] = watch_items
    payload['degraded'] = degraded
    payload['market_scope'] = payload.get('market_scope') or '中国与全球联动'
    payload['time_horizon'] = payload.get('time_horizon') or '1-4周'
    return payload


def render_judgment_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        '# 高信号投资判断卡片',
        '',
        f"- 市场范围: {payload.get('market_scope', '中国与全球联动')}",
        f"- 时间维度: {payload.get('time_horizon', '1-4周')}",
        f"- 状态: {'已降级' if payload.get('degraded') else '正常'}",
        '',
        '## 判断卡片',
        '',
    ]

    theses = payload.get('theses') or []
    if theses:
        for idx, thesis in enumerate(theses, start=1):
            lines.extend([
                f"### {idx}. {thesis.get('hypothesis', '未命名判断')}",
                f"- 影响市场: {thesis.get('market_impact', '未提供')}",
                f"- 时间维度: {thesis.get('time_horizon', payload.get('time_horizon', '1-4周'))}",
                f"- 置信度: {thesis.get('confidence', '中')}",
                f"- 支持证据: {thesis.get('evidence', '未提供')}",
                f"- 反证/风险: {thesis.get('risk', '未提供')}",
                f"- 后续验证点: {thesis.get('validation_point', '未提供')}",
                '',
            ])
    else:
        lines.extend([
            '- 暂无高置信度判断，当前以观察项为主。',
            '',
        ])

    lines.extend(['## 观察项', ''])
    for item in payload.get('watch_items') or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('topic', '观察项')}: {item.get('reason', '待观察')}")
        else:
            lines.append(f"- {item}")

    if payload.get('evidence_summary'):
        lines.extend(['', '## 证据摘要', '', payload['evidence_summary']])
    return '\n'.join(lines).strip() + '\n'


def build_retry_feedback(quality_result: Dict[str, Any]) -> str:
    issues = quality_result.get('issues') or []
    warnings = quality_result.get('warnings') or []
    problems = (issues + warnings)[:6]
    if not problems:
        return ''
    joined = '\n'.join(f"- {item}" for item in problems)
    return (
        '上一次输出存在以下问题，请只保留高置信度判断，并把证据不足内容放入观察项：\n'
        f'{joined}'
    )
