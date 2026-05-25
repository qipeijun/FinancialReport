# Financial-report 优化计划 v2.1（收缩落地版）

## 目标与边界

**目标**: 在"可信优先"链路不变的前提下，修复已确认的实现缺陷，收紧可验证的准确度，升级重试反馈的有效性。

**明确不做**:
- 不改变 acceptance 已写死的 contract（如 theme_only 禁升关注/强关注）
- 不扩张结构化 contract 的字段集合（不新增 signal_confidence / risk_management / position_size_guidance / risk_decomposition 等字段）
- 不上硬门禁式的幻觉统计（只做 warning/stats）
- 不上止损止盈、仓位指导、多维风险分解等"产品增强"

---

## 第一步：修 Bug（已确认的实现缺陷）

### 1.1 风险关键词误报

**文件**: `scripts/utils/stock_recommendation.py` L188

**根因**: `SecurityMasterProvider.build_candidates` 中：
```python
risk_flags = [kw for kw in NEGATIVE_RISK_KEYWORDS if kw in text]
```
`text` 是整篇文章的 title+summary+content 拼接。只要文章某处出现了"停牌""退市""亏损"等词，就会被关联到该文提及的**所有**股票上。5/13 报告中茅台/平安/宁德/浪潮信息全部被标"停牌；退市；亏损"即由此造成。

**修复方案**:
- 将全文匹配改为**句子级匹配**：按句号/换行切分文本，只在包含该股票名称或代码的句子中扫描风险关键词
- 如果风险关键词所在句子不包含该股票名称/代码，不计入该候选的 `risk_flags`
- 新增辅助方法 `_extract_risk_flags_for_symbol(text: str, symbol: str, name: str) -> List[str]`

**测试**: `test_stock_recommendation.py` 新增用例：构造一篇文章，文中提到"A公司退市"但未提及茅台，验证茅台不会被标记"退市"

---

### 1.2 NEWS_FACT 断言去重失效

**文件**: `scripts/utils/fact_checker.py` L120-L136

**根因**: `_dedupe_claims` 把 `normalized_context` 放入了去重 key。当同一数值（如"同比3.8%"）出现在报告中不同段落时（如"市场概况"和"投资主题"各提及一次），`context` 不同导致去重失败。

**修复方案**:
- 对于 `ClaimScope.NEWS_FACT` 类型的断言，去重 key 移除 `context`，改用 `(type, scope, extracted_value, asset_hint)`
- REALTIME_MARKET 类型保持不变（不同上下文中的同一实时数据可能代表不同的验证点）

**测试**: `test_fact_checker_quality.py` 新增用例：构造带重复 NEWS_FACT 值的报告文本，验证去重后只保留一条

---

## 第二步：准确度收紧（可验证的硬改进）

### 2.1 分层收紧事实核查容忍度

**文件**: `scripts/utils/fact_checker.py`

**当前容忍度**（报告末尾也写明了）:
- 价格 ≤5%、涨跌幅 ≤0.5% 绝对值、金价 ≤2%、汇率未显式设定

**收紧方案**（保持可验证，不引入硬门禁）:

| 断言类型 | 当前 | 收紧后 | 理由 |
|---------|------|--------|------|
| 指数价格 (sh000001/sz399001/sz399006) | 5% | 2% | 指数值精度高，5% 可跨日 |
| 个股价格 | 5% | 3% | 留余量应对日内波动 |
| 指数涨跌幅 | 0.5% | 0.3% | 指数涨跌幅通常精确到 0.01% |
| 个股涨跌幅 | 0.5% | 0.5% | 保持不变 |
| 金价 | 2% | 1% | Gold-API 返回精确值 |

- 新增**方向一致性校验**: 在 `_verify_price_change` 中，若断言文本含"涨/上涨/收涨"且实际 change_pct < 0（或反之），直接 `verified=False`，不受数值容忍度保护

**测试**: 更新现有 `test_fact_checker_quality.py` 中容忍度相关断言

### 2.2 AI 幻觉统计（warning 级别，不进硬门禁）

**文件**: `scripts/utils/fact_checker.py` — 新增 `_collect_implausible_signals`

**范围**: 仅产生统计数据，传入 `quality_checker_v2` 的 `stats`，作为 `quality_check['stats']['implausible_signals']` 的一部分，**不参与 pass/fail 判定**。

**检测项**:
- 过度精度计数：提取值含 3+ 位小数的断言数（如"涨3.817%"）
- 整数偏好计数：报告内以 .00/.50 结尾的值占总数值的比例
- 跨资产重复值：同一数值出现在 2+ 个不同 asset_hint 断言中的次数

