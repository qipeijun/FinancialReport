from pathlib import Path
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.run_acceptance import analyze_report_quality
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
