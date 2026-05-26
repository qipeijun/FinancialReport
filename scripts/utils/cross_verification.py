#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交叉验真引擎 V1

对主题和标的做确定性、可复现的多来源证据强度判断。
不依赖 LLM 语义裁判，所有结果由代码规则复现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CROSS_STATUS_CONFIRMED = "confirmed"
CROSS_STATUS_WEAK = "weak"
CROSS_STATUS_CONFLICTED = "conflicted"

SOURCE_TIER_RANK = {
    'aggregator': 1,
    'industry': 2,
    'mainstream': 3,
    'official': 4,
}

# 证据新鲜度阈值（天）
FRESHNESS_THRESHOLD_DAYS = 2

# 主题确认最小独立来源数
MIN_TOPIC_INDEPENDENT_SOURCES = 2
MIN_TOPIC_MAINSTREAM_OR_BETTER = 1

# 标的确认最小条件
MIN_STOCK_DIRECT_MENTIONS = 1
MIN_STOCK_INDEPENDENT_SOURCES = 2

# ---- 冲突检测关键词 ----
# 重大正面催化词
MAJOR_POSITIVE_KEYWORDS = [
    '订单', '回购', '分红', '中标', '产能', '扩产', '超预期',
    '上调指引', '突破', '利好', '大幅增长', '扭亏', '业绩预增',
    'FDA 批准', '获批', 'license-out', '出海',
    'beat estimates', 'guidance raise', 'upgrade', 'breakthrough',
]

# 重大负面风险词
MAJOR_NEGATIVE_KEYWORDS = [
    '立案', '停牌', '退市', '暴雷', '减持', '处罚', '调查',
    '诉讼', '做空', '评级下调', '集体诉讼', '监管调查', '警告',
    '亏损', '大幅下滑', '业绩预减', '商誉减值', '债务违约',
    'lawsuit', 'fraud', 'downgrade', 'short report',
    'class action', 'SEC investigation',
]

# ---- 数值断言提取 ----
# 营收/利润/增长率等指标的模式
NUMERIC_ASSERTION_PATTERNS = [
    # 增长/下降 + 百分比
    re.compile(r'(营收|收入|利润|净利|毛利|revenue|profit|income|earnings).*?'
               r'(增长|下降|下滑|decline|grow|increase|decrease|fall|rise)'
               r'.*?(\d+\.?\d*)\s*%', re.IGNORECASE),
    # 百分比 + 增长/下降
    re.compile(r'(\d+\.?\d*)\s*%\s*(增长|下降|下滑|decline|grow|increase|decrease)',
               re.IGNORECASE),
    # XX亿/万 + 增长/下降
    re.compile(r'(营收|收入|利润|净利).*?(\d+\.?\d*)\s*(亿|万|万亿)',
               re.IGNORECASE),
]

# 正方向词
POSITIVE_DIRECTION = {'增长', '上升', '回暖', '反弹', '利好', '超预期',
                      'grow', 'increase', 'rise', 'beat', 'upgrade'}
NEGATIVE_DIRECTION = {'下降', '下滑', '萎缩', '衰退', '下跌', 'decline',
                      'decrease', 'fall', 'drop', 'downgrade'}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TopicCrossCheck:
    topic: str
    status: str
    evidence_article_ids: List[int] = field(default_factory=list)
    independent_source_count: int = 0
    mainstream_or_better_count: int = 0
    has_fresh_evidence: bool = False
    conflict_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StockCrossCheck:
    symbol: str
    name: str
    status: str
    evidence_article_ids: List[int] = field(default_factory=list)
    direct_mentions: int = 0
    independent_source_count: int = 0
    has_fresh_evidence: bool = False
    source_type: str = ''
    conflict_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> Optional[datetime]:
    """解析日期字符串，与 RecommendationScorer._parse_date 保持一致的逻辑。"""
    text = (value or '').strip()
    if not text:
        return None
    normalized = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%a, %d %b %Y %H:%M:%S %z'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _is_evidence_fresh(
    dates: List[str],
    as_of_date: datetime,
    threshold_days: int = FRESHNESS_THRESHOLD_DAYS,
) -> bool:
    """至少有一条证据的发布日期距参考日 ≤ threshold_days。"""
    if not dates:
        return False
    for date_str in dates:
        parsed = _parse_date(date_str)
        if parsed is None:
            continue
        delta = (as_of_date.date() - parsed.date()).days
        if delta <= threshold_days:
            return True
    return False


