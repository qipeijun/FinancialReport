#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 DeepSeek API Key 是否可用。

判定逻辑与主分析脚本保持一致：
1. 优先读取环境变量 `DEEPSEEK_API_KEY`
2. 回退读取 `config/config.yml` 中的 `api_keys.deepseek`
3. 再回退读取 `config/config.yml` 中的 `deepseek.api_key`

只输出来源，不输出密钥本身。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='检查 DeepSeek API Key 是否可用')
    parser.add_argument('--config', type=str, help='配置文件路径，默认 config/config.yml')
    return parser.parse_args()


def load_key_source(config_path: Path) -> tuple[bool, str]:
    env_key = __import__('os').getenv('DEEPSEEK_API_KEY')
    if env_key:
        return True, 'environment'

    if not config_path.exists():
        return False, f'config_missing:{config_path}'

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as exc:
        return False, f'config_error:{exc}'

    api_key = (cfg.get('api_keys') or {}).get('deepseek')
    if api_key:
        return True, f'config:{config_path}'

    api_key = (cfg.get('deepseek') or {}).get('api_key')
    if api_key:
        return True, f'config:{config_path}'

    return False, 'not_found'


def main() -> int:
    args = parse_args()
    config_path = Path(args.config) if args.config else (PROJECT_ROOT / 'config' / 'config.yml')
    ok, source = load_key_source(config_path)
    if ok:
        print(f'DEEPSEEK_API_KEY available via {source}')
        return 0

    print(f'DEEPSEEK_API_KEY unavailable ({source})')
    return 1


if __name__ == '__main__':
    sys.exit(main())
