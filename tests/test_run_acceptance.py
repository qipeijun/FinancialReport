from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_acceptance as acceptance_module

from scripts.run_acceptance import (
    analyze_mode_output,
    analyze_report_quality,
    detect_blocked_reason,
    normalize_export_payload,
    update_acceptance_summary,
    validate_claim_ledger,
    validate_counter_evidence,
    validate_coverage_matrix,
    validate_evidence_diversity,
    validate_evidence_audit,
    validate_source_citations,
    validate_stock_recommendations_payload,
)
from scripts.infrastructure.realtime_data_fetcher import RealtimeDataFetcher


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
                'decision_views': {
                    'actionable_candidates': [],
                    'conditional_watchlist': [],
                    'stale_or_rejected': [],
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
                    'stale_opportunity_flag': True,
                    'crowding_flag': True,
                    'fresh_evidence_flag': False,
                    'actionability_passed': False,
                    'actionability_reasons': ['grade_not_actionable', 'no_fresh_evidence', 'stale_or_crowded', 'insufficient_independent_confirmation', 'theme_only_not_actionable'],
                    'source_type': 'theme_mapping',
                }
            ],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
        }
    )

    assert result['passed'] is False
    assert result['high_grade_without_evidence'] >= 1
    assert result['strong_focus_with_incomplete'] == 1
    assert result['theme_mapping_strong_focus_count'] == 1
    assert result['stale_high_grade_count'] == 1
    assert result['crowded_high_grade_count'] == 1
    assert result['theme_only_overgraded_count'] == 1
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
                        'stale_opportunity_flag': False,
                        'crowding_flag': False,
                        'fresh_evidence_flag': True,
                        'actionability_passed': True,
                        'actionability_reasons': [],
                        'validation_points': ['确认后续是否出现第二条独立个股证据或进一步官方/主流跟进'],
                        'catalyst_path': ['跟踪个股级直接催化是否继续被主流来源确认'],
                        'failure_triggers': ['若后续催化未兑现或证据链减弱，需要下调关注度'],
                        'source_type': 'direct_news',
                    }
                ],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
                'decision_views': {
                    'actionable_candidates': [
                        {'symbol': 'sh600519', 'grade': '关注'},
                    ],
                    'conditional_watchlist': [],
                    'stale_or_rejected': [],
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
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': False,
                    'actionability_passed': False,
                    'actionability_reasons': ['no_fresh_evidence', 'insufficient_independent_confirmation', 'theme_only_not_actionable'],
                    'source_type': 'theme_mapping',
                }
            ],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
        }
    )

    assert result['passed'] is True
    assert result['count'] == 1
    assert result['high_grade_without_evidence'] == 0
    assert result['decision_views_schema_passed'] is True


def test_validate_stock_recommendations_payload_warns_on_missing_forward_fields():
    result = validate_stock_recommendations_payload(
        {
            'metadata': {
                'stock_recommendations': [
                    {
                        'symbol': 'sh603019',
                        'name': '中科曙光',
                        'base_grade': '观察',
                        'grade': '观察',
                        'grade_caps': [],
                        'total_score': 60,
                        'scores': {
                            'news_catalyst': 18,
                            'technical': 14,
                            'valuation': 10,
                            'quality_risk': 10,
                            'market_regime': 8,
                        },
                        'data_completeness': 0.88,
                        'evidence_article_ids': [1],
                        'candidate_confidence': 'medium',
                        'evidence_strength': {
                            'direct_mentions': 1,
                            'independent_evidence_count': 1,
                            'source_tier_max': 'mainstream',
                        },
                        'industry_trend': {
                            'status': 'available',
                            'direction': 'up',
                            'score': 1,
                            'as_of': '2026-05-07',
                        },
                        'stale_opportunity_flag': False,
                        'crowding_flag': False,
                        'fresh_evidence_flag': True,
                        'actionability_passed': False,
                        'actionability_reasons': ['grade_not_actionable'],
                        'source_type': 'direct_news',
                    }
                ],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
                'decision_views': {
                    'actionable_candidates': [],
                    'conditional_watchlist': [
                        {'symbol': 'sh603019', 'grade': '观察'},
                    ],
                    'stale_or_rejected': [],
                },
            },
            'stock_recommendations': [],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
        }
    )

    assert result['passed'] is True
    assert result['missing_forward_fields_count'] == 3
    assert any('缺少 validation_points' in item for item in result['warnings'])


