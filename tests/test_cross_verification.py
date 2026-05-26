from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.cross_verification import (
    run_cross_verification,
    build_cross_verification_summary,
    TopicCrossCheck,
    StockCrossCheck,
    CROSS_STATUS_CONFIRMED,
    CROSS_STATUS_WEAK,
    CROSS_STATUS_CONFLICTED,
    _is_evidence_fresh,
    _parse_date,
    _detect_stock_keyword_conflict,
    _detect_numeric_conflict,
    _extract_numeric_assertions,
    _article_mentions_security,
)
from scripts.utils.stock_recommendation import CandidateStock


# ---------------------------------------------------------------------------
# 辅助工厂函数
# ---------------------------------------------------------------------------

def _make_article(art_id, title='', summary='', content='', source_tier='mainstream',
                  published='2026-05-26', investment_relevance='high', source='source-a',
                  is_original_source=1, **kwargs):
    return {
        'id': art_id,
        'title': title,
        'summary': summary,
        'content': content,
        'source_tier': source_tier,
        'published': published,
        'investment_relevance': investment_relevance,
        'source': source,
        'is_original_source': is_original_source,
        'collection_date': published,
        'content_quality_status': kwargs.get('content_quality_status', 'full'),
        'primary_topic': kwargs.get('primary_topic', '科技与产业主题'),
    }


def _make_judgment_candidate(topic='科技与产业主题', independent_evidence_count=2,
                             mainstream_or_better_count=1, high_confidence_topic=True,
                             published='2026-05-26', article_ids=None):
    articles = [
        {
            'id': aid,
            'title': f'测试文章{aid}',
            'source': f'source-{aid}',
            'summary': f'关于{topic}的报道',
            'source_tier': 'mainstream',
            'content_quality_status': 'full',
            'published': published,
            'collection_date': published,
        }
        for aid in (article_ids or [1, 2])
    ]
    return {
        'candidate_id': 'C01',
        'topic': topic,
        'evidence_count': 2,
        'independent_evidence_count': independent_evidence_count,
        'mainstream_or_better_count': mainstream_or_better_count,
        'high_confidence_topic': high_confidence_topic,
        'articles': articles,
        'topic_article_count': 2,
        'priority_score': 50,
    }


def _make_candidate_stock(symbol='000001', name='平安银行', source_type='direct_news',
                          direct_mentions=2, independent_evidence_count=1,
                          evidence_article_ids=None, evidence_published_dates=None,
                          risk_flags=None, topic='金融'):
    return CandidateStock(
        symbol=symbol,
        name=name,
        industry='金融',
        source_type=source_type,
        topic=topic,
        evidence_article_ids=evidence_article_ids or [1, 2],
        evidence_summaries=[f'{name}业绩增长', f'{name}订单增加'],
        source_tiers=['mainstream', 'mainstream'],
        independent_evidence_count=independent_evidence_count,
        direct_mentions=direct_mentions,
        risk_flags=risk_flags or [],
        source_tier_max='mainstream',
        high_confidence_topic=True,
        evidence_published_dates=evidence_published_dates or ['2026-05-26', '2026-05-25'],
        topic_article_count=3,
    )


def _make_recommendation(symbol='000001', name='平安银行', grade='关注',
                         source_type='direct_news', actionability_passed=True,
                         direct_mentions=2, independent_evidence_count=1):
    return {
        'symbol': symbol,
        'name': name,
        'grade': grade,
        'source_type': source_type,
        'actionability_passed': actionability_passed,
        'actionability_reasons': [],
        'evidence_strength': {
            'direct_mentions': direct_mentions,
            'independent_evidence_count': independent_evidence_count,
            'source_tier_max': 'mainstream',
        },
        'total_score': 75,
        'evidence_article_ids': [1, 2],
    }


