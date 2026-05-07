#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经日报自动化专用入口。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.daily_digest import (  # noqa: E402
    archive_dirs_for_date,
    classify_failure_text,
    extract_risk_points,
    extract_theme_titles,
    extract_watch_points,
    inspect_mode_artifacts,
    load_json,
    shanghai_now,
    shanghai_today,
    strip_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='运行财经日报自动化摘要流程')
    parser.add_argument('--date', type=str, help='指定日期 YYYY-MM-DD，默认按 Asia/Shanghai 取今天')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='summary')
    parser.add_argument('--output', type=str, help='结构化结果输出路径')
    return parser.parse_args()


def choose_python() -> str:
    venv_python = PROJECT_ROOT / 'venv' / 'bin' / 'python'
    return str(venv_python) if venv_python.exists() else 'python3'


def run_command(name: str, cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout or '') + '\n' + (proc.stderr or '')
    return {
        'name': name,
        'cmd': cmd,
        'returncode': proc.returncode,
        'passed': proc.returncode == 0,
        'stdout_tail': (proc.stdout or '')[-4000:],
        'stderr_tail': (proc.stderr or '')[-4000:],
        'failure': classify_failure_text(combined) if proc.returncode != 0 else None,
    }


def read_text(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ''
    return path.read_text(encoding='utf-8')


def summarize_stock_views(stock_items: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    if not stock_items:
        return ['暂无高确信标的。']

    ranked = sorted(
        stock_items,
        key=lambda item: (
            0 if item.get('source_type') == 'direct_news' else 1,
            -(item.get('total_score') or 0),
        ),
    )

    strong_items = []
    for item in ranked:
        grade = item.get('grade') or '未知'
        caps = item.get('grade_caps') or []
        source_type = item.get('source_type')
        if grade == '观察' and ('theme_mapping_watch_only' in caps or source_type == 'theme_mapping'):
            continue
        strong_items.append(item)

    target_items = strong_items[:limit] if strong_items else []
    if not target_items:
        return ['暂无高确信标的，当前推荐以观察名单为主。']

    lines = []
    for item in target_items:
        evidence = item.get('evidence_strength') or {}
        direct = evidence.get('direct_mentions') or 0
        independent = evidence.get('independent_evidence_count') or 0
        caps = '、'.join(item.get('grade_caps') or []) or '无'
        risks = '、'.join((item.get('risks') or [])[:2]) or '未见显著额外风险'
        lines.append(
            f"{item.get('name')}（{item.get('grade')}）: 证据 direct={direct}/independent={independent}，"
            f"压级={caps}，风险={risks}"
        )
    return lines


def build_digest_summary(
    *,
    date_str: str,
    main_result: Dict[str, Any],
    acceptance_report: Optional[Dict[str, Any]],
    artifact_info: Dict[str, Any],
) -> str:
    markdown_info = artifact_info['markdown-report']
    use_report_context = bool(markdown_info.get('fresh_artifacts') and markdown_info.get('artifact_session_match'))
    report_text = ''
    metadata: Dict[str, Any] = {}
    if use_report_context:
        report_text = read_text(Path(markdown_info['report_path'])) if markdown_info.get('report_path') else ''
        metadata = load_json(Path(markdown_info['metadata_path'])) if markdown_info.get('metadata_path') else {}
    collected_path = archive_dirs_for_date(date_str)['base'] / 'collected_data.json'
    collected = load_json(collected_path) if collected_path.exists() else {}

    failure_type = 'success'
    if not main_result.get('passed'):
        failure_type = (main_result.get('failure') or {}).get('failure_type') or 'logic_failed'

    status_map = {
        'success': '成功',
        'environment_blocked': '环境阻塞',
        'config_blocked': '配置阻塞',
        'logic_failed': '逻辑失败',
    }

    themes = extract_theme_titles(report_text, limit=4) if use_report_context else []
    risks = extract_risk_points(report_text, limit=3) if use_report_context else []
    watches = extract_watch_points(report_text, limit=3) if use_report_context else []
    stock_lines = summarize_stock_views((metadata.get('stock_recommendations') or [])[:10], limit=3) if use_report_context else []

    quality_notes: List[str] = []
    if metadata.get('live_data_degraded'):
        quality_notes.append('实时行情已降级，结论主要依赖新闻与本地快照。')
    quality_check = metadata.get('quality_check') or {}
    stats = quality_check.get('stats') or {}
    if stats.get('verified_claims') is not None and stats.get('total_claims') is not None:
        quality_notes.append(f"事实核查 {stats.get('verified_claims')}/{stats.get('total_claims')}。")
    if markdown_info.get('stale_artifacts'):
        quality_notes.append('当天目录存在旧产物，本次运行未生成可确认的新报告。')
    if acceptance_report:
        blocked_reason = (acceptance_report.get('automation') or {}).get('blocked_reason')
        if blocked_reason == 'pytest_missing':
            quality_notes.append('轻量验收缺少 pytest，环境仍需补齐。')
    if not quality_notes:
        quality_notes.append('未见额外质量降级信号。')

    total_articles = collected.get('total_articles')
    source_stats = []
    if total_articles:
        source_stats.append(f'采集文章 {total_articles} 篇')
    articles_used = metadata.get('articles_used') if use_report_context else None
    if articles_used:
        source_stats.append(f'报告使用 {articles_used} 篇')

    lines = [
        f"运行结果：{status_map.get(failure_type, failure_type)}。",
    ]
    if source_stats:
        lines.append(f"数据概况：{'，'.join(source_stats)}。")
    if themes:
        lines.append(f"主线：{'；'.join(themes[:4])}。")
    if risks:
        lines.append(f"风险点：{'；'.join(risks[:3])}。")
    if watches:
        lines.append(f"继续跟踪：{'；'.join(watches[:3])}。")
    if stock_lines:
        lines.append(f"标的观察：{'；'.join(stock_lines[:3])}")
    if quality_notes:
        lines.append(f"质量与异常：{'；'.join(quality_notes[:4])}")

    return '\n'.join(lines)


def main() -> int:
    args = parse_args()
    python_bin = choose_python()
    date_str = args.date or shanghai_today()
    run_started_at = shanghai_now().timestamp()

    out_dir = PROJECT_ROOT / 'data' / 'acceptance' / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    acceptance_output = out_dir / 'acceptance_report.json'

    key_check = run_command(
        'check_deepseek_key',
        [python_bin, str(PROJECT_ROOT / 'scripts' / 'check_deepseek_key.py')],
    )

    result: Dict[str, Any] = {
        'date': date_str,
        'run_started_at': run_started_at,
        'python_bin': python_bin,
        'steps': {
            'check_deepseek_key': key_check,
        },
        'artifacts': {},
        'summary': '',
        'passed': False,
    }

    if not key_check['passed']:
        result['failure_type'] = 'config_blocked'
        result['summary'] = '运行结果：配置阻塞。DeepSeek key 不可用，主分析未启动。'
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    main_cmd = [str(PROJECT_ROOT / 'scripts' / 'run_start_noninteractive.sh')]
    main_result = run_command('run_start_noninteractive', main_cmd)
    result['steps']['run_start_noninteractive'] = main_result

    acceptance_cmd = [
        python_bin,
        str(PROJECT_ROOT / 'scripts' / 'run_acceptance.py'),
        '--date', date_str,
        '--skip-fetch',
        '--skip-live',
        '--run-started-at', str(run_started_at),
        '--output', str(acceptance_output),
    ]
    acceptance_result = run_command('run_acceptance', acceptance_cmd)
    result['steps']['run_acceptance'] = acceptance_result
    acceptance_report = load_json(acceptance_output) if acceptance_output.exists() else None

    markdown_freshness = inspect_mode_artifacts(
        date_str,
        'markdown-report',
        run_started_at=run_started_at,
    )
    result['artifacts'] = {
        'markdown-report': markdown_freshness.to_dict(),
        'collected_data_exists': (archive_dirs_for_date(date_str)['base'] / 'collected_data.json').exists(),
    }

    acceptance_passed = bool(acceptance_result['passed'] and acceptance_report and acceptance_report.get('passed'))
    success = bool(
        main_result['passed']
        and markdown_freshness.complete
        and acceptance_output.exists()
        and acceptance_passed
    )
    result['passed'] = success
    if success and (markdown_freshness.metadata_payload or {}).get('live_data_degraded'):
        result['live_data_degraded'] = True
    if not success:
        result['failure_type'] = (main_result.get('failure') or {}).get('failure_type') or 'logic_failed'
        if markdown_freshness.stale_artifacts:
            result['stale_artifacts'] = True

    result['summary'] = build_digest_summary(
        date_str=date_str,
        main_result=main_result,
        acceptance_report=acceptance_report,
        artifact_info={'markdown-report': markdown_freshness.to_dict()},
    )

    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
