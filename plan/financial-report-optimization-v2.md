# Financial-report 优化计划 v2：提升准确度、可预判性、可靠性、投资胜率

## Context

当前分支 `codex/git-0506` 完成了 v1.5 股票推荐引擎增强（严格门控、跨日意识、叙述护栏、决策视图）。审查 5/12 和 5/13 的实际报告输出后，发现以下现有缺陷需优先修复，同时设计了四阶段优化方案。

**审查发现的关键缺陷**:
1. 风险标记误报：浪潮信息、茅台、宁德、平安均被标为"停牌；退市；亏损"——`NEGATIVE_RISK_KEYWORDS` 匹配未限定文章是否针对该股票
2. 事实核查 NEWS_FACT 去重失效："同比3.8%"在同一报告中出现两次
3. `backtest_ready` 在 enhanced-context JSON 中为 `null`，回测器不应依赖
4. metadata JSON 中 `quality_score` 为 `null`，质量评分未持久化
5. 5/13 零可行动标的，中科曙光总分 85 但因纯主题映射被压到"观察"——系统可能过度保守

---

## Phase 0 — 紧急 Bug 修复（先于新功能）

### 0.1 修复风险关键词误报

**文件**: `scripts/utils/stock_recommendation.py` — `_score_risk`

**问题**: `NEGATIVE_RISK_KEYWORDS` 匹配到文章中的关键词后，会关联到同一文章中出现的所有股票。例如某文提到"XX公司退市"，该文也被用于茅台/平安的证据列表，导致这些股票被标记"退市"风险。

**修复**:
- 风险关键词匹配时，检查关键词所在句子是否包含了该股票的名称或代码
- 如果关键词来源文章不在 `candidate.evidence_article_ids` 中，不计入该候选的风险标记
- 新增 `_is_risk_keyword_about_stock(keyword, sentence, candidate) -> bool` 辅助方法

### 0.2 修复 NEWS_FACT 断言去重

**文件**: `scripts/utils/fact_checker.py` — `_dedupe_claims`

**问题**: 报告中"同比3.8%"出现两次，说明 NEWS_FACT 类型的去重 key 不充分——当两个断言的 `context` 不同行但内容相同时，应合并。

**修复**:
- NEWS_FACT 类型断言的去重 key 中移除 `context`，改用 `(type, scope, extracted_value, asset_hint)`
- 或保留 context 但先规范化数值部分

### 0.3 修复 quality_score 元数据持久化

**文件**: `scripts/utils/report_generator.py` — `generate` 方法中 `save_metadata` 调用处

**问题**: metadata JSON 中 `quality_score` 为 `null`。

**修复**:
- 在质量检查完成后，将 `quality_result['score']` 写入 `metadata['quality_score']`
- 将 `quality_result['stats']` 写入 `metadata['quality_stats']`
- 将 `quality_result['issues']` / `warnings` 写入 `metadata['quality_issues']` / `quality_warnings`

---

## Phase 1 — 准确度提升

### 1.1 收紧事实核查容忍度 + 跨日陈旧数据检测

**文件**: `scripts/utils/fact_checker.py`

**修改**:
- `_verify_stock_price`: 指数类 5%→2%，个股 5%→3%
- `_verify_price_change`: 指数 0.5%→0.3% 绝对值，新增**方向一致性校验**（断言说"涨"但实际为跌→直接拒绝）
- `_verify_gold_price`: 2%→1%
- 新增 `_detect_stale_claim`: 将断言值与 price_history 缓存中 T-1/T-2 收盘价对比，匹配历史值而非当日值 → 标记 `likely_stale_data`
- 新增 `IMPOSSIBLE_VALUE_RANGES`: 上证 > 10000、金价 < 500 等物理不可能的值直接拒绝

### 1.2 AI 幻觉数字统计检测

**文件**: `scripts/utils/fact_checker.py` — 新增方法 `_detect_implausible_claims`

**修改**:
- **过度精度检测**: 3+ 位小数的断言（真实金融数据极少有此精度）→ 自动降置信度
- **整数偏好检测**: 报告内数值高比例以 .00/.50/.25 结尾 → 标记
- **重复值检测**: 同一数值出现在不同资产的断言中 → 强幻觉信号
- 输出 `implausible_claims` 列表传入 quality_checker_v2 统计

