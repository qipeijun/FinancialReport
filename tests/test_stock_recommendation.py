from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.utils.stock_recommendation import (
    CandidateStock,
    HistoryBar,
    PriceHistoryProvider,
    RecommendationScorer,
    SecurityMasterProvider,
    render_stock_recommendation_markdown,
)


def test_security_master_build_candidates_supports_direct_and_theme_mapping():
    provider = SecurityMasterProvider()
    articles = [
        {
            'id': 1,
            'title': '贵州茅台披露一季报，盈利维持增长',
            'summary': '贵州茅台与五粮液被市场持续关注。',
            'content': '机构继续跟踪贵州茅台与五粮液表现。',
            'source_tier': 'mainstream',
            'is_original_source': 1,
        }
    ]
    judgment_candidates = [
        {
            'topic': '科技与产业主题',
            'independent_evidence_count': 2,
            'articles': [{'id': 9, 'title': '算力投资仍有景气支撑', 'source_tier': 'mainstream'}],
        }
    ]

    candidates = provider.build_candidates(
        articles=articles,
        judgment_candidates=judgment_candidates,
        max_candidates=5,
    )

    symbols = {item.symbol for item in candidates}
    assert 'sh600519' in symbols
    assert any(item.source_type == 'theme_mapping' for item in candidates)


def test_price_history_provider_compute_indicators_returns_expected_metrics():
    bars = []
    for day in range(1, 81):
        bars.append(
            HistoryBar(
                date=f'2026-01-{day:02d}',
                open=10 + day * 0.1,
                high=10.2 + day * 0.1,
                low=9.8 + day * 0.1,
                close=10 + day * 0.1,
                volume=1000 + day * 20,
            )
        )

    metrics = PriceHistoryProvider.compute_indicators(bars)

    assert metrics['ma20'] is not None
    assert metrics['ma60'] is not None
    assert metrics['rsi14'] is not None
    assert metrics['macd'] is not None
    assert metrics['boll_upper'] is not None
    assert metrics['volume_ratio_5_20'] is not None


class FakePriceHistoryProvider:
    def __init__(self, history_map, regime=None):
        self.history_map = history_map
        self.regime = regime or {
            'indices': {},
            'style_bias': 'growth',
            'risk_on': True,
        }

    def fetch_history(self, symbol, lookback_days=180):
        return self.history_map.get(symbol, [])

    def fetch_market_regime(self):
        return self.regime

    @staticmethod
    def compute_indicators(bars):
        return PriceHistoryProvider.compute_indicators(bars)


class FakeValuationProvider:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def get_snapshot(self, symbol):
        return self.snapshots[symbol]

    @staticmethod
    def get_industry_stats(industry, symbol_snapshots):
        same_industry = [item for item in symbol_snapshots if item.get('industry') == industry]
        pe_values = [item.get('pe_ttm') for item in same_industry if isinstance(item.get('pe_ttm'), (int, float))]
        pb_values = [item.get('pb_lf') for item in same_industry if isinstance(item.get('pb_lf'), (int, float))]
        return {
            'industry_pe_median': pe_values[0] if pe_values else None,
            'industry_pb_median': pb_values[0] if pb_values else None,
        }


def build_bars(close_start=10.0, step=0.2, count=90):
    return [
        HistoryBar(
            date=f'2026-02-{(idx % 28) + 1:02d}',
            open=close_start + idx * step,
            high=close_start + idx * step + 0.3,
            low=close_start + idx * step - 0.3,
            close=close_start + idx * step,
            volume=1000 + idx * 15,
        )
        for idx in range(count)
    ]


def test_recommendation_scorer_caps_grade_when_data_incomplete():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='财报与公司经营',
        evidence_article_ids=[1, 2],
        evidence_summaries=['贵州茅台业绩增长', '机构持续跟踪'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
    )

    price_provider = FakePriceHistoryProvider({'sh600519': build_bars(count=30)})
    valuation_provider = FakeValuationProvider(
        {
            'sh600519': {
                'symbol': 'sh600519',
                'pe_ttm': 20.0,
                'pb_lf': 5.0,
                'industry': '白酒',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [18.0, 19.0, 22.0],
                'pb_history': [4.5, 5.1, 5.4],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
    )

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert result['grade'] in {'观察', '回避'}
    assert result['scores']['technical'] == 0
    assert result['data_completeness'] < 0.7


def test_render_stock_recommendation_markdown_contains_required_section():
    markdown = render_stock_recommendation_markdown(
        [
            {
                'symbol': 'sh600519',
                'name': '贵州茅台',
                'total_score': 78,
                'grade': '关注',
                'scores': {
                    'news_catalyst': 24,
                    'technical': 17,
                    'valuation': 12,
                    'quality_risk': 15,
                    'market_regime': 10,
                },
                'signals': ['近20日与60日均线呈多头排列'],
                'risks': ['估值偏高'],
                'invalidators': ['若价格跌破20日均线且量能同步走弱，技术评分应重算'],
                'evidence_article_ids': [1, 2],
                'data_completeness': 0.92,
            }
        ],
        scoring_config={'market': 'CN', 'style': 'balanced', 'lookback_days': 60},
    )

    assert '## 股票推荐评分' in markdown
    assert '贵州茅台' in markdown
    assert '个股解释卡' in markdown