def test_validate_stock_recommendations_payload_rejects_non_actionable_item_inside_actionable_bucket():
    result = validate_stock_recommendations_payload(
        {
            'metadata': {
                'stock_recommendations': [
                    {
                        'symbol': 'sh603019',
                        'name': '中科曙光',
                        'base_grade': '关注',
                        'grade': '关注',
                        'grade_caps': [],
                        'total_score': 72,
                        'scores': {
                            'news_catalyst': 18,
                            'technical': 20,
                            'valuation': 12,
                            'quality_risk': 12,
                            'market_regime': 10,
                        },
                        'data_completeness': 0.9,
                        'evidence_article_ids': [1],
                        'candidate_confidence': 'high',
                        'evidence_strength': {
                            'direct_mentions': 1,
                            'independent_evidence_count': 1,
                            'source_tier_max': 'mainstream',
                        },
                        'industry_trend': {
                            'status': 'available',
                            'direction': 'up',
                            'score': 1,
                            'as_of': '2026-05-07',
                        },
                        'stale_opportunity_flag': False,
                        'crowding_flag': False,
                        'fresh_evidence_flag': False,
                        'actionability_passed': False,
                        'actionability_reasons': ['no_fresh_evidence'],
                        'validation_points': ['确认后续是否出现第二条独立个股证据或进一步官方/主流跟进'],
                        'catalyst_path': ['跟踪个股级直接催化是否继续被主流来源确认'],
                        'failure_triggers': ['若后续催化未兑现或证据链减弱，需要下调关注度'],
                        'source_type': 'direct_news',
                    }
                ],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
                'decision_views': {
                    'actionable_candidates': [
                        {'symbol': 'sh603019', 'grade': '关注'},
                    ],
                    'conditional_watchlist': [],
                    'stale_or_rejected': [],
                },
            },
            'stock_recommendations': [],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
        }
    )

    assert result['passed'] is False
    assert result['actionable_count'] == 1
    assert result['actionable_with_fresh_evidence_count'] == 0
    assert any('未通过 actionability 门槛却进入 actionable_candidates' in item for item in result['issues'])


def test_validate_stock_recommendations_payload_rejects_missing_decision_views():
    result = validate_stock_recommendations_payload(
        {
            'metadata': {
                'stock_recommendations': [
                    {
                        'symbol': 'sh603019',
                        'name': '中科曙光',
                        'base_grade': '观察',
                        'grade': '观察',
                        'grade_caps': [],
                        'total_score': 60,
                        'scores': {
                            'news_catalyst': 18,
                            'technical': 14,
                            'valuation': 10,
                            'quality_risk': 10,
                            'market_regime': 8,
                        },
                        'data_completeness': 0.88,
                        'evidence_article_ids': [1],
                        'candidate_confidence': 'medium',
                        'evidence_strength': {
                            'direct_mentions': 1,
                            'independent_evidence_count': 1,
                            'source_tier_max': 'mainstream',
                        },
                        'industry_trend': {
                            'status': 'available',
                            'direction': 'up',
                            'score': 1,
                            'as_of': '2026-05-07',
                        },
                        'stale_opportunity_flag': False,
                        'crowding_flag': False,
                        'fresh_evidence_flag': True,
                        'actionability_passed': False,
                        'actionability_reasons': ['grade_not_actionable'],
                        'validation_points': ['确认后续是否出现第二条独立个股证据或进一步官方/主流跟进'],
                        'catalyst_path': ['跟踪个股级直接催化是否继续被主流来源确认'],
                        'failure_triggers': ['若后续催化未兑现或证据链减弱，需要下调关注度'],
                        'source_type': 'direct_news',
                    }
                ],
                'score_distribution': {},
                'scoring_config': {
                    'pool_mode': 'strict',
                    'value_acceptance_enabled': True,
                },
            },
            'stock_recommendations': [],
            'score_distribution': {},
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
            },
        }
    )

    assert result['passed'] is False
    assert result['decision_views_schema_passed'] is False
    assert any('decision_views' in item for item in result['issues'])


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


