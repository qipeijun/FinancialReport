from pathlib import Path
import sys
import json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.domain.stock_recommendation import (
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
            'evidence_count': 2,
            'source_tier_max': 'mainstream',
            'high_relevance_article_count': 1,
            'high_confidence_topic': True,
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


def test_security_master_merges_direct_and_theme_hits_into_single_candidate():
    provider = SecurityMasterProvider()
    articles = [
        {
            'id': 1,
            'title': '中科曙光获新增订单',
            'summary': '中科曙光所在算力链条景气延续。',
            'content': '中科曙光在 AI 算力链条中继续受关注。',
            'source_tier': 'mainstream',
            'is_original_source': 1,
        }
    ]
    judgment_candidates = [
        {
            'topic': '科技与产业主题',
            'independent_evidence_count': 2,
            'evidence_count': 2,
            'source_tier_max': 'mainstream',
            'high_relevance_article_count': 1,
            'high_confidence_topic': True,
            'articles': [{'id': 9, 'title': '算力投资仍有景气支撑', 'source_tier': 'mainstream'}],
        }
    ]

    candidates = provider.build_candidates(articles=articles, judgment_candidates=judgment_candidates, max_candidates=5)

    target = next(item for item in candidates if item.symbol == 'sh603019')
    assert target.source_type == 'direct_news'
    assert '科技与产业主题' in (target.theme_topics or [])


def test_security_master_risk_flags_only_apply_to_mentioned_stock_sentence():
    provider = SecurityMasterProvider()
    articles = [
        {
            'id': 1,
            'title': '贵州茅台继续获机构关注',
            'summary': '贵州茅台业绩稳健。另一家公司因退市风险被问询。',
            'content': '贵州茅台维持增长。某小盘公司因退市风险被监管问询。',
            'source_tier': 'mainstream',
            'is_original_source': 1,
        }
    ]

    candidates = provider.build_candidates(articles=articles, judgment_candidates=[], max_candidates=5)

    maotai = next(item for item in candidates if item.symbol == 'sh600519')
    assert '退市' not in maotai.risk_flags
    assert '问询' not in maotai.risk_flags


def test_security_master_rejects_incidental_us_lifestyle_mentions():
    provider = SecurityMasterProvider(config_path=PROJECT_ROOT / 'config' / 'theme_stock_map_us.json')
    articles = [
        {
            'id': 101,
            'title': 'How to save money on gas and groceries this summer',
            'summary': 'Some shoppers compare Walmart, Costco and Amazon prices before holiday travel.',
            'content': 'The article is a consumer guide with shopping tips and travel budgeting examples.',
            'source_tier': 'mainstream',
            'is_original_source': 1,
        }
    ]

    candidates = provider.build_candidates(articles=articles, judgment_candidates=[], max_candidates=5)

    assert candidates == []
    rejected_symbols = {item['symbol'] for item in provider.rejected_false_positive_mentions}
    assert {'AMZN', 'COST', 'WMT'}.issubset(rejected_symbols)


def test_security_master_keeps_material_us_company_catalyst():
    provider = SecurityMasterProvider(config_path=PROJECT_ROOT / 'config' / 'theme_stock_map_us.json')
    articles = [
        {
            'id': 102,
            'title': 'Amazon earnings beat estimates as revenue guidance rises',
            'summary': 'Amazon shares rally after earnings and guidance raise.',
            'content': 'Amazon reported stronger revenue and raised guidance.',
            'source_tier': 'mainstream',
            'is_original_source': 1,
        }
    ]

    candidates = provider.build_candidates(articles=articles, judgment_candidates=[], max_candidates=5)

    assert [item.symbol for item in candidates] == ['AMZN']
    assert candidates[0].evidence_relevance_status == 'direct_material_news'
    assert any('material_keyword' in item for item in candidates[0].evidence_relevance_reasons or [])


def test_merged_direct_candidate_is_not_forced_into_theme_watch_only():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh603019',
        name='中科曙光',
        industry='算力基础设施',
        source_type='direct_news',
        topic='新闻直接提及',
        evidence_article_ids=[1, 2],
        evidence_summaries=['新增订单', '产业链景气持续'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=['科技与产业主题'],
        topic_article_count=5,
    )
    price_provider = FakePriceHistoryProvider({'sh603019': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh603019': {
                'symbol': 'sh603019',
                'pe_ttm': 24.0,
                'pb_lf': 3.6,
                'industry': '算力基础设施',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [22.0, 23.0, 25.0],
                'pb_history': [3.2, 3.4, 3.7],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {}

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert 'theme_mapping_watch_only' not in result['grade_caps']


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

    def fetch_market_regime(self, market='CN'):
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
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=[],
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
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {}

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert result['grade'] in {'观察', '回避'}
    assert result['scores']['technical'] == 0
    assert result['data_completeness'] < 0.7
    assert result['grade_caps'] == []
    assert result['base_grade'] in {'关注', '强关注', '观察'}


def test_recommendation_scorer_caps_theme_only_candidate_to_watch():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh688981',
        name='中芯国际',
        industry='半导体',
        source_type='theme_mapping',
        topic='科技与产业主题',
        evidence_article_ids=[1, 2],
        evidence_summaries=['产业景气回升', '半导体链条关注度提升'],
        source_tiers=['mainstream', 'official'],
        independent_evidence_count=2,
        direct_mentions=0,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=['科技与产业主题'],
        topic_article_count=5,
    )
    price_provider = FakePriceHistoryProvider({'sh688981': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh688981': {
                'symbol': 'sh688981',
                'pe_ttm': 30.0,
                'pb_lf': 4.0,
                'industry': '半导体',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [28.0, 29.0, 31.0],
                'pb_history': [3.6, 3.8, 4.1],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {}

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert result['grade'] == '观察'
    assert 'theme_mapping_watch_only' in result['grade_caps']
    assert result['industry_trend']['status'] == 'available'
    assert result['crowding_flag'] is True


def test_recommendation_scorer_clears_grade_caps_when_grade_unchanged():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='新闻直接提及',
        evidence_article_ids=[1],
        evidence_summaries=['贵州茅台业绩增长'],
        source_tiers=['official'],
        independent_evidence_count=1,
        direct_mentions=1,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=False,
        theme_topics=[],
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

    assert result['grade'] == result['base_grade']
    assert result['grade_caps'] == []
    assert 'stale_opportunity_flag' in result
    assert 'fresh_evidence_flag' in result
    assert 'validation_points' in result
    assert 'catalyst_path' in result
    assert 'failure_triggers' in result
    assert 'evidence_relevance_status' in result
    assert 'historical_calibration_status' in result
    assert 'historical_forward_stats' in result


def test_render_stock_recommendation_markdown_contains_required_section():
    markdown = render_stock_recommendation_markdown(
        [
            {
                'symbol': 'sh600519',
                'name': '贵州茅台',
                'total_score': 78,
                'grade': '关注',
                'base_grade': '关注',
                'grade_caps': [],
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
                'candidate_confidence': 'high',
                'evidence_strength': {
                    'direct_mentions': 2,
                    'independent_evidence_count': 2,
                    'source_tier_max': 'official',
                },
                'industry_trend': {
                    'status': 'available',
                    'direction': 'flat',
                    'score': 0,
                    'as_of': '2026-05-07',
                },
                'stale_opportunity_flag': False,
                'crowding_flag': False,
                'fresh_evidence_flag': True,
                'forward_window': '1-4周',
                'catalyst_path': ['跟踪个股级直接催化是否继续被主流来源确认'],
                'validation_points': ['确认后续是否出现第二条独立个股证据或进一步官方/主流跟进'],
                'failure_triggers': ['若后续催化未兑现或证据链减弱，需要下调关注度'],
            }
        ],
        scoring_config={'market': 'CN', 'style': 'balanced', 'lookback_days': 60},
    )

    assert '## 股票推荐评分' in markdown
    assert '贵州茅台' in markdown
    assert '个股解释卡' in markdown
    assert '压级原因' in markdown


def test_load_industry_trend_snapshot_warns_on_invalid_json(tmp_path, caplog):
    invalid_path = tmp_path / 'data' / 'market_cache' / 'industry_trend_snapshot.json'
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text('{invalid json', encoding='utf-8')

    provider = SecurityMasterProvider(config_path=PROJECT_ROOT / 'config' / 'theme_stock_map.json')
    scorer = RecommendationScorer(
        security_master=provider,
        price_history_provider=FakePriceHistoryProvider({}),
        valuation_provider=FakeValuationProvider({}),
        lookback_days=60,
    )

    from scripts.domain import stock_recommendation as stock_recommendation_module
    original_root = stock_recommendation_module.PROJECT_ROOT
    stock_recommendation_module.PROJECT_ROOT = tmp_path
    try:
        caplog.clear()
        snapshot = scorer._load_industry_trend_snapshot()
    finally:
        stock_recommendation_module.PROJECT_ROOT = original_root

    assert snapshot == {}
    assert any('Failed to load industry trend snapshot' in message for message in caplog.messages)


def test_recommendation_scorer_flags_stale_direct_candidate():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='新闻直接提及',
        evidence_article_ids=[1, 2],
        evidence_summaries=['渠道反馈继续向好', '高端白酒景气仍在'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=[],
        evidence_published_dates=['2026-05-07', '2026-05-08'],
        topic_article_count=2,
    )
    bars = build_bars(close_start=10.0, step=0.2, count=90)
    for offset, bar in enumerate(bars[-20:], start=1):
        boosted_close = 28.0 + offset * 0.9
        bar.open = boosted_close - 0.2
        bar.high = boosted_close + 0.3
        bar.low = boosted_close - 0.4
        bar.close = boosted_close
    for index in range(-5, 0):
        bars[index].volume = 10000 + (index + 5) * 500
    price_provider = FakePriceHistoryProvider({'sh600519': bars})
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
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {}

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert result['stale_opportunity_flag'] is True
    assert result['fresh_evidence_flag'] is True
    assert result['grade'] != '强关注'


def test_recommendation_scorer_uses_recent_enhanced_context_for_cross_day_signals(tmp_path):
    archive_dir = tmp_path / 'docs' / 'archive' / '2026-05' / '2026-05-08' / 'metadata'
    archive_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'selected_articles': [
            {'primary_topic': '科技与产业主题'},
            {'primary_topic': '科技与产业主题'},
            {'primary_topic': '科技与产业主题'},
        ],
        'candidate_stocks': [
            {'symbol': 'sh603019', 'direct_mentions': 1},
        ],
    }
    (archive_dir / 'morning_enhanced-context_markdown-report_deepseek.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh603019',
        name='中科曙光',
        industry='算力基础设施',
        source_type='direct_news',
        topic='科技与产业主题',
        evidence_article_ids=[1, 2],
        evidence_summaries=['新增订单', '产业链景气持续'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=['科技与产业主题'],
        evidence_published_dates=['2026-05-09', '2026-05-09'],
        topic_article_count=5,
    )
    price_provider = FakePriceHistoryProvider({'sh603019': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh603019': {
                'symbol': 'sh603019',
                'pe_ttm': 24.0,
                'pb_lf': 3.6,
                'industry': '算力基础设施',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [22.0, 23.0, 25.0],
                'pb_history': [3.2, 3.4, 3.7],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
        enhanced_context_root=tmp_path / 'docs' / 'archive',
    )

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert result['fresh_evidence_flag'] is False
    assert result['crowding_flag'] is True


def test_recommendation_scorer_deduplicates_same_day_enhanced_context_articles(tmp_path):
    archive_root = tmp_path / 'docs' / 'archive' / '2026-05'
    day_one_dir = archive_root / '2026-05-07' / 'metadata'
    day_two_dir = archive_root / '2026-05-08' / 'metadata'
    day_one_dir.mkdir(parents=True, exist_ok=True)
    day_two_dir.mkdir(parents=True, exist_ok=True)

    duplicate_payload = {
        'selected_articles': [
            {'id': 1, 'title': '算力景气延续', 'source': 'source-a', 'published': '2026-05-07', 'primary_topic': '科技与产业主题'},
            {'id': 2, 'title': '订单继续释放', 'source': 'source-b', 'published': '2026-05-07', 'primary_topic': '科技与产业主题'},
        ],
        'candidate_stocks': [],
    }
    single_payload = {
        'selected_articles': [
            {'id': 3, 'title': '主题继续发酵', 'source': 'source-c', 'published': '2026-05-08', 'primary_topic': '科技与产业主题'},
        ],
        'candidate_stocks': [],
    }

    (day_one_dir / 'morning_enhanced-context_markdown-report_deepseek.json').write_text(
        json.dumps(duplicate_payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (day_one_dir / 'evening_enhanced-context_judgment-cards_deepseek.json').write_text(
        json.dumps(duplicate_payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (day_two_dir / 'morning_enhanced-context_markdown-report_deepseek.json').write_text(
        json.dumps(single_payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh603019',
        name='中科曙光',
        industry='算力基础设施',
        source_type='direct_news',
        topic='科技与产业主题',
        evidence_article_ids=[1, 2],
        evidence_summaries=['新增订单', '产业链景气持续'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=['科技与产业主题'],
        evidence_published_dates=['2026-05-09', '2026-05-09'],
        topic_article_count=4,
    )

    class CalmPriceHistoryProvider(FakePriceHistoryProvider):
        @staticmethod
        def compute_indicators(_bars):
            return {
                'ma20': 10.0,
                'ma60': 10.0,
                'rsi14': 55.0,
                'macd': 0.1,
                'boll_upper': 10.5,
                'boll_lower': 9.5,
                'momentum_20d': 5.0,
                'volume_ratio_5_20': 1.0,
            }

    price_provider = CalmPriceHistoryProvider({'sh603019': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh603019': {
                'symbol': 'sh603019',
                'pe_ttm': 24.0,
                'pb_lf': 3.6,
                'industry': '算力基础设施',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [22.0, 23.0, 25.0],
                'pb_history': [3.2, 3.4, 3.7],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
        enhanced_context_root=tmp_path / 'docs' / 'archive',
    )

    result = scorer.score_candidates([candidate])['recommendations'][0]

    assert scorer.topic_recent_daily_counts['科技与产业主题'] == {
        '2026-05-07': 2,
        '2026-05-08': 1,
    }
    assert result['crowding_flag'] is False


def test_recommendation_scorer_decision_views_are_mutually_exclusive():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='新闻直接提及',
        evidence_article_ids=[1, 2],
        evidence_summaries=['渠道反馈继续向好', '高端白酒景气仍在'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        theme_topics=[],
        evidence_published_dates=['2026-05-09', '2026-05-09'],
        topic_article_count=2,
    )
    price_provider = FakePriceHistoryProvider({'sh600519': build_bars(count=90)})
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
        as_of_date='2026-05-09',
    )

    payload = scorer.score_candidates([candidate])

    assert [item['symbol'] for item in payload['decision_views']['actionable_candidates']] == ['sh600519']
    assert payload['decision_views']['conditional_watchlist'] == []
    assert payload['decision_views']['stale_or_rejected'] == []
    assert payload['recommendations'][0]['actionability_passed'] is True
    assert payload['recommendations'][0]['actionability_reasons'] == []


def test_non_fresh_focus_candidate_stays_in_watchlist():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='新闻直接提及',
        evidence_article_ids=[1, 2],
        evidence_summaries=['新增回购', '盈利改善'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        evidence_published_dates=['2026-05-01', '2026-05-02'],
        topic_article_count=2,
    )
    price_provider = FakePriceHistoryProvider({'sh600519': build_bars(count=90)})
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
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {'sh600519': ['2026-05-08']}

    payload = scorer.score_candidates([candidate])

    assert payload['decision_views']['actionable_candidates'] == []
    assert [item['symbol'] for item in payload['decision_views']['conditional_watchlist']] == ['sh600519']
    assert payload['recommendations'][0]['actionability_passed'] is False
    assert 'no_fresh_evidence' in payload['recommendations'][0]['actionability_reasons']


def test_old_evidence_is_not_treated_as_fresh_and_decay_lowers_news_score():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='财报与公司经营',
        evidence_article_ids=[1, 2],
        evidence_summaries=['新增回购', '盈利改善'],
        source_tiers=['official', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='official',
        high_confidence_topic=True,
        evidence_published_dates=['2026-05-01', '2026-05-02'],
        topic_article_count=2,
    )
    price_provider = FakePriceHistoryProvider({'sh600519': build_bars(count=90)})
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
        as_of_date='2026-05-09',
    )
    scorer.symbol_recent_direct_days = {}

    payload = scorer.score_candidates([candidate])

    assert scorer._has_fresh_evidence(candidate) is False
    assert payload['recommendations'][0]['scores']['news_catalyst'] < 30


def test_theme_only_candidate_is_never_actionable():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh603019',
        name='中科曙光',
        industry='算力基础设施',
        source_type='theme_mapping',
        topic='科技与产业主题',
        evidence_article_ids=[1, 2],
        evidence_summaries=['算力投资景气', '行业政策催化'],
        source_tiers=['mainstream', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=0,
        risk_flags=[],
        source_tier_max='mainstream',
        high_confidence_topic=True,
        theme_topics=['科技与产业主题'],
        evidence_published_dates=['2026-05-08', '2026-05-09'],
        topic_article_count=2,
    )
    price_provider = FakePriceHistoryProvider({'sh603019': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh603019': {
                'symbol': 'sh603019',
                'pe_ttm': 24.0,
                'pb_lf': 3.6,
                'industry': '算力基础设施',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [22.0, 23.0, 25.0],
                'pb_history': [3.2, 3.4, 3.7],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
    )

    payload = scorer.score_candidates([candidate])

    assert payload['decision_views']['actionable_candidates'] == []
    assert [item['symbol'] for item in payload['decision_views']['conditional_watchlist']] == ['sh603019']
    assert payload['recommendations'][0]['actionability_passed'] is False
    assert 'theme_only_not_actionable' in payload['recommendations'][0]['actionability_reasons']


def test_direct_candidate_without_independent_confirmation_is_capped_to_watch():
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='AAPL',
        name='Apple',
        industry='科技',
        source_type='direct_news',
        topic='财报与公司经营',
        evidence_article_ids=[1],
        evidence_summaries=['Apple 单一来源直接提及'],
        source_tiers=['mainstream'],
        independent_evidence_count=0,
        direct_mentions=1,
        risk_flags=[],
        source_tier_max='mainstream',
        high_confidence_topic=True,
        evidence_published_dates=['2026-05-09'],
        topic_article_count=1,
    )
    price_provider = FakePriceHistoryProvider({'AAPL': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'AAPL': {
                'symbol': 'AAPL',
                'pe_ttm': 24.0,
                'pb_lf': 7.0,
                'industry': '科技',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [22.0, 23.0, 25.0],
                'pb_history': [6.2, 6.7, 7.2],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
        market='US',
    )
    scorer.symbol_recent_direct_days = {}

    recommendation = scorer.score_candidates([candidate])['recommendations'][0]

    assert recommendation['grade'] == '观察'
    assert 'insufficient_independent_confirmation' in recommendation['grade_caps']
    assert recommendation['actionability_passed'] is False


def test_evidence_strength_contains_cross_verification_fields():
    """验证 RecommendationScorer 输出的 evidence_strength 包含交叉验真字段（字段存在性检查）。"""
    security_master = SecurityMasterProvider()
    candidate = CandidateStock(
        symbol='sh600519',
        name='贵州茅台',
        industry='白酒',
        source_type='direct_news',
        topic='消费主题',
        evidence_article_ids=[1, 2],
        evidence_summaries=['白酒消费回暖', '茅台业绩稳健'],
        source_tiers=['mainstream', 'mainstream'],
        independent_evidence_count=2,
        direct_mentions=2,
        risk_flags=[],
        source_tier_max='mainstream',
        high_confidence_topic=True,
        evidence_published_dates=['2026-05-09', '2026-05-08'],
        topic_article_count=3,
    )
    price_provider = FakePriceHistoryProvider({'sh600519': build_bars(count=90)})
    valuation_provider = FakeValuationProvider(
        {
            'sh600519': {
                'symbol': 'sh600519',
                'pe_ttm': 22.0,
                'pb_lf': 8.0,
                'industry': '白酒',
                'profitability': 'profitable',
                'company_type': 'general',
                'pe_history': [20.0, 21.0, 23.0],
                'pb_history': [7.0, 7.5, 8.5],
            }
        }
    )
    scorer = RecommendationScorer(
        security_master=security_master,
        price_history_provider=price_provider,
        valuation_provider=valuation_provider,
        lookback_days=60,
        as_of_date='2026-05-09',
    )

    payload = scorer.score_candidates([candidate])
    recommendation = payload['recommendations'][0]
    evidence_strength = recommendation.get('evidence_strength') or {}

    # 验证 evidence_strength 核心字段存在
    assert 'direct_mentions' in evidence_strength
    assert 'independent_evidence_count' in evidence_strength
    assert 'source_tier_max' in evidence_strength
