"""
实时财经数据采集器

功能:
1. 获取股票实时行情(新浪财经API)
2. 获取黄金/外汇实时价格
3. 获取宏观经济指标
4. 格式化数据供AI分析使用

目标: 杜绝AI编造数据,提供可验证的实时市场信息
"""

import re
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

        # API端点
        self.apis = {
            'sina_stock': 'https://hq.sinajs.cn/list=',
            'sina_gold': 'https://hq.sinajs.cn/list=hf_GC',  # 纽约黄金期货
            'eastmoney_gold': 'https://www.goldprice.org/zh-hans/gold-price-china.html',
        }

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

        # 分批处理(新浪限制单次最多100个)
        batch_size = 100
        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            codes_str = ','.join(batch)
            url = f"{self.apis['sina_stock']}{codes_str}"

            try:
                response = self.session.get(url, timeout=5)
                response.encoding = 'gbk'
                lines = response.text.strip().split('\n')

                for line in lines:
                    if not line or '=""' in line:
                        continue

                    # 解析格式: var hq_str_sh601899="紫金矿业,15.23,15.12,15.45,..."
                    match = re.search(r'var hq_str_(.+?)="(.+?)"', line)
                    if not match:
                        continue

                    code, data = match.groups()
                    fields = data.split(',')

                    # A股格式: 32个字段
                    if len(fields) >= 32:
                        try:
                            stock = StockData(
                                code=code,
                                name=fields[0],
                                open=float(fields[1]) if fields[1] else 0.0,
                                prev_close=float(fields[2]) if fields[2] else 0.0,
                                price=float(fields[3]) if fields[3] else 0.0,
                                high=float(fields[4]) if fields[4] else 0.0,
                                low=float(fields[5]) if fields[5] else 0.0,
                                volume=int(float(fields[8])) if fields[8] else 0,
                                amount=float(fields[9]) if fields[9] else 0.0,
                                change_pct=self._calculate_change_pct(
                                    float(fields[3]) if fields[3] else 0.0,
                                    float(fields[2]) if fields[2] else 0.0
                                ),
                                timestamp=self._parse_timestamp(fields[30], fields[31])
                            )
                            result[code] = stock
                        except (ValueError, IndexError) as e:
                            logger.warning(f"解析股票数据失败 {code}: {e}")
                            continue

            except Exception as e:
                logger.error(f"获取股票数据失败: {e}")

        return result

    def get_gold_price(self) -> Optional[GoldData]:
        """
        获取黄金实时价格

        Returns:
            GoldData 或 None(如果获取失败)
        """
        try:
            # 方法1: 新浪黄金期货数据
            url = self.apis['sina_gold']
            response = self.session.get(url, timeout=5)
            response.encoding = 'gbk'

            # 解析: var hq_str_hf_GC="黄金,2650.50,2648.30,..."
            match = re.search(r'"([^"]+)"', response.text)
            if match:
                fields = match.group(1).split(',')
                if len(fields) >= 3:
                    price = float(fields[1])  # 当前价
                    prev = float(fields[2])   # 昨收

                    return GoldData(
                        price_usd=price,
                        change_24h=((price - prev) / prev * 100) if prev > 0 else 0.0,
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
        except Exception as e:
            logger.warning(f"从新浪获取黄金价格失败: {e}")

        # 方法2: 如果新浪失败,返回None(未来可添加备用API)
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
            # 新浪外汇API
            code_map = {
                "USD/CNY": "fx_susdcny",
                "EUR/CNY": "fx_seurcny",
                "JPY/CNY": "fx_sjpycny"
            }

            code = code_map.get(pair)
            if not code:
                logger.warning(f"不支持的货币对: {pair}")
                return None

            url = f"{self.apis['sina_stock']}{code}"
            response = self.session.get(url, timeout=5)
            response.encoding = 'gbk'

            match = re.search(r'"([^"]+)"', response.text)
            if match:
                fields = match.group(1).split(',')
                if len(fields) >= 2:
                    return ForexData(
                        pair=pair,
                        rate=float(fields[1]),
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
        prompt += "**数据来源**: 新浪财经实时行情  \n"
        prompt += f"**数据时效**: {timestamp}  \n"
        prompt += "**使用约束**:  \n"
        prompt += "1. ✅ 引用数据时必须标注来源和时间  \n"
        prompt += "2. ❌ 禁止编造任何未在上表中出现的价格或涨幅  \n"
        prompt += "3. ❌ 禁止推测未来具体目标价格或涨幅百分比  \n"
        prompt += "4. ✅ 可基于当前数据进行趋势分析,但需注明\"基于现价XX\"  \n"

        return prompt

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