def test_validate_rejects_theme_only_cross_confirmed():
    """theme-only 标的不允许 cross_verification_status=confirmed"""
    payload = {
        'metadata': {
            'stock_recommendations': [
                {
                    'symbol': '688001',
                    'name': '某科技股',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 60,
                    'scores': {'news_catalyst': 20, 'technical': 15, 'valuation': 15, 'quality_risk': 5, 'market_regime': 5},
                    'data_completeness': 0.8,
                    'candidate_confidence': 'medium',
                    'evidence_strength': {
                        'direct_mentions': 0,
                        'independent_evidence_count': 1,
                        'source_tier_max': 'mainstream',
                        'cross_verification_status': 'confirmed',
                        'cross_verified_source_count': 1,
                        'cross_verification_reasons': [],
                    },
                    'industry_trend': 'neutral',
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': True,
                    'actionability_reasons': [],
                    'source_type': 'theme_mapping',
                    'evidence_article_ids': [1],
                }
            ],
            'decision_views': {
                'actionable_candidates': [
                    {'symbol': '688001', 'name': '某科技股', 'grade': '关注'}
                ],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        },
        'stock_recommendations': [],
        'score_distribution': {},
        'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        'decision_views': {},
    }
    result = validate_stock_recommendations_payload(payload)
    assert any('theme-only' in issue for issue in result['issues']), \
        f"应拒绝 theme-only cross confirmed，但 issues={result['issues']}"


def test_validate_rejects_conflicted_in_actionable():
    """conflicted 标的不允许 actionability_passed=True"""
    payload = {
        'metadata': {
            'stock_recommendations': [
                {
                    'symbol': '000001',
                    'name': '平安银行',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 70,
                    'scores': {'news_catalyst': 25, 'technical': 15, 'valuation': 15, 'quality_risk': 10, 'market_regime': 5},
                    'data_completeness': 0.9,
                    'candidate_confidence': 'high',
                    'evidence_strength': {
                        'direct_mentions': 2,
                        'independent_evidence_count': 2,
                        'source_tier_max': 'mainstream',
                        'cross_verification_status': 'conflicted',
                        'cross_verified_source_count': 2,
                        'cross_verification_reasons': ['cross_verification_conflicted'],
                    },
                    'industry_trend': 'positive',
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': True,
                    'actionability_reasons': [],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [1, 2],
                }
            ],
            'decision_views': {
                'actionable_candidates': [
                    {'symbol': '000001', 'name': '平安银行', 'grade': '关注'}
                ],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
            'cross_verification': {
                'topic_checks': [],
                'stock_checks': [
                    {
                        'symbol': '000001', 'name': '平安银行', 'status': 'conflicted',
                        'evidence_article_ids': [1, 2], 'direct_mentions': 2,
                        'independent_source_count': 2, 'has_fresh_evidence': True,
                        'source_type': 'direct_news',
                    }
                ],
                'summary': {'stocks_conflicted': 1},
            },
        },
        'stock_recommendations': [],
        'score_distribution': {},
        'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        'decision_views': {},
    }
    result = validate_stock_recommendations_payload(payload)
    assert any('conflicted' in issue and 'actionability_passed' in issue
               for issue in result['issues']), \
        f"应拒绝 conflicted + actionability_passed=True，但 issues={result['issues']}"


def test_validate_accepts_valid_cross_verification_metadata():
    """合法的 cross_verification metadata 应通过 schema 校验"""
    payload = {
        'metadata': {
            'stock_recommendations': [
                {
                    'symbol': '000001',
                    'name': '平安银行',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 75,
                    'scores': {'news_catalyst': 25, 'technical': 15, 'valuation': 15, 'quality_risk': 15, 'market_regime': 5},
                    'data_completeness': 0.9,
                    'candidate_confidence': 'high',
                    'evidence_strength': {
                        'direct_mentions': 2,
                        'independent_evidence_count': 2,
                        'source_tier_max': 'mainstream',
                        'cross_verification_status': 'confirmed',
                        'cross_verified_source_count': 2,
                        'cross_verification_reasons': [],
                    },
                    'industry_trend': 'positive',
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': True,
                    'actionability_reasons': [],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [1, 2],
                }
            ],
            'decision_views': {
                'actionable_candidates': [
                    {'symbol': '000001', 'name': '平安银行', 'grade': '关注'}
                ],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
            'cross_verification': {
                'topic_checks': [
                    {
                        'topic': '科技', 'status': 'confirmed',
                        'evidence_article_ids': [1, 2], 'independent_source_count': 2,
                        'mainstream_or_better_count': 2, 'has_fresh_evidence': True,
                    }
                ],
                'stock_checks': [
                    {
                        'symbol': '000001', 'name': '平安银行', 'status': 'confirmed',
                        'evidence_article_ids': [1, 2], 'direct_mentions': 2,
                        'independent_source_count': 2, 'has_fresh_evidence': True,
                        'source_type': 'direct_news',
                    }
                ],
                'summary': {'topics_confirmed': 1, 'stocks_confirmed': 1},
            },
        },
        'stock_recommendations': [],
        'score_distribution': {},
        'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        'decision_views': {},
    }
    result = validate_stock_recommendations_payload(payload)
    # 不应有 cross_verification 相关的 issue
    cv_issues = [i for i in result['issues'] if 'cross_verification' in i.lower()]
    assert len(cv_issues) == 0, f"不应有 cross_verification issue，但: {cv_issues}"


def test_validate_allows_legacy_artifact_without_cross_verification():
    """旧产物即使已有 output_mode/backtest_ready，也不强制要求新字段。"""
    payload = {
        'metadata': {
            'output_mode': 'markdown-report',
            'backtest_ready': True,
            'stock_recommendations': [
                {
                    'symbol': '000001',
                    'name': '平安银行',
                    'grade': '观察',
                    'base_grade': '观察',
                    'grade_caps': [],
                    'total_score': 60,
                    'scores': {'news_catalyst': 20, 'technical': 10, 'valuation': 10, 'quality_risk': 10, 'market_regime': 10},
                    'data_completeness': 0.8,
                    'candidate_confidence': 'medium',
                    'evidence_strength': {
                        'direct_mentions': 1,
                        'independent_evidence_count': 1,
                        'source_tier_max': 'mainstream',
                    },
                    'industry_trend': 'neutral',
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': False,
                    'actionability_reasons': ['insufficient_independent_confirmation'],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [1],
                }
            ],
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [
                    {'symbol': '000001', 'name': '平安银行', 'grade': '观察'}
                ],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        },
    }
    result = validate_stock_recommendations_payload(payload)
    assert not any('缺少 cross_verification' in issue for issue in result['issues'])


def test_validate_requires_cross_verification_when_marked_required():
    """生成器显式标记 required 时，缺少 cross_verification 必须失败。"""
    payload = {
        'metadata': {
            'cross_verification_required': True,
            'stock_recommendations': [
                {
                    'symbol': '000001',
                    'name': '平安银行',
                    'grade': '观察',
                    'base_grade': '观察',
                    'grade_caps': [],
                    'total_score': 60,
                    'scores': {'news_catalyst': 20, 'technical': 10, 'valuation': 10, 'quality_risk': 10, 'market_regime': 10},
                    'data_completeness': 0.8,
                    'candidate_confidence': 'medium',
                    'evidence_strength': {
                        'direct_mentions': 1,
                        'independent_evidence_count': 1,
                        'source_tier_max': 'mainstream',
                    },
                    'industry_trend': 'neutral',
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': False,
                    'actionability_reasons': ['insufficient_independent_confirmation'],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [1],
                }
            ],
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [
                    {'symbol': '000001', 'name': '平安银行', 'grade': '观察'}
                ],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
        },
    }
    result = validate_stock_recommendations_payload(payload)
    assert any('缺少 cross_verification' in issue for issue in result['issues'])


def test_source_citations_reject_placeholder_and_unknown_ids():
    metadata = {
        'source_references_required': True,
        'source_references': {
            'required': True,
            'article_ids': [101],
            'articles': [{'article_id': 101, 'source': '来源A', 'title': '标题A', 'published': '2026-05-28'}],
        },
    }

    result = validate_source_citations('事实来自【新闻101】，另一个来自【新闻X】和【新闻999】。', metadata)

    assert result['passed'] is False
    assert result['placeholder_citation_count'] == 1
    assert result['unresolved_ids'] == ['999']


def test_source_citations_required_report_must_use_real_ids():
    metadata = {
        'source_references_required': True,
        'source_references': {
            'required': True,
            'article_ids': [101],
            'articles': [{'article_id': 101, 'source': '来源A', 'title': '标题A', 'published': '2026-05-28'}],
        },
    }

    result = validate_source_citations('这里有结论，但没有真实新闻引用。', metadata)

    assert result['passed'] is False
    assert any('缺少真实 article_id' in issue for issue in result['issues'])


def test_normalize_export_payload_preserves_truth_source_contract():
    normalized = normalize_export_payload({
        'market': 'US',
        'source_references_required': True,
        'source_references': {'article_ids': [7], 'articles': []},
        'claim_ledger_required': True,
        'claim_ledger': {'summary': {'total_claims': 1}, 'claims': []},
        'coverage_matrix_required': True,
        'coverage_matrix': {'categories': {}},
        'evidence_diversity_required': True,
        'evidence_diversity': {'source_count': 3, 'topic_count': 2},
        'evidence_audit_required': True,
        'evidence_audit_path': '/tmp/audit.json',
    })

    metadata = normalized['metadata']
    assert metadata['source_references_required'] is True
    assert metadata['source_references']['article_ids'] == [7]
    assert metadata['claim_ledger_required'] is True
    assert metadata['coverage_matrix_required'] is True
    assert metadata['evidence_diversity_required'] is True
    assert metadata['evidence_diversity']['source_count'] == 3
    assert metadata['evidence_audit_required'] is True
    assert metadata['evidence_audit_path'] == '/tmp/audit.json'


def test_claim_ledger_schema_accepts_required_rows():
    result = validate_claim_ledger({
        'claim_ledger_required': True,
        'claim_ledger': {
            'required': True,
            'summary': {'total_claims': 1},
            'claims': [
                {
                    'claim_id': 'cn-claim-001',
                    'market': 'CN',
                    'claim_type': '涨跌幅断言',
                    'scope': '实时行情断言',
                    'content': '上证指数跌0.7%',
                    'verified': True,
                    'verification_status': 'verified',
                    'source': 'Yahoo Finance',
                    'realtime_source': 'Yahoo Finance',
                    'timestamp': '2026-05-28 10:00:00',
                    'freshness_status': 'timestamped',
                    'failure_reason': '',
                    'source_articles': [{'article_id': 101, 'source': '来源A', 'title': '标题A', 'published': '2026-05-28'}],
                }
            ],
        },
    })

    assert result['passed'] is True
    assert result['count'] == 1


def test_coverage_matrix_requires_all_core_categories():
    result = validate_coverage_matrix({
        'coverage_matrix_required': True,
        'coverage_matrix': {
            'required': True,
            'categories': {
                'macro_liquidity': {'status': 'sufficient'},
                'policy_regulation': {'status': 'partial'},
                'company_earnings': {'status': 'missing'},
                'industry_theme': {'status': 'sufficient'},
                'risk_event': {'status': 'partial'},
                'realtime_market': {'status': 'sufficient'},
            },
        },
    })

    assert result['passed'] is True


def test_evidence_diversity_rejects_concentration_pass_mismatch():
    result = validate_evidence_diversity({
        'evidence_diversity_required': True,
        'evidence_diversity': {
            'required': True,
            'market': 'US',
            'total_articles': 10,
            'source_count': 1,
            'topic_count': 1,
            'max_source_share': 0.9,
            'max_topic_share': 0.9,
            'max_aggregator_share': 0.9,
            'original_source_share': 0.0,
            'source_distribution': [{'name': 'ZeroHedge', 'count': 9, 'share': 0.9}],
            'topic_distribution': [{'name': '政策与监管', 'count': 9, 'share': 0.9}],
            'entity_distribution': [],
            'source_tier_distribution': [{'name': 'aggregator', 'count': 9, 'share': 0.9}],
            'concentration_flags': ['source_concentration', 'topic_concentration', 'aggregator_concentration'],
            'passed': True,
        },
    })

    assert result['passed'] is False
    assert any('passed=true' in issue for issue in result['issues'])
    assert result['concentration_flags'] == ['source_concentration', 'topic_concentration', 'aggregator_concentration']


def test_counter_evidence_schema_accepts_topic_rows():
    result = validate_counter_evidence({
        'counter_evidence_required': True,
        'counter_evidence_ledger': {
            'required': True,
            'market': 'US',
            'summary': {
                'topic_count': 1,
                'topics_with_counter_evidence': 1,
                'high_confidence_topics_with_counter_evidence': 1,
            },
            'topics': [
                {
                    'topic': '科技与产业主题',
                    'market': 'US',
                    'high_confidence_topic': True,
                    'evidence_article_ids': [1, 2],
                    'supporting_article_ids': [1],
                    'counter_article_ids': [2],
                    'counter_evidence_count': 1,
                    'positive_keywords': ['订单'],
                    'negative_keywords': ['调查'],
                    'status': 'mixed',
                }
            ],
        },
    })

    assert result['passed'] is True
    assert result['high_confidence_topics_with_counter_evidence'] == 1


def test_evidence_audit_schema_checks_path_and_market(tmp_path: Path):
    audit_path = tmp_path / 'audit.json'
    audit_path.write_text(
        """{
  "market": "CN",
  "source_references": {},
  "claim_ledger": {},
  "coverage_matrix": {},
  "evidence_diversity": {},
  "counter_evidence_ledger": {},
  "decision_views": {},
  "quality_check": {}
}
""",
        encoding='utf-8',
    )

    result = validate_evidence_audit({
        'market': 'CN',
        'evidence_audit_required': True,
        'evidence_audit_path': str(audit_path),
    })

    assert result['passed'] is True
    assert result['required'] is True


def test_evidence_audit_rejects_metadata_mismatch(tmp_path: Path):
    audit_path = tmp_path / 'audit.json'
    audit_path.write_text(
        """{
  "market": "CN",
  "source_references": {"article_ids": [101]},
  "claim_ledger": {"summary": {"total_claims": 1}},
  "coverage_matrix": {"categories": {"macro_liquidity": {"status": "partial"}}},
  "evidence_diversity": {"source_count": 2, "topic_count": 1, "max_source_share": 0.8, "max_topic_share": 1.0, "concentration_flags": ["source_concentration"]},
  "counter_evidence_ledger": {"summary": {"topic_count": 1, "high_confidence_topics_with_counter_evidence": 1}},
  "decision_views": {"actionable_candidates": []},
  "quality_check": {"passed": true, "score": 90}
}
""",
        encoding='utf-8',
    )

    result = validate_evidence_audit({
        'market': 'CN',
        'source_references_required': True,
        'source_references': {'article_ids': [202]},
        'claim_ledger_required': True,
        'claim_ledger': {'summary': {'total_claims': 2}},
        'coverage_matrix_required': True,
        'coverage_matrix': {'categories': {'macro_liquidity': {'status': 'sufficient'}}},
        'evidence_diversity_required': True,
        'evidence_diversity': {'source_count': 3, 'topic_count': 2, 'max_source_share': 0.4, 'max_topic_share': 0.5, 'concentration_flags': []},
        'counter_evidence_required': True,
        'counter_evidence_ledger': {'summary': {'topic_count': 2, 'high_confidence_topics_with_counter_evidence': 0}},
        'decision_views': {'actionable_candidates': [{'symbol': '000001'}]},
        'stock_recommendations': [{'symbol': '000001'}],
        'quality_check': {'passed': False, 'score': 70},
        'evidence_audit_required': True,
        'evidence_audit_path': str(audit_path),
    })

    assert result['passed'] is False
    assert any('source_references' in issue for issue in result['issues'])
    assert any('claim_ledger' in issue for issue in result['issues'])
    assert any('coverage_matrix' in issue for issue in result['issues'])
    assert any('evidence_diversity' in issue for issue in result['issues'])
    assert any('counter_evidence_ledger' in issue for issue in result['issues'])
    assert any('decision_views' in issue for issue in result['issues'])
    assert any('quality_check.passed' in issue for issue in result['issues'])


def test_market_acceptance_summary_keeps_cn_us_reports(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(acceptance_module, 'PROJECT_ROOT', tmp_path)
    base_report = {
        'passed': True,
        'artifacts': {
            'modes': {
                'markdown-report': {
                    'report_path': '/tmp/report.md',
                    'metadata_path': '/tmp/meta.json',
                    'quality': {'passed': True},
                    'stock_scoring': {'passed': True},
                    'metadata': {'cross_verification_required': True},
                    'source_citations': {'passed': True},
                    'claim_ledger': {'passed': True},
                    'coverage_matrix': {'passed': True},
                    'evidence_audit': {'required': True, 'passed': True},
                }
            },
            'freshness': {
                'markdown-report': {'fresh_artifacts': True},
            },
        },
    }

    update_acceptance_summary('2026-05-28', 'CN', tmp_path / 'cn.json', base_report)
    summary = update_acceptance_summary('2026-05-28', 'US', tmp_path / 'us.json', base_report)

    assert sorted(summary['markets'].keys()) == ['CN', 'US']
    assert summary['markets']['CN']['acceptance_report_path'].endswith('cn.json')
    assert summary['markets']['US']['acceptance_report_path'].endswith('us.json')
    assert summary['markets']['CN']['evidence_audit_passed'] is True
    assert summary['markets']['CN']['failure_reasons'] == []


def test_market_acceptance_summary_includes_failure_reasons(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(acceptance_module, 'PROJECT_ROOT', tmp_path)
    report = {
        'passed': False,
        'artifacts': {
            'modes': {
                'markdown-report': {
                    'report_path': '/tmp/report.md',
                    'metadata_path': '/tmp/meta.json',
                    'quality': {
                        'passed': False,
                        'issues': ['引用来源严重不足', '准确性严重不足'],
                    },
                    'stock_scoring': {
                        'passed': False,
                        'issues': ['AAPL 高等级推荐缺少最小独立证据'],
                    },
                    'metadata': {'cross_verification_required': True},
                    'source_citations': {'required': True, 'passed': False, 'issues': ['存在未回溯的新闻占位引用']},
                    'claim_ledger': {'required': True, 'passed': True},
                    'coverage_matrix': {'required': True, 'passed': True},
                    'evidence_diversity': {'required': True, 'passed': True},
                    'counter_evidence': {'required': True, 'passed': True},
                    'evidence_audit': {'required': True, 'passed': True},
                }
            },
            'freshness': {
                'markdown-report': {'fresh_artifacts': False},
            },
        },
    }

    summary = update_acceptance_summary('2026-05-28', 'US', tmp_path / 'us.json', report)
    reasons = summary['markets']['US']['failure_reasons']

    assert 'freshness: 未找到同日新鲜 markdown-report 产物' in reasons
    assert 'quality: 质量门禁未通过' in reasons
    assert 'stock_scoring: 结构化推荐门禁未通过' in reasons
    assert 'quality: 引用来源严重不足' in reasons
    assert 'stock_scoring: AAPL 高等级推荐缺少最小独立证据' in reasons
    assert 'source_citations: 存在未回溯的新闻占位引用' in reasons


def test_validate_rejects_weak_cross_verification_actionable_when_required():
    payload = {
        'metadata': {
            'cross_verification_required': True,
            'stock_recommendations': [
                {
                    'symbol': 'AAPL',
                    'name': 'Apple',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 70,
                    'scores': {'news_catalyst': 20, 'technical': 15, 'valuation': 15, 'quality_risk': 12, 'market_regime': 8},
                    'data_completeness': 0.9,
                    'candidate_confidence': 'high',
                    'evidence_strength': {
                        'direct_mentions': 1,
                        'independent_evidence_count': 1,
                        'source_tier_max': 'mainstream',
                        'cross_verification_status': 'weak',
                        'cross_verified_source_count': 1,
                        'cross_verification_reasons': [],
                    },
                    'industry_trend': {'status': 'available', 'direction': 'up', 'score': 1, 'as_of': '2026-05-28'},
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': True,
                    'actionability_reasons': [],
                    'validation_points': ['等待第二来源确认'],
                    'catalyst_path': ['跟踪主流来源确认'],
                    'failure_triggers': ['证据减弱'],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [101],
                }
            ],
            'decision_views': {
                'actionable_candidates': [{'symbol': 'AAPL', 'grade': '关注'}],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {'pool_mode': 'strict', 'value_acceptance_enabled': True},
            'cross_verification': {
                'topic_checks': [],
                'stock_checks': [
                    {'symbol': 'AAPL', 'status': 'weak', 'evidence_article_ids': [101]},
                ],
                'summary': {},
            },
        },
    }

    result = validate_stock_recommendations_payload(payload)

    assert result['passed'] is False
    assert any('未 confirmed' in issue for issue in result['issues'])


def test_validate_requires_material_evidence_for_actionable_when_enabled():
    payload = {
        'metadata': {
            'stock_recommendations': [
                {
                    'symbol': 'AMZN',
                    'name': 'Amazon',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 70,
                    'scores': {'news_catalyst': 20, 'technical': 15, 'valuation': 10, 'quality_risk': 15, 'market_regime': 10},
                    'data_completeness': 0.9,
                    'candidate_confidence': 'high',
                    'evidence_strength': {'direct_mentions': 2, 'independent_evidence_count': 2, 'source_tier_max': 'mainstream'},
                    'industry_trend': {'status': 'available', 'direction': 'up', 'score': 1, 'as_of': '2026-05-29'},
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': True,
                    'actionability_reasons': [],
                    'validation_points': ['确认实质催化'],
                    'catalyst_path': ['跟踪公司催化'],
                    'failure_triggers': ['证据减弱'],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [101],
                    'evidence_relevance_status': 'incidental_mention',
                    'evidence_relevance_reasons': ['sentence_mentions_symbol_but_no_material_catalyst'],
                    'historical_calibration_status': '样本不足',
                    'historical_forward_stats': {'sample_count': 0},
                }
            ],
            'decision_views': {
                'actionable_candidates': [{'symbol': 'AMZN'}],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
                'evidence_relevance_enabled': True,
                'historical_calibration_enabled': True,
            },
        },
    }

    result = validate_stock_recommendations_payload(payload)

    assert result['passed'] is False
    assert any('实质证据相关性' in issue for issue in result['issues'])
    assert any('direct_news 缺少实质个股证据' in issue for issue in result['issues'])


def test_validate_rejects_reverse_calibrated_high_grade():
    payload = {
        'metadata': {
            'stock_recommendations': [
                {
                    'symbol': 'NVDA',
                    'name': 'NVIDIA',
                    'grade': '关注',
                    'base_grade': '关注',
                    'grade_caps': [],
                    'total_score': 70,
                    'scores': {'news_catalyst': 20, 'technical': 15, 'valuation': 10, 'quality_risk': 15, 'market_regime': 10},
                    'data_completeness': 0.9,
                    'candidate_confidence': 'high',
                    'evidence_strength': {'direct_mentions': 2, 'independent_evidence_count': 2, 'source_tier_max': 'mainstream'},
                    'industry_trend': {'status': 'available', 'direction': 'up', 'score': 1, 'as_of': '2026-05-29'},
                    'stale_opportunity_flag': False,
                    'crowding_flag': False,
                    'fresh_evidence_flag': True,
                    'actionability_passed': False,
                    'actionability_reasons': ['cross_verification_not_confirmed'],
                    'validation_points': ['确认实质催化'],
                    'catalyst_path': ['跟踪公司催化'],
                    'failure_triggers': ['证据减弱'],
                    'source_type': 'direct_news',
                    'evidence_article_ids': [101],
                    'evidence_relevance_status': 'direct_material_news',
                    'evidence_relevance_reasons': ['material_keyword:earnings'],
                    'historical_calibration_status': '反向失效',
                    'historical_forward_stats': {'sample_count': 12, 'win_rate_10d': 35.0},
                }
            ],
            'decision_views': {
                'actionable_candidates': [],
                'conditional_watchlist': [{'symbol': 'NVDA'}],
                'stale_or_rejected': [],
            },
            'scoring_config': {
                'pool_mode': 'strict',
                'value_acceptance_enabled': True,
                'evidence_relevance_enabled': True,
                'historical_calibration_enabled': True,
            },
        },
    }

    result = validate_stock_recommendations_payload(payload)

    assert result['passed'] is False
    assert any('历史校准反向失效' in issue for issue in result['issues'])
