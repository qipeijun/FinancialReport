#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一前置检查模块。

供 interactive_runner.py 和 run_daily_digest.py 共用。
在开始抓取/分析之前一次性检查所有前置条件，给出分类失败建议。
"""

from __future__ import annotations

import os
import socket
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'
CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.yml'

# 关键依赖包（import 失败说明环境不完整）
CRITICAL_PACKAGES = (
    'openai',
    'yaml',
    'peewee',
)

# requests / urllib 用于网络检查，不作为关键依赖
# —— 网络检查是可选的 warning 级别


@dataclass
class CheckItem:
    """单条检查结果"""
    name: str
    label: str
    passed: bool
    severity: str = 'blocker'          # 'blocker' | 'warning'
    failure_type: str = ''             # 'config_blocked' | 'environment_blocked' | 'data_missing'
    detail: str = ''
    suggestion: str = ''


@dataclass
class PreflightResult:
    """前置检查汇总"""
    passed: bool = True
    checks: List[CheckItem] = field(default_factory=list)
    blockers: List[CheckItem] = field(default_factory=list)
    warnings: List[CheckItem] = field(default_factory=list)
    first_blocker: Optional[CheckItem] = None

    @property
    def all_passed(self) -> bool:
        return len(self.blockers) == 0


def _check_venv() -> CheckItem:
    """检查虚拟环境 python 是否存在"""
    candidates = [
        PROJECT_ROOT / 'venv' / 'bin' / 'python',
        PROJECT_ROOT / 'venv' / 'Scripts' / 'python.exe',
    ]
    for p in candidates:
        if p.exists():
            return CheckItem(
                name='venv_check',
                label='虚拟环境',
                passed=True,
            )
    return CheckItem(
        name='venv_check',
        label='虚拟环境',
        passed=False,
        severity='blocker',
        failure_type='environment_blocked',
        detail='venv 目录下未找到 Python 解释器',
        suggestion='python3 -m venv venv',
    )


def _check_dependencies() -> CheckItem:
    """检查关键包是否可导入"""
    missing = []
    for pkg in CRITICAL_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return CheckItem(
            name='dep_check',
            label='依赖包',
            passed=True,
        )
    return CheckItem(
        name='dep_check',
        label='依赖包',
        passed=False,
        severity='blocker',
        failure_type='environment_blocked',
        detail=f'缺少关键依赖: {", ".join(missing)}',
        suggestion='pip install -r requirements.txt',
    )


def _check_config() -> CheckItem:
    """检查 config.yml 是否存在且可解析。

    如果环境变量 DEEPSEEK_API_KEY 已设置，config.yml 缺失降级为 warning，
    因为 README 推荐的环境变量方式可以独立工作。
    """
    env_key = os.getenv('DEEPSEEK_API_KEY')
    if not CONFIG_PATH.exists():
        severity = 'warning' if env_key else 'blocker'
        return CheckItem(
            name='config_check',
            label='配置文件',
            passed=False,
            severity=severity,
            failure_type='config_blocked',
            detail=f'配置文件不存在: {CONFIG_PATH}',
            suggestion='请创建 config/config.yml（参考 config/config.example.yml）\n'
                       '  或设置环境变量 DEEPSEEK_API_KEY 可跳过此检查',
        )
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
    except Exception as exc:
        return CheckItem(
            name='config_check',
            label='配置文件',
            passed=False,
            severity='blocker',
            failure_type='config_blocked',
            detail=f'配置文件解析失败: {exc}',
            suggestion='请检查 config/config.yml 的 YAML 格式',
        )
    return CheckItem(
        name='config_check',
        label='配置文件',
        passed=True,
    )


def _check_api_key() -> CheckItem:
    """检查 DeepSeek API Key 是否可用（复用 check_deepseek_key 判定逻辑）"""
    env_key = os.getenv('DEEPSEEK_API_KEY')
    if env_key:
        return CheckItem(
            name='apikey_check',
            label='API Key',
            passed=True,
        )

    if not CONFIG_PATH.exists():
        return CheckItem(
            name='apikey_check',
            label='API Key',
            passed=False,
            severity='blocker',
            failure_type='config_blocked',
            detail='配置文件缺失，无法读取 API Key',
            suggestion='设置环境变量 DEEPSEEK_API_KEY 或创建 config/config.yml',
        )

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return CheckItem(
            name='apikey_check',
            label='API Key',
            passed=False,
            severity='blocker',
            failure_type='config_blocked',
            detail='配置文件解析失败，无法读取 API Key',
            suggestion='设置环境变量 DEEPSEEK_API_KEY',
        )

    api_key = (cfg.get('api_keys') or {}).get('deepseek')
    if api_key:
        return CheckItem(name='apikey_check', label='API Key', passed=True)

    api_key = (cfg.get('deepseek') or {}).get('api_key')
    if api_key:
        return CheckItem(name='apikey_check', label='API Key', passed=True)

    return CheckItem(
        name='apikey_check',
        label='API Key',
        passed=False,
        severity='blocker',
        failure_type='config_blocked',
        detail='未找到 DeepSeek API Key',
        suggestion='export DEEPSEEK_API_KEY="your-key"\n'
                   '  或在 config/config.yml 中设置 api_keys.deepseek',
    )


def _check_database() -> CheckItem:
    """检查数据库文件是否存在且 news_articles 表可查询。

    缺失时只做 warning：rss_finance_analyzer.py 首次抓取时会自动创建数据库和表。
    """
    if not DB_PATH.exists():
        return CheckItem(
            name='db_check',
            label='数据库',
            passed=False,
            severity='warning',
            failure_type='environment_blocked',
            detail=f'数据库文件不存在: {DB_PATH}',
            suggestion='首次运行 RSS 抓取时会自动创建，无需手动操作。',
        )
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute('SELECT COUNT(1) FROM news_articles')
        conn.close()
    except Exception as exc:
        return CheckItem(
            name='db_check',
            label='数据库',
            passed=False,
            severity='blocker',
            failure_type='environment_blocked',
            detail=f'数据库表结构异常: {exc}',
            suggestion='python scripts/init_db.py  # 重新初始化数据库',
        )
    return CheckItem(
        name='db_check',
        label='数据库',
        passed=True,
    )


def _check_today_data(today: str) -> CheckItem:
    """检查今日是否已有数据"""
    if not DB_PATH.exists():
        return CheckItem(
            name='today_data_check',
            label='今日数据',
            passed=False,
            severity='warning',
            failure_type='data_missing',
            detail='数据库不存在，跳过数据检查',
            suggestion='',
        )
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            'SELECT COUNT(1) FROM news_articles WHERE collection_date = ?',
            (today,),
        )
        count = cur.fetchone()[0]
        conn.close()
        if count > 0:
            return CheckItem(
                name='today_data_check',
                label='今日数据',
                passed=True,
                detail=f'{count} 篇',
            )
        return CheckItem(
            name='today_data_check',
            label='今日数据',
            passed=False,
            severity='warning',
            failure_type='data_missing',
            detail='今日尚无数据',
            suggestion='选择模式 1 或模式 3 抓取新闻数据',
        )
    except Exception as exc:
        return CheckItem(
            name='today_data_check',
            label='今日数据',
            passed=False,
            severity='warning',
            failure_type='data_missing',
            detail=f'查询失败: {exc}',
            suggestion='',
        )


def _check_network(timeout: float = 3.0) -> CheckItem:
    """检查 DeepSeek API 是否可达"""
    host = 'api.deepseek.com'
    port = 443
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return CheckItem(
            name='network_check',
            label='网络连接',
            passed=True,
        )
    except Exception:
        return CheckItem(
            name='network_check',
            label='网络连接',
            passed=False,
            severity='warning',
            failure_type='environment_blocked',
            detail=f'{host}:{port} 不可达',
            suggestion='请检查网络连接或代理设置',
        )


def run_preflight(today: str) -> PreflightResult:
    """
    运行全部前置检查。

    并行执行无依赖的检查项；有依赖的检查项串行。
    network_check 超时短，不拖慢整体。
    """
    result = PreflightResult()

    # 第 1 组：无依赖，可并行（实际串行也很快，总耗时 < 0.5s）
    items_1 = [
        _check_venv(),
        _check_dependencies(),
        _check_config(),
    ]
    result.checks.extend(items_1)

    # apikey 依赖 config，但 _check_api_key 内部已处理 config 缺失
    apikey = _check_api_key()
    result.checks.append(apikey)

    # db_check
    db_check = _check_database()
    result.checks.append(db_check)

    # today_data
    today_data = _check_today_data(today)
    result.checks.append(today_data)

    # network（放在最后，用户已看到前面的结果）
    network = _check_network(timeout=3.0)
    result.checks.append(network)

    # 汇总
    for item in result.checks:
        if not item.passed:
            if item.severity == 'blocker':
                result.blockers.append(item)
                if result.first_blocker is None:
                    result.first_blocker = item
            else:
                result.warnings.append(item)

    result.passed = len(result.blockers) == 0
    return result


def format_preflight_panel(result: PreflightResult) -> str:
    """生成 preflight 结果的终端展示文本"""

    # 检查结果图标行
    icons: List[str] = []
    for item in result.checks:
        if item.passed:
            icons.append(f'  ✅ {item.label}')
        elif item.severity == 'blocker':
            icons.append(f'  ❌ {item.label}')
        else:
            icons.append(f'  ⚠️ {item.label}')

    lines = [
        '━' * 46,
        '🔍 前置检查',
        '',
    ]
    # 每行放 3 个
    for i in range(0, len(icons), 3):
        lines.append(''.join(icons[i:i + 3]))

    lines.append('')

    if result.all_passed and not result.warnings:
        lines.append('结果: ✅ 全部通过')
    elif result.all_passed:
        warning_labels = [w.label for w in result.warnings]
        lines.append(f'结果: ⚠️ {len(result.warnings)} 项警告 ({", ".join(warning_labels)})，可继续运行')
    else:
        first = result.first_blocker
        lines.append(f'阻塞: ❌ {first.label} — {first.detail}')
        lines.append(f'修复: {first.suggestion}')
        if result.warnings:
            lines.append(f'另有 {len(result.warnings)} 项警告')

    lines.append('━' * 46)
    return '\n'.join(lines)


def print_preflight_panel(result: PreflightResult) -> None:
    """打印 preflight 结果到终端"""
    print(format_preflight_panel(result))
