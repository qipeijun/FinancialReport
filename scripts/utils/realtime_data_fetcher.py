"""
实时财经数据采集器

功能:
1. 获取股票实时行情(Yahoo Finance)
2. 获取黄金/外汇实时价格
3. 获取宏观经济指标
4. 格式化数据供AI分析使用

目标: 杜绝AI编造数据,提供可验证的实时市场信息
"""

import re
import time
import os
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class StockData:
    """股票实时数据"""
    code: str
    name: str
    price: float
    prev_close: float
    change_pct: float
    volume: int
    amount: float  # 成交额
    high: float
    low: float
    open: float
    timestamp: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GoldData:
    """黄金价格数据"""
    price_usd: float  # 美元/盎司
    price_cny: Optional[float] = None  # 人民币/克
    change_24h: Optional[float] = None
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ForexData:
    """外汇数据"""
    pair: str  # 如 "USD/CNY"
    rate: float
    timestamp: str

    def to_dict(self) -> Dict:
        return asdict(self)


class RealtimeDataFetcher:
    """实时财经数据采集器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.force_failure = os.getenv('FINANCIAL_REPORT_FORCE_REALTIME_FAILURE') == '1'
        self.request_timeout = (3, 8)
        self.max_retries = 2
        self.retry_backoff = 1.0

        # API端点
        self.apis = {
            'yahoo_chart': 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d',
            'frankfurter_latest': 'https://api.frankfurter.dev/v1/latest?base={base}&symbols={symbols}',
            'gold_api': 'https://api.gold-api.com/price/XAU',
        }

    def _request_text(self, urls: List[str] | str, encoding: str = 'gbk') -> Optional[str]:
        """带重试与备用地址的文本请求"""
        if self.force_failure:
            logger.warning("已启用实时数据失败模拟，跳过所有外部行情请求")
            return None

        candidates = [urls] if isinstance(urls, str) else urls
        last_error: Optional[Exception] = None

        for url in candidates:
            for attempt in range(self.max_retries + 1):
                try:
                    response = self.session.get(url, timeout=self.request_timeout)
                    response.raise_for_status()
                    response.encoding = encoding
                    return response.text
                except Exception as exc:
                    last_error = exc
                    is_last_attempt = attempt >= self.max_retries
                    if not is_last_attempt:
                        sleep_s = self.retry_backoff * (attempt + 1)
                        logger.warning(
                            f"请求失败，{sleep_s:.1f}s 后重试 ({attempt + 1}/{self.max_retries}) {url}: {exc}"
                        )
                        time.sleep(sleep_s)

            logger.warning(f"备用地址请求失败: {url}")

        if last_error:
            raise last_error
        return None

    def _request_json(self, urls: List[str] | str) -> Optional[Dict]:
        """带重试与备用地址的JSON请求"""
        text = self._request_text(urls, encoding='utf-8')
        if not text:
            return None
        return json.loads(text)

    def _to_yahoo_symbol(self, code: str) -> str:
        """转换仓库内部代码为 Yahoo Finance 符号"""
        code = (code or '').strip()
        if not code:
            return code

        if code.startswith('sh') and len(code) == 8:
            return f"{code[2:]}.SS"
        if code.startswith('sz') and len(code) == 8:
            return f"{code[2:]}.SZ"
        return code

    def _display_name_for_code(self, original_code: str, yahoo_symbol: str, meta: Dict) -> str:
        known_names = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指',
        }
        return (
            known_names.get(original_code)
            or meta.get('shortName')
            or meta.get('longName')
            or yahoo_symbol
        )

    def _format_unix_timestamp(self, unix_ts: Optional[int]) -> str:
        if not unix_ts:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return datetime.fromtimestamp(unix_ts).strftime('%Y-%m-%d %H:%M:%S')

    def get_stock_realtime(self, stock_codes: List[str]) -> Dict[str, StockData]:
        """
        获取股票实时行情

        Args:
            stock_codes: 股票代码列表,如 ['sh601899', 'sz000001', 'NVDA']
                        A股需要加前缀: sh(上海) 或 sz(深圳)

        Returns:
            {
                'sh601899': StockData(name='紫金矿业', price=15.23, ...),
                ...
            }
        """
        if not stock_codes:
            return {}

        result = {}
        for original_code in stock_codes:
            yahoo_symbol = self._to_yahoo_symbol(original_code)
            url = self.apis['yahoo_chart'].format(symbol=yahoo_symbol)
            try:
                payload = self._request_json(url)
                if not payload:
                    continue
                chart = (payload.get('chart') or {}).get('result') or []
                if not chart:
                    continue
                result0 = chart[0]
                meta = result0.get('meta') or {}
                indicators = (result0.get('indicators') or {}).get('quote') or [{}]
                quote = indicators[0] or {}

                price = float(meta.get('regularMarketPrice') or 0.0)
                prev_close = float(meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0)
                open_price = self._last_numeric(quote.get('open'))
                high_price = self._last_numeric(quote.get('high'))
                low_price = self._last_numeric(quote.get('low'))
                volume = int(self._last_numeric(quote.get('volume')))

                if price <= 0:
                    logger.warning(f"Yahoo 未返回有效价格 {yahoo_symbol}")
                    continue

                stock = StockData(
                    code=original_code,
                    name=self._display_name_for_code(original_code, yahoo_symbol, meta),
                    open=open_price if open_price > 0 else price,
                    prev_close=prev_close,
                    price=price,
                    high=high_price if high_price > 0 else price,
                    low=low_price if low_price > 0 else price,
                    volume=volume,
                    amount=0.0,
                    change_pct=self._calculate_change_pct(price, prev_close),
                    timestamp=self._format_unix_timestamp(meta.get('regularMarketTime')),
                )
                result[original_code] = stock

            except Exception as e:
                logger.error(f"获取股票数据失败 {original_code}: {e}")

        return result

    def get_gold_price(self) -> Optional[GoldData]:
        """
        获取黄金实时价格

        Returns:
            GoldData 或 None(如果获取失败)
        """
        try:
            payload = self._request_json(self.apis['gold_api'])
            if payload and payload.get('price'):
                price = float(payload['price'])
                change_pct = payload.get('chp')
                updated_at = payload.get('updatedAt')
                return GoldData(
                    price_usd=price,
                    change_24h=float(change_pct) if change_pct is not None else None,
                    timestamp=updated_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
        except Exception as e:
            logger.warning(f"从 Gold-API 获取黄金价格失败: {e}")

        try:
            yahoo_symbol = 'GC=F'
            payload = self._request_json(self.apis['yahoo_chart'].format(symbol=yahoo_symbol))
            chart = ((payload or {}).get('chart') or {}).get('result') or []
            if chart:
                meta = chart[0].get('meta') or {}
                price = float(meta.get('regularMarketPrice') or 0.0)
                prev = float(meta.get('chartPreviousClose') or 0.0)
                if price > 0:
                    return GoldData(
                        price_usd=price,
                        change_24h=((price - prev) / prev * 100) if prev > 0 else None,
                        timestamp=self._format_unix_timestamp(meta.get('regularMarketTime'))
                    )
        except Exception as e:
            logger.warning(f"从 Yahoo 获取黄金价格失败: {e}")

        logger.error("获取黄金价格失败")
        return None

    def get_forex_rate(self, pair: str = "USD/CNY") -> Optional[ForexData]:
        """
        获取外汇汇率

        Args:
            pair: 货币对,如 "USD/CNY"

        Returns:
            ForexData 或 None
        """
        try:
            base, quote = pair.split('/')
            if not base or not quote:
                logger.warning(f"不支持的货币对: {pair}")
                return None

            url = self.apis['frankfurter_latest'].format(base=base, symbols=quote)
            payload = self._request_json(url)
            if not payload:
                return None

            rate = ((payload.get('rates') or {}).get(quote))
            if rate is not None:
                return ForexData(
                    pair=pair,
                    rate=float(rate),
                    timestamp=f"{payload.get('date', datetime.now().strftime('%Y-%m-%d'))} 00:00:00"
                )
        except Exception as e:
            logger.error(f"获取外汇汇率失败 {pair}: {e}")

        return None

    def extract_stock_codes_from_text(self, text: str) -> List[str]:
        """
        从文本中提取股票代码

        Args:
            text: 新闻内容或文章文本

        Returns:
            股票代码列表(已添加前缀,如 ['sh601899', 'sz000001'])
        """
        codes = []

        # 模式1: 6位数字 + .SS 或 .SZ (如 601899.SS)
        pattern1 = r'(\d{6})\.(SS|SZ)'
        for match in re.finditer(pattern1, text):
            code = match.group(1)
            market = 'sh' if match.group(2) == 'SS' else 'sz'
            codes.append(f"{market}{code}")

        # 模式2: 直接的6位数字(在财经上下文中)
        # 沪市: 600xxx, 601xxx, 603xxx, 688xxx
        # 深市: 000xxx, 001xxx, 002xxx, 003xxx, 300xxx
        pattern2 = r'\b(60[0|1|3]\d{3}|688\d{3}|00[0-3]\d{3}|300\d{3})\b'
        for match in re.finditer(pattern2, text):
            code = match.group(1)
            if code.startswith(('60', '68')):
                codes.append(f"sh{code}")
            else:
                codes.append(f"sz{code}")

        # 去重并保持顺序
        seen = set()
        unique_codes = []
        for code in codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)

        return unique_codes

    def format_for_prompt(self,
                         stocks: Optional[Dict[str, StockData]] = None,
                         gold: Optional[GoldData] = None,
                         forex: Optional[Dict[str, ForexData]] = None) -> str:
        """
        格式化数据为Prompt文本(供AI理解)

        Returns:
            Markdown格式的实时数据摘要
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        prompt = f"""## 📊 实时市场数据（{timestamp}）

**重要说明**: 以下数据为实时市场行情,请在分析时**严格引用**这些数据,**禁止编造**任何未在此处列出的数值。

"""

        # 股票行情
        if stocks:
            prompt += "### 股票行情\n\n"
            prompt += "| 股票代码 | 股票名称 | 现价 | 涨跌幅 | 成交量 | 成交额 | 更新时间 |\n"
            prompt += "|---------|---------|------|--------|--------|--------|----------|\n"

            for code, stock in stocks.items():
                prompt += f"| {stock.code} | {stock.name} | "
                prompt += f"¥{stock.price:.2f} | "
                prompt += f"{stock.change_pct:+.2f}% | "
                prompt += f"{stock.volume:,}手 | "
                prompt += f"¥{stock.amount/100000000:.2f}亿 | "
                prompt += f"{stock.timestamp} |\n"

            prompt += "\n"

        # 贵金属
        if gold:
            prompt += "### 贵金属价格\n\n"
            prompt += f"- **国际黄金**: ${gold.price_usd:.2f}/盎司"
            if gold.change_24h is not None:
                prompt += f" ({gold.change_24h:+.2f}%)"
            prompt += f" | 更新: {gold.timestamp}\n"
            if gold.price_cny:
                prompt += f"- **黄金(人民币)**: ¥{gold.price_cny:.2f}/克\n"
            prompt += "\n"

        # 外汇
        if forex:
            prompt += "### 外汇汇率\n\n"
            for pair, data in forex.items():
                prompt += f"- **{data.pair}**: {data.rate:.4f} | 更新: {data.timestamp}\n"
            prompt += "\n"

        # 数据来源声明
        prompt += "---\n\n"
        prompt += "**数据来源**: Yahoo Finance、Gold-API、Frankfurter  \n"
        prompt += f"**数据时效**: {timestamp}  \n"
        prompt += "**使用约束**:  \n"
        prompt += "1. ✅ 引用数据时必须标注来源和时间  \n"
        prompt += "2. ❌ 禁止编造任何未在上表中出现的价格或涨幅  \n"
        prompt += "3. ❌ 禁止推测未来具体目标价格或涨幅百分比  \n"
        prompt += "4. ✅ 可基于当前数据进行趋势分析,但需注明\"基于现价XX\"  \n"

        return prompt

    def fetch_all(self) -> Dict:
        """
        获取通用的实时市场数据（不依赖具体文章）

        Returns:
            {
                'stocks': {...},
                'gold': GoldData,
                'forex': {...},
                'prompt': '格式化的Prompt文本'
            }
        """
        # 获取常见的核心股票
        common_stock_codes = [
            'sh000001',  # 上证指数
            'sz399001',  # 深证成指
            'sz399006',  # 创业板指
        ]

        # 获取股票数据
        stocks = {}
        try:
            stocks = self.get_stock_realtime(common_stock_codes)
            logger.info(f"成功获取 {len(stocks)} 个指数数据")
        except Exception as e:
            logger.warning(f"获取股票数据失败: {e}")

        # 获取黄金价格
        gold = None
        try:
            gold = self.get_gold_price()
            if gold:
                logger.info(f"获取黄金价格: ${gold.price_usd:.2f}/盎司")
        except Exception as e:
            logger.warning(f"获取黄金价格失败: {e}")

        # 获取外汇
        forex = {}
        try:
            usd_cny = self.get_forex_rate("USD/CNY")
            if usd_cny:
                forex['USD/CNY'] = usd_cny
                logger.info(f"获取美元汇率: {usd_cny.rate:.4f}")
        except Exception as e:
            logger.warning(f"获取外汇数据失败: {e}")

        # 格式化为Prompt
        prompt_text = self.format_for_prompt(stocks=stocks, gold=gold, forex=forex)

        return {
            'stocks': {k: v.to_dict() for k, v in stocks.items()},
            'gold': gold.to_dict() if gold else None,
            'forex': {k: v.to_dict() for k, v in forex.items()},
            'prompt': prompt_text,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def fetch_all_for_articles(self, articles: List[Dict]) -> Dict:
        """
        为一批文章获取所有相关实时数据

        Args:
            articles: 文章列表,每篇文章包含 title, summary, content

        Returns:
            {
                'stocks': {...},
                'gold': GoldData,
                'forex': {...},
                'prompt': '格式化的Prompt文本'
            }
        """
        # 1. 从所有文章中提取股票代码
        all_text = ""
        for article in articles:
            all_text += f"{article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}\n"

        stock_codes = self.extract_stock_codes_from_text(all_text)
        logger.info(f"从文章中提取到 {len(stock_codes)} 个股票代码: {stock_codes[:10]}...")

        # 2. 获取股票数据
        stocks = {}
        if stock_codes:
            stocks = self.get_stock_realtime(stock_codes)
            logger.info(f"成功获取 {len(stocks)}/{len(stock_codes)} 个股票的实时数据")

        # 3. 获取黄金价格(如果文章提到黄金相关)
        gold = None
        if any(kw in all_text for kw in ['黄金', '金价', '贵金属', '紫金']):
            gold = self.get_gold_price()
            if gold:
                logger.info(f"获取黄金价格: ${gold.price_usd:.2f}/盎司")

        # 4. 获取外汇(如果文章提到汇率)
        forex = {}
        if any(kw in all_text for kw in ['美元', '汇率', '人民币', 'USD', 'CNY']):
            usd_cny = self.get_forex_rate("USD/CNY")
            if usd_cny:
                forex['USD/CNY'] = usd_cny
                logger.info(f"获取美元汇率: {usd_cny.rate:.4f}")

        # 5. 格式化为Prompt
        prompt_text = self.format_for_prompt(stocks=stocks, gold=gold, forex=forex)

        return {
            'stocks': {k: v.to_dict() for k, v in stocks.items()},
            'gold': gold.to_dict() if gold else None,
            'forex': {k: v.to_dict() for k, v in forex.items()},
            'prompt': prompt_text,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _calculate_change_pct(self, current: float, previous: float) -> float:
        """计算涨跌幅百分比"""
        if previous == 0:
            return 0.0
        return round((current - previous) / previous * 100, 2)

    def _last_numeric(self, values: Optional[List]) -> float:
        """从序列中提取最后一个有效数值"""
        if not values:
            return 0.0
        for value in reversed(values):
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    def _parse_timestamp(self, date: str, time: str) -> str:
        """解析新浪时间戳"""
        try:
            return f"{date} {time}"
        except:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ============================================================
# 使用示例和测试
# ============================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )

    print("="*60)
    print("实时数据采集器 - 功能测试")
    print("="*60)

    fetcher = RealtimeDataFetcher()

    # 测试1: 获取单个股票数据
    print("\n【测试1】获取紫金矿业实时行情")
    stocks = fetcher.get_stock_realtime(['sh601899'])
    if stocks:
        stock = stocks['sh601899']
        print(f"  股票: {stock.name} ({stock.code})")
        print(f"  现价: ¥{stock.price:.2f}")
        print(f"  涨跌: {stock.change_pct:+.2f}%")
        print(f"  成交量: {stock.volume:,}手")
        print(f"  更新: {stock.timestamp}")
    else:
        print("  ⚠️ 获取失败(可能是非交易时间)")

    # 测试2: 获取黄金价格
    print("\n【测试2】获取国际黄金价格")
    gold = fetcher.get_gold_price()
    if gold:
        print(f"  价格: ${gold.price_usd:.2f}/盎司")
        if gold.change_24h:
            print(f"  24h变化: {gold.change_24h:+.2f}%")
        print(f"  更新: {gold.timestamp}")
    else:
        print("  ⚠️ 获取失败")

    # 测试3: 获取外汇汇率
    print("\n【测试3】获取美元汇率")
    forex = fetcher.get_forex_rate("USD/CNY")
    if forex:
        print(f"  汇率: {forex.rate:.4f}")
        print(f"  更新: {forex.timestamp}")
    else:
        print("  ⚠️ 获取失败")

    # 测试4: 从文本提取股票代码
    print("\n【测试4】从文本提取股票代码")
    test_text = """
    紫金矿业(601899.SS)今日上涨2.5%,
    平安银行(000001.SZ)表现平稳,
    贵州茅台600519创新高。
    """
    codes = fetcher.extract_stock_codes_from_text(test_text)
    print(f"  提取结果: {codes}")

    # 测试5: 格式化Prompt
    print("\n【测试5】生成AI Prompt格式数据")
    print("-" * 60)
    prompt = fetcher.format_for_prompt(stocks=stocks, gold=gold, forex={'USD/CNY': forex} if forex else None)
    print(prompt)

    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)
