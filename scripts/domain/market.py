#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market 值对象 —— 内聚市场相关行为，消除散落的裸字符串 'CN'/'US' 分支判断。

使用方式:
    from scripts.domain.market import Market

    market = Market.CN          # 预配置实例
    market = Market.US
    market = Market.from_code('CN')   # 工厂方法，边界校验
    market = Market.from_code('invalid')  # 抛出 ValueError
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


# 美股模式默认消费的新闻源（美股聚焦 + 国际财经 + 美国官方）
_US_MARKET_SOURCE_NAMES: Tuple[str, ...] = (
    'Yahoo Finance', 'MarketWatch', 'Seeking Alpha', 'CNBC Top News',
    "Investor's Business Daily",
    'FT中文网', 'Wall Street Journal', '经济学人 Economist',
    'BBC全球经济', 'CNBC', 'ZeroHedge', 'ETF Trends', 'Thomson Reuters',
    'Federal Reserve Board', '美国证监会-新闻发布',
)


@dataclass(frozen=True)
class Market:
    """市场值对象。

    所有字段不可变，Market 实例可以安全地用作字典键和集合成员。
    """

    code: str                  # 'CN' | 'US'
    label: str                 # 'A股' | '美股'
    timezone: str              # 'Asia/Shanghai' | 'America/New_York'
    default_prompt_version: str  # 'pro_v2'
    source_names: Tuple[str, ...]  # 新闻源 allowlist，CN 为空 tuple 表示不过滤

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Market):
            return self.code == other.code
        if isinstance(other, str):
            return self.code == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.code)

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_code(cls, code: str) -> Market:
        """从字符串代码构造 Market 实例，边界处做严格校验。"""
        upper = code.upper()
        if upper == 'CN':
            return Market.CN
        if upper == 'US':
            return Market.US
        raise ValueError(f'无效的市场代码: {code!r}，仅支持 CN 或 US')


# 预配置实例（在类定义之后赋值，避免循环引用）
Market.CN = Market(
    code='CN',
    label='A股',
    timezone='Asia/Shanghai',
    default_prompt_version='pro_v2',
    source_names=(),
)
Market.US = Market(
    code='US',
    label='美股',
    timezone='America/New_York',
    default_prompt_version='pro_v2',
    source_names=_US_MARKET_SOURCE_NAMES,
)
