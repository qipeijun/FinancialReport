#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐回看 —— 轻量复盘模块

从归档 metadata 中提取历史推荐，对比后续行情表现，
按等级/决策视图/来源类型分组统计。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _archive_dirs_for_date(date_str: str) -> Dict[str, Path]:
    """返回某日期的归档目录路径"""
    year_month = '-'.join(date_str.split('-')[:2])
    base_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str
    return {
        'reports': base_dir / 'reports',
        'metadata': base_dir / 'metadata',
    }


@dataclass
class LookbackEntry:
    date: str
    symbol: str
    name: str
    grade: str
    total_score: int
    source_type: str
    decision_view: str  # actionable / watchlist / stale
    forward_returns: Dict[str, Optional[float]]  # {"5": 1.2, "10": 2.8, ...}


def collect_recommendations(
    from_date: str,
    to_date: str,
    market: str = 'CN',
) -> List[Dict[str, Any]]:
    """
    从归档中收集指定日期范围内的所有推荐条目。

    Returns:
        [{date, symbol, name, grade, total_score, source_type, decision_view, ...}]
    """
    entries: List[Dict[str, Any]] = []
    current = datetime.strptime(from_date, '%Y-%m-%d')
    end = datetime.strptime(to_date, '%Y-%m-%d')

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        current += timedelta(days=1)

        dirs = _archive_dirs_for_date(date_str)
        if not dirs['metadata'].exists():
            continue

        for meta_path in sorted(dirs['metadata'].glob('analysis_meta_*.json')):
            try:
                payload = _load_json(meta_path)
            except Exception:
                continue

            # 市场过滤
            scoring_config = payload.get('scoring_config') or {}
            if scoring_config.get('market', 'CN') != market:
                continue

            recommendations = payload.get('stock_recommendations') or []
            decision_views = payload.get('decision_views') or {}
            actionable_symbols = {
                item.get('symbol') for item in decision_views.get('actionable_candidates', [])
            }
            stale_symbols = {
                item.get('symbol') for item in decision_views.get('stale_or_rejected', [])
            }

            for rec in recommendations:
                symbol = rec.get('symbol')
                if not symbol:
                    continue
                if symbol in actionable_symbols:
                    view = 'actionable'
                elif symbol in stale_symbols:
                    view = 'stale'
                else:
                    view = 'watchlist'

                entries.append({
                    'date': date_str,
                    'symbol': symbol,
                    'name': rec.get('name', symbol),
                    'grade': rec.get('grade', ''),
                    'total_score': rec.get('total_score', 0),
                    'source_type': rec.get('source_type', ''),
                    'decision_view': view,
                })

    return entries


def compute_forward_returns(
    entries: List[Dict[str, Any]],
    horizons: List[int] | None = None,
) -> List[LookbackEntry]:
    """
    为每条推荐计算 N 个交易日后的前向收益。
    """
    if horizons is None:
        horizons = [5, 10, 20]

    from scripts.utils.stock_recommendation import PriceHistoryProvider

    provider = PriceHistoryProvider()
    # 缓存：同一 symbol 只取一次行情
    bars_cache: Dict[str, List] = {}
    results: List[LookbackEntry] = []
    skipped_no_bars = 0
    skipped_no_index = 0
    skipped_bad_close = 0

    for entry in entries:
        symbol = entry['symbol']
        date_str = entry['date']

        if symbol not in bars_cache:
            bars_cache[symbol] = provider.fetch_history(symbol, lookback_days=250)
        bars = bars_cache[symbol]

        if not bars:
            skipped_no_bars += 1
            continue

        # 找到推荐日的 bar 索引
        base_idx = _find_bar_index(bars, date_str)
        if base_idx is None:
            skipped_no_index += 1
            continue

        base_close = bars[base_idx].close
        if base_close <= 0:
            skipped_bad_close += 1
            continue

        returns: Dict[str, Optional[float]] = {}
        for h in horizons:
            target_idx = base_idx + h
            if target_idx < len(bars):
                forward_close = bars[target_idx].close
                if forward_close > 0:
                    returns[str(h)] = round((forward_close / base_close - 1) * 100, 2)
                else:
                    returns[str(h)] = None
            else:
                returns[str(h)] = None

        results.append(LookbackEntry(
            date=entry['date'],
            symbol=entry['symbol'],
            name=entry['name'],
            grade=entry['grade'],
            total_score=entry['total_score'],
            source_type=entry['source_type'],
            decision_view=entry['decision_view'],
            forward_returns=returns,
        ))

    total_skipped = skipped_no_bars + skipped_no_index + skipped_bad_close
    if total_skipped > 0:
        print(f'[lookback] 跳过 {total_skipped} 条：无行情 {skipped_no_bars} / 日期无匹配 {skipped_no_index} / 收盘价异常 {skipped_bad_close}')

    return results