### 1.3 证据时间衰减加权

**文件**: `scripts/utils/stock_recommendation.py`

**修改**:
- `CandidateStock` 新增 `evidence_decay_weights: List[float]`
- `_score_news`: `evidence_bonus = sum(min(w * 4, 12) for w in decay_weights)` 替代 `count * 4`
- 衰减函数: `weight = max(0, 1.0 - (days_old / 7))`
- `_has_fresh_evidence`: 最新证据 > 2 天也视为非新鲜

### 1.4 针对性重试反馈

**文件**: `scripts/utils/investment_signal.py` — `build_retry_feedback`

**修改**:
- 按问题类别生成具体修复指令：
  - 编造目标价/涨幅：列出禁止模式 + "删除该建议段落"
  - 观察列表提升：列出股票名 + "降级为'继续观察'"
  - 不支持股票提及：列出 symbol + "从正文删除"
  - 主题标题幻觉：列出虚假主题 + "删除或改为观察项"
  - 验证边界超声称：禁止"整份报告已验证"
- 修复指令预置到重试 prompt 最前面

---

## Phase 2 — 可预判性 + 决策增强

### 2.1 信号置信度评分

**文件**: `scripts/utils/stock_recommendation.py`

**修改**:
- 新增 `_compute_signal_confidence(item) -> Dict`，0-100 分 + 分解因子：
  - `source_diversity` (30%): 来源层级熵值
  - `cross_day_consistency` (25%): 近几日是否持续出现且方向一致
  - `score_margin` (25%): 总分超出等级门槛的余量
  - `evidence_recency` (20%): 证据平均天数
- 输出 `signal_confidence: very_high / high / medium / tentative`
- 新增"高置信观察"中间层：置信度高但缺直接证据的标的 → `conditional_watchlist` 中细分标记，不作为完全不可行动

### 2.2 止损/止盈价位建议

**文件**: `scripts/utils/stock_recommendation.py`

**修改**:
- `_score_single_candidate` 新增 `risk_management` 字段：
  - 止损: `min(boll_lower, ma20)` — 具体价位
  - 止盈: `boll_upper` — 配合 RSI > 75
  - 移动止损: 动量正向 → 10日均线
  - 风险回报比计算
- 在 `render_stock_recommendation_markdown` 新增"风险管理"章节
- 数据不完整时不输出具体价位，仅定性指导

### 2.3 仓位规模指导

**文件**: `scripts/utils/stock_recommendation.py` + `report_generator.py`

**修改**:
- 新增 `position_size_guidance` 字段：
  - `very_high` → 3-5% 组合仓位
  - `high` → 2-3%
  - `medium` → 1-2%
  - `tentative` → 仅观察
  - 受风险评分和市场环境调节
- 全局约束：所有可行动建议总仓位不超组合 20%
- 在结构化推荐摘要中渲染

### 2.4 多维风险分解

**文件**: `scripts/utils/stock_recommendation.py` — `_score_risk`

**修改**:
- 新增维度：
  - **流动性风险**: `volume_ratio_5_20 < 0.3` → 标记 `low_liquidity`
  - **Beta 风险**: 60 根 bar 计算个股 vs sh000001 滚动 beta；beta > 1.5 → "高贝塔"
  - **集中度风险**: 同行业 3+ actionable
  - **事件风险**: 所有证据来自同一天 → 标记 `thin_evidence`
- 输出 `risk_decomposition: Dict[str, float]`
- "强关注"最低风险分 → 8/15

---

## Phase 3 — 系统性可靠性

### 3.1 市场节假日感知

**文件**: 新增 `scripts/utils/china_market_calendar.py`

**修改**:
- `data/china_trading_calendar.json`：2025-2027 A股节假日
- `PriceHistoryProvider.fetch_history`: 非交易日使用上一交易日数据，标记 `market_closed`
- `FactChecker`: 非交易日放宽容忍度 1.5x
- `report_generator.generate`: 添加"今日A股休市"提示到 prompt context

### 3.2 市场制度转换检测

**文件**: `scripts/utils/stock_recommendation.py` — `fetch_market_regime`