def _collect_evidence_dates_from_candidate_articles(
    articles: List[Dict[str, Any]],
) -> List[str]:
    """从 judgment_candidate 的 articles 列表中提取 published 日期。"""
    dates: List[str] = []
    for art in articles:
        pub = art.get('published')
        if pub:
            dates.append(str(pub))
    return dates


# ---------------------------------------------------------------------------
# 冲突检测
# ---------------------------------------------------------------------------

def _extract_keywords(text: str, keyword_set: List[str]) -> Set[str]:
    """从文本中提取匹配的关键词集合。"""
    lowered = text.lower()
    found: Set[str] = set()
    for kw in keyword_set:
        if kw.lower() in lowered:
            found.add(kw)
    return found


def _extract_numeric_assertions(text: str) -> List[Dict[str, Any]]:
    """从文本中提取关键数值断言（方向 + 百分比/金额）。"""
    assertions: List[Dict[str, Any]] = []
    for pattern in NUMERIC_ASSERTION_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            assertion = {
                'full_match': match.group(0).strip(),
                'groups': groups,
            }
            assertions.append(assertion)
    return assertions


def _classify_numeric_direction(assertion: Dict[str, Any]) -> Optional[str]:
    """判断数值断言的方向：positive / negative / None。"""
    text = assertion['full_match'].lower()
    for word in POSITIVE_DIRECTION:
        if word.lower() in text:
            return 'positive'
    for word in NEGATIVE_DIRECTION:
        if word.lower() in text:
            return 'negative'
    return None


