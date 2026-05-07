# A股推荐引擎价值优先完善方案

## Summary

目标不是机械补齐旧 plan，而是把当前 A 股推荐能力收敛成一个“少而准、可解释、可验收”的 v1.5：优先提升推荐质量，其次补齐计划闭环，最后让验收直接约束“有没有投资价值”。

默认策略定为：**严格收敛候选池 + 高等级强约束 + 价值代理指标验收**。实现后，系统应明显减少“泛主题映射带来的弱相关标的”，让 `关注/强关注` 只出现在证据链、催化、行情和风险说明都足够完整的股票上。

## Key Changes

### 1. 候选池收敛升级为“高价值优先”
- 主题映射不再对所有主题候选默认开放，只允许进入“高置信度主题候选组”的主题做映射。
- 高置信度主题定义固定为可计算规则，不留给实现者二次判断：
  - `source_tier_max >= mainstream`
  - `independent_evidence_count >= 2`
  - `evidence_count >= 2`
  - 主题下至少有 1 条文章的 `investment_relevance == high`
- 直接提及个股优先级始终高于主题映射股；若候选数超限，先保留直接提及股，再按主题映射优先级补齐。
- 主题映射股默认最高只能到 `观察`，只有同时满足“高置信度主题 + 存在个股级直接证据 + 风险项为空”时，才允许升到 `关注`；**主题映射股默认禁止 `强关注`**。
- 继续保留“单次最多 10 只、单主题最多 3 只”的硬限制，但在严格模式下把默认展示目标收敛到 `5-8` 只，避免推荐池失控。

### 2. 评分规则从“能打分”升级为“高等级难获得”
- 保留现有五维评分结构和分值上限，不推翻现有实现。
- 强化等级门槛，固定为：
  - `强关注` 必须同时满足：`总分 >= 80`、`news_catalyst >= 20`、`quality_risk >= 10`、`data_completeness >= 0.85`、有直接个股证据、无重大风险标签、非主题映射候选。
  - `关注` 必须同时满足：`总分 >= 65`、`news_catalyst >= 15`、`data_completeness >= 0.70`、有证据文章 ID。
  - 不满足以上硬条件时，即使总分达标，也按上限压到 `观察/回避`。
- 市场环境分补齐“行业趋势”输入，不再只看大盘指数和风格偏好：
  - 从本地 `theme_stock_map` 中已有行业标签出发，引入行业趋势快照缓存。
  - v1.5 不要求联网拉全量行业指数；允许用本地缓存或简化行业代理序列实现，但必须形成可计算的 `industry_trend` 字段并参与环境分。
- 风险解释层从“列风险”升级为“说明为什么只能观察/回避”：
  - 当发生压级时，在输出对象中增加 `grade_caps` 或等价字段，列出触发压级的原因，如“证据不足”“无估值基准”“主题映射仅观察”“数据完整度不足”等。
  - Judgment Cards 仍不输出完整评分表，但允许引用“该主题仅有观察级代表股”的状态结论。

### 3. 对外接口和产物结构补成“可消费、可追责”
- `stock_recommendations` 每个对象新增固定字段：
  - `candidate_confidence`: `high / medium / low`
  - `grade_caps`: 触发的压级原因数组
  - `evidence_strength`: 证据强度摘要对象，至少包含 `direct_mentions`, `independent_evidence_count`, `source_tier_max`
  - `industry_trend`: 行业趋势摘要，至少包含方向或状态
- `scoring_config` 增加：
  - `pool_mode: strict`
  - `theme_mapping_max_grade: watch`
  - `value_acceptance_enabled: true`
- `--output` JSON 固定作为回测/验收消费对象，要求：
  - 顶层保留 `stock_recommendations`, `score_distribution`, `scoring_config`, `metadata`
  - 不依赖 markdown 才能理解推荐结果
  - 每只股票都能从 JSON 直接读出“为什么推荐/为什么被压级/证据来自哪类来源”

### 4. 验收从“结构正确”升级为“价值代理指标通过”
- 在现有 `run_acceptance.py` 基础上新增一组“价值代理指标”硬校验，不通过则整体验收失败：
  - 高等级推荐不得缺少直接证据
  - 主题映射股不得输出 `强关注`
  - `关注/强关注` 必须至少满足最小独立证据数
  - 被压级的股票必须写出压级原因
  - 输出 JSON 必须通过结构校验，且字段可被后续回测直接消费
  - 推荐列表中“观察/回避”可存在，但若全部为弱证据主题映射且无直接提及股，应视为候选质量不足并给出告警
- 人工 checklist 调整为价值导向：
  - 推荐理由是否具体到催化与验证点
  - 风险是否能解释“不上强关注”
  - 观察级标的是不是只是“有主题、没个股证据”
  - 同一主题下是否出现重复、同质化推荐

## Test Plan

- 单元测试
  - 高置信度主题与非高置信度主题的分流
  - 主题映射股默认最高 `观察`，具备直接证据后最多升到 `关注`
  - `强关注` 的多条件硬门槛校验
  - 压级原因字段完整输出
  - 行业趋势参与市场环境分后，总分与等级变化可解释
- 集成测试
  - 强个股催化 + 完整证据 + 完整数据 -> `关注/强关注`
  - 强主题但无个股直接证据 -> 仅 `观察`
  - 仅技术面好看但无催化 -> 不得高等级
  - 无估值基准 / 无足够行情 / 风险标签命中 -> 明确压级且写出原因
- 产物测试
  - `markdown-report` 仍包含“股票推荐评分”与“个股解释卡”
  - `judgment-cards` 不混入完整评分表
  - `--output` JSON 回读校验通过，字段完整且无需解析 markdown
  - 验收脚本对“价值代理指标失败”能稳定报错

## Important Interface Changes

- 推荐对象新增：`candidate_confidence`, `grade_caps`, `evidence_strength`, `industry_trend`
- `scoring_config` 新增：`pool_mode`, `theme_mapping_max_grade`, `value_acceptance_enabled`
- 验收结果新增价值专项统计，如：
  - `theme_mapping_strong_focus_count`
  - `high_grade_without_direct_evidence`
  - `missing_grade_caps_count`
  - `output_json_schema_passed`

## Assumptions

- 本轮仍只服务 A 股，不引入港股/美股扩展。
- 不修改 SQLite 主业务表结构；新增信息仅进入 metadata、导出 JSON 和验收报告。
- 行业趋势允许先用本地缓存/代理实现，不要求这轮接入新的在线数据源。
- 这轮不做真实收益回测，但必须把“价值”前置成可执行代理指标，为下一轮历史回测留接口。
- 默认选择“严格收敛”策略；如果后续要扩池，只放宽 `观察` 层，不放宽 `关注/强关注` 的硬门槛。