**修改**:
- 新增 `regime_stability: stable / transitioning / volatile`
- 计算：当前 MA20/MA60 交叉方向 vs 5 天前 + 20日波动率分位数
- `volatile` 时降低 regime_score 贡献，强关注门槛 80→85

### 3.3 跨日推荐一致性追踪

**文件**: `scripts/utils/stock_recommendation.py`

**修改**:
- `_load_recent_enhanced_contexts` 提取前一日各股票 grade
- 新增 `day_over_day_grade_change: improved / stable / degraded`
- 等级下降 → 添加风险标记

### 3.4 数据质量监控

**文件**: 新增 `scripts/utils/data_quality_monitor.py`

**修改**:
- `DataQualityMonitor` 类：
  - API 健康追踪 (持久化 `data/market_cache/api_health.json`)
  - 文章量异常检测（< 20日均值 50% → 告警）
  - 估值覆盖度追踪（< 60% → 告警）
  - 行业趋势覆盖度追踪
- 在 `report_generator.generate` 中集成，异常时注入保守化提示到 prompt
- 输出到 metadata JSON

---

## Phase 4 — 回测验证（数据驱动的参数校准）

### 4.1 推荐回测框架

**文件**: 新增 `scripts/utils/backtester.py`

**数据源**: `docs/archive/*/metadata/*enhanced-context*.json`（直接扫描文件系统，不依赖 `backtest_ready` 字段）

**修改**:
- `RecommendationBacktester` 类：
  - 扫描 `docs/archive/` 下所有日期的 enhanced-context JSON
  - 提取每日 `stock_recommendations`（symbol, grade, total_score, decision_view, as_of_date）
  - 用 `PriceHistoryProvider` 计算前向收益：1周(5交易日)/2周(10交易日)/4周(20交易日)
  - 按等级、行业、五分位分组统计：
    - 命中率（正收益比例）
    - 平均前向收益
    - 收益标准差 / Sharpe 类比率
    - 最大回撤
  - 输出 `backtest_summary.json`
  - **校准建议**: 自动检测各参数阈值的最优值（如"强关注总分门槛 80→85，命中率从 X%→Y%"）
- CLI 入口: `python scripts/utils/backtester.py --from 2026-01-01 --to 2026-05-13`

---

## 修改文件总览

| 文件 | Phase | 类型 |
|------|-------|------|
| `scripts/utils/stock_recommendation.py` | 0-3 | 风险误报修复 + 衰减 + 置信度 + 止损 + 仓位 + 多维风险 + 制度转换 + 跨日一致性 |
| `scripts/utils/fact_checker.py` | 0-1 | 去重修复 + 容忍度 + 陈旧检测 + 幻觉检测 |
| `scripts/utils/investment_signal.py` | 1 | 针对性重试反馈 |
| `scripts/utils/report_generator.py` | 0-3 | 质量分数持久化 + 仓位渲染 + 节假日提示集成 |
| `scripts/utils/quality_checker_v2.py` | 1 | 幻觉计数集成 |
| `scripts/utils/china_market_calendar.py` | 3 | **新建** |
| `scripts/utils/data_quality_monitor.py` | 3 | **新建** |
| `scripts/utils/backtester.py` | 4 | **新建** |
| `data/china_trading_calendar.json` | 3 | **新建** |
| `tests/` | 0-4 | 新增测试用例 |

## 验证步骤

每个 Phase 完成后：
1. `python -m pytest tests/ -v` — 确保无回归
2. 新增测试覆盖新功能和已修复的 bug：
   - Phase 0: `test_stock_recommendation.py` 新增风险关键词精准匹配用例；`test_fact_checker_quality.py` 新增 NEWS_FACT 去重用例
   - Phase 1: `test_fact_checker_quality.py` 新增陈旧数据检测、幻觉检测、方向一致性用例
   - Phase 2: `test_stock_recommendation.py` 新增置信度评分、止损止盈、仓位指导、风险分解用例
   - Phase 3: 新增 `test_market_calendar.py`, `test_data_quality_monitor.py`
   - Phase 4: 新增 `test_backtester.py`
3. `python scripts/run_acceptance.py` — 端到端验收
4. Phase 4: `python scripts/utils/backtester.py --from 2026-01-01 --to 2026-05-13` — 回测校准
