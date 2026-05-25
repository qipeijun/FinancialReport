from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))


from scripts.utils.fact_checker import Claim, ClaimScope, ClaimType, FactChecker
from scripts.utils.quality_checker_v2 import check_report_quality_v2
from scripts.utils.ai_analyzer_common import build_source_stats_block, summarize_content_quality


def test_extract_claims_separates_realtime_market_from_news_facts():
    report = """
    - 基于实时数据，上证指数收涨1.81%至4160.17点，美元兑人民币为6.8302，现货黄金站上4700美元/盎司。
    - 寒武纪一季度营收同比+159.56%，CBPI同比上涨20.2%，沪银涨5.85%【新闻4】。
    """

    claims = FactChecker().extract_claims(report)
    realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]
    news_fact_claims = [c for c in claims if c.scope == ClaimScope.NEWS_FACT]

    assert any(c.type == ClaimType.FOREX_RATE and c.extracted_value == '6.8302' for c in realtime_claims)
    assert any(c.type == ClaimType.GOLD_PRICE and c.extracted_value == '4700' for c in realtime_claims)
    assert any(c.type == ClaimType.PRICE_CHANGE and c.extracted_value == '1.81' for c in realtime_claims)
    assert any(c.extracted_value == '20.2' for c in news_fact_claims)
    assert all(c.extracted_value != '5.85' for c in realtime_claims)


def test_extract_claims_supports_us_index_realtime_claims():
    report = """
    - 基于实时数据（更新时间：2026-05-25 19:14），道指收涨2.13%至$50,579.70，标普500收涨0.88%至$7,473.47，纳指收涨0.45%至$26,343.97。
    """

    claims = FactChecker().extract_claims(report)
    realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]

    assert any(
        c.type == ClaimType.PRICE_CHANGE and c.asset_hint == '^DJI' and c.extracted_value == '2.13'
        for c in realtime_claims
    )
    assert any(
        c.type == ClaimType.PRICE_CHANGE and c.asset_hint == '^GSPC' and c.extracted_value == '0.88'
        for c in realtime_claims
    )
    assert any(
        c.type == ClaimType.PRICE_CHANGE and c.asset_hint == '^IXIC' and c.extracted_value == '0.45'
        for c in realtime_claims
    )
    assert any(
        c.type == ClaimType.STOCK_PRICE and c.asset_hint == '^DJI' and c.extracted_value == '50579.70'
        for c in realtime_claims
    )
    assert any(
        c.type == ClaimType.STOCK_PRICE and c.asset_hint == '^GSPC' and c.extracted_value == '7473.47'
        for c in realtime_claims
    )
    assert any(
        c.type == ClaimType.STOCK_PRICE and c.asset_hint == '^IXIC' and c.extracted_value == '26343.97'
        for c in realtime_claims
    )


def test_extract_claims_counts_news_money_and_percent_claims_only_as_news_facts():
    report = """
    - 人形机器人商业化出现早期信号，旧金山已推出$150的人形机器人清洁服务【新闻3】。
    - 机器人清洁服务的$150定价已低于传统家政服务$200-$400的价格区间【新闻3】。
    - 迪士尼新片首周末国内票房仅$8,200万【新闻8】，国际油价应声下跌约5%【新闻6】。
    """

    claims = FactChecker().extract_claims(report)
    realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]
    news_fact_claims = [c for c in claims if c.scope == ClaimScope.NEWS_FACT]
    news_values = {c.extracted_value for c in news_fact_claims}

    assert not realtime_claims
    assert {'150', '200', '400', '8200', '5'}.issubset(news_values)


def test_extract_claims_marks_target_gain_as_violation():
    report = "建议关注某股票，目标涨幅25%。"

    claims = FactChecker().extract_claims(report)

    assert len(claims) == 1
    assert claims[0].scope == ClaimScope.VIOLATION
    assert claims[0].type == ClaimType.PRICE_CHANGE
    assert claims[0].error