def summarize(results: List[LookbackEntry], horizons: List[int] | None = None) -> Dict[str, Any]:
    """按维度分组统计"""
    if horizons is None:
        horizons = [5, 10, 20]
    horizon_keys = [str(h) for h in horizons]

    def _group_stats(items: List[LookbackEntry]) -> Dict[str, Any]:
        stats: Dict[str, Any] = {'count': len(items)}
        for hk in horizon_keys:
            vals = [r.forward_returns[hk] for r in items if r.forward_returns.get(hk) is not None]
            if vals:
                stats[f'avg_return_{hk}d'] = round(mean(vals), 2)
                stats[f'median_return_{hk}d'] = round(median(vals), 2)
                stats[f'win_rate_{hk}d'] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)
                stats[f'max_return_{hk}d'] = round(max(vals), 2)
                stats[f'min_return_{hk}d'] = round(min(vals), 2)
            else:
                stats[f'avg_return_{hk}d'] = None
                stats[f'win_rate_{hk}d'] = None
        return stats

    # 按等级
    by_grade: Dict[str, List[LookbackEntry]] = defaultdict(list)
    for r in results:
        by_grade[r.grade].append(r)

    # 按决策视图
    by_view: Dict[str, List[LookbackEntry]] = defaultdict(list)
    for r in results:
        by_view[r.decision_view].append(r)

    # 按来源类型
    by_source: Dict[str, List[LookbackEntry]] = defaultdict(list)
    for r in results:
        by_source[r.source_type].append(r)

    # 异常标的（超出均值 ±2 标准差）
    outliers = []
    for hk in horizon_keys:
        vals = [(r, r.forward_returns.get(hk)) for r in results if r.forward_returns.get(hk) is not None]
        if len(vals) < 10:
            continue
        returns_only = [v for _, v in vals]
        avg = mean(returns_only)
        std = (sum((v - avg) ** 2 for v in returns_only) / len(returns_only)) ** 0.5
        threshold = 2 * std
        for r, ret in vals:
            if ret is not None and abs(ret - avg) > threshold:
                outliers.append({
                    'date': r.date,
                    'symbol': r.symbol,
                    'name': r.name,
                    'grade': r.grade,
                    'decision_view': r.decision_view,
                    f'return_{hk}d': ret,
                    'direction': 'outperform' if ret > avg else 'underperform',
                })

    return {
        'total_entries': len(results),
        'by_grade': {g: _group_stats(items) for g, items in sorted(by_grade.items())},
        'by_decision_view': {v: _group_stats(items) for v, items in sorted(by_view.items())},
        'by_source_type': {s: _group_stats(items) for s, items in sorted(by_source.items())},
        'outliers': outliers[:10],
    }


def render_summary(summary: Dict[str, Any], from_date: str, to_date: str, market: str, horizons: List[int] | None = None) -> str:
    """渲染 Markdown 摘要"""
    if horizons is None:
        horizons = [5, 10, 20]
    horizon_keys = [str(h) for h in horizons]
    lines = [
        f'## 推荐回看摘要（{from_date} → {to_date}，{market}）',
        '',
        f'共 {summary["total_entries"]} 条推荐记录。',
        '',
    ]

    # 按等级
    by_grade = summary.get('by_grade', {})
    if by_grade:
        lines.append('### 按等级')
        lines.append('')
        header = '| 等级 | 样本 |'
        sep = '|------|------|'
        for hk in horizon_keys:
            header += f' {hk}日平均 | {hk}日胜率 |'
            sep += '--------|--------|'
        lines.append(header)
        lines.append(sep)
        for grade in ['强关注', '关注', '观察', '回避']:
            stats = by_grade.get(grade)
            if not stats:
                continue
            row = f'| {grade} | {stats["count"]} |'
            for hk in horizon_keys:
                avg = stats.get(f'avg_return_{hk}d')
                wr = stats.get(f'win_rate_{hk}d')
                row += f' {avg:+.1f}% |' if avg is not None else ' — |'
                row += f' {wr:.0f}% |' if wr is not None else ' — |'
            lines.append(row)
        lines.append('')

    # 按决策视图
    by_view = summary.get('by_decision_view', {})
    if by_view:
        lines.append('### 按决策视图')
        lines.append('')
        header = '| 分类 | 样本 |'
        sep = '|------|------|'
        for hk in horizon_keys:
            header += f' {hk}日平均 | {hk}日胜率 |'
            sep += '--------|--------|'
        lines.append(header)
        lines.append(sep)
        for view in ['actionable', 'watchlist', 'stale']:
            stats = by_view.get(view)
            if not stats:
                continue
            label = {'actionable': '可行动', 'watchlist': '观察', 'stale': '拒绝/拥挤'}.get(view, view)
            row = f'| {label} | {stats["count"]} |'
            for hk in horizon_keys:
                avg = stats.get(f'avg_return_{hk}d')
                wr = stats.get(f'win_rate_{hk}d')
                row += f' {avg:+.1f}% |' if avg is not None else ' — |'
                row += f' {wr:.0f}% |' if wr is not None else ' — |'
            lines.append(row)
        lines.append('')

    # 异常标的
    outliers = summary.get('outliers', [])
    if outliers:
        lines.append('### 异常标的')
        lines.append('')
        for o in outliers[:8]:
            direction = '超涨' if o['direction'] == 'outperform' else '超跌'
            horizon_label = next((k for k in o if k.startswith('return_')), '')
            hk = horizon_label.replace('return_', '').replace('d', '') if horizon_label else '?'
            ret = o.get(horizon_label)
            lines.append(
                f'- **{o["name"]}**（{o["symbol"]}）{o["date"]} {o["grade"]}/{o["decision_view"]}，'
                f'{hk}日后 {direction} {ret:+.1f}%'
            )
        lines.append('')

    return '\n'.join(lines)


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _find_bar_index(bars, date_str: str) -> Optional[int]:
    """在日线列表中查找匹配日期的索引"""
    for i, bar in enumerate(bars):
        if bar.date == date_str:
            return i
    # 日期可能因周末/假日不在数据中，找最近的下一个交易日
    target = datetime.strptime(date_str, '%Y-%m-%d')
    for i, bar in enumerate(bars):
        bar_date = datetime.strptime(bar.date, '%Y-%m-%d')
        if bar_date >= target:
            return i
    return None
