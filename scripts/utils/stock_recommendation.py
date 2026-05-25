#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股候选股与结构化推荐评分引擎

V1 目标：
1. 从新闻直接提及和主题映射中收敛候选股池
2. 获取行情/估值/行业等多维特征
3. 输出可解释、可降级的推荐评分结果
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

import requests


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRADE_CAP_REASONS = {
    'insufficient_evidence',
    'no_direct_stock_evidence',
    'theme_mapping_watch_only',
    'data_incomplete',
    'insufficient_history',
    'missing_valuation_baseline',
    'risk_flag_present',
    'score_gate_not_met',
}

ACTIONABILITY_REASONS = {
    'no_fresh_evidence',
    'insufficient_independent_confirmation',
    'theme_only_not_actionable',
    'stale_or_crowded',
    'grade_not_actionable',
}

TOPIC_MARKET_SCOPE = {
    '政策与监管': 'broad',
    '宏观与流动性': 'broad',
    '汇率与大宗': 'cyclical',
    '财报与公司经营': 'broad',
    '科技与产业主题': 'growth',
    '风险事件': 'defensive',
}

NEGATIVE_RISK_KEYWORDS = [
    # 中文（A股 + 美股通用）
    '立案', '停牌', '退市', '暴雷', '减持', '处罚', '问询', '亏损', '违约', '调查', '诉讼',
    '做空', '评级下调', '召回', '集体诉讼', '监管调查', '做空报告',
    # 英文（美股）
    'lawsuit', 'fraud', 'recall', 'downgrade', 'restatement',
    'short report', 'class action', 'SEC investigation', 'DOJ',
]

POSITIVE_CATALYST_KEYWORDS = [
    # 中文
    '订单', '回购', '分红', '中标', '产能', '扩产', '财报', '业绩', '增长', '新品', '合作',
    '超预期', '上调指引', 'FDA 批准', '突破',
    # 英文
    'beat estimates', 'guidance raise', 'upgrade', 'FDA approval',
]


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def percentile_rank(value: float, samples: List[float]) -> Optional[float]:
    clean = [item for item in samples if isinstance(item, (int, float)) and math.isfinite(item)]
    if not clean:
        return None
    lower = sum(1 for item in clean if item < value)
    equal = sum(1 for item in clean if item == value)
    return (lower + 0.5 * equal) / len(clean)


