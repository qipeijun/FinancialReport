from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.run_acceptance import (
    analyze_mode_output,
    analyze_report_quality,
    detect_blocked_reason,
    validate_stock_recommendations_payload,
)
from scripts.utils.realtime_data_fetcher import RealtimeDataFetcher


def test_analyze_report_quality_accepts_well_formed_judgment_cards(tmp_path: Path):
    report_path = tmp_path / 'report.md'
    metadata_path = tmp_path / 'metadata.json'

    report_path.write_text(
        """# 高信号投资判断卡片

- 市场范围: 中国与全球联动
- 时间维度: 1-4周
- 状态: 正常

## 判断卡片

### 1. 美联储口径转松有利成长股风险偏好
- 影响市场: 美股科技与A股成长风格偏正面
- 时间维度: 1-4周
- 置信度: 中
- 支持证据: 【新闻1】与【新闻2】均提到通胀回落及收益率下行
- 反证/风险: 若后续通胀数据反弹，宽松预期可能逆转
- 后续验证点: 下次CPI与联储表态是否延续转松

## 观察项

- AI硬件景气: 当前仍需更多订单与财报交叉验证

## 证据摘要

两条主流来源支持流动性改善主线。
""",
        encoding='utf-8',
    )
    metadata_path.write_text(
        """{
  "output_mode": "judgment-cards",
  "articles_used": 8,
  "verification_enabled": true,
  "quality_check": {"score": 85, "passed": true},
  "thesis_count": 1,
  "watch_item_count": 1,
  "degraded": false
}
""",
        encoding='utf-8',
    )

    result = analyze_report_quality(
        report_path,
        metadata_path,
        mode='judgment-cards',
        realtime_data={'timestamp': '2099-01-01 00:00:00'},
    )

    assert result['required_sections']['判断卡片'] is True
    assert result['required_sections']['观察项'] is True
    assert result['metadata']['output_mode'] == 'judgment-cards'
    assert result['quality']['issues'] == []


def test_realtime_fetcher_force_failure_env_skips_all_network(monkeypatch):
    monkeypatch.setenv('FINANCIAL_REPORT_FORCE_REALTIME_FAILURE', '1')
    fetcher = RealtimeDataFetcher()

    data = fetcher.fetch_all()

    assert data['stocks'] == {}
    assert data['gold'] is None
    assert data['forex'] == {}


def test_analyze_report_quality_skip_live_does_not_fetch_external_data(tmp_path: Path, monkeypatch):
    report_path = tmp_path / 'report.md'
    metadata_path = tmp_path / 'metadata.json'

    report_path.write_text(
        """
## 市场概况
- 基于实时数据，现货黄金站上4700美元/盎司，美元兑人民币为6.8302。
        """.strip(),
        encoding='utf-8',
    )
    metadata_path.write_text(
        """{
  "output_mode": "markdown-report",
  "articles_used": 2,
  "verification_enabled": true,
  "quality_check": {"score": 80, "passed": true}
}
""",
        encoding='utf-8',
    )

    def fail_gold(self):
        raise AssertionError('skip-live 验收不应触发黄金实时请求')

    def fail_fx(self, pair):
        raise AssertionError(f'skip-live 验收不应触发汇率实时请求: {pair}')

    monkeypatch.setattr(RealtimeDataFetcher, 'get_gold_price', fail_gold)
    monkeypatch.setattr(RealtimeDataFetcher, 'get_forex_rate', fail_fx)

    result = analyze_report_quality(
        report_path,
        metadata_path,
        mode='markdown-report',
        realtime_data=None,
    )

    assert result['claims']['realtime'] >= 2
    assert result['quality']['stats']['has_realtime_data'] is False
    assert result['suspicious_realtime_phrases'] == []


