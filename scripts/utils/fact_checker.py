"""
AI报告事实核查器

功能:
1. 从报告中提取所有可验证的断言(价格、涨跌幅、数据等)
2. 对每个断言进行实时验证
3. 标注可信度和证据来源
4. 生成事实核查报告附加到AI报告末尾

目标: 杜绝AI虚假信息,确保报告中所有数据可追溯
"""

import re
from typing import Any, List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

from .realtime_data_fetcher import RealtimeDataFetcher, StockData, GoldData

logger = logging.getLogger(__name__)


class ClaimType(Enum):
    """断言类型"""
    STOCK_PRICE = "股价断言"          # "紫金矿业现价15.23元"
    PRICE_CHANGE = "涨跌幅断言"       # "涨幅2.5%"
    GOLD_PRICE = "金价断言"          # "金价突破2650美元"
    FOREX_RATE = "汇率断言"          # "美元兑人民币7.12"
    MACRO_DATA = "宏观数据断言"       # "PMI为49.8"
    COMPANY_EVENT = "公司事件断言"    # "紫金矿业发布财报"
    MARKET_TREND = "市场趋势断言"     # "黄金板块表现强势"


class ClaimScope(Enum):
    """断言验证范围"""
    REALTIME_MARKET = "实时行情断言"
    NEWS_FACT = "新闻事实断言"
    VIOLATION = "违规预测断言"


@dataclass
class Claim:
    """断言数据类"""
    type: ClaimType
    content: str                    # 原始断言文本
    extracted_value: Optional[str] = None  # 提取的关键值
    verified: bool = False
    confidence: float = 0.0         # 可信度 0-1
    evidence: str = ""              # 验证依据
    source: str = ""                # 数据来源
    timestamp: str = ""
    error: str = ""                 # 验证失败原因
    scope: ClaimScope = ClaimScope.REALTIME_MARKET
    context: str = ""               # 断言所在完整语句/行
    asset_hint: Optional[str] = None  # 目标资产提示，如 sh000001/gold/forex

    def to_dict(self) -> Dict:
        return {
            'type': self.type.value,
            'content': self.content,
            'extracted_value': self.extracted_value,
            'verified': self.verified,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'source': self.source,
            'timestamp': self.timestamp,
            'error': self.error,
            'scope': self.scope.value,
            'context': self.context,
            'asset_hint': self.asset_hint,
        }