def test_quality_checker_uses_system_realtime_timestamp_when_text_omits_it():
    report = """
    ## 市场概况
    上证指数今日走强【新闻1】。

    ## 投资主题
    AI 算力链维持活跃【新闻2】【新闻3】。

    ## 风险
    警惕短线波动【新闻4】。

    ## 建议
    建议继续跟踪成交量与政策催化【新闻5】【新闻6】【新闻7】【新闻8】【新闻9】【新闻10】【新闻11】【新闻12】【新闻13】【新闻14】【新闻15】。
    """

    result = check_report_quality_v2(
        report_text=report,
        claims=[],
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
    )

    assert result['stats']['has_realtime_data'] is True
    assert result['timeliness_score'] == 20
    assert result['accuracy_score'] == 45


def test_quality_checker_reports_missing_source_without_calling_citations_insufficient():
    report = """
    ## 市场概况
    基于实时数据（更新时间：2099-01-01 08:00），道指收涨2.13%至$50,579.70【新闻1】。

    ## 投资主题
    机器人清洁服务定价为$150【新闻2】。

    ## 风险
    油价下跌约5%【新闻3】。

    ## 建议
    继续观察【新闻4】【新闻5】【新闻6】【新闻7】【新闻8】【新闻9】【新闻10】【新闻11】【新闻12】【新闻13】【新闻14】【新闻15】。
    """
    claims = FactChecker().extract_claims(report)
    for claim in claims:
        if claim.scope == ClaimScope.REALTIME_MARKET:
            claim.verified = True

    result = check_report_quality_v2(
        report_text=report,
        claims=claims,
        realtime_data={'timestamp': '2099-01-01 08:00:00'},
        report_mode='markdown-report',
    )

    assert result['reliability_score'] == 15
    assert result['source_annotation_missing'] is True
    assert result['stats']['claim_coverage_score'] >= 10
    assert any('缺少实时数据来源标注' in warning for warning in result['warnings'])
    assert not any('引用来源偏少' in warning for warning in result['warnings'])


def test_quality_checker_uses_more_conservative_time_when_report_and_system_conflict():
    report = """
    ## 市场概况
    基于实时数据（更新时间：2000-01-01），道指收涨2.13%至$50,579.70【新闻1】。

    ## 投资主题
    机器人清洁服务定价为$150【新闻2】。

    ## 风险
    油价下跌约5%【新闻3】。

    ## 建议
    继续观察【新闻4】【新闻5】【新闻6】【新闻7】【新闻8】【新闻9】【新闻10】【新闻11】【新闻12】【新闻13】【新闻14】【新闻15】。
    """
    claims = FactChecker().extract_claims(report)
    for claim in claims:
        if claim.scope == ClaimScope.REALTIME_MARKET:
            claim.verified = True

    result = check_report_quality_v2(
        report_text=report,
        claims=claims,
        realtime_data={'timestamp': '2099-01-01 08:00:00'},
        report_mode='markdown-report',
    )

    assert result['time_source'] == 'report_text'
    assert result['timeliness_score'] == 5
    assert result['passed'] is False
    assert result['stats']['data_age_hours'] > 24
    assert any('超过24小时' in issue for issue in result['issues'])
    assert any('更保守时间' in warning for warning in result['warnings'])


def test_quality_checker_counts_only_realtime_claims_in_accuracy():
    checker = FactChecker()
    claims = checker.extract_claims(
        """
        - 基于实时数据，上证指数收涨1.81%至4160.17点。
        - PMI为49.8，营收同比增长21.56%。
        """
    )
    realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]
    news_claims = [c for c in claims if c.scope == ClaimScope.NEWS_FACT]

    assert len(realtime_claims) == 1
    assert len(news_claims) >= 1

    for claim in realtime_claims:
        claim.verified = True
    result = check_report_quality_v2(
        report_text="""
        ## 市场概况
        基于实时数据，上证指数收涨1.81%【新闻1】。
        ## 投资主题
        AI【新闻2】。
        ## 风险
        波动【新闻3】。
        ## 建议
        跟踪【新闻4】【新闻5】【新闻6】【新闻7】【新闻8】【新闻9】【新闻10】【新闻11】【新闻12】【新闻13】【新闻14】【新闻15】。
        """,
        claims=claims,
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
    )

    assert result['stats']['total_claims'] == len(realtime_claims)
    assert result['stats']['verified_claims'] == len(realtime_claims)
    assert result['accuracy_score'] == 60


