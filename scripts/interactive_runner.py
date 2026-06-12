#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式运行器 —— 五模式入口

模式:
  1. 一键运行 —— 抓取+分析CN/US → 验收 → 摘要
  2. 自定义分析 —— 指定市场/日期/关键词/模式
  3. 仅抓取数据 —— 只更新新闻数据库
  4. 仅验收 —— 对已有产物运行验收
  5. 预览报告 —— 查看最近报告 / 启动 MkDocs

提示：本脚本不依赖第三方库（除项目内 utils）。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'
LAST_RUN_FILE = PROJECT_ROOT / '.last_run'

# ── print_utils 导入 ────────────────────────────────────────────
try:
    from scripts.infrastructure.print_utils import (
        print_header, print_success, print_warning, print_error,
        print_info, print_progress, print_plain,
        configure_dashboard, start_stage, update_stage, finish_stage,
        note_event, heartbeat, suspend_status, resume_status,
        prompt_input, prompt_yes_no,
    )
except ModuleNotFoundError:
    from scripts.infrastructure.print_utils import (  # type: ignore
        print_header, print_success, print_warning, print_error,
        print_info, print_progress, print_plain,
        configure_dashboard, start_stage, update_stage, finish_stage,
        note_event, heartbeat, suspend_status, resume_status,
        prompt_input, prompt_yes_no,
    )

# ── preflight 导入 ───────────────────────────────────────────────
try:
    from scripts.application.preflight import run_preflight, print_preflight_panel
except ModuleNotFoundError:
    from scripts.application.preflight import run_preflight, print_preflight_panel  # type: ignore

# ── 失败分类（复用 daily_digest） ──────────────────────────────────
try:
    from scripts.application.daily_digest import classify_failure_text
except ModuleNotFoundError:
    from scripts.application.daily_digest import classify_failure_text  # type: ignore


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def _venv_python() -> str:
    """获取 venv 中的 python 路径"""
    for candidate in (
        PROJECT_ROOT / 'venv' / 'bin' / 'python',
        PROJECT_ROOT / 'venv' / 'Scripts' / 'python.exe',
    ):
        if candidate.exists():
            return str(candidate)
    return 'python3'


def _normalize_cmd(cmd: list[str]) -> list[str]:
    """确保命令使用 venv python"""
    normalized = list(cmd)
    if normalized and normalized[0] in ('python3', 'python', 'py'):
        normalized[0] = _venv_python()
    return normalized


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours:02d}:{minutes:02d}:{secs:02d}'
    return f'{minutes:02d}:{secs:02d}'


def _run_streaming(cmd: list[str], *, label: str, cwd: Path | None = None) -> int:
    """流式执行命令，实时输出。返回退出码。"""
    cmd = _normalize_cmd(cmd)
    start_stage('执行任务', step=4, total=4, detail=f'启动 {label}')
    print_progress(f'执行: {" ".join(cmd)}')
    started = time.time()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'},
        cwd=cwd,
    )

    last_output = time.monotonic()
    with heartbeat(
        label,
        interval_seconds=6.0,
        details=('整理上下文', '等待命令返回', '继续等待输出'),
        should_emit=lambda _elapsed: time.monotonic() - last_output >= 6.0,
        before_emit=resume_status,
    ):
        if proc.stdout is not None:
            for line in proc.stdout:
                last_output = time.monotonic()
                suspend_status()
                print_plain(line.rstrip('\n'))
        code = proc.wait()

    resume_status()
    elapsed = time.time() - started
    if code == 0:
        finish_stage(f'{label}完成 ({_format_duration(elapsed)})', duration=False)
        note_event(f'{label}已完成')
    else:
        finish_stage(f'{label}失败，退出码 {code} ({_format_duration(elapsed)})', duration=False)
        note_event(f'{label}失败')
    return code


def _run_captured(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    """执行命令，捕获全部输出。返回 (退出码, 合并的stdout+stderr)。"""
    cmd = _normalize_cmd(cmd)
    proc = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or '') + '\n' + (proc.stderr or '')


