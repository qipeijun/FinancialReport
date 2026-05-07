from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.utils.investment_signal import (
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