# ---------------------------------------------------------------------------
# 工具函数测试
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_iso_date(self):
        d = _parse_date('2026-05-26')
        assert d is not None
        assert d.year == 2026 and d.month == 5 and d.day == 26

    def test_datetime_with_tz(self):
        d = _parse_date('2026-05-26T10:30:00Z')
        assert d is not None
        assert d.day == 26

    def test_empty_returns_none(self):
        assert _parse_date('') is None
        assert _parse_date(None) is None


class TestIsEvidenceFresh:
    def test_fresh_within_threshold(self):
        from datetime import datetime
        ref = datetime(2026, 5, 26)
        assert _is_evidence_fresh(['2026-05-25', '2026-05-26'], ref) is True

    def test_stale_beyond_threshold(self):
        from datetime import datetime
        ref = datetime(2026, 5, 26)
        assert _is_evidence_fresh(['2026-05-20'], ref) is False

    def test_empty_dates(self):
        from datetime import datetime
        ref = datetime(2026, 5, 26)
        assert _is_evidence_fresh([], ref) is False


# ---------------------------------------------------------------------------
# 关键词冲突检测测试
# ---------------------------------------------------------------------------

class TestStockKeywordConflict:
    def test_cross_article_conflict_detected(self):
        articles = [
            _make_article(1, title='某公司订单大增', summary='获得大额订单'),
            _make_article(2, title='某公司被调查', summary='收到监管调查通知'),
        ]
        has_conflict, detail = _detect_stock_keyword_conflict('test', articles)
        assert has_conflict is True
        assert detail is not None

    def test_same_article_both_kw_no_conflict(self):
        articles = [
            _make_article(1, title='某公司订单增长但面临减持压力',
                          summary='虽然有订单利好，但大股东减持带来风险'),
        ]
        has_conflict, _ = _detect_stock_keyword_conflict('test', articles)
        assert has_conflict is False

    def test_no_negative_no_conflict(self):
        articles = [
            _make_article(1, title='订单大增', summary='获得大额订单'),
            _make_article(2, title='产能扩张', summary='扩产计划推进'),
        ]
        has_conflict, _ = _detect_stock_keyword_conflict('test', articles)
        assert has_conflict is False

    def test_empty_articles_no_conflict(self):
        has_conflict, _ = _detect_stock_keyword_conflict('test', [])
        assert has_conflict is False


# ---------------------------------------------------------------------------
# 数值断言冲突测试
# ---------------------------------------------------------------------------

class TestNumericConflict:
    def test_direction_conflict_detected(self):
        assertions = _extract_numeric_assertions(
            '营收增长25%，但也有报告指出营收下降10%'
        )
        has_conflict, detail = _detect_numeric_conflict(assertions)
        assert has_conflict is True

    def test_single_assertion_no_conflict(self):
        assertions = _extract_numeric_assertions('营收增长25%')
        has_conflict, _ = _detect_numeric_conflict(assertions)
        assert has_conflict is False

    def test_same_direction_no_conflict(self):
        assertions = _extract_numeric_assertions('营收增长25%，利润增长15%')
        has_conflict, _ = _detect_numeric_conflict(assertions)
        assert has_conflict is False


# ---------------------------------------------------------------------------
# 主函数 run_cross_verification 测试
# ---------------------------------------------------------------------------