def _classify_failure(returncode: int, output: str) -> dict:
    """对非零退出码执行失败分类"""
    if returncode == 0:
        return {'failure_type': 'success', 'matched_markers': [], 'matched_hosts': []}
    return classify_failure_text(output)


# ── 偏好记忆 ──────────────────────────────────────────────────────

def _load_last_run() -> dict:
    """加载上次运行偏好"""
    if LAST_RUN_FILE.exists():
        try:
            return json.loads(LAST_RUN_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save_last_run(data: dict) -> None:
    """保存本次运行偏好"""
    LAST_RUN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ── 用户交互 ──────────────────────────────────────────────────────

def _ask_mode() -> str:
    """询问运行模式"""
    last = _load_last_run()
    last_mode = last.get('mode', '1')
    # 校验存储值合法性，防止 .last_run 损坏导致静默跳过
    if last_mode not in ('1', '2', '3', '4', '5'):
        last_mode = '1'

    print_plain()
    print_plain('请选择运行模式:')
    print_plain()
    print_plain('  1. 🚀 一键运行 (推荐)')
    print_plain('     抓取+分析CN/US → 验收 → 摘要 → 打开报告')
    print_plain()
    print_plain('  2. 🔧 自定义分析')
    print_plain('     指定市场/日期/关键词/模式')
    print_plain()
    print_plain('  3. 📥 仅抓取数据')
    print_plain('     只更新新闻数据库，不分析')
    print_plain()
    print_plain('  4. ✅ 仅验收')
    print_plain('     对已有产物运行验收')
    print_plain()
    print_plain('  5. 📖 预览报告')
    print_plain('     查看最近报告 / 启动 MkDocs')
    print_plain()

    import sys as _sys
    while True:
        try:
            choice = prompt_input(f'输入数字选择 [{last_mode}]: ').strip()
        except (EOFError, OSError):
            return last_mode
        if not choice:
            return last_mode
        if choice in ('1', '2', '3', '4', '5'):
            return choice
        if not _sys.stdin.isatty():
            return '1'
        print_warning('请输入 1-5')


def _ask_market(last_choice: str = 'CN') -> str:
    """询问市场选择"""
    import sys as _sys
    label_map = {'CN': 'A 股', 'US': '美股', 'CN+US': 'A股+美股'}
    last_label = label_map.get(last_choice, last_choice)

    print_info('🌍 市场选择：')
    print_plain('  1. A 股（上证/深证/创业板）')
    print_plain('  2. 美股（S&P 500 / NASDAQ / Dow Jones）')
    print_plain('  3. A股+美股（双市场分析）')
    print_plain()

    while True:
        try:
            choice = prompt_input(f'请选择 [1/2/3，默认{last_label}]: ').strip()
        except (EOFError, OSError):
            return last_choice
        if not choice:
            return last_choice
        if choice == '1':
            return 'CN'
        if choice == '2':
            return 'US'
        if choice == '3':
            return 'CN+US'
        if not _sys.stdin.isatty():
            return last_choice
        print_warning('请输入 1、2 或 3')


def _ask_content_field() -> str:
    """询问分析字段"""
    print_info('📝 分析字段：')
    print_plain('  1. summary — 摘要优先（推荐，速度快）')
    print_plain('  2. content — 正文优先（信息详细，较慢）')
    print_plain('  3. auto   — 智能选择')
    print_plain()

    import sys as _sys
    while True:
        try:
            choice = prompt_input('请选择 [1/2/3，默认1]: ').strip()
        except (EOFError, OSError):
            return 'summary'
        if not choice or choice == '1':
            return 'summary'
        if choice == '2':
            return 'content'
        if choice == '3':
            return 'auto'
        if not _sys.stdin.isatty():
            return 'summary'
        print_warning('请输入 1、2 或 3')


# ══════════════════════════════════════════════════════════════════
# 各模式实现
# ══════════════════════════════════════════════════════════════════

def _run_rss_fetch(date_str: str, *, only_source: str = '') -> int:
    """运行 RSS 抓取"""
    cmd = [_venv_python(), str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py'),
           '--fetch-content']
    if only_source:
        cmd += ['--only-source', only_source]
    return _run_streaming(cmd, label='RSS 数据抓取')


def _run_ai_analysis(
    date_str: str,
    market: str,
    *,
    mode: str = 'markdown-report',
    content_field: str = 'summary',
    extra_args: list[str] | None = None,
) -> int:
    """运行 AI 分析"""
    cmd = [
        _venv_python(),
        str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek.py'),
        '--date', date_str,
        '--mode', mode,
        '--content-field', content_field,
        '--stock-market', market,
        '--verify',
        '--enable-stock-scoring',
    ]
    if extra_args:
        cmd += extra_args
    return _run_streaming(cmd, label=f'AI 分析 ({market})')


def _run_acceptance(date_str: str, markets: str) -> tuple[int, str]:
    """运行验收，返回 (退出码, 输出文本)"""
    cmd = [
        _venv_python(),
        str(PROJECT_ROOT / 'scripts' / 'run_acceptance.py'),
        '--date', date_str,
        '--all-markets',
        '--skip-fetch',
        '--skip-live',
    ]
    # 如果只验收单个市场
    if markets in ('CN', 'US'):
        cmd.remove('--all-markets')
        cmd += ['--stock-market', markets]
    return _run_captured(cmd)


def _get_latest_report_paths(date_str: str) -> dict[str, str | None]:
    """扫描当天 archive，返回 {market: report_path}"""
    from scripts.application.daily_digest import archive_dirs_for_date, find_mode_artifacts
    result: dict[str, str | None] = {}
    for market in ('CN', 'US'):
        artifacts = find_mode_artifacts(date_str, 'markdown-report', market=market)
        reports = artifacts.get('reports') or []
        result[market] = str(reports[-1]) if reports else None
    return result


def _build_summary_panel(
    date_str: str,
    elapsed: float,
    market_results: dict[str, dict],
) -> str:
    """构建收尾面板"""
    lines = [
        '━' * 56,
        f'📊 运行完成 · 用时 {_format_duration(elapsed)}',
        '',
    ]

    # 报告路径
    report_paths = _get_latest_report_paths(date_str)
    for market, path in report_paths.items():
        label = '🇨🇳 CN' if market == 'CN' else '🇺🇸 US'
        if path:
            rel = Path(path).relative_to(PROJECT_ROOT) if path else None
            lines.append(f'  {label} 报告  {rel}')
        else:
            lines.append(f'  {label} 报告  (未生成)')

    lines.append('')

    # 验收与可信度
    for market in ('CN', 'US'):
        info = market_results.get(market, {})
        if not info:
            continue
        label = 'CN' if market == 'CN' else 'US'

        passed = info.get('acceptance_passed')
        score = info.get('score', '?')
        verified = info.get('verified_claims', '?')
        total_claims = info.get('total_claims', '?')
        degraded = info.get('live_data_degraded', False)

        if passed:
            lines.append(f'  验收 {label}  ✅ 通过 ({score}/100)')
        elif passed is False:
            lines.append(f'  验收 {label}  ❌ 未通过 ({score}/100)')
        else:
            lines.append(f'  验收 {label}  ⏭ 未运行')

        lines.append(f'  事实核查 {label}  {verified}/{total_claims}')
        if degraded:
            lines.append(f'  实时行情    ⚠️ 降级 —— 结论依赖新闻与快照')

    lines.append('')
    lines.append('  下一步')
    lines.append('    mkdocs serve          预览文档站')
    lines.append('    模式 4                重新验收')
    lines.append('    模式 2                自定义重新分析')
    lines.append('━' * 56)
    return '\n'.join(lines)


def _extract_acceptance_info(acceptance_output: str) -> dict:
    """从 run_acceptance.py 的输出中提取关键信息。

    run_acceptance.py 输出格式: {passed: bool, summary: str, live_data_degraded: bool, ...}
    """
    info: dict = {'acceptance_passed': None, 'score': None,
                  'verified_claims': None, 'total_claims': None,
                  'live_data_degraded': False}
    try:
        data = json.loads(acceptance_output)
    except Exception:
        return info

    info['acceptance_passed'] = data.get('passed')
    info['live_data_degraded'] = data.get('live_data_degraded', False)
    return info


# ── 模式 1: 一键运行 ──────────────────────────────────────────────

def run_daily_flow(today: str, _preflight_warnings: list) -> int:
    """日常默认流：抓取 → CN+US 分析 → 验收 → 摘要"""
    last = _load_last_run()
    default_market = last.get('market', 'CN+US')
    default_field = last.get('content_field', 'summary')

    print_info('🚀 一键运行模式')
    print_plain()

    # 检查今日数据
    import sqlite3
    has_data = False
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.execute(
                'SELECT COUNT(1) FROM news_articles WHERE collection_date = ?', (today,)
            )
            has_data = cur.fetchone()[0] > 0
            conn.close()
        except Exception:
            pass

    if has_data:
        print_info(f'今日已抓取数据')
        if prompt_yes_no('是否重新抓取今天的数据？', default=False):
            if _run_rss_fetch(today) != 0:
                print_error('抓取失败，终止。')
                return 1
        else:
            print_info('跳过抓取，使用已有数据')
    else:
        print_info('今日尚无数据，开始抓取...')
        if _run_rss_fetch(today) != 0:
            print_error('抓取失败，终止。')
            return 1

    # 市场确认（一次确认）
    print_plain()
    market = _ask_market(last_choice=default_market)
    _save_last_run({'market': market, 'mode': '1', 'content_field': default_field})

    markets_to_run = market.split('+') if '+' in market else [market]

    # 总确认
    market_labels = ' + '.join(markets_to_run)
    print_plain()
    print_info(f'将分析 {market_labels} 市场，预计 3-5 分钟')
    ans = prompt_input('按 Enter 继续，输入 q 退出: ').strip().lower()
    if ans == 'q':
        print_info('已取消')
        return 0

    started = time.time()
    market_results: dict = {}
    any_failure = False

    for mkt in markets_to_run:
        print_header(f'分析 {mkt} 市场')
        # 分析
        code = _run_ai_analysis(today, mkt, content_field=default_field)
        if code != 0:
            print_error(f'{mkt} 分析失败')
            market_results[mkt] = {'error': 'analysis_failed'}
            any_failure = True
            continue
        market_results[mkt] = {'analysis_ok': True}

    # 验收
    print_header('运行验收')
    acc_code, acc_output = _run_acceptance(today, market)
    acceptance_info = _extract_acceptance_info(acc_output)
    if acc_code != 0:
        any_failure = True
    # 将验收结果写入每个已分析市场的 market_results
    for mkt in markets_to_run:
        if mkt in market_results and 'error' not in market_results[mkt]:
            market_results[mkt].update(acceptance_info)

    elapsed = time.time() - started

    # 收尾面板
    print_plain()
    panel = _build_summary_panel(today, elapsed, market_results)
    print(panel)

    # 打开预览
    if prompt_yes_no('是否启动 MkDocs 预览？', default=True):
        _run_mkdocs_preview()

    return 1 if any_failure else 0


# ── 模式 2: 自定义分析 ────────────────────────────────────────────

def run_custom_flow(today: str) -> int:
    """自定义分析流（保留原有交互逻辑，精简）"""
    print_info('🔧 自定义分析模式')
    print_plain()

    import sqlite3
    has_data = False
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.execute(
                'SELECT COUNT(1) FROM news_articles WHERE collection_date = ?', (today,)
            )
            has_data = cur.fetchone()[0] > 0
            conn.close()
        except Exception:
            pass

    # 数据确认
    if has_data:
        print_success(f'今日已有数据')
        if prompt_yes_no('是否重新抓取今天的数据？', default=False):
            fetch_content = prompt_yes_no('抓取正文写入数据库？', default=True)
            cmd = [_venv_python(), str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
            if fetch_content:
                cmd.append('--fetch-content')
            if _run_streaming(cmd, label='RSS 数据抓取') != 0:
                print_error('抓取失败')
                return 1
    else:
        print_warning('今日尚无数据')
        if not prompt_yes_no('是否现在抓取？', default=True):
            print_info('已取消')
            return 0
        fetch_content = prompt_yes_no('抓取正文写入数据库？', default=True)
        cmd = [_venv_python(), str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
        if fetch_content:
            cmd.append('--fetch-content')
        if _run_streaming(cmd, label='RSS 数据抓取') != 0:
            print_error('抓取失败')
            return 1

    # 分析配置
    print_plain()
    market = _ask_market()
    content_field = _ask_content_field()

    # 模式选择
    print_plain()
    print_info('📋 输出模式：')
    print_plain('  1. markdown-report — 完整分析报告（推荐）')
    print_plain('  2. judgment-cards — 判断卡片')
    print_plain()
    mode_choice = prompt_input('请选择 [1/2，默认1]: ').strip()
    analysis_mode = 'judgment-cards' if mode_choice == '2' else 'markdown-report'

    # 日期范围
    print_plain()
    date_mode = prompt_yes_no('仅分析当天？', default=True)
    extra_args = []
    if not date_mode:
        start = prompt_input('开始日期 YYYY-MM-DD: ').strip()
        end = prompt_input('结束日期 YYYY-MM-DD: ').strip()
        if start:
            extra_args += ['--start', start]
        if end:
            extra_args += ['--end', end]

    # 来源过滤
    print_plain()
    fsrc = prompt_input('仅分析来源（逗号分隔，可空）: ').strip()
    if fsrc:
        extra_args += ['--filter-source', fsrc]

    # 关键词过滤
    fkw = prompt_input('仅分析关键词（逗号分隔，可空）: ').strip()
    if fkw:
        extra_args += ['--filter-keyword', fkw]

    # 文章数量
    maxa = prompt_input('最多文章数（可空）: ').strip()
    if maxa.isdigit():
        extra_args += ['--max-articles', maxa]

    # 执行
    print_plain()
    print_info('🚀 开始执行自定义分析...')
    started = time.time()

    markets_to_run = market.split('+') if '+' in market else [market]
    for mkt in markets_to_run:
        code = _run_ai_analysis(
            today, mkt,
            mode=analysis_mode,
            content_field=content_field,
            extra_args=extra_args,
        )
        if code != 0:
            # 流式执行已将输出打印到终端，用户可向上滚动查看具体错误
            print_error(f'{mkt} 分析失败（退出码 {code}），请查看上方输出定位原因')
            print_info('常见原因：API Key 未配置、网络不通、或模型返回异常')
            return code

    elapsed = time.time() - started
    print_plain()
    print(f'━' * 56)
    print(f'📊 自定义分析完成 · 用时 {_format_duration(elapsed)}')
    print(f'━' * 56)

    if prompt_yes_no('是否启动 MkDocs 预览？', default=True):
        _run_mkdocs_preview()

    return 0


# ── 模式 3: 仅抓取数据 ────────────────────────────────────────────

def run_fetch_only(today: str) -> int:
    """只抓取新闻数据，不分析"""
    print_info('📥 仅抓取数据模式')
    print_plain()

    if prompt_yes_no('抓取正文写入数据库？', default=True):
        cmd = [_venv_python(), str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py'),
               '--fetch-content']
    else:
        cmd = [_venv_python(), str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]

    # 可选来源过滤
    only_src = prompt_input('仅抓取某些来源（逗号分隔，可空）: ').strip()
    if only_src:
        cmd += ['--only-source', only_src]

    code = _run_streaming(cmd, label='RSS 数据抓取')
    if code == 0:
        print_success('抓取完成。运行模式 1 可继续分析。')
    else:
        print_error('抓取失败，请查看上方日志')
    return code


# ── 模式 4: 仅验收 ────────────────────────────────────────────────

def run_acceptance_only(today: str) -> int:
    """对已有产物运行验收"""
    print_info('✅ 仅验收模式')
    print_plain()

    market = _ask_market(last_choice='CN+US')

    print_info(f'对 {today} 的 {market} 产物运行验收...')
    code, output = _run_acceptance(today, market)

    if code == 0:
        info = _extract_acceptance_info(output)
        score = info.get('score', '?')
        passed = info.get('acceptance_passed')
        status = '✅ 通过' if passed else ('❌ 未通过' if passed is False else '?')
        print_plain()
        print(f'验收结果: {status} (评分 {score})')
    else:
        print_error(f'验收脚本退出码 {code}')
        classification = _classify_failure(code, output)
        ft = classification.get('failure_type', '')
        if ft == 'environment_blocked':
            print_error('验收环境不完整，请检查')
        elif ft == 'config_blocked':
            print_error('配置阻塞，请检查 API Key 设置')

    return code


# ── 模式 5: 预览报告 ──────────────────────────────────────────────

def run_preview_only(today: str) -> int:
    """查看最近报告或启动 MkDocs"""
    print_info('📖 预览报告模式')
    print_plain()

    # 扫描最近 7 天
    from datetime import datetime, timedelta
    from scripts.application.daily_digest import archive_dirs_for_date, find_mode_artifacts

    print_plain('最近报告:')
    print_plain()

    found_any = False
    for i in range(7):
        d = datetime.strptime(today, '%Y-%m-%d') - timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')
        dirs = archive_dirs_for_date(ds)
        if not dirs['reports'].exists():
            continue
        for market in ('CN', 'US'):
            artifacts = find_mode_artifacts(ds, 'markdown-report', market=market)
            reports = artifacts.get('reports') or []
            if reports:
                found_any = True
                label = '🇨🇳' if market == 'CN' else '🇺🇸'
                latest = reports[-1]
                rel = latest.relative_to(PROJECT_ROOT)
                print_plain(f'  {ds} {label} {rel}')

    if not found_any:
        print_warning('未找到任何报告产物')

    print_plain()
    print_plain('选项:')
    print_plain('  1. 启动 MkDocs 预览 (mkdocs serve)')
    print_plain('  2. 退出')
    print_plain()

    choice = prompt_input('请选择 [1/2，默认1]: ').strip()
    if not choice or choice == '1':
        _run_mkdocs_preview()

    return 0


# ── MkDocs 预览 ───────────────────────────────────────────────────

def _run_mkdocs_preview() -> None:
    """启动 MkDocs 预览服务器"""
    print_info('启动 MkDocs 预览服务器...')
    print_info('访问地址: http://127.0.0.1:8000')
    print_info('按 Ctrl+C 停止')
    try:
        suspend_status()
        subprocess.run(['mkdocs', 'serve'], cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        print_info('预览服务器已停止')
    finally:
        resume_status()


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════

def main() -> int:
    today = datetime.now().strftime('%Y-%m-%d')
    configure_dashboard(title='Financial Report', total_steps=4)

    print_header("财经新闻分析系统")
    print_info(f'日期：{today}')
    note_event(f'当前分析日期: {today}')

    # ── Preflight ────────────────────────────────────────────────
    preflight = run_preflight(today)
    print_preflight_panel(preflight)

    if not preflight.all_passed:
        # 有 blocker
        print_plain()
        print_error('前置检查未通过，请先修复以上阻塞项再运行。')
        return 1

    # ── 模式选择 ──────────────────────────────────────────────────
    mode = _ask_mode()

    print_plain()

    if mode == '1':
        return run_daily_flow(today, preflight.warnings)
    elif mode == '2':
        return run_custom_flow(today)
    elif mode == '3':
        return run_fetch_only(today)
    elif mode == '4':
        return run_acceptance_only(today)
    elif mode == '5':
        return run_preview_only(today)
    else:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