def _detect_numeric_conflict(assertions: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """检测数值断言是否存在方向性矛盾。

    规则：如果存在 >=2 条断言且方向相反（一正一负），认定为冲突。
    """
    if len(assertions) < 2:
        return False, None

    directions = [_classify_numeric_direction(a) for a in assertions]
    directions = [d for d in directions if d is not None]

    has_positive = 'positive' in directions
    has_negative = 'negative' in directions

    if has_positive and has_negative:
        pos_example = next(
            a['full_match'] for a in assertions
            if _classify_numeric_direction(a) == 'positive'
        )
        neg_example = next(
            a['full_match'] for a in assertions
            if _classify_numeric_direction(a) == 'negative'
        )
        detail = f"数值方向矛盾: 「{pos_example[:80]}」vs「{neg_example[:80]}」"
        return True, detail

    return False, None


def _detect_stock_keyword_conflict(
    symbol: str,
    selected_articles: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """V1 保守关键词冲突检测：跨文章正负关键词并存。

    只在不同文章中出现正/负关键词时才标记冲突；
    同一篇文章同时出现正负关键词是正常的平衡报道，不触发。
    """
    articles_with_positive: Set[int] = set()
    articles_with_negative: Set[int] = set()
    positive_keywords_found: Set[str] = set()
    negative_keywords_found: Set[str] = set()

    for art in selected_articles:
        art_id = art.get('id')
        if art_id is None:
            continue
        text_parts = [
            art.get('title') or '',
            art.get('summary') or '',
            art.get('content') or '',
        ]
        combined = ' '.join(text_parts)
        if not combined.strip():
            continue

        pos = _extract_keywords(combined, MAJOR_POSITIVE_KEYWORDS)
        neg = _extract_keywords(combined, MAJOR_NEGATIVE_KEYWORDS)

        if pos:
            articles_with_positive.add(art_id)
            positive_keywords_found.update(pos)
        if neg:
            articles_with_negative.add(art_id)
            negative_keywords_found.update(neg)

    # 跨文章检测：正负关键词出现在不同文章中
    cross_positive = articles_with_positive - articles_with_negative
    cross_negative = articles_with_negative - articles_with_positive

    if cross_positive and cross_negative:
        detail = (
            f"跨文章关键词冲突: 正面关键词 {sorted(positive_keywords_found)} "
            f"(文章 {sorted(cross_positive)[:3]}) vs "
            f"负面关键词 {sorted(negative_keywords_found)} "
            f"(文章 {sorted(cross_negative)[:3]})"
        )
        return True, detail

    return False, None


def _contains_cjk(text: str) -> bool:
    """检查文本是否包含 CJK 字符（中文等）。"""
    return any('一' <= ch <= '鿿' for ch in text)


def _article_mentions_security(text: str, symbol: str, name: str) -> bool:
    """用词边界匹配检查文本是否真正提到某只股票。

    与 SecurityMasterProvider._sentence_mentions_security 保持一致：
    - A 股用 6 位数字码匹配
    - 美股 ticker 用 \\b 边界匹配防止短代码误命中
    - 中文名称用子串匹配（\\b 对 CJK 字符无效）
    """
    lowered = (text or '').lower()
    # A 股：sh/sz + 6 位数字
    if symbol.startswith(('sh', 'sz')) and len(symbol) >= 6:
        raw_code = symbol[-6:]
        if raw_code in lowered or symbol.lower() in lowered:
            return True
    # 纯字母 ticker（美股等）：严格词边界
    elif symbol.isalpha():
        if re.search(r'\b' + re.escape(symbol.lower()) + r'\b', lowered):
            return True
    elif symbol.lower() in lowered:
        return True

    # 名称匹配
    name_lower = name.lower()
    if len(name_lower) >= 3:
        if _contains_cjk(name_lower):
            # 中文名称：直接子串匹配（中文文本无双空格分隔）
            if name_lower in lowered:
                return True
        elif re.search(r'\b' + re.escape(name_lower) + r'\b', lowered):
            return True
    return False


def _detect_stock_conflict(
    symbol: str,
    name: str,
    selected_articles: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """对单只股票执行完整的 V1 冲突检测。

    返回 (has_conflict, conflict_detail)。
    """
    # 筛选提及该股票的文本（使用词边界匹配防止短 ticker 误命中）
    relevant_articles: List[Dict[str, Any]] = []
    for art in selected_articles:
        title = art.get('title') or ''
        summary = art.get('summary') or ''
        content = art.get('content') or ''
        combined = f"{title} {summary} {content}"
        if _article_mentions_security(combined, symbol, name):
            relevant_articles.append(art)

    if len(relevant_articles) < 2:
        return False, None

    # 1. 关键词冲突检测
    kw_conflict, kw_detail = _detect_stock_keyword_conflict(symbol, relevant_articles)
    if kw_conflict:
        return True, kw_detail

    # 2. 数值断言冲突检测
    all_text = ' '.join(
        f"{a.get('title', '')} {a.get('summary', '')} {a.get('content', '')}"
        for a in relevant_articles
    )
    assertions = _extract_numeric_assertions(all_text)
    num_conflict, num_detail = _detect_numeric_conflict(assertions)
    if num_conflict:
        return True, num_detail

    return False, None


def _detect_topic_conflict(
    topic: str,
    articles: List[Dict[str, Any]],
    selected_articles: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """对单个主题执行 V1 冲突检测。

    通过检查主题关联文章中的关键词和数值断言方向判断。
    """
    article_ids = {a.get('id') for a in articles if a.get('id') is not None}
    relevant = [a for a in selected_articles if a.get('id') in article_ids]

    if len(relevant) < 2:
        return False, None

    # 关键词冲突
    kw_conflict, kw_detail = _detect_stock_keyword_conflict(
        f"topic:{topic}", relevant,
    )
    if kw_conflict:
        # 重写 detail 去掉 symbol 前缀
        return True, kw_detail

    # 数值断言冲突
    all_text = ' '.join(
        f"{a.get('title', '')} {a.get('summary', '')} {a.get('content', '')}"
        for a in relevant
    )
    assertions = _extract_numeric_assertions(all_text)
    num_conflict, num_detail = _detect_numeric_conflict(assertions)
    if num_conflict:
        return True, num_detail

    return False, None


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def run_cross_verification(
    selected_articles: List[Dict[str, Any]],
    judgment_candidates: List[Dict[str, Any]],
    candidate_stocks: List[Any],
    stock_recommendations: List[Dict[str, Any]],
    as_of_date: str,
    market: str = 'CN',
) -> Dict[str, Any]:
    """执行交叉验真，返回 topic_checks / stock_checks / summary。

    参数：
        selected_articles: 原始文章列表
        judgment_candidates: build_judgment_candidates() 的输出
        candidate_stocks: List[CandidateStock]
        stock_recommendations: scorer.score_candidates()['recommendations']
        as_of_date: 参考日期 "YYYY-MM-DD"
        market: 'CN' 或 'US'
    """
    ref_date = _parse_date(as_of_date)
    if ref_date is None:
        ref_date = datetime.now()

    # 构建 candidate_stocks 的 symbol -> CandidateStock 映射
    stock_map: Dict[str, Any] = {}
    for cs in candidate_stocks:
        stock_map[cs.symbol] = cs

    topic_checks: List[TopicCrossCheck] = []
    stock_checks: List[StockCrossCheck] = []
    issues: List[str] = []
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # 主题交叉验真
    # ------------------------------------------------------------------
    for jc in judgment_candidates:
        topic = jc.get('topic', '')
        if not topic:
            continue

        independent_count = int(jc.get('independent_evidence_count', 0))
        mainstream_count = int(jc.get('mainstream_or_better_count', 0))
        articles = jc.get('articles', [])
        article_ids = [a.get('id') for a in articles if a.get('id') is not None]

        dates = _collect_evidence_dates_from_candidate_articles(articles)
        fresh = _is_evidence_fresh(dates, ref_date)

        # 冲突检测
        has_conflict, conflict_detail = _detect_topic_conflict(
            topic, articles, selected_articles,
        )

        # 判定状态
        if has_conflict:
            status = CROSS_STATUS_CONFLICTED
        elif (
            independent_count >= MIN_TOPIC_INDEPENDENT_SOURCES
            and mainstream_count >= MIN_TOPIC_MAINSTREAM_OR_BETTER
            and fresh
        ):
            status = CROSS_STATUS_CONFIRMED
        else:
            status = CROSS_STATUS_WEAK

        topic_checks.append(TopicCrossCheck(
            topic=topic,
            status=status,
            evidence_article_ids=article_ids,
            independent_source_count=independent_count,
            mainstream_or_better_count=mainstream_count,
            has_fresh_evidence=fresh,
            conflict_detail=conflict_detail,
        ))

    # ------------------------------------------------------------------
    # 标的交叉验真
    # ------------------------------------------------------------------
    for rec in stock_recommendations:
        symbol = rec.get('symbol', '')
        name = rec.get('name', '')
        if not symbol:
            continue

        cs = stock_map.get(symbol)
        if cs is None:
            stock_checks.append(StockCrossCheck(
                symbol=symbol,
                name=name,
                status=CROSS_STATUS_WEAK,
                source_type=rec.get('source_type', ''),
            ))
            warnings.append(f"{symbol} 在 candidate_stocks 中未找到，跳过交叉验真")
            continue

        direct_mentions = int(cs.direct_mentions or 0)
        independent_count = int(cs.independent_evidence_count or 0)
        source_type = cs.source_type or ''
        evidence_ids = list(cs.evidence_article_ids or [])
        evidence_dates = list(cs.evidence_published_dates or [])

        fresh = _is_evidence_fresh(evidence_dates, ref_date)

        # 冲突检测
        has_conflict, conflict_detail = _detect_stock_conflict(
            symbol, name, selected_articles,
        )

        # 判定状态
        is_theme_only = (source_type == 'theme_mapping' and direct_mentions < 1)

        if has_conflict:
            status = CROSS_STATUS_CONFLICTED
        elif is_theme_only:
            # theme-only 永不 confirmed
            status = CROSS_STATUS_WEAK
        elif (
            direct_mentions >= MIN_STOCK_DIRECT_MENTIONS
            and independent_count >= MIN_STOCK_INDEPENDENT_SOURCES
            and fresh
        ):
            status = CROSS_STATUS_CONFIRMED
        else:
            status = CROSS_STATUS_WEAK

        stock_checks.append(StockCrossCheck(
            symbol=symbol,
            name=name,
            status=status,
            evidence_article_ids=evidence_ids,
            direct_mentions=direct_mentions,
            independent_source_count=independent_count,
            has_fresh_evidence=fresh,
            source_type=source_type,
            conflict_detail=conflict_detail,
        ))

    # ------------------------------------------------------------------
    # 汇总统计
    # ------------------------------------------------------------------
    def _count(items: list, status: str) -> int:
        return sum(1 for item in items if item.status == status)

    summary = {
        'topics_confirmed': _count(topic_checks, CROSS_STATUS_CONFIRMED),
        'topics_weak': _count(topic_checks, CROSS_STATUS_WEAK),
        'topics_conflicted': _count(topic_checks, CROSS_STATUS_CONFLICTED),
        'stocks_confirmed': _count(stock_checks, CROSS_STATUS_CONFIRMED),
        'stocks_weak': _count(stock_checks, CROSS_STATUS_WEAK),
        'stocks_conflicted': _count(stock_checks, CROSS_STATUS_CONFLICTED),
    }

    return {
        'topic_checks': [tc.to_dict() for tc in topic_checks],
        'stock_checks': [sc.to_dict() for sc in stock_checks],
        'summary': summary,
        'issues': issues,
        'warnings': warnings,
    }


def build_cross_verification_summary(result: Dict[str, Any]) -> str:
    """构建交叉验真摘要文本，用于注入 prompt 约束。"""
    summary = result.get('summary', {})
    topic_checks = result.get('topic_checks', [])
    stock_checks = result.get('stock_checks', [])

    lines = [
        "=== 交叉验真摘要 ===",
        f"- 主题: {summary.get('topics_confirmed', 0)} confirmed, "
        f"{summary.get('topics_weak', 0)} weak, "
        f"{summary.get('topics_conflicted', 0)} conflicted",
        f"- 标的: {summary.get('stocks_confirmed', 0)} confirmed, "
        f"{summary.get('stocks_weak', 0)} weak, "
        f"{summary.get('stocks_conflicted', 0)} conflicted",
    ]

    conflicted_topics = [
        tc for tc in topic_checks
        if tc.get('status') == CROSS_STATUS_CONFLICTED
    ]
    if conflicted_topics:
        names = ', '.join(tc.get('topic', '') for tc in conflicted_topics[:3])
        lines.append(f"- 冲突主题: {names}")

    conflicted_stocks = [
        sc for sc in stock_checks
        if sc.get('status') == CROSS_STATUS_CONFLICTED
    ]
    if conflicted_stocks:
        names = ', '.join(sc.get('symbol', '') for sc in conflicted_stocks[:5])
        lines.append(f"- 冲突标的: {names}")

    return '\n'.join(lines)