class TestRunCrossVerification:
    def test_confirms_well_supported_topic(self):
        """多来源 mainstream+official 同一主题应返回 confirmed"""
        articles = [
            _make_article(1, published='2026-05-26', source_tier='official'),
            _make_article(2, published='2026-05-26', source_tier='mainstream'),
        ]
        jc = [
            _make_judgment_candidate(
                independent_evidence_count=2, mainstream_or_better_count=2,
                published='2026-05-26', article_ids=[1, 2],
            )
        ]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=jc,
            candidate_stocks=[],
            stock_recommendations=[],
            as_of_date='2026-05-26',
        )
        assert len(result['topic_checks']) == 1
        assert result['topic_checks'][0]['status'] == CROSS_STATUS_CONFIRMED

    def test_single_source_topic_is_weak(self):
        """只有1个独立来源应返回 weak"""
        articles = [
            _make_article(1, published='2026-05-26', source_tier='mainstream'),
        ]
        jc = [
            _make_judgment_candidate(
                independent_evidence_count=1, mainstream_or_better_count=1,
                published='2026-05-26', article_ids=[1],
            )
        ]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=jc,
            candidate_stocks=[],
            stock_recommendations=[],
            as_of_date='2026-05-26',
        )
        assert result['topic_checks'][0]['status'] == CROSS_STATUS_WEAK

    def test_stale_topic_is_weak(self):
        """证据过期应返回 weak"""
        articles = [
            _make_article(1, published='2026-05-20', source_tier='official'),
            _make_article(2, published='2026-05-19', source_tier='mainstream'),
        ]
        jc = [
            _make_judgment_candidate(
                independent_evidence_count=2, mainstream_or_better_count=2,
                published='2026-05-20', article_ids=[1, 2],
            )
        ]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=jc,
            candidate_stocks=[],
            stock_recommendations=[],
            as_of_date='2026-05-26',
        )
        assert result['topic_checks'][0]['status'] == CROSS_STATUS_WEAK

    def test_confirms_direct_mention_stock(self):
        """直接个股新闻 + 独立来源 + 新鲜证据应 confirmed"""
        articles = [
            _make_article(1, title='平安银行订单大增', summary='平安银行获得大额订单',
                          published='2026-05-26'),
            _make_article(2, title='银行板块走强', summary='银行股表现活跃',
                          published='2026-05-26'),
        ]
        cs = _make_candidate_stock(
            symbol='000001', name='平安银行', source_type='direct_news',
            direct_mentions=2, independent_evidence_count=2,
            evidence_published_dates=['2026-05-26', '2026-05-25'],
        )
        recs = [_make_recommendation(symbol='000001', name='平安银行',
                                     direct_mentions=2, independent_evidence_count=2)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=[],
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        assert len(result['stock_checks']) == 1
        assert result['stock_checks'][0]['status'] == CROSS_STATUS_CONFIRMED

    def test_theme_only_stock_is_weak(self):
        """纯 theme_mapping 无直接提及的股票永远 weak"""
        articles = [
            _make_article(1, title='科技板块走强', summary='AI概念股活跃',
                          published='2026-05-26'),
        ]
        cs = _make_candidate_stock(
            symbol='688001', name='某科技股', source_type='theme_mapping',
            direct_mentions=0, independent_evidence_count=1,
            evidence_published_dates=['2026-05-26'],
        )
        recs = [_make_recommendation(symbol='688001', name='某科技股',
                                     source_type='theme_mapping',
                                     direct_mentions=0, independent_evidence_count=1)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=[],
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        assert result['stock_checks'][0]['status'] == CROSS_STATUS_WEAK

    def test_stale_stock_evidence_is_weak(self):
        """证据过期应返回 weak"""
        articles = [
            _make_article(1, title='平安银行', summary='平安银行消息',
                          published='2026-05-20'),
        ]
        cs = _make_candidate_stock(
            symbol='000001', name='平安银行', source_type='direct_news',
            direct_mentions=1, independent_evidence_count=1,
            evidence_published_dates=['2026-05-20'],
        )
        recs = [_make_recommendation(symbol='000001', name='平安银行',
                                     direct_mentions=1, independent_evidence_count=1)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=[],
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        assert result['stock_checks'][0]['status'] == CROSS_STATUS_WEAK

    def test_single_source_direct_mention_stock_is_weak(self):
        """只有单一独立来源不能标记为多来源 confirmed。"""
        articles = [
            _make_article(1, title='平安银行订单大增', summary='平安银行获得大额订单',
                          published='2026-05-26'),
        ]
        cs = _make_candidate_stock(
            symbol='000001', name='平安银行', source_type='direct_news',
            direct_mentions=1, independent_evidence_count=1,
            evidence_article_ids=[1],
            evidence_published_dates=['2026-05-26'],
        )
        recs = [_make_recommendation(symbol='000001', name='平安银行',
                                     direct_mentions=1, independent_evidence_count=1)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=[],
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        assert result['stock_checks'][0]['status'] == CROSS_STATUS_WEAK

    def test_cross_article_keyword_conflict_detected(self):
        """跨文章正负关键词并存应返回 conflicted"""
        articles = [
            _make_article(1, title='平安银行订单大增', summary='获得大额订单利好',
                          published='2026-05-26'),
            _make_article(2, title='平安银行被调查', summary='收到监管调查通知',
                          published='2026-05-26'),
        ]
        cs = _make_candidate_stock(
            symbol='000001', name='平安银行', source_type='direct_news',
            direct_mentions=2, independent_evidence_count=2,
            evidence_published_dates=['2026-05-26', '2026-05-26'],
        )
        recs = [_make_recommendation(symbol='000001', name='平安银行',
                                     direct_mentions=2, independent_evidence_count=2)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=[],
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        assert result['stock_checks'][0]['status'] == CROSS_STATUS_CONFLICTED
        assert result['summary']['stocks_conflicted'] == 1

    def test_empty_inputs_returns_empty_result(self):
        """空输入返回空结果"""
        result = run_cross_verification(
            selected_articles=[],
            judgment_candidates=[],
            candidate_stocks=[],
            stock_recommendations=[],
            as_of_date='2026-05-26',
        )
        assert result['topic_checks'] == []
        assert result['stock_checks'] == []
        assert result['summary']['stocks_confirmed'] == 0

    def test_summary_counts_are_correct(self):
        """summary 统计各状态计数正确"""
        articles = [
            _make_article(1, published='2026-05-26', source_tier='official'),
            _make_article(2, published='2026-05-26', source_tier='mainstream'),
            _make_article(3, published='2026-05-26', source_tier='mainstream',
                          title='平安银行订单大增', summary='平安银行利好'),
        ]
        jc = [
            _make_judgment_candidate(
                topic='topic1', independent_evidence_count=2,
                mainstream_or_better_count=2,
                published='2026-05-26', article_ids=[1, 2],
            ),
            _make_judgment_candidate(
                topic='topic2', independent_evidence_count=1,
                mainstream_or_better_count=0, high_confidence_topic=False,
                published='2026-05-20', article_ids=[3],
            ),
        ]
        cs = _make_candidate_stock(
            symbol='000001', name='平安银行',
            direct_mentions=2, independent_evidence_count=2,
            evidence_published_dates=['2026-05-26', '2026-05-25'],
        )
        recs = [_make_recommendation(symbol='000001', name='平安银行',
                                     direct_mentions=2, independent_evidence_count=2)]
        result = run_cross_verification(
            selected_articles=articles,
            judgment_candidates=jc,
            candidate_stocks=[cs],
            stock_recommendations=recs,
            as_of_date='2026-05-26',
        )
        s = result['summary']
        assert s['topics_confirmed'] == 1
        assert s['topics_weak'] == 1
        assert s['topics_conflicted'] == 0
        assert s['stocks_confirmed'] == 1


# ---------------------------------------------------------------------------
# 摘要文本测试
# ---------------------------------------------------------------------------

class TestBuildSummary:
    def test_summary_contains_counts(self):
        result = {
            'topic_checks': [
                {'topic': 't1', 'status': 'confirmed'},
                {'topic': 't2', 'status': 'confirmed'},
                {'topic': 't3', 'status': 'weak'},
            ],
            'stock_checks': [
                {'symbol': 's1', 'name': 'n1', 'status': 'confirmed'},
                {'symbol': 's2', 'name': 'n2', 'status': 'weak'},
                {'symbol': 's3', 'name': 'n3', 'status': 'conflicted',
                 'conflict_detail': 'test conflict'},
            ],
            'summary': {
                'topics_confirmed': 2, 'topics_weak': 1, 'topics_conflicted': 0,
                'stocks_confirmed': 1, 'stocks_weak': 1, 'stocks_conflicted': 1,
            },
        }
        text = build_cross_verification_summary(result)
        assert '2 confirmed' in text
        assert '1 conflicted' in text
        assert 's3' in text


# ---------------------------------------------------------------------------
# 数据结构测试
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_topic_cross_check_to_dict(self):
        tc = TopicCrossCheck(
            topic='test',
            status=CROSS_STATUS_CONFIRMED,
            evidence_article_ids=[1, 2],
            independent_source_count=2,
            mainstream_or_better_count=1,
            has_fresh_evidence=True,
        )
        d = tc.to_dict()
        assert d['topic'] == 'test'
        assert d['status'] == CROSS_STATUS_CONFIRMED
        assert d['evidence_article_ids'] == [1, 2]

    def test_stock_cross_check_to_dict(self):
        sc = StockCrossCheck(
            symbol='000001',
            name='test',
            status=CROSS_STATUS_WEAK,
            direct_mentions=1,
            independent_source_count=1,
            has_fresh_evidence=False,
            source_type='direct_news',
        )
        d = sc.to_dict()
        assert d['symbol'] == '000001'
        assert d['status'] == CROSS_STATUS_WEAK


# ---------------------------------------------------------------------------
# Fix 1 回归：美股短 ticker 词边界匹配
# ---------------------------------------------------------------------------

class TestArticleMentionsSecurity:
    def test_us_ticker_not_falsely_matched(self):
        """短代码 GS 不应命中 ratings 等无关词。"""
        assert _article_mentions_security(
            'Goldman Sachs reports strong earnings', 'GS', 'Goldman Sachs'
        ) is True
        # ratings 不含 GS 的词边界
        assert _article_mentions_security(
            'Moody upgrades credit ratings for the bank', 'GS', 'Goldman Sachs'
        ) is False
        # things 不含 GS 的词边界
        assert _article_mentions_security(
            'Among other things the market rallied', 'GS', 'Goldman Sachs'
        ) is False

    def test_cn_symbol_matches_digit_code(self):
        """A 股 6 位数字码应正确匹配。"""
        assert _article_mentions_security(
            '平安银行(000001)今日大涨', '000001', '平安银行'
        ) is True

    def test_chinese_name_substring_match(self):
        """中文名称用子串匹配。"""
        assert _article_mentions_security(
            '贵州茅台业绩稳健增长', '600519', '贵州茅台'
        ) is True


# ---------------------------------------------------------------------------
# Fix 3 回归：overclaim 检查遍历所有出现位置
# ---------------------------------------------------------------------------

def test_overclaim_check_catches_second_occurrence():
    """第二个强措辞出现位置附近有 weak 标的名时也应被检测。"""
    from scripts.utils.quality_checker_v2 import _cross_verification_overclaim_check

    cross_verification = {
        'stock_checks': [
            {'symbol': 'GOOD', 'name': '强股', 'status': 'confirmed',
             'evidence_article_ids': [1]},
            {'symbol': 'WEAK', 'name': '弱股', 'status': 'weak',
             'evidence_article_ids': [2]},
        ],
        'topic_checks': [],
    }
    report_text = (
        "强股 多来源验证 这是对强股的描述。"
        "弱股 多来源验证 这是对弱股的不当宣称。"
    )
    issues = _cross_verification_overclaim_check(report_text, cross_verification)
    assert len(issues) >= 1
    assert any('弱股' in issue for issue in issues), \
        f"应检测到弱股被写成多来源验证，但 issues={issues}"


def test_overclaim_check_respects_confirmed():
    """confirmed 标的旁边的强措辞不应误报。"""
    from scripts.utils.quality_checker_v2 import _cross_verification_overclaim_check

    cross_verification = {
        'stock_checks': [
            {'symbol': 'GOOD', 'name': '强股', 'status': 'confirmed',
             'evidence_article_ids': [1]},
        ],
        'topic_checks': [],
    }
    report_text = "强股 多来源验证 这是正常描述。"
    issues = _cross_verification_overclaim_check(report_text, cross_verification)
    assert len(issues) == 0