class FactChecker:
    """事实核查器"""

    def __init__(self, realtime_fetcher: Optional[RealtimeDataFetcher] = None):
        """
        Args:
            realtime_fetcher: 实时数据采集器实例
        """
        self.fetcher = realtime_fetcher or RealtimeDataFetcher()

    @staticmethod
    def _normalize_number(value: str) -> str:
        """移除金融数字中的千分位逗号，保留小数精度。"""
        return str(value or '').replace(',', '').strip()

    def extract_claims(self, report_text: str) -> List[Claim]:
        """
        从报告中提取所有可验证的断言

        Args:
            report_text: AI生成的报告文本

        Returns:
            断言列表
        """
        claims = []

        # 1. 提取价格断言
        claims.extend(self._extract_price_claims(report_text))

        # 2. 提取涨跌幅断言
        claims.extend(self._extract_change_claims(report_text))

        # 3. 提取金价断言
        claims.extend(self._extract_gold_claims(report_text))

        # 4. 提取汇率断言
        claims.extend(self._extract_forex_claims(report_text))

        # 5. 提取宏观数据断言
        claims.extend(self._extract_macro_claims(report_text))

        # 6. 提取新闻事实断言（不纳入实时行情校验）
        claims.extend(self._extract_news_fact_claims(report_text))

        deduped = self._dedupe_claims(claims)
        logger.info(f"从报告中提取到 {len(deduped)} 个断言")
        return deduped

    def _dedupe_claims(self, claims: List[Claim]) -> List[Claim]:
        seen = set()
        result: List[Claim] = []
        for claim in claims:
            normalized_context = re.sub(r'[\s，。；：:,.]+', '', (claim.context or claim.content or ''))
            if claim.scope == ClaimScope.NEWS_FACT:
                key = (
                    claim.type.value,
                    claim.scope.value,
                    claim.asset_hint,
                    claim.extracted_value,
                )
            else:
                key = (
                    claim.type.value,
                    claim.scope.value,
                    claim.asset_hint,
                    claim.extracted_value,
                    normalized_context,
                )
            if key in seen:
                continue
            seen.add(key)
            result.append(claim)
        return result

    def collect_implausible_signals(self, claims: List[Claim]) -> Dict[str, object]:
        """统计可疑数字信号，仅用于 warning/stats，不参与通过判定。"""
        numeric_claims = [claim for claim in claims if claim.extracted_value and re.fullmatch(r'-?\d+\.?\d*', str(claim.extracted_value))]
        if not numeric_claims:
            return {
                'over_precision_count': 0,
                'rounded_ratio': 0.0,
                'cross_asset_repeated_value_count': 0,
            }

        over_precision_count = 0
        rounded_count = 0
        value_assets: Dict[str, set[str]] = {}
        for claim in numeric_claims:
            value = str(claim.extracted_value or '')
            if '.' in value and len(value.split('.', 1)[1]) >= 3:
                over_precision_count += 1
            if value.endswith('.00') or value.endswith('.50'):
                rounded_count += 1
            asset = claim.asset_hint or claim.type.value
            value_assets.setdefault(value, set()).add(asset)

        cross_asset_repeated_value_count = sum(1 for assets in value_assets.values() if len(assets) >= 2)
        return {
            'over_precision_count': over_precision_count,
            'rounded_ratio': round(rounded_count / len(numeric_claims), 3),
            'cross_asset_repeated_value_count': cross_asset_repeated_value_count,
        }

    def _extract_price_claims(self, text: str) -> List[Claim]:
        """提取价格断言"""
        claims = []

        # 模式: "现价XX元", "价格XX", "报XX元"
        patterns = [
            r'([\u4e00-\u9fa5]+)(?:现价|价格|报)(?:为)?[¥￥]?(\d+\.?\d*)\s*元',
            r'([\u4e00-\u9fa5]+)\((\d{6})\).*?(?:现价|价格)[¥￥]?(\d+\.?\d*)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                if len(groups) >= 2:
                    claims.append(Claim(
                        type=ClaimType.STOCK_PRICE,
                        content=match.group(0),
                        extracted_value=groups[-1],  # 价格值
                        context=match.group(0),
                        asset_hint=self._infer_asset_hint(match.group(0))
                    ))

        # 美股/指数常见写法: "道指收涨2.13%至$50,579.70"
        for line in text.splitlines():
            if not any(cue in line for cue in ('基于实时数据', '实时', '收涨', '收跌', '现价')):
                continue
            for clause in re.split(r'[，。；]', line):
                clause = clause.strip()
                asset_hint = self._infer_asset_hint(clause)
                if not asset_hint:
                    continue
                for match in re.finditer(r'(?:至|报|收于|站上|突破)\s*[$¥￥]?\s*([0-9,]+(?:\.\d+)?)', clause):
                    if asset_hint not in {'^DJI', '^GSPC', '^IXIC'} and '$' not in match.group(0):
                        continue
                    claims.append(Claim(
                        type=ClaimType.STOCK_PRICE,
                        content=match.group(0),
                        extracted_value=self._normalize_number(match.group(1)),
                        context=clause,
                        asset_hint=asset_hint,
                    ))

        return claims

    def _extract_change_claims(self, text: str) -> List[Claim]:
        """提取涨跌幅断言"""
        claims = []
        realtime_cues = (
            '基于实时数据', '实时', '现价', '收涨', '收跌',
            '上证指数', '深证成指', '创业板指', '黄金', '金价',
            '美元兑人民币', '汇率', '道指', '标普', '标普500',
            '纳指', 'S&P 500', 'NASDAQ', 'Dow Jones'
        )

        # 模式: "涨幅XX%", "上涨XX%", "下跌XX%", "涨XX%"
        patterns = [
            r'([涨跌]幅?)\s*(\+?-?\d+\.?\d*)\s*%',
            r'(上涨|下跌)\s*(\d+\.?\d*)\s*%',
            r'(收涨|收跌)\s*(\d+\.?\d*)\s*%',
            r'([\u4e00-\u9fa5]+)(?:涨|跌)\s*(\d+\.?\d*)\s*%',
        ]

        for line in text.splitlines():
            if not any(cue in line for cue in realtime_cues):
                continue
            for clause in re.split(r'[，。；]', line):
                clause = clause.strip()
                if not clause:
                    continue
                asset_hint = self._infer_asset_hint(clause)
                if asset_hint is None:
                    continue
                for pattern in patterns:
                    for match in re.finditer(pattern, clause):
                        claims.append(Claim(
                            type=ClaimType.PRICE_CHANGE,
                            content=match.group(0),
                            extracted_value=match.group(2) if len(match.groups()) >= 2 else match.group(1),
                            context=clause,
                            asset_hint=asset_hint,
                        ))

        # 特别检测: 目标涨幅(这是严重违规!)
        target_pattern = r'目标(?:涨幅|价格?)\s*(\d+\.?\d*)\s*%'
        for match in re.finditer(target_pattern, text):
            claims.append(Claim(
                type=ClaimType.PRICE_CHANGE,
                content=match.group(0),
                extracted_value=match.group(1),
                verified=False,
                confidence=0.0,
                error="❌❌❌ 严重违规: AI编造目标涨幅,明确禁止此类断言!",
                scope=ClaimScope.VIOLATION,
                context=match.group(0),
            ))

        return claims

    def _extract_gold_claims(self, text: str) -> List[Claim]:
        """提取金价断言"""
        claims = []

        # 模式: "金价XX美元", "黄金XX/盎司"
        patterns = [
            r'(?:金价|黄金价格?)(?:突破|达到|为|报)?(?:\$|美元)?\s*(\d+\.?\d*)\s*(?:美元)?(?:/盎司)?',
            r'黄金.*?(\d+\.?\d*)\s*美元',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                line = self._extract_line(text, match.start(), match.end())
                if '基于实时数据' not in line and '实时' not in line and '现货黄金' not in line and '黄金ETF' not in line:
                    continue
                claims.append(Claim(
                    type=ClaimType.GOLD_PRICE,
                    content=match.group(0),
                    extracted_value=match.group(1),
                    context=line,
                    asset_hint='gold',
                ))

        return claims

    def _extract_forex_claims(self, text: str) -> List[Claim]:
        """提取汇率断言"""
        claims = []

        # 模式: "美元兑人民币XX", "USD/CNY XX"
        patterns = [
            r'美元兑人民币(?:汇率)?(?:为|报)?\s*(\d+\.?\d*)',
            r'USD/CNY(?:为|报)?\s*(\d+\.?\d*)',
            r'人民币汇率(?:为|报)?\s*(\d+\.?\d*)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                line = self._extract_line(text, match.start(), match.end())
                if '基于实时数据' not in line and '实时' not in line and '汇率' not in line:
                    continue
                claims.append(Claim(
                    type=ClaimType.FOREX_RATE,
                    content=match.group(0),
                    extracted_value=match.group(1),
                    context=line,
                    asset_hint='USD/CNY',
                ))

        return claims

    def _extract_macro_claims(self, text: str) -> List[Claim]:
        """提取宏观数据断言"""
        claims = []

        # 模式: "PMI为XX", "GDP增长XX%", "CPI XX"
        patterns = [
            r'(PMI|GDP|CPI)(?:为|达到)?\s*(\d+\.?\d*)',
            r'(制造业PMI)\s*(\d+\.?\d*)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                claims.append(Claim(
                    type=ClaimType.MACRO_DATA,
                    content=match.group(0),
                    extracted_value=match.group(2) if len(match.groups()) >= 2 else match.group(1),
                    scope=ClaimScope.NEWS_FACT,
                    context=self._extract_line(text, match.start(), match.end()),
                ))

        return claims

    def _extract_news_fact_claims(self, text: str) -> List[Claim]:
        """提取新闻事实断言（只统计覆盖，不纳入实时行情校验）"""
        claims = []
        patterns = [
            (r'(?:同比|环比)(?:增长|上涨|下滑|下降)?\s*\+?(\d+\.?\d*)\s*%', False),
            (r'(?:营收|收入|净利润|利润)(?:同比|环比)(?:增长|上涨|下滑|下降)?\s*\+?(\d+\.?\d*)\s*%', False),
            (r'(?:非农就业|新增就业|融资|募资|订单|产能|销量|零售)\D{0,8}(\d+\.?\d*)\s*(万亿|亿|万|%)', False),
            (r'(?:指数|价格|收益率|汇率)\D{0,8}(\d+\.?\d*)\s*(点|美元|%|元)', False),
            (r'[$]\s*([0-9,]+(?:\.\d+)?)\s*(万|亿|百万|million|billion)?', True),
            (r'([0-9,]+(?:\.\d+)?)\s*%', True),
        ]

        for line in text.splitlines():
            if '基于实时数据' in line or '现价' in line or '收涨' in line or '收跌' in line:
                continue
            for pattern, requires_citation in patterns:
                if requires_citation and '【新闻' not in line:
                    continue
                for match in re.finditer(pattern, line):
                    value = next(
                        (
                            self._normalize_number(group)
                            for group in match.groups()
                            if re.fullmatch(r'[0-9,]+(?:\.\d+)?', str(group or ''))
                        ),
                        ''
                    )
                    claims.append(Claim(
                        type=ClaimType.MARKET_TREND,
                        content=match.group(0),
                        extracted_value=value,
                        scope=ClaimScope.NEWS_FACT,
                        context=line.strip(),
                    ))

        return claims

    def _extract_line(self, text: str, start: int, end: int) -> str:
        line_start = text.rfind('\n', 0, start) + 1
        line_end = text.find('\n', end)
        if line_end == -1:
            line_end = len(text)
        return text[line_start:line_end].strip()

    def _infer_asset_hint(self, text: str) -> Optional[str]:
        hint_map = {
            'sh000001': ['上证指数', '沪指', '上证'],
            'sz399001': ['深证成指', '深成指'],
            'sz399006': ['创业板指', '创业板'],
            '^DJI': ['道指', '道琼斯', 'Dow Jones', 'DJIA'],
            '^GSPC': ['标普500', '标普 500', '标普', 'S&P 500', 'S&P500'],
            '^IXIC': ['纳指', '纳斯达克', 'NASDAQ', 'Nasdaq'],
            'gold': ['黄金', '金价', '现货黄金', '黄金ETF'],
            'USD/CNY': ['美元兑人民币', 'USD/CNY', '汇率'],
        }
        for asset, cues in hint_map.items():
            if any(cue in text for cue in cues):
                return asset
        return None

    def verify_claims(self, claims: List[Claim], context_data: Optional[Dict] = None) -> List[Claim]:
        """
        批量验证断言

        Args:
            claims: 待验证的断言列表
            context_data: 上下文数据(可选),包含已获取的实时数据,避免重复请求

        Returns:
            验证后的断言列表
        """
        for claim in claims:
            if claim.error:  # 已标记为错误的跳过
                continue
            if claim.scope != ClaimScope.REALTIME_MARKET:
                claim.evidence = "新闻事实断言，不纳入实时行情校验"
                continue

            try:
                self._verify_single_claim(claim, context_data)
            except Exception as e:
                claim.error = f"验证异常: {str(e)}"
                logger.warning(f"验证断言失败: {claim.content} - {e}")

        verified_count = sum(1 for c in claims if c.verified)
        logger.info(f"验证完成: {verified_count}/{len(claims)} 个断言通过验证")

        return claims

    @staticmethod
    def build_claim_ledger(
        claims: List[Claim],
        *,
        market: str,
        selected_articles: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """把事实核查结果落成结构化断言账本，供报告、metadata 与验收共用。"""
        article_map = {
            str(article.get('id')): {
                'article_id': article.get('id'),
                'source': article.get('source'),
                'title': article.get('title'),
                'published': article.get('published') or article.get('collection_date'),
            }
            for article in (selected_articles or [])
            if article.get('id') is not None
        }

        rows: List[Dict[str, Any]] = []
        for index, claim in enumerate(claims, start=1):
            citation_ids = [
                item for item in re.findall(r'【新闻(\d+)】', claim.context or claim.content or '')
                if item in article_map
            ]
            verification_status = 'verified' if claim.verified else 'failed'
            freshness_status = (
                'timestamped'
                if claim.timestamp
                else ('missing_timestamp' if claim.scope == ClaimScope.REALTIME_MARKET else 'not_applicable')
            )
            rows.append({
                'claim_id': f'{market.lower()}-claim-{index:03d}',
                'market': market,
                'claim_type': claim.type.value,
                'scope': claim.scope.value,
                'content': claim.content,
                'context': claim.context,
                'asset_hint': claim.asset_hint,
                'extracted_value': claim.extracted_value,
                'verified': claim.verified,
                'verification_status': verification_status,
                'confidence': claim.confidence,
                'source': claim.source,
                'realtime_source': claim.source if claim.scope == ClaimScope.REALTIME_MARKET else '',
                'timestamp': claim.timestamp,
                'freshness_status': freshness_status,
                'evidence': claim.evidence,
                'failure_reason': claim.error or ('' if claim.verified else claim.evidence),
                'source_articles': [article_map[item] for item in citation_ids],
            })

        realtime_claims = [claim for claim in claims if claim.scope == ClaimScope.REALTIME_MARKET]
        news_claims = [claim for claim in claims if claim.scope == ClaimScope.NEWS_FACT]
        return {
            'required': True,
            'market': market,
            'summary': {
                'total_claims': len(claims),
                'realtime_claims': len(realtime_claims),
                'verified_realtime_claims': sum(1 for claim in realtime_claims if claim.verified),
                'news_fact_claims': len(news_claims),
                'failed_claims': sum(1 for claim in realtime_claims if not claim.verified),
            },
            'claims': rows,
        }

    def _skip_live_fetch(self, context_data: Optional[Dict] = None) -> bool:
        return bool(context_data and context_data.get('_skip_live_fetch'))

    def _verify_single_claim(self, claim: Claim, context_data: Optional[Dict] = None):
        """验证单个断言"""

        if claim.type == ClaimType.STOCK_PRICE:
            self._verify_stock_price(claim, context_data)

        elif claim.type == ClaimType.PRICE_CHANGE:
            # 检查是否是"目标涨幅"(已在提取时标记)
            if '目标' in claim.content:
                return  # 已标记为错误

            self._verify_price_change(claim, context_data)

        elif claim.type == ClaimType.GOLD_PRICE:
            self._verify_gold_price(claim, context_data)

        elif claim.type == ClaimType.FOREX_RATE:
            self._verify_forex_rate(claim, context_data)

        elif claim.type == ClaimType.MACRO_DATA:
            # 宏观数据需要专门的数据源,暂时标记为"无法验证"
            claim.verified = False
            claim.confidence = 0.5
            claim.evidence = "宏观数据暂无实时验证源,建议人工核查"

    def _verify_stock_price(self, claim: Claim, context_data: Optional[Dict] = None):
        """验证股价断言"""
        if not claim.extracted_value:
            return

        try:
            claimed_price = float(self._normalize_number(claim.extracted_value))

            # 从上下文获取股票数据(避免重复API调用)
            stocks_data = context_data.get('stocks', {}) if context_data else {}

            # 如果上下文中没有,需要实时获取(提取股票代码)
            if not stocks_data:
                # 简化: 暂时跳过,因为无法准确匹配股票
                claim.evidence = "缺少实时数据上下文,无法验证"
                return

            candidate_codes = [claim.asset_hint] if claim.asset_hint in stocks_data else list(stocks_data.keys())

            # 查找匹配的股票
            for code in candidate_codes:
                stock_dict = stocks_data.get(code) or {}
                actual_price = stock_dict.get('price', 0)

                tolerance = 0.02 if code in {'sh000001', 'sz399001', 'sz399006', '^DJI', '^GSPC', '^IXIC'} else 0.03
                if actual_price > 0:
                    diff_pct = abs(actual_price - claimed_price) / actual_price

                    if diff_pct < tolerance:
                        claim.verified = True
                        claim.confidence = 1.0 - diff_pct
                        claim.evidence = f"实时数据验证: {actual_price:.2f} (误差 {diff_pct*100:.1f}%)"
                        claim.source = "Yahoo Finance"
                        claim.timestamp = stock_dict.get('timestamp', '')
                        return

            claim.verified = False
            claim.confidence = 0.0
            claim.evidence = f"实时数据不符或未找到对应股票"

        except ValueError:
            claim.error = "价格格式错误"

    def _verify_price_change(self, claim: Claim, context_data: Optional[Dict] = None):
        """验证涨跌幅断言"""
        if not claim.extracted_value:
            return

        try:
            claimed_change = float(self._normalize_number(claim.extracted_value))

            stocks_data = context_data.get('stocks', {}) if context_data else {}
            if not stocks_data:
                claim.evidence = "缺少实时数据上下文,无法验证"
                return

            if claim.asset_hint == 'gold':
                gold_data = context_data.get('gold') if context_data else None
                if not gold_data or gold_data.get('change_24h') is None:
                    claim.evidence = "缺少黄金涨跌幅实时数据,无法验证"
                    return
                actual_change = float(gold_data.get('change_24h') or 0)
                if self._direction_conflicts(claim, actual_change):
                    claim.verified = False
                    claim.evidence = "涨跌方向与实时黄金数据不一致"
                    return
                if abs(actual_change - claimed_change) < 0.5:
                    claim.verified = True
                    claim.confidence = 0.95
                    claim.evidence = f"实时黄金涨跌幅: {actual_change:+.2f}%"
                    claim.source = "Gold-API / Yahoo Finance"
                    claim.timestamp = gold_data.get('timestamp', '')
                    return
                claim.verified = False
                claim.evidence = "实时黄金涨跌幅数据不符"
                return

            candidate_codes = [claim.asset_hint] if claim.asset_hint in stocks_data else list(stocks_data.keys())
            for code in candidate_codes:
                stock_dict = stocks_data.get(code) or {}
                actual_change = stock_dict.get('change_pct', 0)

                if self._direction_conflicts(claim, actual_change):
                    continue
                tolerance = 0.3 if code in {'sh000001', 'sz399001', 'sz399006', '^DJI', '^GSPC', '^IXIC'} else 0.5
                if abs(actual_change - claimed_change) < tolerance:
                    claim.verified = True
                    claim.confidence = 0.95
                    claim.evidence = f"实时涨跌幅: {actual_change:+.2f}%"
                    claim.source = "Yahoo Finance"
                    claim.timestamp = stock_dict.get('timestamp', '')
                    return

            claim.verified = False
            claim.evidence = "实时涨跌幅数据不符"

        except ValueError:
            claim.error = "涨跌幅格式错误"

    def _verify_gold_price(self, claim: Claim, context_data: Optional[Dict] = None):
        """验证金价断言"""
        if not claim.extracted_value:
            return

        try:
            claimed_price = float(claim.extracted_value)

            gold_data = context_data.get('gold') if context_data else None
            if not gold_data:
                if self._skip_live_fetch(context_data):
                    claim.evidence = "缺少实时金价上下文,已跳过外部实时校验"
                    return
                # 实时获取
                gold = self.fetcher.get_gold_price()
                if not gold:
                    claim.evidence = "无法获取实时金价"
                    return
                actual_price = gold.price_usd
                timestamp = gold.timestamp
            else:
                actual_price = gold_data.get('price_usd', 0)
                timestamp = gold_data.get('timestamp', '')

            # 允许1%误差
            diff_pct = abs(actual_price - claimed_price) / actual_price if actual_price > 0 else 1.0

            if diff_pct < 0.01:
                claim.verified = True
                claim.confidence = 1.0 - diff_pct
                claim.evidence = f"实时金价: ${actual_price:.2f}/盎司 (误差 {diff_pct*100:.1f}%)"
                claim.source = "Gold-API / Yahoo Finance"
                claim.timestamp = timestamp
            else:
                claim.verified = False
                claim.confidence = 0.0
                claim.evidence = f"实时金价不符: ${actual_price:.2f} vs 断言 ${claimed_price:.2f} (误差 {diff_pct*100:.1f}%)"

        except ValueError:
            claim.error = "金价格式错误"

    def _verify_forex_rate(self, claim: Claim, context_data: Optional[Dict] = None):
        """验证汇率断言"""
        if not claim.extracted_value:
            return

        try:
            claimed_rate = float(claim.extracted_value)

            forex_data = context_data.get('forex', {}) if context_data else {}
            usd_cny = forex_data.get('USD/CNY')

            if not usd_cny:
                if self._skip_live_fetch(context_data):
                    claim.evidence = "缺少实时汇率上下文,已跳过外部实时校验"
                    return
                # 实时获取
                forex = self.fetcher.get_forex_rate("USD/CNY")
                if not forex:
                    claim.evidence = "无法获取实时汇率"
                    return
                actual_rate = forex.rate
                timestamp = forex.timestamp
            else:
                actual_rate = usd_cny.get('rate', 0)
                timestamp = usd_cny.get('timestamp', '')

            # 允许1%误差
            diff_pct = abs(actual_rate - claimed_rate) / actual_rate if actual_rate > 0 else 1.0

            if diff_pct < 0.01:
                claim.verified = True
                claim.confidence = 1.0 - diff_pct
                claim.evidence = f"实时汇率: {actual_rate:.4f}"
                claim.source = "Frankfurter"
                claim.timestamp = timestamp
            else:
                claim.verified = False
                claim.evidence = f"实时汇率不符: {actual_rate:.4f} vs 断言 {claimed_rate:.4f}"

        except ValueError:
            claim.error = "汇率格式错误"

    @staticmethod
    def _direction_conflicts(claim: Claim, actual_change: float) -> bool:
        text = f"{claim.content} {claim.context}"
        positive_words = ('上涨', '收涨', '涨幅', '涨')
        negative_words = ('下跌', '收跌', '跌幅', '跌')
        expects_positive = any(word in text for word in positive_words)
        expects_negative = any(word in text for word in negative_words)
        if expects_positive and not expects_negative:
            return actual_change < 0
        if expects_negative and not expects_positive:
            return actual_change > 0
        return False

    def generate_report_annotation(self, claims: List[Claim]) -> str:
        """
        生成事实核查报告(追加到AI报告末尾)

        Args:
            claims: 已验证的断言列表

        Returns:
            Markdown格式的核查报告
        """
        if not claims:
            return ""

        annotation = "\n\n---\n\n"
        annotation += "## 📌 事实核查报告\n\n"

        # 统计
        realtime_claims = [c for c in claims if c.scope == ClaimScope.REALTIME_MARKET]
        news_fact_claims = [c for c in claims if c.scope == ClaimScope.NEWS_FACT]
        violation_claims = [c for c in claims if c.scope == ClaimScope.VIOLATION]

        total = len(realtime_claims)
        verified = sum(1 for c in realtime_claims if c.verified)
        unverified = total - verified
        errors = sum(1 for c in realtime_claims if c.error)

        annotation += f"**实时行情断言**: {total}  \n"
        verified_pct = (verified / total * 100) if total > 0 else 0.0
        annotation += f"**实时行情已验证**: {verified} ({verified_pct:.1f}%)  \n"
        annotation += f"**实时行情未验证**: {unverified}  \n"
        annotation += f"**数值型新闻断言**: {len(news_fact_claims)}（仅统计覆盖，不做实时校验）  \n"
        annotation += f"**分析性判断**: 不纳入自动核查，请结合新闻证据与结构化推荐人工判断  \n"
        if errors > 0 or violation_claims:
            annotation += f"**错误/违规**: {errors + len(violation_claims)} ❌  \n"

        # 可信度评级
        if total > 0:
            avg_confidence = sum(c.confidence for c in realtime_claims if c.verified) / verified if verified > 0 else 0
            if avg_confidence >= 0.9:
                rating = "高"
            elif avg_confidence >= 0.7:
                rating = "中"
            else:
                rating = "低"
            annotation += f"**平均可信度**: {avg_confidence:.1%} ({rating})  \n"

        annotation += "\n"

        # 已验证的断言
        verified_claims = [c for c in realtime_claims if c.verified]
        if verified_claims:
            annotation += "### ✅ 已验证的断言\n\n"
            for claim in verified_claims[:5]:  # 最多显示5个
                annotation += f"- **{claim.content}** (可信度: {claim.confidence:.0%})  \n"
                annotation += f"  > 验证依据: {claim.evidence}  \n"
                if claim.source:
                    annotation += f"  > 数据来源: {claim.source}  \n"
                annotation += "\n"

            if len(verified_claims) > 5:
                annotation += f"*（还有 {len(verified_claims)-5} 个已验证断言未完全列出）*\n\n"

        # 未验证的断言
        unverified_claims = [c for c in realtime_claims if not c.verified and not c.error]
        if unverified_claims:
            annotation += "### ⚠️ 无法验证的断言\n\n"
            for claim in unverified_claims[:3]:
                annotation += f"- {claim.content}  \n"
                annotation += f"  > 原因: {claim.evidence or '缺少实时数据源'}  \n"
                annotation += "\n"

        if news_fact_claims:
            annotation += "### ℹ️ 数值型新闻断言覆盖\n\n"
            for claim in news_fact_claims[:5]:
                annotation += f"- {claim.content}  \n"
                annotation += "  > 说明: 已识别为新闻事实或历史数据，不纳入实时行情核查  \n\n"
            if len(news_fact_claims) > 5:
                annotation += f"*（还有 {len(news_fact_claims)-5} 个数值型新闻断言未完全列出）*\n\n"

        # 错误/违规断言
        error_claims = [c for c in realtime_claims if c.error] + violation_claims
        if error_claims:
            annotation += "### ❌ 检测到的问题\n\n"
            for claim in error_claims:
                annotation += f"- **{claim.content}**  \n"
                annotation += f"  > {claim.error}  \n"
                annotation += "\n"

        # 建议
        annotation += "---\n\n"
        annotation += "**事实核查说明**:  \n"
        annotation += "- 本核查基于报告生成时的实时市场数据  \n"
        annotation += "- 数据来源: Yahoo Finance、Gold-API、Frankfurter 等公开接口  \n"
        annotation += "- 价格类断言允许≤5%误差,涨跌幅允许≤0.5%误差  \n"

        if errors > 0:
            annotation += "\n⚠️ **重要提示**: 检测到违规内容,建议人工审核后再发布!  \n"

        return annotation

    def calculate_quality_score(self, claims: List[Claim]) -> Dict:
        """
        计算报告质量评分

        Returns:
            {
                'score': 85,  # 总分 0-100
                'accuracy': 0.85,  # 准确性
                'passed': True,  # 是否通过(≥80分)
                'issues': ['...']
            }
        """
        if not claims:
            return {
                'score': 50,
                'accuracy': 0.0,
                'passed': False,
                'issues': ['缺少可验证的具体断言']
            }

        verified_count = sum(1 for c in claims if c.verified)
        total_count = len(claims)
        error_count = sum(1 for c in claims if c.error)

        # 准确性评分 (60分)
        accuracy_rate = verified_count / total_count if total_count > 0 else 0
        accuracy_score = accuracy_rate * 60

        # 错误惩罚 (每个错误 -10分)
        penalty = min(error_count * 10, 40)

        # 总分
        final_score = max(0, accuracy_score - penalty)

        issues = []
        if accuracy_rate < 0.5:
            issues.append(f"准确性严重不足: 仅{accuracy_rate:.0%}的断言得到验证")
        if error_count > 0:
            issues.append(f"检测到 {error_count} 个错误或违规断言")

        return {
            'score': round(final_score, 1),
            'accuracy': accuracy_rate,
            'passed': final_score >= 80,
            'issues': issues,
            'verified': verified_count,
            'total': total_count,
            'errors': error_count
        }


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )

    print("="*60)
    print("事实核查器 - 功能测试")
    print("="*60)

    # 模拟AI报告
    test_report = """
    # 财经分析报告

    ## 市场概况

    今日A股市场表现活跃,紫金矿业现价15.23元,涨幅2.5%。
    国际金价突破2650美元/盎司,创近期新高。
    美元兑人民币汇率为7.12。

    ## 投资建议

    | 股票 | 目标涨幅 | 风险 |
    |------|---------|------|
    | 紫金矿业 | 25% | 中 |

    制造业PMI为49.8,显示经济仍在收缩区间。
    """

    # 创建核查器
    checker = FactChecker()

    # 1. 提取断言
    print("\n【步骤1】提取断言")
    claims = checker.extract_claims(test_report)
    print(f"  提取到 {len(claims)} 个断言:")
    for i, claim in enumerate(claims, 1):
        print(f"  {i}. {claim.type.value}: {claim.content}")

    # 2. 验证断言(模拟上下文数据)
    print("\n【步骤2】验证断言")
    context = {
        'stocks': {
            'sh601899': {
                'name': '紫金矿业',
                'price': 15.20,
                'change_pct': 2.48,
                'timestamp': '2026-01-07 15:00:00'
            }
        },
        'gold': {
            'price_usd': 2655.30,
            'timestamp': '2026-01-07 15:00:00'
        },
        'forex': {
            'USD/CNY': {
                'rate': 7.1245,
                'timestamp': '2026-01-07 15:00:00'
            }
        }
    }

    verified_claims = checker.verify_claims(claims, context)

    print("  验证结果:")
    for claim in verified_claims:
        status = "✅" if claim.verified else ("❌" if claim.error else "⚠️")
        print(f"  {status} {claim.content}")
        if claim.evidence:
            print(f"     证据: {claim.evidence}")
        if claim.error:
            print(f"     错误: {claim.error}")

    # 3. 生成核查报告
    print("\n【步骤3】生成核查报告")
    print("-"*60)
    annotation = checker.generate_report_annotation(verified_claims)
    print(annotation)

    # 4. 质量评分
    print("\n【步骤4】质量评分")
    quality = checker.calculate_quality_score(verified_claims)
    print(f"  总分: {quality['score']}/100")
    print(f"  准确率: {quality['accuracy']:.1%}")
    print(f"  通过: {'是' if quality['passed'] else '否'}")
    if quality['issues']:
        print("  问题:")
        for issue in quality['issues']:
            print(f"    - {issue}")

    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)