def test_validate_stock_recommendations_payload_rejects_incomplete_high_grade():
    result = validate_stock_recommendations_payload(
        {
            'metadata': {
                'stock_recommendations': [],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
            },
            'stock_recommendations': [
                {
                    'symbol': 'sh600519',
                    'name': '贵州茅台',
                    'base_grade': '强关注',
                    'grade': '强关注',
                    'grade_caps': [],
                    'total_score': 85,
                    'scores': {
                        'news_catalyst': 25,
                        'technical': 20,
                        'valuation': 15,
                        'quality_risk': 15,
                        'market_regime': 10,
                    },
                    'data_completeness': 0.5,
                    'evidence_article_ids': [],
                    'candidate_confidence': 'high',
                    'evidence_strength': {
                        'direct_mentions': 0,
                        'independent_evidence_count': 0,
                        'source_tier_max': 'mainstream',
                    },
                    'industry_trend': {
                        'status': 'missing',
                        'direction': 'flat',
                        'score': 0,
                        'as_of': None,
                    },
                    'source_type': 'theme_mapping',
                }
            ],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
        }
    )

    assert result['passed'] is False
    assert result['high_grade_without_evidence'] >= 1
    assert result['strong_focus_with_incomplete'] == 1
    assert result['theme_mapping_strong_focus_count'] == 1
    assert result['output_json_schema_passed'] is True


def test_validate_stock_recommendations_payload_prefers_metadata_recommendations():
    result = validate_stock_recommendations_payload(
        {
            'metadata': {
                'stock_recommendations': [
                    {
                        'symbol': 'sh600519',
                        'name': '贵州茅台',
                        'base_grade': '关注',
                        'grade': '关注',
                        'grade_caps': [],
                        'total_score': 70,
                        'scores': {
                            'news_catalyst': 18,
                            'technical': 15,
                            'valuation': 15,
                            'quality_risk': 12,
                            'market_regime': 10,
                        },
                        'data_completeness': 0.9,
                        'evidence_article_ids': [1],
                        'candidate_confidence': 'high',
                        'evidence_strength': {
                            'direct_mentions': 1,
                            'independent_evidence_count': 2,
                            'source_tier_max': 'official',
                        },
                        'industry_trend': {
                            'status': 'available',
                            'direction': 'flat',
                            'score': 0,
                            'as_of': '2026-05-07',
                        },
                        'source_type': 'direct_news',
                    }
                ],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
            },
            'stock_recommendations': [
                {
                    'symbol': 'sz000977',
                    'name': '浪潮信息',
                    'base_grade': '强关注',
                    'grade': '强关注',
                    'grade_caps': [],
                    'total_score': 85,
                    'scores': {
                        'news_catalyst': 25,
                        'technical': 20,
                        'valuation': 15,
                        'quality_risk': 15,
                        'market_regime': 10,
                    },
                    'data_completeness': 0.95,
                    'evidence_article_ids': [],
                    'candidate_confidence': 'high',
                    'evidence_strength': {
                        'direct_mentions': 0,
                        'independent_evidence_count': 0,
                        'source_tier_max': 'mainstream',
                    },
                    'industry_trend': {
                        'status': 'missing',
                        'direction': 'flat',
                        'score': 0,
                        'as_of': None,
                    },
                    'source_type': 'theme_mapping',
                }
            ],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
        }
    )

    assert result['passed'] is True
    assert result['count'] == 1
    assert result['high_grade_without_evidence'] == 0


def test_analyze_mode_output_fails_when_structured_export_is_missing(tmp_path: Path):
    report_path = tmp_path / 'report.md'
    report_path.write_text("## 股票推荐评分\n", encoding='utf-8')

    result = analyze_mode_output(
        report_path=report_path,
        export_json_path=tmp_path / 'missing.json',
        mode='markdown-report',
        realtime_data=None,
    )

    assert result['passed'] is False
    assert '缺少结构化导出文件' in result['error']


def test_detect_blocked_reason_marks_missing_pytest():
    blocked = detect_blocked_reason(
        [
            {
                'name': 'pytest',
                'stderr_tail': '/tmp/venv/bin/python: No module named pytest\n',
            }
        ]
    )

    assert blocked == 'pytest_missing'