现有 `quality_check` 字段已正确持久化到 metadata（如 `meta['quality_check']`），这些 stats 会自然跟随。

### 2.3 证据时间衰减加权

**文件**: `scripts/utils/stock_recommendation.py`

**修改**:
- `_score_news` (L1005-L1018): 当前 `evidence_bonus = min(count * 4, 12)` 对所有证据等权。改为按证据发布时间衰减：
  ```python
  weights = [max(0, 1.0 - days_old / 7) for days_old in evidence_ages]
  evidence_bonus = min(sum(w * 4 for w in weights), 12)
  ```
- `_has_fresh_evidence` (L920-L934): 已有逻辑检查 cross-day 重复 + 证据日期跨度 ≤3 天。新增一个条件：最新证据 > 2 天 → 视为非新鲜

**数据已就绪**: `CandidateStock.evidence_published_dates` 字段已存在，无需改 contract

---

## 第三步：重试反馈升级（低风险高收益）

### 3.1 针对性重试反馈

**文件**: `scripts/utils/investment_signal.py` — `build_retry_feedback` (L414-L423)

**当前**: 仅拼接 issues + warnings 列表，加一句通用提示。

**升级方案**: 按 `quality_checker_v2` 输出的问题类别，生成具体指令：

| 问题类别 | retry 指令 |
|---------|-----------|
| 编造目标价/目标涨幅 (fabrication) | "严禁在报告中出现'目标涨幅''目标价'等表述。若已写出，请删除包含这些词语的整段建议。" |
| 观察列表提升 (watchlist_promotion) | "以下股票在系统中为观察项，请将其建议措辞改为'继续观察'或'等待验证'：{股票列表}" |
| 不支持的股票提及 | "以下标的未在系统许可列表中，请从报告正文删除所有相关建议：{symbol 列表}" |
| 主题标题幻觉 | "报告中的'{topic}'主题在系统候选组中不存在或证据不足，请删除该主题段落或将其归入观察项" |
| 验证边界超声称 | "不得使用'整份报告已验证'或类似表述" |
| 数据完整性声明不匹配 | "请按系统提供的 data_quality_stats 准确描述数据质量分布" |

- 将上述指令**预置到重试 prompt 最前面**（而非追加到末尾），确保模型首先看到修正要求

**不改 contract**: `build_retry_feedback` 的签名和返回值格式不变

---

## 暂缓项（明确不做，或等回测后再议）

| 原方案项 | 现阶段结论 |
|---------|-----------|
| Phase 2.1 信号置信度评分 | 需在 structured contract 新增字段，暂缓 |
| Phase 2.2 止损/止盈价位 | 产品增强，非当前北极星 |
| Phase 2.3 仓位规模指导 | 同上 |
| Phase 2.4 多维风险分解 | 同上 |
| Phase 3.1 市场节假日感知 | 有价值但需独立评估，本次不纳入 |
| Phase 3.2 制度转换检测 | 同上 |
| Phase 3.3 跨日一致性追踪 | 同上 |
| Phase 3.4 数据质量监控 | 同上 |
| Phase 4 回测框架 | 等历史 archive 中 scoring 语义稳定（actionability_passed 引入后的样本积累足够）再做 |
| "零可行动标的"问题 | 不是缺陷，是 acceptance contract 的正常表现 |

---

## 修改文件清单

| 文件 | 改动内容 | 风险 |
|------|---------|------|
| `scripts/utils/stock_recommendation.py` | 1.1 风险关键词句子级匹配 + 2.3 证据衰减 | 低：只改匹配粒度，不改变量/contract |
| `scripts/utils/fact_checker.py` | 1.2 NEWS_FACT 去重 + 2.1 容忍度分层 + 2.2 幻觉 stats | 低-中：去重改 key 需测边界；容忍度是数值变更 |
| `scripts/utils/investment_signal.py` | 3.1 针对性 retry 反馈 | 低：只改字符串模板 |
| `tests/test_stock_recommendation.py` | 新增风险关键词精准匹配 + 衰减加权用例 | — |
| `tests/test_fact_checker_quality.py` | 新增 NEWS_FACT 去重 + 容忍度边界 + 方向一致性用例 | — |

---

## 验证步骤

1. `python -m pytest tests/test_stock_recommendation.py tests/test_fact_checker_quality.py -v` — 新老测试全绿
2. `python -m pytest tests/ -v` — 全量回归
3. `python scripts/run_acceptance.py` — 端到端验收，确保 acceptance contract 不变