@dataclass
class CandidateStock:
    symbol: str
    name: str
    industry: str
    source_type: str
    topic: str
    evidence_article_ids: List[int]
    evidence_summaries: List[str]
    source_tiers: List[str]
    independent_evidence_count: int
    direct_mentions: int
    risk_flags: List[str]
    source_tier_max: str
    high_confidence_topic: bool = False
    theme_topics: List[str] | None = None
    evidence_published_dates: List[str] | None = None
    topic_article_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoryBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class SecurityMasterProvider:
    """证券主数据与候选股抽取"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (PROJECT_ROOT / 'config' / 'theme_stock_map.json')
        self.config = self._load_config()
        self.securities = self.config.get('securities', {})
        self.alias_map = self._build_alias_map(self.securities)
        self.topic_map = self.config.get('topic_stock_map', {})

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            logger.warning("候选股配置不存在: %s", self.config_path)
            return {'securities': {}, 'topic_stock_map': {}}
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _build_alias_map(securities: Dict[str, Any]) -> Dict[str, str]:
        alias_map: Dict[str, str] = {}
        for symbol, meta in securities.items():
            for alias in meta.get('aliases', []):
                alias_map[alias.lower()] = symbol
            alias_map[meta.get('name', '').lower()] = symbol
        return alias_map

    @staticmethod
    def normalize_symbol(value: str) -> Optional[str]:
        code = (value or '').strip().upper()
        if not code:
            return None
        # CN格式: SH600519 / SZ000858（存储用小写）
        if re.fullmatch(r'(SH|SZ)\d{6}', code):
            return code.lower()
        if re.fullmatch(r'6\d{5}', code):
            return f'sh{code}'
        if re.fullmatch(r'[03]\d{5}', code):
            return f'sz{code}'
        # US格式: 1-5个大写字母，可带.后缀（如 BRK.B）
        if re.fullmatch(r'[A-Z]{1,5}(\.[A-Z])?', code):
            return code
        return None

    def get_security(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.securities.get(symbol)

    def resolve_symbol_from_text(self, text: str) -> List[str]:
        found = set()
        lowered = (text or '').lower()
        # CN: 6位数字代码
        for raw in re.findall(r'\b(?:sh|sz)?\d{6}\b', lowered):
            symbol = self.normalize_symbol(raw)
            if symbol and symbol in self.securities:
                found.add(symbol)
        # US: $TICKER 格式或大写ticker
        for raw in re.findall(r'\$?([A-Z]{1,5})\b', text or ''):
            symbol = self.normalize_symbol(raw)
            if symbol and symbol in self.securities:
                found.add(symbol)
        # 别名匹配（中英文名称）
        for alias, symbol in self.alias_map.items():
            if alias and alias in lowered:
                found.add(symbol)
        return sorted(found)

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        return [item.strip() for item in re.split(r'[。！？；\n]+', text or '') if item.strip()]

    @staticmethod
    def _sentence_mentions_security(sentence: str, symbol: str, name: str) -> bool:
        lowered = (sentence or '').lower()
        # CN symbol: 提取尾部6位数字码（数字码不会误匹配其他词）
        if symbol.startswith(('sh', 'sz')) and len(symbol) >= 6:
            raw_code = symbol[-6:]
            return any(token for token in (name.lower(), symbol.lower(), raw_code) if token in lowered)
        # US ticker: 使用词边界避免短代码误匹配（如 BA 命中 Bank）
        import re as _re
        ticker_lower = symbol.lower()
        if _re.search(r'\b' + _re.escape(ticker_lower) + r'\b', lowered):
            return True
        name_lower = name.lower()
        if len(name_lower) >= 3 and _re.search(r'\b' + _re.escape(name_lower) + r'\b', lowered):
            return True
        return False

    def _extract_risk_flags_for_symbol(self, text: str, symbol: str, name: str) -> List[str]:
        matched: List[str] = []
        for sentence in self._split_sentences(text):
            if not self._sentence_mentions_security(sentence, symbol, name):
                continue
            for keyword in NEGATIVE_RISK_KEYWORDS:
                if keyword in sentence and keyword not in matched:
                    matched.append(keyword)
        return matched

    def build_candidates(
        self,
        *,
        articles: List[Dict[str, Any]],
        judgment_candidates: Optional[List[Dict[str, Any]]] = None,
        max_candidates: int = 10,
        max_theme_stocks: int = 3,
    ) -> List[CandidateStock]:
        direct_map: Dict[str, CandidateStock] = {}

        for article in articles:
            text = '\n'.join(
                str(article.get(key, '') or '')
                for key in ('title', 'summary', 'content')
            )
            symbols = self.resolve_symbol_from_text(text)
            if not symbols:
                continue

            source_tier = article.get('source_tier', 'mainstream')
            is_original = 1 if article.get('is_original_source') else 0
            for symbol in symbols:
                security = self.securities[symbol]
                risk_flags = self._extract_risk_flags_for_symbol(
                    text=text,
                    symbol=symbol,
                    name=security.get('name', symbol),
                )
                item = direct_map.get(symbol)
                if not item:
                    item = CandidateStock(
                        symbol=symbol,
                        name=security.get('name', symbol),
                        industry=security.get('industry', '未知行业'),
                        source_type='direct_news',
                        topic='新闻直接提及',
                        evidence_article_ids=[],
                        evidence_summaries=[],
                        source_tiers=[],
                        independent_evidence_count=0,
                        direct_mentions=0,
                        risk_flags=[],
                        source_tier_max=source_tier,
                        theme_topics=[],
                        evidence_published_dates=[],
                        topic_article_count=0,
                    )
                    direct_map[symbol] = item
                item.evidence_article_ids.append(int(article.get('id') or 0))
                item.evidence_summaries.append((article.get('title') or '')[:120])
                item.source_tiers.append(source_tier)
                item.direct_mentions += 1
                item.independent_evidence_count += is_original
                published = str(article.get('published') or article.get('collection_date') or '').strip()
                if published:
                    item.evidence_published_dates = (item.evidence_published_dates or []) + [published]
                if self._source_tier_rank(source_tier) > self._source_tier_rank(item.source_tier_max):
                    item.source_tier_max = source_tier
                for flag in risk_flags:
                    if flag not in item.risk_flags:
                        item.risk_flags.append(flag)

        ranked_direct = sorted(
            direct_map.values(),
            key=lambda item: (
                item.direct_mentions,
                item.independent_evidence_count,
                -len(item.risk_flags),
            ),
            reverse=True,
        )

        result = ranked_direct[:max_candidates]
        result_symbols = {item.symbol for item in result}

        if judgment_candidates:
            for candidate in judgment_candidates:
                topic = candidate.get('topic')
                if topic not in self.topic_map or not candidate.get('high_confidence_topic'):
                    continue
                for mapped_symbol in self.topic_map[topic][:max_theme_stocks]:
                    symbol = self.normalize_symbol(mapped_symbol)
                    if not symbol or symbol not in self.securities:
                        continue
                    if symbol in direct_map:
                        direct_item = direct_map[symbol]
                        if topic not in (direct_item.theme_topics or []):
                            direct_item.theme_topics = sorted((direct_item.theme_topics or []) + [topic])
                        direct_item.high_confidence_topic = (
                            direct_item.high_confidence_topic or bool(candidate.get('high_confidence_topic'))
                        )
                        continue
                    if symbol in result_symbols:
                        continue
                    security = self.securities[symbol]
                    source_tiers = [
                        article.get('source_tier', 'mainstream')
                        for article in candidate.get('articles', [])
                    ]
                    result.append(
                        CandidateStock(
                            symbol=symbol,
                            name=security.get('name', symbol),
                            industry=security.get('industry', '未知行业'),
                            source_type='theme_mapping',
                            topic=topic,
                            evidence_article_ids=[
                                int(item.get('id') or 0)
                                for item in candidate.get('articles', [])
                                if item.get('id') is not None
                            ],
                            evidence_summaries=[
                                (item.get('title') or '')[:120]
                                for item in candidate.get('articles', [])
                            ],
                            source_tiers=source_tiers,
                            independent_evidence_count=int(candidate.get('independent_evidence_count') or 0),
                            direct_mentions=0,
                            risk_flags=[],
                            source_tier_max=str(candidate.get('source_tier_max') or 'mainstream'),
                            high_confidence_topic=bool(candidate.get('high_confidence_topic')),
                            theme_topics=[topic],
                            evidence_published_dates=[
                                str(item.get('published') or item.get('collection_date') or '').strip()
                                for item in candidate.get('articles', [])
                                if str(item.get('published') or item.get('collection_date') or '').strip()
                            ],
                            topic_article_count=int(candidate.get('topic_article_count') or 0),
                        )
                    )
                    result_symbols.add(symbol)
                    if len(result) >= max_candidates:
                        return result

        return result[:max_candidates]

    @staticmethod
    def _source_tier_rank(tier: str) -> int:
        return {
            'aggregator': 1,
            'industry': 2,
            'mainstream': 3,
            'official': 4,
        }.get(tier, 0)


class PriceHistoryProvider:
    """历史行情与技术指标"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (PROJECT_ROOT / 'data' / 'market_cache' / 'price_history')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})

    @staticmethod
    def _to_yahoo_symbol(symbol: str) -> str:
        if symbol.startswith('sh') and len(symbol) == 8:
            return f'{symbol[2:]}.SS'
        if symbol.startswith('sz') and len(symbol) == 8:
            return f'{symbol[2:]}.SZ'
        return symbol

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f'{symbol}.json'

    def fetch_history(self, symbol: str, lookback_days: int = 180) -> List[HistoryBar]:
        cached = self._read_cache(symbol, max_age_hours=12)
        if cached:
            return cached

        yahoo_symbol = self._to_yahoo_symbol(symbol)
        url = (
            f'https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}'
            '?interval=1d&range=1y&includePrePost=false'
        )
        try:
            response = self.session.get(url, timeout=(3, 8))
            response.raise_for_status()
            payload = response.json()
            result = ((payload.get('chart') or {}).get('result') or [None])[0] or {}
            timestamps = result.get('timestamp') or []
            quote = (((result.get('indicators') or {}).get('quote') or [{}])[0]) or {}
            bars = []
            for idx, ts in enumerate(timestamps):
                close = self._value_at(quote.get('close'), idx)
                volume = self._value_at(quote.get('volume'), idx)
                if close is None or volume is None:
                    continue
                bars.append(
                    HistoryBar(
                        date=datetime.fromtimestamp(ts).strftime('%Y-%m-%d'),
                        open=self._value_at(quote.get('open'), idx) or close,
                        high=self._value_at(quote.get('high'), idx) or close,
                        low=self._value_at(quote.get('low'), idx) or close,
                        close=close,
                        volume=volume,
                    )
                )
            if bars:
                self._write_cache(symbol, bars)
            return bars[-lookback_days:]
        except Exception as exc:
            logger.warning("获取历史行情失败 %s: %s", symbol, exc)
            return cached or []

    def _read_cache(self, symbol: str, max_age_hours: int) -> List[HistoryBar]:
        path = self._cache_path(symbol)
        if not path.exists():
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            updated_at = datetime.fromisoformat(payload['updated_at'])
            if datetime.now() - updated_at > timedelta(hours=max_age_hours):
                return []
            return [HistoryBar(**item) for item in payload.get('bars', [])]
        except Exception:
            return []

    def _write_cache(self, symbol: str, bars: List[HistoryBar]) -> None:
        path = self._cache_path(symbol)
        payload = {
            'updated_at': datetime.now().isoformat(),
            'bars': [asdict(item) for item in bars[-250:]],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _value_at(values: Optional[List[Any]], index: int) -> Optional[float]:
        if not values or index >= len(values) or values[index] is None:
            return None
        try:
            return float(values[index])
        except Exception:
            return None

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _ema_series(values: List[float], period: int) -> List[float]:
        if not values:
            return []
        k = 2 / (period + 1)
        result = [values[0]]
        for value in values[1:]:
            result.append(value * k + result[-1] * (1 - k))
        return result

    @classmethod
    def compute_indicators(cls, bars: List[HistoryBar]) -> Dict[str, Optional[float]]:
        closes = [item.close for item in bars]
        volumes = [item.volume for item in bars]
        if len(closes) < 20:
            return {
                'ma20': None,
                'ma60': None,
                'rsi14': None,
                'macd': None,
                'macd_signal': None,
                'boll_mid': None,
                'boll_upper': None,
                'boll_lower': None,
                'volume_ratio_5_20': None,
                'momentum_20d': None,
            }

        ma20 = cls._sma(closes, 20)
        ma60 = cls._sma(closes, 60)
        momentum_20d = ((closes[-1] / closes[-20]) - 1) * 100 if len(closes) >= 20 and closes[-20] else None
        volume_ratio_5_20 = None
        if len(volumes) >= 20:
            avg5 = sum(volumes[-5:]) / 5
            avg20 = sum(volumes[-20:]) / 20
            volume_ratio_5_20 = avg5 / avg20 if avg20 else None

        # RSI14
        rsi14 = None
        if len(closes) >= 15:
            gains = []
            losses = []
            for prev, curr in zip(closes[-15:-1], closes[-14:]):
                delta = curr - prev
                gains.append(max(delta, 0))
                losses.append(abs(min(delta, 0)))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss == 0:
                rsi14 = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi14 = 100 - (100 / (1 + rs))

        ema12 = cls._ema_series(closes, 12)
        ema26 = cls._ema_series(closes, 26)
        macd_series = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
        macd_signal_series = cls._ema_series(macd_series, 9) if macd_series else []
        macd = macd_series[-1] if macd_series else None
        macd_signal = macd_signal_series[-1] if macd_signal_series else None

        boll_mid = ma20
        if len(closes) >= 20 and boll_mid is not None:
            sample = closes[-20:]
            variance = sum((item - boll_mid) ** 2 for item in sample) / len(sample)
            std = math.sqrt(variance)
            boll_upper = boll_mid + 2 * std
            boll_lower = boll_mid - 2 * std
        else:
            boll_upper = None
            boll_lower = None

        return {
            'ma20': ma20,
            'ma60': ma60,
            'rsi14': rsi14,
            'macd': macd,
            'macd_signal': macd_signal,
            'boll_mid': boll_mid,
            'boll_upper': boll_upper,
            'boll_lower': boll_lower,
            'volume_ratio_5_20': volume_ratio_5_20,
            'momentum_20d': momentum_20d,
        }

    def fetch_market_regime(self, market: str = 'CN') -> Dict[str, Any]:
        if market == 'US':
            index_symbols = {
                '^GSPC': 'S&P 500',
                '^IXIC': 'NASDAQ',
                '^DJI': 'Dow Jones',
            }
        else:
            index_symbols = {
                'sh000001': '上证指数',
                'sz399001': '深证成指',
            }
        indices = {sym: self.fetch_history(sym) for sym in index_symbols}
        trends = {}
        style_bias = 'balanced'
        for symbol, bars in indices.items():
            metrics = self.compute_indicators(bars)
            close = bars[-1].close if bars else None
            ma20 = metrics.get('ma20')
            ma60 = metrics.get('ma60')
            bullish = bool(close and ma20 and ma60 and close > ma20 > ma60)
            trends[symbol] = {
                'close': close,
                'ma20': ma20,
                'ma60': ma60,
                'bullish': bullish,
            }
        if market == 'US':
            if trends.get('^IXIC', {}).get('bullish'):
                style_bias = 'growth'
            elif trends.get('^GSPC', {}).get('bullish'):
                style_bias = 'value'
        else:
            if trends.get('sz399001', {}).get('bullish'):
                style_bias = 'growth'
            elif trends.get('sh000001', {}).get('bullish'):
                style_bias = 'value'
        risk_on = sum(1 for item in trends.values() if item.get('bullish')) >= 1
        return {
            'indices': trends,
            'style_bias': style_bias,
            'risk_on': risk_on,
        }


class ValuationProvider:
    """估值快照与行业基准"""

    def __init__(self, security_master: SecurityMasterProvider, cache_dir: Optional[Path] = None):
        self.security_master = security_master
        self.cache_dir = cache_dir or (PROJECT_ROOT / 'data' / 'market_cache' / 'valuation')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.cache_dir / 'valuation_snapshot.json'

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        payload = self._load_snapshot()
        item = payload.get(symbol)
        if item:
            return item
        security = self.security_master.get_security(symbol) or {}
        return {
            'symbol': symbol,
            'pe_ttm': None,
            'pb_lf': None,
            'industry': security.get('industry', '未知行业'),
            'profitability': security.get('profitability', 'unknown'),
            'company_type': security.get('company_type', 'general'),
            'pe_history': [],
            'pb_history': [],
        }

    def _load_snapshot(self) -> Dict[str, Any]:
        if not self.snapshot_path.exists():
            return {}
        try:
            with open(self.snapshot_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('symbols', {})
        except Exception:
            return {}

    def get_industry_stats(self, industry: str, symbol_snapshots: Iterable[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        same_industry = [item for item in symbol_snapshots if item.get('industry') == industry]
        pe_values = [item.get('pe_ttm') for item in same_industry if isinstance(item.get('pe_ttm'), (int, float))]
        pb_values = [item.get('pb_lf') for item in same_industry if isinstance(item.get('pb_lf'), (int, float))]
        return {
            'industry_pe_median': median(pe_values) if pe_values else None,
            'industry_pb_median': median(pb_values) if pb_values else None,
        }


class RecommendationScorer:
    """结构化推荐评分器"""

    def __init__(
        self,
        *,
        security_master: SecurityMasterProvider,
        price_history_provider: PriceHistoryProvider,
        valuation_provider: ValuationProvider,
        lookback_days: int = 60,
        style: str = 'balanced',
        as_of_date: Optional[str] = None,
        enhanced_context_root: Optional[Path] = None,
        recent_context_days: int = 5,
        market: str = 'CN',
    ):
        self.security_master = security_master
        self.price_history_provider = price_history_provider
        self.valuation_provider = valuation_provider
        self.lookback_days = lookback_days
        self.style = style
        self.as_of_date = self._resolve_as_of_date(as_of_date)
        self.enhanced_context_root = enhanced_context_root or (PROJECT_ROOT / 'docs' / 'archive')
        self.recent_context_days = recent_context_days
        self.market = market
        self.industry_trend_snapshot = self._load_industry_trend_snapshot()
        self.recent_contexts = self._load_recent_enhanced_contexts()
        self.symbol_recent_direct_days = self._build_symbol_recent_direct_days(self.recent_contexts)
        self.topic_recent_daily_counts = self._build_topic_recent_daily_counts(self.recent_contexts)

    def score_candidates(self, candidates: List[CandidateStock]) -> Dict[str, Any]:
        market_regime = self.price_history_provider.fetch_market_regime(market=self.market)
        snapshots = [self.valuation_provider.get_snapshot(item.symbol) for item in candidates]

        recommendations = []
        for candidate, snapshot in zip(candidates, snapshots):
            bars = self.price_history_provider.fetch_history(candidate.symbol, lookback_days=max(self.lookback_days, 90))
            indicators = self.price_history_provider.compute_indicators(bars)
            industry_stats = self.valuation_provider.get_industry_stats(candidate.industry, snapshots)
            recommendations.append(
                self._score_single_candidate(
                    candidate,
                    snapshot=snapshot,
                    bars=bars,
                    indicators=indicators,
                    industry_stats=industry_stats,
                    market_regime=market_regime,
                )
            )

        recommendations.sort(key=lambda item: item['total_score'], reverse=True)
        distribution = {
            'strong_focus': sum(1 for item in recommendations if item['grade'] == '强关注'),
            'focus': sum(1 for item in recommendations if item['grade'] == '关注'),
            'watch': sum(1 for item in recommendations if item['grade'] == '观察'),
            'avoid': sum(1 for item in recommendations if item['grade'] == '回避'),
        }
        actionable_candidates = [item for item in recommendations if item.get('actionability_passed')]
        actionable_symbols = {item['symbol'] for item in actionable_candidates}
        stale_or_rejected = [
            item for item in recommendations
            if item['grade'] == '回避'
            or item['stale_opportunity_flag']
            or item['crowding_flag']
        ]
        stale_or_rejected_symbols = {item['symbol'] for item in stale_or_rejected}
        decision_views = {
            'actionable_candidates': actionable_candidates,
            'conditional_watchlist': [
                item for item in recommendations
                if item['symbol'] not in actionable_symbols
                and item['symbol'] not in stale_or_rejected_symbols
                and item['grade'] != '回避'
            ],
            'stale_or_rejected': stale_or_rejected,
        }
        return {
            'recommendations': recommendations,
            'score_distribution': distribution,
            'decision_views': decision_views,
            'scoring_config': {
                'market': self.market,
                'style': self.style,
                'lookback_days': self.lookback_days,
                'pool_mode': 'strict',
                'theme_mapping_max_grade': 'watch',
                'value_acceptance_enabled': True,
                'industry_trend_enabled': True,
            },
        }

    def _score_single_candidate(
        self,
        candidate: CandidateStock,
        *,
        snapshot: Dict[str, Any],
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
        industry_stats: Dict[str, Optional[float]],
        market_regime: Dict[str, Any],
    ) -> Dict[str, Any]:
        news_score = self._score_news(candidate)
        technical_score = self._score_technical(bars, indicators)
        valuation_score, valuation_flags, has_valuation_baseline = self._score_valuation(
            candidate, snapshot, industry_stats
        )
        risk_score, risk_flags = self._score_risk(candidate, bars, indicators, snapshot)
        industry_trend = self._get_industry_trend(candidate.industry)
        regime_score, regime_flags = self._score_market_regime(
            candidate, bars, indicators, market_regime, industry_trend
        )

        completeness_weights = {
            'evidence': 0.25,
            'history': 0.40,
            'valuation': 0.25,
            'industry': 0.10,
        }
        data_completeness = round(
            (completeness_weights['evidence'] if candidate.evidence_article_ids else 0.0)
            + (completeness_weights['history'] if len(bars) >= self.lookback_days else 0.0)
            + (completeness_weights['valuation'] if has_valuation_baseline else 0.12)
            + (completeness_weights['industry'] if snapshot.get('industry') else 0.05),
            2,
        )

        scores = {
            'news_catalyst': news_score,
            'technical': technical_score,
            'valuation': valuation_score,
            'quality_risk': risk_score,
            'market_regime': regime_score,
        }
        total_score = sum(scores.values())
        if len(bars) < self.lookback_days:
            technical_score = 0
            scores['technical'] = 0
            total_score = sum(scores.values())

        base_grade = self._grade_for_score(total_score)
        grade = base_grade
        grade_caps: List[str] = []
        stale_opportunity_flag = self._is_stale_opportunity(candidate, bars, indicators)
        crowding_flag = self._is_crowded_opportunity(candidate, bars, indicators)
        fresh_evidence_flag = self._has_fresh_evidence(candidate)

        if len(bars) < self.lookback_days:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('insufficient_history')
        if not has_valuation_baseline:
            grade = self._cap_grade(grade, '关注')
            grade_caps.append('missing_valuation_baseline')
        if candidate.risk_flags:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('risk_flag_present')
        if data_completeness < 0.7:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('data_incomplete')
        elif data_completeness < 0.85 and base_grade == '强关注':
            grade = self._cap_grade(grade, '关注')
            grade_caps.append('data_incomplete')
        if not candidate.evidence_article_ids:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('insufficient_evidence')
        if news_score < 15:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('score_gate_not_met')
        if base_grade in {'关注', '强关注'} and candidate.direct_mentions < 1:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('no_direct_stock_evidence')
        # Theme-only candidates stay capped at watch. If the stock is also directly
        # mentioned, it is merged into a direct candidate earlier and can compete
        # under the direct-evidence rules instead of using an unreachable branch here.
        if candidate.source_type == 'theme_mapping' and candidate.direct_mentions < 1:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('theme_mapping_watch_only')
        if stale_opportunity_flag and base_grade == '强关注':
            grade = self._cap_grade(grade, '关注')
            grade_caps.append('score_gate_not_met')
        if crowding_flag:
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('score_gate_not_met')

        if not self._meets_grade_gate(
            grade=grade,
            total_score=total_score,
            news_score=news_score,
            risk_score=risk_score,
            data_completeness=data_completeness,
            candidate=candidate,
        ):
            grade = self._cap_grade(grade, '观察')
            grade_caps.append('score_gate_not_met')

        grade_caps = sorted({item for item in grade_caps if item in GRADE_CAP_REASONS})
        if grade == base_grade:
            grade_caps = []

        signals = self._build_signals(candidate, bars, indicators, snapshot, market_regime)
        risks = list(dict.fromkeys(candidate.risk_flags + risk_flags + valuation_flags + regime_flags))
        invalidators = self._build_invalidators(candidate, indicators, snapshot, grade_caps)
        candidate_confidence = self._candidate_confidence(candidate)
        actionability_reasons = self._build_actionability_reasons(
            candidate=candidate,
            grade=grade,
            stale_opportunity_flag=stale_opportunity_flag,
            crowding_flag=crowding_flag,
            fresh_evidence_flag=fresh_evidence_flag,
        )
        actionability_passed = not actionability_reasons

        return {
            'symbol': candidate.symbol,
            'name': candidate.name,
            'industry': candidate.industry,
            'candidate_confidence': candidate_confidence,
            'base_grade': base_grade,
            'grade': grade,
            'grade_caps': grade_caps,
            'total_score': total_score,
            'scores': scores,
            'signals': signals,
            'risks': risks,
            'invalidators': invalidators,
            'evidence_article_ids': candidate.evidence_article_ids,
            'evidence_summaries': candidate.evidence_summaries,
            'data_completeness': data_completeness,
            'source_type': candidate.source_type,
            'topic': candidate.topic,
            'theme_topics': candidate.theme_topics or [],
            'stale_opportunity_flag': stale_opportunity_flag,
            'crowding_flag': crowding_flag,
            'fresh_evidence_flag': fresh_evidence_flag,
            'actionability_passed': actionability_passed,
            'actionability_reasons': actionability_reasons,
            'forward_window': '1-4周',
            'catalyst_path': self._build_catalyst_path(candidate, fresh_evidence_flag),
            'validation_points': self._build_validation_points(candidate, indicators, stale_opportunity_flag),
            'failure_triggers': invalidators,
            'evidence_strength': {
                'direct_mentions': candidate.direct_mentions,
                'independent_evidence_count': candidate.independent_evidence_count,
                'source_tier_max': candidate.source_tier_max,
            },
            'industry_trend': industry_trend,
        }

    @staticmethod
    def _build_actionability_reasons(
        *,
        candidate: CandidateStock,
        grade: str,
        stale_opportunity_flag: bool,
        crowding_flag: bool,
        fresh_evidence_flag: bool,
    ) -> List[str]:
        reasons: List[str] = []
        if grade not in {'关注', '强关注'}:
            reasons.append('grade_not_actionable')
        if not fresh_evidence_flag:
            reasons.append('no_fresh_evidence')
        if stale_opportunity_flag or crowding_flag:
            reasons.append('stale_or_crowded')
        independent_count = int(candidate.independent_evidence_count or 0)
        direct_mentions = int(candidate.direct_mentions or 0)
        if independent_count < 2 and not (direct_mentions >= 1 and independent_count >= 1):
            reasons.append('insufficient_independent_confirmation')
        if candidate.source_type == 'theme_mapping' and direct_mentions < 1:
            reasons.append('theme_only_not_actionable')
        return [item for item in reasons if item in ACTIONABILITY_REASONS]

    @staticmethod
    def _parse_date(value: str) -> Optional[datetime]:
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

    def _resolve_as_of_date(self, value: Optional[str]) -> datetime:
        parsed = self._parse_date(value or '')
        if parsed is not None:
            return parsed
        return datetime.now()

    def _load_recent_enhanced_contexts(self) -> List[Dict[str, Any]]:
        contexts: List[Dict[str, Any]] = []
        for days_ago in range(1, self.recent_context_days + 1):
            day = (self.as_of_date - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            metadata_dir = self.enhanced_context_root / day[:7] / day / 'metadata'
            if not metadata_dir.exists():
                continue
            for path in sorted(metadata_dir.glob('*enhanced-context*.json')):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        payload = json.load(f)
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning('Failed to load enhanced context %s: %s', path, exc)
                    continue
                payload['_archive_date'] = day
                contexts.append(payload)
        return contexts

    @staticmethod
    def _build_symbol_recent_direct_days(contexts: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        result: Dict[str, set[str]] = {}
        for payload in contexts:
            archive_date = str(payload.get('_archive_date') or '')
            for item in payload.get('candidate_stocks') or []:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get('symbol') or '').strip()
                direct_mentions = int(item.get('direct_mentions') or 0)
                if not symbol or direct_mentions < 1 or not archive_date:
                    continue
                result.setdefault(symbol, set()).add(archive_date)
        return {symbol: sorted(days) for symbol, days in result.items()}

    @staticmethod
    def _build_topic_recent_daily_counts(contexts: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        seen_article_keys: Dict[str, set[tuple[str, str, str, str]]] = {}
        for payload in contexts:
            archive_date = str(payload.get('_archive_date') or '')
            for article in payload.get('selected_articles') or []:
                if not isinstance(article, dict):
                    continue
                topic = str(article.get('primary_topic') or '').strip()
                if not topic or not archive_date:
                    continue
                article_key = (
                    str(article.get('id') or ''),
                    str(article.get('title') or ''),
                    str(article.get('source') or ''),
                    str(article.get('published') or article.get('collection_date') or ''),
                )
                day_seen = seen_article_keys.setdefault(archive_date, set())
                if article_key in day_seen:
                    continue
                day_seen.add(article_key)
                result.setdefault(topic, {})
                result[topic][archive_date] = result[topic].get(archive_date, 0) + 1
        return result

    def _has_fresh_evidence(self, candidate: CandidateStock) -> bool:
        if candidate.direct_mentions < 1:
            return False
        if self.symbol_recent_direct_days.get(candidate.symbol):
            return False
        evidence_dates = [
            self._parse_date(item)
            for item in (candidate.evidence_published_dates or [])
        ]
        evidence_dates = [item for item in evidence_dates if item is not None]
        if not evidence_dates:
            return candidate.direct_mentions >= 1 and candidate.independent_evidence_count >= 1
        latest = max(evidence_dates)
        earliest = min(evidence_dates)
        if (self.as_of_date.date() - latest.date()).days > 2:
            return False
        return (latest - earliest).days <= 3

    def _evidence_decay_weights(self, candidate: CandidateStock) -> List[float]:
        weights: List[float] = []
        for published in candidate.evidence_published_dates or []:
            parsed = self._parse_date(published)
            if parsed is None:
                continue
            days_old = max((self.as_of_date.date() - parsed.date()).days, 0)
            weights.append(max(0.0, 1.0 - (days_old / 7.0)))
        return weights

    def _is_stale_opportunity(
        self,
        candidate: CandidateStock,
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
    ) -> bool:
        if candidate.direct_mentions < 1 or len(bars) < 20:
            return False
        momentum = indicators.get('momentum_20d') or 0
        rsi14 = indicators.get('rsi14') or 0
        volume_ratio = indicators.get('volume_ratio_5_20') or 0
        return bool(momentum >= 25 and rsi14 >= 72 and volume_ratio >= 1.2)

    def _is_crowded_opportunity(
        self,
        candidate: CandidateStock,
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
    ) -> bool:
        momentum = indicators.get('momentum_20d') or 0
        rsi14 = indicators.get('rsi14') or 0
        volume_ratio = indicators.get('volume_ratio_5_20') or 0
        prior_daily_counts = self.topic_recent_daily_counts.get(candidate.topic, {})
        prior_active_days = sum(1 for count in prior_daily_counts.values() if count > 0)
        prior_average = (
            sum(prior_daily_counts.values()) / len(prior_daily_counts)
            if prior_daily_counts else 0.0
        )
        return bool(
            candidate.topic_article_count >= 4
            and len(bars) >= 20
            and (
                (prior_active_days >= 2 and prior_average >= 2)
                or momentum >= 18
                or rsi14 >= 75
                or volume_ratio >= 2.2
            )
        )

    @staticmethod
    def _build_catalyst_path(candidate: CandidateStock, fresh_evidence_flag: bool) -> List[str]:
        items = []
        if candidate.source_type == 'direct_news':
            items.append('跟踪个股级直接催化是否继续被主流来源确认')
        else:
            items.append(f'跟踪“{candidate.topic}”主题是否从主题扩散走向个股兑现')
        if fresh_evidence_flag:
            items.append('观察新增证据能否在未来 1-4 周继续扩散并转化为业绩/订单/政策兑现')
        else:
            items.append('若后续缺少新增个股证据，需警惕题材已被交易完成')
        return items[:2]

    @staticmethod
    def _build_validation_points(
        candidate: CandidateStock,
        indicators: Dict[str, Optional[float]],
        stale_opportunity_flag: bool,
    ) -> List[str]:
        items = []
        if candidate.direct_mentions >= 1:
            items.append('确认后续是否出现第二条独立个股证据或进一步官方/主流跟进')
        else:
            items.append('等待主题催化转化为个股级新增证据')
        if indicators.get('ma20') is not None:
            items.append('观察价格是否继续站稳 20 日均线并维持健康量能')
        if stale_opportunity_flag:
            items.append('若短线继续放量冲高且无新增证据，应下调为后手交易机会')
        return items[:3]

    def _score_news(self, candidate: CandidateStock) -> int:
        source_rank = {
            'aggregator': 1,
            'industry': 2,
            'mainstream': 3,
            'official': 4,
        }
        best_source = max((source_rank.get(item, 2) for item in candidate.source_tiers), default=1)
        direct_bonus = 8 if candidate.source_type == 'direct_news' else 3
        decay_weights = self._evidence_decay_weights(candidate)
        if decay_weights:
            evidence_bonus = min(sum(weight * 4 for weight in decay_weights), 12)
        else:
            evidence_bonus = min(candidate.independent_evidence_count * 4, 12)
        mention_bonus = min(candidate.direct_mentions * 2, 6)
        topic_bonus = 4 if candidate.topic in {'财报与公司经营', '政策与监管'} else 2
        score = direct_bonus + evidence_bonus + mention_bonus + topic_bonus + best_source
        return int(clamp(score, 0, 30))

    def _score_technical(self, bars: List[HistoryBar], indicators: Dict[str, Optional[float]]) -> int:
        if len(bars) < self.lookback_days:
            return 0
        close = bars[-1].close
        score = 8
        ma20 = indicators.get('ma20')
        ma60 = indicators.get('ma60')
        rsi14 = indicators.get('rsi14')
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        boll_upper = indicators.get('boll_upper')
        boll_mid = indicators.get('boll_mid')
        volume_ratio = indicators.get('volume_ratio_5_20')
        momentum = indicators.get('momentum_20d')

        if ma20 and ma60 and close > ma20 > ma60:
            score += 7
        elif ma20 and close > ma20:
            score += 4
        if momentum is not None:
            if 5 <= momentum <= 25:
                score += 4
            elif momentum > 25:
                score += 2
            elif momentum < -8:
                score -= 3
        if rsi14 is not None:
            if 45 <= rsi14 <= 68:
                score += 3
            elif rsi14 > 78:
                score -= 2
            elif rsi14 < 30:
                score -= 1
        if macd is not None and macd_signal is not None and macd > macd_signal:
            score += 2
        if volume_ratio is not None:
            if 1.0 <= volume_ratio <= 1.8:
                score += 2
            elif volume_ratio > 2.5:
                score -= 1
        if boll_upper and boll_mid:
            if close > boll_upper:
                score -= 2
            elif close >= boll_mid:
                score += 1
        return int(clamp(score, 0, 25))

    def _score_valuation(
        self,
        candidate: CandidateStock,
        snapshot: Dict[str, Any],
        industry_stats: Dict[str, Optional[float]],
    ) -> tuple[int, List[str], bool]:
        pe = snapshot.get('pe_ttm')
        pb = snapshot.get('pb_lf')
        company_type = snapshot.get('company_type', 'general')
        profitability = snapshot.get('profitability', 'unknown')
        flags: List[str] = []

        pe_hist = snapshot.get('pe_history') or []
        pb_hist = snapshot.get('pb_history') or []
        pe_pct = percentile_rank(pe, pe_hist) if isinstance(pe, (int, float)) else None
        pb_pct = percentile_rank(pb, pb_hist) if isinstance(pb, (int, float)) else None

        has_valuation_baseline = any(
            value is not None
            for value in (
                pe_pct,
                pb_pct,
                industry_stats.get('industry_pe_median'),
                industry_stats.get('industry_pb_median'),
            )
        )

        if not has_valuation_baseline:
            flags.append('估值基准不足，按中性处理')
            return 10, flags, False

        score = 10
        if company_type == 'financial':
            if isinstance(pb, (int, float)) and industry_stats.get('industry_pb_median'):
                if pb <= industry_stats['industry_pb_median'] * 0.9:
                    score += 5
                elif pb >= industry_stats['industry_pb_median'] * 1.2:
                    score -= 3
        elif company_type == 'cyclical':
            if pb_pct is not None:
                score += 4 if pb_pct <= 0.35 else -2 if pb_pct >= 0.75 else 1
            if isinstance(pe, (int, float)) and pe < 0:
                flags.append('周期股盈利波动较大，PE参考意义有限')
        else:
            if profitability == 'loss_making':
                score = 8
                flags.append('亏损成长股，PE 不纳入主评分')
            else:
                if pe_pct is not None:
                    score += 4 if pe_pct <= 0.35 else -3 if pe_pct >= 0.75 else 1
                if pb_pct is not None:
                    score += 3 if pb_pct <= 0.4 else -2 if pb_pct >= 0.8 else 1
                pe_median = industry_stats.get('industry_pe_median')
                if isinstance(pe, (int, float)) and isinstance(pe_median, (int, float)):
                    if pe <= pe_median * 0.9:
                        score += 2
                    elif pe >= pe_median * 1.25:
                        score -= 2

        if score >= 16:
            flags.append('估值处于相对合理或偏低区间')
        elif score <= 8:
            flags.append('估值性价比较弱或高估值压力较大')
        return int(clamp(score, 0, 20)), flags, True

    def _score_risk(
        self,
        candidate: CandidateStock,
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
        snapshot: Dict[str, Any],
    ) -> tuple[int, List[str]]:
        score = 12
        flags = []
        if candidate.risk_flags:
            score -= min(len(candidate.risk_flags) * 3, 8)
            flags.extend([f'新闻风险信号: {item}' for item in candidate.risk_flags[:3]])

        if snapshot.get('profitability') == 'loss_making':
            score -= 3
            flags.append('盈利质量偏弱')

        if len(bars) >= 20:
            closes = [item.close for item in bars[-20:]]
            avg = sum(closes) / len(closes)
            variance = sum((item - avg) ** 2 for item in closes) / len(closes)
            volatility = math.sqrt(variance) / avg if avg else 0
            if volatility > 0.12:
                score -= 2
                flags.append('短期波动偏高')

        volume_ratio = indicators.get('volume_ratio_5_20')
        if volume_ratio and volume_ratio > 3:
            score -= 1
            flags.append('短期换手放大，需要警惕情绪化波动')

        return int(clamp(score, 0, 15)), flags

    def _score_market_regime(
        self,
        candidate: CandidateStock,
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
        market_regime: Dict[str, Any],
        industry_trend: Dict[str, Any],
    ) -> tuple[int, List[str]]:
        score = 5
        flags = []
        style_bias = market_regime.get('style_bias', 'balanced')
        risk_on = market_regime.get('risk_on', False)
        topic_style = TOPIC_MARKET_SCOPE.get(candidate.topic, 'broad')

        if risk_on:
            score += 2
        else:
            score -= 1
            flags.append('大盘风险偏好一般')

        if style_bias == 'growth' and topic_style == 'growth':
            score += 2
        elif style_bias == 'value' and topic_style == 'cyclical':
            score += 1
        elif style_bias == 'growth' and topic_style == 'defensive':
            score -= 1

        if bars:
            close = bars[-1].close
            ma20 = indicators.get('ma20')
            if ma20 and close < ma20:
                score -= 1

        trend_score = float(industry_trend.get('score') or 0)
        score += int(clamp(trend_score, -2, 2))
        status = industry_trend.get('status')
        if status == 'missing':
            flags.append('行业趋势缺失，按中性环境处理')

        return int(clamp(score, 0, 10)), flags

    def _get_industry_trend(self, industry: str) -> Dict[str, Any]:
        entry = self.industry_trend_snapshot.get(industry)
        if not entry:
            return {
                'status': 'missing',
                'direction': 'flat',
                'score': 0,
                'as_of': None,
                'source': 'local_snapshot',
            }
        return {
            'status': 'available',
            'direction': entry.get('trend_direction', 'flat'),
            'score': entry.get('trend_score', 0),
            'as_of': entry.get('as_of'),
            'source': entry.get('source', 'local_snapshot'),
        }

    @staticmethod
    def _load_industry_trend_snapshot() -> Dict[str, Dict[str, Any]]:
        path = PROJECT_ROOT / 'data' / 'market_cache' / 'industry_trend_snapshot.json'
        if not path.exists():
            logger.warning('Industry trend snapshot missing: %s', path)
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning('Failed to load industry trend snapshot %s: %s', path, exc)
            return {}
        if isinstance(payload, dict):
            items = payload.get('industries')
            if isinstance(items, list):
                result = {
                    str(item.get('industry')): item
                    for item in items
                    if isinstance(item, dict) and item.get('industry')
                }
                if len(result) < 8:
                    logger.warning(
                        'Industry trend snapshot coverage is low: %s industries loaded from %s',
                        len(result),
                        path,
                    )
                return result
        if isinstance(payload, list):
            result = {
                str(item.get('industry')): item
                for item in payload
                if isinstance(item, dict) and item.get('industry')
            }
            if len(result) < 8:
                logger.warning(
                    'Industry trend snapshot coverage is low: %s industries loaded from %s',
                    len(result),
                    path,
                )
            return result
        logger.warning('Industry trend snapshot has unexpected structure: %s', path)
        return {}

    def _meets_grade_gate(
        self,
        *,
        grade: str,
        total_score: int,
        news_score: int,
        risk_score: int,
        data_completeness: float,
        candidate: CandidateStock,
    ) -> bool:
        if grade == '强关注':
            return (
                total_score >= 80
                and news_score >= 20
                and risk_score >= 10
                and data_completeness >= 0.85
                and candidate.direct_mentions >= 1
                and candidate.source_type != 'theme_mapping'
                and not candidate.risk_flags
            )
        if grade == '关注':
            return (
                total_score >= 65
                and news_score >= 15
                and data_completeness >= 0.70
                and bool(candidate.evidence_article_ids)
            )
        return True

    @staticmethod
    def _candidate_confidence(candidate: CandidateStock) -> str:
        if candidate.direct_mentions >= 1 and candidate.independent_evidence_count >= 2:
            return 'high'
        if candidate.high_confidence_topic or candidate.independent_evidence_count >= 1:
            return 'medium'
        return 'low'

    @staticmethod
    def _grade_for_score(score: int) -> str:
        if score >= 80:
            return '强关注'
        if score >= 65:
            return '关注'
        if score >= 50:
            return '观察'
        return '回避'

    @staticmethod
    def _cap_grade(current: str, cap: str) -> str:
        order = ['回避', '观察', '关注', '强关注']
        return order[min(order.index(current), order.index(cap))]

    def _build_signals(
        self,
        candidate: CandidateStock,
        bars: List[HistoryBar],
        indicators: Dict[str, Optional[float]],
        snapshot: Dict[str, Any],
        market_regime: Dict[str, Any],
    ) -> List[str]:
        signals = []
        if candidate.source_type == 'direct_news':
            signals.append('新闻直接提及个股，催化关联度较高')
        else:
            signals.append(f'来自“{candidate.topic}”主题映射，适合作为代表标的跟踪')
        if indicators.get('ma20') and indicators.get('ma60') and bars:
            if bars[-1].close > indicators['ma20'] > indicators['ma60']:
                signals.append('近20日与60日均线呈多头排列')
        rsi14 = indicators.get('rsi14')
        if rsi14 is not None:
            if 45 <= rsi14 <= 68:
                signals.append('RSI 处于健康区间，趋势未明显过热')
            elif rsi14 > 78:
                signals.append('RSI 偏高，趋势强但需留意短线过热')
        if indicators.get('macd') is not None and indicators.get('macd_signal') is not None:
            if indicators['macd'] > indicators['macd_signal']:
                signals.append('MACD 维持多头结构')
        if snapshot.get('pe_ttm') is not None or snapshot.get('pb_lf') is not None:
            signals.append('估值层已纳入行业相对比较')
        if market_regime.get('risk_on'):
            signals.append('当前市场风险偏好未明显转弱')
        return signals[:4]

    @staticmethod
    def _build_invalidators(
        candidate: CandidateStock,
        indicators: Dict[str, Optional[float]],
        snapshot: Dict[str, Any],
        grade_caps: List[str],
    ) -> List[str]:
        items = [
            '若后续催化未兑现或证据链减弱，需要下调关注度',
            '若价格跌破20日均线且量能同步走弱，技术评分应重算',
        ]
        if snapshot.get('profitability') == 'loss_making':
            items.append('若盈利改善进度继续不及预期，高估值容忍度将下降')
        if candidate.risk_flags:
            items.append('若负面事件继续发酵，需从观察名单移出')
        if 'missing_valuation_baseline' in grade_caps:
            items.append('若后续补齐估值基准，应重新评估估值与等级')
        if 'no_direct_stock_evidence' in grade_caps:
            items.append('若出现个股级直接催化证据，可重新评估是否升级')
        return items[:3]


def render_stock_recommendation_markdown(
    recommendations: List[Dict[str, Any]],
    *,
    scoring_config: Dict[str, Any],
) -> str:
    if not recommendations:
        market_label = '美股' if scoring_config.get('market') == 'US' else 'A 股'
        return (
            "## 股票推荐评分\n\n"
            f"当前未形成满足规则门槛的 {market_label} 推荐列表，建议继续观察主题催化与数据完整性。\n"
        )

    lines = [
        '## 股票推荐评分',
        '',
        f"- 市场: {scoring_config.get('market', 'CN')}",
        f"- 风格: {scoring_config.get('style', 'balanced')}",
        f"- 时间窗: {scoring_config.get('lookback_days', 60)} 日历史样本，默认决策窗口 5-20 个交易日",
        '',
        '| 股票代码 | 股票名称 | 总分 | 推荐等级 | 新闻 | 技术 | 估值 | 风险 | 环境 | 数据完整度 |',
        '|---------|---------|-----:|---------|----:|----:|----:|----:|----:|-----------:|',
    ]

    for item in recommendations:
        score_map = item.get('scores') or {}
        lines.append(
            f"| {item['symbol']} | {item['name']} | {item['total_score']} | {item['grade']} | "
            f"{score_map.get('news_catalyst', 0)} | {score_map.get('technical', 0)} | "
            f"{score_map.get('valuation', 0)} | {score_map.get('quality_risk', 0)} | "
            f"{score_map.get('market_regime', 0)} | {item.get('data_completeness', 0):.2f} |"
        )

    lines.extend(['', '### 个股解释卡', ''])
    for index, item in enumerate(recommendations, start=1):
        lines.extend(
            [
                f"#### {index}. {item['name']}（{item['symbol']}）",
                f"- 推荐等级: {item['grade']} / 总分 {item['total_score']}",
                f"- 压级原因: {'；'.join(item.get('grade_caps') or ['无'])}",
                f"- 核心催化: {'；'.join(item.get('signals') or ['暂无'])}",
                f"- 主要风险: {'；'.join(item.get('risks') or ['暂无'])}",
                f"- 失效条件: {'；'.join(item.get('invalidators') or ['暂无'])}",
                f"- 证据文章ID: {', '.join(str(x) for x in item.get('evidence_article_ids') or []) or '无'}",
                '- 适用时间窗: 5-20 个交易日',
                '',
            ]
        )
    return '\n'.join(lines)