def test_extract_claims_dedupes_same_realtime_fact_with_same_context():
    report = """
    - 基于实时数据，深证成指上涨2.93%，涨2.93%，上涨2.93%。
    """

    claims = FactChecker().extract_claims(report)
    realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]

    assert len(realtime_claims) == 1
    assert realtime_claims[0].extracted_value == '2.93'


def test_extract_claims_dedupes_same_news_fact_across_different_contexts():
    report = """
    - 市场概况：制造业 PMI 同比3.8%，景气度回升。
    - 投资主题：上游设备订单同比3.8%，板块情绪修复。
    """

    claims = FactChecker().extract_claims(report)
    news_fact_claims = [c for c in claims if c.scope == ClaimScope.NEWS_FACT and c.extracted_value == '3.8']

    assert len(news_fact_claims) == 1


def test_collect_implausible_signals_returns_warning_level_stats():
    checker = FactChecker()
    claims = [
        Claim(type=ClaimType.PRICE_CHANGE, content='上证上涨3.817%', extracted_value='3.817', asset_hint='sh000001'),
        Claim(type=ClaimType.FOREX_RATE, content='美元兑人民币7.50', extracted_value='7.50', asset_hint='USD/CNY'),
        Claim(type=ClaimType.GOLD_PRICE, content='黄金7.50美元', extracted_value='7.50', asset_hint='gold'),
    ]

    stats = checker.collect_implausible_signals(claims)

    assert stats['over_precision_count'] == 1
    assert stats['rounded_ratio'] > 0
    assert stats['cross_asset_repeated_value_count'] == 1


def test_build_source_stats_block_uses_content_quality_distribution():
    selected = [
        {'source': '华尔街见闻', 'content_quality_status': 'full'},
        {'source': '36氪', 'content_quality_status': 'partial'},
        {'source': '中新网', 'content_quality_status': 'summary_only'},
    ]

    summary = summarize_content_quality(selected)
    block = build_source_stats_block(selected, 'auto', '2026-05-09', '2026-05-09')

    assert summary['counts']['full'] == 1
    assert summary['counts']['partial'] == 1
    assert summary['counts']['summary_only'] == 1
    assert '完整正文 1篇(33.3%) / 部分正文 1篇(33.3%) / 仅摘要 1篇(33.3%)' in block


def test_quality_checker_rejects_long_report_with_too_few_claims():
    report = """
    ## 市场概况
    基于实时数据，上证指数收涨1.81%【新闻1】。

    ## 投资主题
    """ + ("宏观叙事延伸。" * 800) + """

    ## 风险
    波动【新闻2】。

    ## 建议
    继续观察【新闻3】【新闻4】【新闻5】【新闻6】【新闻7】【新闻8】【新闻9】【新闻10】【新闻11】【新闻12】【新闻13】【新闻14】【新闻15】。
    """
    claims = FactChecker().extract_claims(report)
    for claim in claims:
        if claim.scope == ClaimScope.REALTIME_MARKET:
            claim.verified = True

    result = check_report_quality_v2(
        report_text=report,
        claims=claims,
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
    )

    assert result['claim_coverage_score'] == 0
    assert any('可验证断言覆盖过少' in issue for issue in result['issues'])
    assert result['passed'] is False


def test_quality_checker_rejects_data_integrity_mismatch_and_unsupported_stock_mentions():
    report = """
    ## 市场概况
    市场以结构性机会为主【新闻1】。

    ## 投资主题
    ### 科技与产业主题
    - 聚焦 AI 基建【新闻2】。

    ## 建议
    ### 推荐摘要
    - 核心持仓考虑 sh600522 与 sh603019。

    ## 风险
    警惕追高【新闻3】。

    ## 数据质量说明
    - 数据质量分布：100%的文章包含完整内容
    """
    result = check_report_quality_v2(
        report_text=report,
        claims=[],
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
        stock_recommendations=[{'symbol': 'sh603019', 'name': '中科曙光'}],
        judgment_candidates=[{'topic': '科技与产业主题', 'high_confidence_topic': True}],
        data_quality_stats={
            'counts': {'full': 32, 'partial': 11, 'summary_only': 3},
            'ratios': {'full': 69.6, 'partial': 23.9, 'summary_only': 6.5},
        },
    )

    assert result['narrative_consistency_passed'] is False
    assert result['data_integrity_statement_passed'] is False
    assert any('未支持的股票代码' in issue for issue in result['issues'])
    assert any('数据质量说明与真实文章分布不一致' in issue for issue in result['issues'])


