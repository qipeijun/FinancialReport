#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐回看 CLI

用法:
    python scripts/lookback.py --from 2026-05-07 --to 2026-05-25 --market CN
    python scripts/lookback.py --from 2026-05-07 --to 2026-05-25 --horizons 5,10,20 --output result.json
"""

import argparse
import json
from pathlib import Path

try:
    from scripts.bootstrap import ensure_project_root
except ModuleNotFoundError:
    from bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from scripts.application.lookback import (
    collect_recommendations,
    compute_forward_returns,
    summarize,
    render_summary,
)


def main():
    parser = argparse.ArgumentParser(description='推荐回看 —— 历史推荐表现复盘')
    parser.add_argument('--from', dest='from_date', required=True, help='起始日期 YYYY-MM-DD')
    parser.add_argument('--to', dest='to_date', required=True, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--market', default='CN', choices=['CN', 'US'], help='市场（默认 CN）')
    parser.add_argument('--horizons', default='5,10,20', help='回看周期（交易日），逗号分隔（默认 5,10,20）')
    parser.add_argument('--output', type=str, help='可选 JSON 输出路径')
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(',') if h.strip().isdigit()] or [5, 10, 20]

    print(f'收集 {args.from_date} → {args.to_date} 的推荐记录...')
    entries = collect_recommendations(args.from_date, args.to_date, market=args.market)
    print(f'共 {len(entries)} 条推荐记录')

    if not entries:
        print('无推荐数据，退出。')
        return

    print(f'计算前向收益（周期: {horizons}）...')
    results = compute_forward_returns(entries, horizons=horizons)
    print(f'有效结果: {len(results)} 条')

    summary = summarize(results, horizons=horizons)
    md = render_summary(summary, args.from_date, args.to_date, args.market, horizons=horizons)
    print()
    print(md)

    if args.output:
        out_path = Path(args.output)
        if out_path.is_absolute():
            print(f'错误: --output 不允许绝对路径，请使用相对路径（如 data/lookback_result.json）', file=sys.stderr)
            sys.exit(1)
        out_path = PROJECT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'config': {
                'from_date': args.from_date,
                'to_date': args.to_date,
                'market': args.market,
                'horizons': horizons,
            },
            'summary': summary,
        }
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'\nJSON 已导出: {out_path}')


if __name__ == '__main__':
    main()
