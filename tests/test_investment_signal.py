from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.domain.investment_signal import (
    build_retry_feedback,
    build_judgment_candidates,
    enforce_judgment_rules,
)


def test_build_judgment_candidates_groups_high_value_articles():
    articles = [
        {
            'id': 1,
            'title': '美联储官员释放降息信号',
            'summary': '多位官员提到通胀回落与利率路径。',
            'content': '美联储官员表示未来几个季度可能讨论降息，美元与美债收益率承压。',
            'source': 'Federal Reserve Board',
            'source_tier': 'official',
            'content_quality_status': 'full',
            'investment_relevance': 'high',
            'is_original_source': 1,
        },
        {
            'id': 2,
            'title': '路透：美债收益率回落，成长股风险偏好回升',
            'summary': '市场交易员重新定价降息预期。',
            'content': '随着收益率回落，科技成长股风险偏好改善。',
            'source': 'Thomson Reuters',
            'source_tier': 'mainstream',
            'content_quality_status': 'full',
            'investment_relevance': 'high',
            'is_original_source': 1,
        },
    ]

    candidates = build_judgment_candidates(articles, max_candidates=5)

    assert len(candidates) == 1
    assert candidates[0]['topic'] == '宏观与流动性'
    assert candidates[0]['independent_evidence_count'] >= 1
    assert candidates[0]['high_confidence_topic'] is True


def test_enforce_judgment_rules_degrades_weak_thesis_to_watch_item():
    candidates = [
        {
            'candidate_id': 'C01',
            'topic': '科技与产业主题',
            'market_scope': ['A股'],
            'time_horizon': '2-6周',
            'evidence_count': 1,
            'independent_evidence_count': 1,
            'source_tier_max': 'aggregator',
            'high_confidence_topic': False,
            'original_source_count': 0,
            'articles': [],
            'priority_score': 8,
        }
    ]
    payload = {
        'theses': [
            {
                'candidate_id': 'C01',
                'hypothesis': 'AI 链条情绪可能继续扩散',
                'market_impact': 'A股科技成长',
                'confidence': '高',
            }
        ],
        'watch_items': [],
    }

    result = enforce_judgment_rules(
        payload,
        candidates,
        realtime_available=False,
        min_source_tier='mainstream',
        min_independent_evidence=2,
        degrade_on_weak_evidence=True,
        output_observation_only_when_weak=True,
        max_theses=5,
    )

    assert result['theses'] == []
    assert result['degraded'] is True
    assert len(result['watch_items']) == 1


def test_build_judgment_candidates_does_not_treat_aggregators_as_independent_confirmation():
    articles = [
        {
            'id': 1,
            'title': '芯片股继续走强',
            'summary': '聚合站点跟踪芯片板块表现。',
            'content': '芯片板块延续走强，市场继续交易 AI 算力。',
            'source': 'ZeroHedge',
            'source_tier': 'aggregator',
            'content_quality_status': 'full',
            'investment_relevance': 'high',
            'is_original_source': 0,
        },
        {
            'id': 2,
            'title': 'AI 算力景气延续',
            'summary': '另一家聚合站点继续引用相同主题。',
            'content': '聚合来源继续讨论芯片、算力与 AI 投资热度。',
            'source': 'ETF Trends',
            'source_tier': 'aggregator',
            'content_quality_status': 'full',
            'investment_relevance': 'high',
            'is_original_source': 0,
        },
    ]

    candidates = build_judgment_candidates(articles, max_candidates=5)

    assert len(candidates) == 1
    assert candidates[0]['topic'] == '科技与产业主题'
    assert candidates[0]['independent_evidence_count'] == 0
    assert candidates[0]['high_confidence_topic'] is False


def test_build_retry_feedback_outputs_targeted_fix_instructions():
    feedback = build_retry_feedback(
        {
            'issues': [
                '❌❌❌ 严重违规: AI编造目标涨幅 (25%),明确禁止!',
                '❌ 中科曙光 属于观察/非可行动层级，却在建议段落被写成明确动作建议',
                '❌ 正文出现结构化推荐层未支持的股票代码: sh600522',
                '❌ 正文出现未进入高置信候选的主题标题: 机器人主题',
                '❌ 把局部已验证断言扩写成整份报告已验证，超出了事实核查边界',
                '❌ 数据质量说明与真实文章分布不一致',
            ],
            'warnings': [],
        }
    )

    assert '目标涨幅' in feedback
    assert '中科曙光' in feedback
    assert 'sh600522' in feedback
    assert '机器人主题' in feedback
    assert '整份报告已验证' in feedback
    assert 'data_quality_stats' in feedback