def test_quality_checker_rejects_watchlist_promotion_and_verification_overclaim():
    report = """
    ## 市场概况
    基于实时数据，上证指数收涨1.81%【新闻1】。

    ## 投资主题
    ### 科技与产业主题
    - AI 基建仍有热度【新闻2】。

    ## 建议
    ### 推荐摘要
    - 中科曙光（sh603019）属于核心配置，可执行买点已经出现。
    - 整份报告已验证，可直接参考执行。

    ## 风险
    警惕追高【新闻3】。
    """
    claims = FactChecker().extract_claims(report)
    for claim in claims:
        if claim.scope == ClaimScope.REALTIME_MARKET:
            claim.verified = True

    result = check_report_quality_v2(
        report_text=report,
        claims=claims,
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
        stock_recommendations=[
            {
                'symbol': 'sh603019',
                'name': '中科曙光',
                'grade': '关注',
                'fresh_evidence_flag': False,
                'actionability_passed': False,
            }
        ],
        judgment_candidates=[{'topic': '科技与产业主题', 'high_confidence_topic': True}],
    )

    assert result['passed'] is False
    assert result['stats']['watchlist_promoted_in_narrative_count'] == 1
    assert result['stats']['verification_boundary_overclaim_count'] == 1
    assert any('明确动作建议' in issue for issue in result['issues'])
    assert any('事实核查边界' in issue for issue in result['issues'])


def test_quality_checker_does_not_flag_watchlist_when_strong_words_only_apply_to_actionable_pick():
    report = """
    ## 市场概况
    基于实时数据，上证指数收涨1.81%【新闻1】。

    ## 投资主题
    ### 科技与产业主题
    - AI 基建仍有热度【新闻2】。

    ## 建议
    - **可行动标的**: 中国移动（sh600941）属于核心配置，可执行买点已经出现。
    - **继续观察**:
      - 中科曙光（sh603019）：证据链未达高信号门槛，继续观察。
    """

    result = check_report_quality_v2(
        report_text=report,
        claims=[],
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
        stock_recommendations=[
            {
                'symbol': 'sh600941',
                'name': '中国移动',
                'grade': '关注',
                'fresh_evidence_flag': True,
                'actionability_passed': True,
            },
            {
                'symbol': 'sh603019',
                'name': '中科曙光',
                'grade': '观察',
                'fresh_evidence_flag': False,
                'actionability_passed': False,
            },
        ],
        judgment_candidates=[{'topic': '科技与产业主题', 'high_confidence_topic': True}],
    )

    assert result['stats']['watchlist_promoted_in_narrative_count'] == 0
    assert not any('中科曙光' in issue and '明确动作建议' in issue for issue in result['issues'])


def test_quality_checker_rejects_fresh_but_non_actionable_promotion():
    report = """
    ## 市场概况
    基于实时数据，上证指数收涨1.81%【新闻1】。

    ## 投资主题
    ### 科技与产业主题
    - AI 基建仍有热度【新闻2】。

    ## 建议
    - 浪潮信息（sz000977）属于核心配置，可执行买点已经出现。
    """

    result = check_report_quality_v2(
        report_text=report,
        claims=[],
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
        report_mode='markdown-report',
        stock_recommendations=[
            {
                'symbol': 'sz000977',
                'name': '浪潮信息',
                'grade': '关注',
                'fresh_evidence_flag': True,
                'actionability_passed': False,
            }
        ],
        judgment_candidates=[{'topic': '科技与产业主题', 'high_confidence_topic': True}],
    )

    assert result['stats']['watchlist_promoted_in_narrative_count'] == 1
    assert any('浪潮信息' in issue and '明确动作建议' in issue for issue in result['issues'])
