#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财经分析链路验收脚本

覆盖内容：
1. 自动化测试与语法检查
2. RSS抓取与数据库入库校验
3. Markdown Report / Judgment Cards 产物校验
4. 双模式不覆盖专项验收
5. 实时数据全失败降级专项验收
6. 质量评分与人工抽样清单输出
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.fact_checker import FactChecker
from scripts.utils.quality_checker_v2 import check_report_quality_v2
from scripts.utils.realtime_data_fetcher import RealtimeDataFetcher
from scripts.utils.daily_digest import (
    archive_dirs_for_date,
    inspect_mode_artifacts,
    load_json,
)


@dataclass
class CommandResult:
    name: str
    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='执行财经分析链路验收')
    parser.add_argument('--date', type=str, help='验收日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--python', dest='python_bin', default=sys.executable, help='Python解释器路径')
    parser.add_argument('--api-key', type=str, help='DeepSeek API Key（默认读取环境变量）')
    parser.add_argument('--max-articles', type=int, default=20, help='分析时最多使用多少篇文章')
    parser.add_argument('--content-field', choices=['summary', 'content', 'auto'], default='summary', help='分析字段模式')
    parser.add_argument('--skip-fetch', action='store_true', help='跳过RSS抓取步骤')
    parser.add_argument('--skip-live', action='store_true', help='跳过需要调用模型的实时验收步骤')
    parser.add_argument('--output', type=str, help='验收报告输出路径（JSON）')
    parser.add_argument('--run-started-at', type=float, help='本次自动化启动时间戳（epoch秒）')
    return parser.parse_args()


def beijing_today() -> str:
    return datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')


def run_command(
    name: str,
    cmd: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Path = PROJECT_ROOT,
) -> CommandResult:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        name=name,
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def acceptance_output_dir(date_str: str) -> Path:
    out_dir = PROJECT_ROOT / 'data' / 'acceptance' / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def find_mode_artifacts(date_str: str, mode: str, model_suffix: str = 'deepseek') -> Dict[str, List[Path]]:
    dirs = archive_dirs_for_date(date_str)
    report_glob = f"*_{mode}_{model_suffix}.md"
    meta_glob = f"analysis_meta_*_{mode}_{model_suffix}.json"
    return {
        'reports': sorted(dirs['reports'].glob(report_glob), key=lambda p: p.stat().st_mtime),
        'metadata': sorted(dirs['metadata'].glob(meta_glob), key=lambda p: p.stat().st_mtime),
    }


def latest_artifact(date_str: str, mode: str, model_suffix: str = 'deepseek') -> Dict[str, Optional[Path]]:
    artifacts = find_mode_artifacts(date_str, mode, model_suffix=model_suffix)
    return {
        'report': artifacts['reports'][-1] if artifacts['reports'] else None,
        'metadata': artifacts['metadata'][-1] if artifacts['metadata'] else None,
    }


def inspect_database(date_str: str) -> Dict[str, Any]:
    db_path = PROJECT_ROOT / 'data' / 'news_data.db'
    result: Dict[str, Any] = {
        'db_exists': db_path.exists(),
        'row_count': 0,
        'extended_fields': {},
        'passed': False,
    }
    if not db_path.exists():
        return result

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row_count = conn.execute(
            'SELECT COUNT(1) AS cnt FROM news_articles WHERE collection_date = ?',
            (date_str,),
        ).fetchone()['cnt']
        result['row_count'] = row_count

        fields = {}
        for field in ('source_tier', 'content_quality_status', 'investment_relevance', 'is_original_source'):
            try:
                value = conn.execute(
                    f'SELECT COUNT(1) AS cnt FROM news_articles WHERE collection_date = ? AND {field} IS NOT NULL AND {field} != ""',
                    (date_str,),
                ).fetchone()['cnt']
            except sqlite3.OperationalError:
                value = 0
            fields[field] = value
        result['extended_fields'] = fields
        result['passed'] = row_count > 0 and all(v > 0 for v in fields.values())
        return result
    finally:
        conn.close()


def validate_entrypoint_wiring() -> Dict[str, Any]:
    checks = {}
    interactive_text = (PROJECT_ROOT / 'scripts' / 'interactive_runner.py').read_text(encoding='utf-8')
    start_text = (PROJECT_ROOT / 'start.sh').read_text(encoding='utf-8')

    checks['interactive_runner_markdown'] = '--mode' in interactive_text and 'markdown-report' in interactive_text
    checks['interactive_runner_judgment'] = '--mode' in interactive_text and 'judgment-cards' in interactive_text
    checks['interactive_runner_entrypoint'] = 'ai_analyze_deepseek_verified.py' in interactive_text
    checks['start_sh_markdown'] = '--mode markdown-report' in start_text
    checks['start_sh_entrypoint'] = 'ai_analyze_deepseek_verified.py' in start_text

    return {
        'checks': checks,
        'passed': all(checks.values()),
    }


def build_analysis_command(
    python_bin: str,
    *,
    date_str: str,
    mode: str,
    content_field: str,
    max_articles: int,
    output_json: Path,
) -> List[str]:
    cmd = [
        python_bin,
        str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'),
        '--date', date_str,
        '--mode', mode,
        '--content-field', content_field,
        '--max-articles', str(max_articles),
        '--max-retries', '1',
        '--min-score', '80',
        '--output', str(output_json),
    ]
    if mode == 'markdown-report':
        cmd.append('--enable-stock-scoring')
    return cmd


def normalize_export_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if 'metadata' in payload and isinstance(payload.get('metadata'), dict):
        return payload
    return {
        'metadata': {
            'stock_recommendations': payload.get('stock_recommendations') or [],
            'score_distribution': payload.get('score_distribution') or {},
            'scoring_config': payload.get('scoring_config') or {},
            'output_mode': payload.get('output_mode'),
            'articles_used': payload.get('articles_used'),
            'verification_enabled': payload.get('verification_enabled'),
            'quality_check': payload.get('quality_check'),
        },
        'stock_recommendations': payload.get('stock_recommendations') or [],
        'score_distribution': payload.get('score_distribution') or {},
        'scoring_config': payload.get('scoring_config') or {},
    }


def validate_stock_recommendations_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_export_payload(payload)
    metadata = normalized.get('metadata') or {}
    recommendations = metadata.get('stock_recommendations') or normalized.get('stock_recommendations') or []
    required_fields = {
        'symbol', 'name', 'grade', 'base_grade', 'grade_caps', 'total_score', 'scores',
        'data_completeness', 'candidate_confidence', 'evidence_strength', 'industry_trend',
    }
    issues = []
    warnings = []
    high_grade_without_evidence = 0
    theme_mapping_strong_focus_count = 0
    strong_focus_with_incomplete = 0
    score_mismatch = 0
    missing_grade_caps_count = 0
    candidate_pool_low_quality = False
    allowed_grade_caps = {
        'insufficient_evidence',
        'no_direct_stock_evidence',
        'theme_mapping_watch_only',
        'data_incomplete',
        'insufficient_history',
        'missing_valuation_baseline',
        'risk_flag_present',
        'score_gate_not_met',
    }
    output_json_schema_passed = all(
        key in normalized for key in ('metadata', 'stock_recommendations', 'score_distribution', 'scoring_config')
    )
    scoring_config = metadata.get('scoring_config') or normalized.get('scoring_config') or {}

    for item in recommendations:
        missing = sorted(required_fields - set(item.keys()))
        if missing:
            issues.append(f"{item.get('symbol', 'unknown')} 缺少字段: {', '.join(missing)}")
            continue

        scores = item.get('scores') or {}
        total_score = item.get('total_score')
        if isinstance(total_score, int) and sum(scores.values()) != total_score:
            score_mismatch += 1
            issues.append(f"{item.get('symbol')} 子分求和与总分不一致")

        if item.get('grade') in {'关注', '强关注'} and not item.get('evidence_article_ids'):
            high_grade_without_evidence += 1
            issues.append(f"{item.get('symbol')} 高等级推荐缺少新闻证据")

        if item.get('grade') == '强关注' and float(item.get('data_completeness', 0)) < 0.7:
            strong_focus_with_incomplete += 1
            issues.append(f"{item.get('symbol')} 数据不完整却给出强关注")

        if item.get('source_type') == 'theme_mapping' and item.get('grade') == '强关注':
            theme_mapping_strong_focus_count += 1
            issues.append(f"{item.get('symbol')} 主题映射股不允许输出强关注")

        grade_caps = item.get('grade_caps')
        if item.get('base_grade') != item.get('grade') and not grade_caps:
            missing_grade_caps_count += 1
            issues.append(f"{item.get('symbol')} 已压级但未写出 grade_caps")
        elif grade_caps and any(cap not in allowed_grade_caps for cap in grade_caps):
            issues.append(f"{item.get('symbol')} 存在非法 grade_caps 枚举")

        evidence_strength = item.get('evidence_strength') or {}
        direct_mentions = int(evidence_strength.get('direct_mentions') or 0)
        independent_evidence_count = int(evidence_strength.get('independent_evidence_count') or 0)
        if item.get('grade') in {'关注', '强关注'} and independent_evidence_count < 1:
            issues.append(f"{item.get('symbol')} 高等级推荐缺少最小独立证据")
        if item.get('grade') == '强关注' and direct_mentions < 1:
            high_grade_without_evidence += 1
            issues.append(f"{item.get('symbol')} 强关注缺少直接个股证据")

    if recommendations and all(
        item.get('source_type') == 'theme_mapping'
        and item.get('candidate_confidence') == 'low'
        and int((item.get('evidence_strength') or {}).get('direct_mentions') or 0) == 0
        for item in recommendations
    ):
        candidate_pool_low_quality = True
        warnings.append('推荐列表全部为弱证据 theme-only 候选，候选质量偏低')

    return {
        'count': len(recommendations),
        'issues': issues,
        'warnings': warnings,
        'score_mismatch': score_mismatch,
        'high_grade_without_evidence': high_grade_without_evidence,
        'theme_mapping_strong_focus_count': theme_mapping_strong_focus_count,
        'strong_focus_with_incomplete': strong_focus_with_incomplete,
        'missing_grade_caps_count': missing_grade_caps_count,
        'candidate_pool_low_quality': candidate_pool_low_quality,
        'output_json_schema_passed': output_json_schema_passed,
        'passed': bool(output_json_schema_passed) and (not issues if recommendations else True)
                 and scoring_config.get('pool_mode') == 'strict'
                 and scoring_config.get('value_acceptance_enabled') is True,
    }


def fetch_realtime_context(force_failure: bool = False) -> Optional[Dict[str, Any]]:
    prev = os.environ.get('FINANCIAL_REPORT_FORCE_REALTIME_FAILURE')
    try:
        if force_failure:
            os.environ['FINANCIAL_REPORT_FORCE_REALTIME_FAILURE'] = '1'
        elif 'FINANCIAL_REPORT_FORCE_REALTIME_FAILURE' in os.environ:
            del os.environ['FINANCIAL_REPORT_FORCE_REALTIME_FAILURE']
        data = RealtimeDataFetcher().fetch_all()
        kinds = sum(1 for key in ('stocks', 'gold', 'forex') if data.get(key))
        return data if kinds > 0 else None
    finally:
        if prev is None:
            os.environ.pop('FINANCIAL_REPORT_FORCE_REALTIME_FAILURE', None)
        else:
            os.environ['FINANCIAL_REPORT_FORCE_REALTIME_FAILURE'] = prev


def analyze_report_quality(
    report_path: Path,
    metadata_path: Path,
    *,
    mode: str,
    realtime_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    report_text = report_path.read_text(encoding='utf-8')
    export_payload = normalize_export_payload(load_json(metadata_path))
    metadata = export_payload.get('metadata') or {}
    verification_context = realtime_data
    if verification_context is None:
        verification_context = {
            '_skip_live_fetch': True,
            'stocks': {},
            'gold': None,
            'forex': {},
        }

    checker = FactChecker()
    claims = checker.extract_claims(report_text)
    verified_claims = checker.verify_claims(claims, verification_context)
    quality_result = check_report_quality_v2(
        report_text=report_text,
        claims=verified_claims,
        realtime_data=realtime_data,
        report_mode=mode,
    )

    required_sections = (
        ['市场概况', '投资主题', '风险', '建议', '股票推荐评分']
        if mode == 'markdown-report'
        else ['判断卡片', '观察项']
    )
    structure = {section: section in report_text for section in required_sections}
    suspicious_realtime_phrases = [
        phrase for phrase in ('基于实时数据', '现价', '收涨', '收跌', '美元兑人民币为', '现货黄金')
        if phrase in report_text
    ]
    if realtime_data is None:
        suspicious_realtime_phrases = []

    payload = {
        'report_path': str(report_path),
        'metadata_path': str(metadata_path),
        'metadata': {
            'output_mode': metadata.get('output_mode'),
            'articles_used': metadata.get('articles_used'),
            'verification_enabled': metadata.get('verification_enabled'),
            'quality_check': metadata.get('quality_check'),
            'thesis_count': metadata.get('thesis_count'),
            'watch_item_count': metadata.get('watch_item_count'),
            'degraded': metadata.get('degraded'),
            'live_data_degraded': metadata.get('live_data_degraded'),
            'stock_recommendations': metadata.get('stock_recommendations') or [],
            'score_distribution': metadata.get('score_distribution') or {},
            'scoring_config': metadata.get('scoring_config') or {},
        },
        'required_sections': structure,
        'claims': {
            'total': len(claims),
            'verified': sum(1 for c in verified_claims if c.verified),
            'realtime': sum(1 for c in verified_claims if c.scope.value == '实时行情断言'),
            'news_fact': sum(1 for c in verified_claims if c.scope.value == '新闻事实断言'),
            'violations': sum(1 for c in verified_claims if c.scope.value == '违规预测断言'),
        },
        'quality': quality_result,
        'citation_count': report_text.count('【新闻'),
        'suspicious_realtime_phrases': suspicious_realtime_phrases,
        'stock_scoring': validate_stock_recommendations_payload(export_payload) if mode == 'markdown-report' else {},
        'passed': all(structure.values()) and quality_result.get('passed', False) and not quality_result.get('issues'),
    }
    if mode == 'markdown-report':
        payload['passed'] = payload['passed'] and payload['stock_scoring'].get('passed', True)
    return payload


def analyze_mode_output(
    *,
    report_path: Optional[Path],
    export_json_path: Path,
    mode: str,
    realtime_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not export_json_path.exists():
        return {
            'passed': False,
            'error': f'缺少结构化导出文件: {export_json_path}',
            'report_path': str(report_path) if report_path else None,
            'metadata_path': str(export_json_path),
        }
    if not report_path or not report_path.exists():
        return {
            'passed': False,
            'error': '未找到对应模式报告产物',
            'report_path': str(report_path) if report_path else None,
            'metadata_path': str(export_json_path),
        }
    return analyze_report_quality(
        report_path,
        export_json_path,
        mode=mode,
        realtime_data=realtime_data,
    )


def build_manual_checklist() -> List[str]:
    return [
        '确认 Markdown 报告不是简单复述新闻，而是有清晰结论提炼。',
        '确认没有把新闻中的旧行情数字包装成“基于实时数据”或“现价”。',
        '确认没有把同比、环比、财报增速写成当前实时涨跌。',
        '确认 Judgment Cards 区分了事实、推断、风险。',
        '确认观察项承接了证据不足内容，而不是强行输出确定性结论。',
        '确认建议具有跟踪价值，不是模板化、空泛表述。',
        '确认股票推荐评分章节包含总分、子分、等级、数据完整度与失效条件。',
    ]


def detect_blocked_reason(checks: List[Dict[str, Any]]) -> Optional[str]:
    for item in checks:
        stderr_tail = item.get('stderr_tail') or ''
        if 'No module named pytest' in stderr_tail:
            return 'pytest_missing'
    return None


def main() -> int:
    args = parse_args()
    date_str = args.date or beijing_today()
    out_dir = acceptance_output_dir(date_str)
    acceptance_report_path = Path(args.output) if args.output else (out_dir / 'acceptance_report.json')

    env = os.environ.copy()
    if args.api_key:
        env['DEEPSEEK_API_KEY'] = args.api_key

    report: Dict[str, Any] = {
        'date': date_str,
        'generated_at': datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
        'automation': {},
        'database': {},
        'entrypoints': {},
        'artifacts': {},
        'manual_checklist': build_manual_checklist(),
        'passed': False,
    }

    automation_results = []
    for name, cmd in (
        ('pytest', [args.python_bin, '-m', 'pytest', '-q', 'tests/test_fact_checker_quality.py', 'tests/test_investment_signal.py', 'tests/test_run_acceptance.py', 'tests/test_stock_recommendation.py']),
        ('compileall', [args.python_bin, '-m', 'compileall', 'scripts', 'tests']),
    ):
        result = run_command(name, cmd, env=env)
        automation_results.append({
            'name': name,
            'cmd': result.cmd,
            'returncode': result.returncode,
            'passed': result.passed,
            'stdout_tail': result.stdout[-2000:],
            'stderr_tail': result.stderr[-2000:],
        })
    report['automation']['checks'] = automation_results
    report['automation']['passed'] = all(item['passed'] for item in automation_results)
    blocked_reason = detect_blocked_reason(automation_results)
    if blocked_reason:
        report['automation']['blocked_reason'] = blocked_reason

    fetch_result = None
    if not args.skip_fetch:
        fetch_result = run_command(
            'rss_fetch',
            [args.python_bin, str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py'), '--fetch-content'],
            env=env,
        )
        report['automation']['rss_fetch'] = {
            'returncode': fetch_result.returncode,
            'passed': fetch_result.passed,
            'stdout_tail': fetch_result.stdout[-4000:],
            'stderr_tail': fetch_result.stderr[-4000:],
        }

    report['database'] = inspect_database(date_str)
    report['entrypoints'] = validate_entrypoint_wiring()

    mode_checks: Dict[str, Any] = {}
    overlap_check: Dict[str, Any] = {}
    degrade_check: Dict[str, Any] = {}
    freshness_check: Dict[str, Any] = {}

    markdown_freshness = inspect_mode_artifacts(
        date_str,
        'markdown-report',
        run_started_at=args.run_started_at,
    )
    judgment_freshness = inspect_mode_artifacts(
        date_str,
        'judgment-cards',
        run_started_at=args.run_started_at,
    )
    freshness_check = {
        'markdown-report': markdown_freshness.to_dict(),
        'judgment-cards': judgment_freshness.to_dict(),
    }

    if args.skip_live and markdown_freshness.complete:
        mode_checks['markdown-report'] = analyze_report_quality(
            markdown_freshness.report,
            markdown_freshness.metadata,
            mode='markdown-report',
            realtime_data=None,
        )
    elif args.skip_live:
        mode_checks['markdown-report'] = {
            'passed': False,
            'error': '未找到本次新鲜 markdown-report 产物',
            **markdown_freshness.to_dict(),
        }

    if not args.skip_live:
        if 'DEEPSEEK_API_KEY' not in env or not env['DEEPSEEK_API_KEY']:
            raise SystemExit('执行实时验收需要设置 DEEPSEEK_API_KEY 或传入 --api-key')

        realtime_data = fetch_realtime_context(force_failure=False)

        live_runs = []
        for mode in ('judgment-cards', 'markdown-report', 'markdown-report', 'judgment-cards'):
            output_json = out_dir / f'{mode}_latest.json'
            cmd = build_analysis_command(
                args.python_bin,
                date_str=date_str,
                mode=mode,
                content_field=args.content_field,
                max_articles=args.max_articles,
                output_json=output_json,
            )
            result = run_command(f'generate_{mode}', cmd, env=env)
            live_runs.append({
                'mode': mode,
                'returncode': result.returncode,
                'passed': result.passed,
                'stdout_tail': result.stdout[-4000:],
                'stderr_tail': result.stderr[-4000:],
            })
        report['automation']['live_runs'] = live_runs

        for mode in ('markdown-report', 'judgment-cards'):
            output_json = out_dir / f'{mode}_latest.json'
            freshness = inspect_mode_artifacts(
                date_str,
                mode,
                run_started_at=args.run_started_at,
            )
            if not freshness.complete:
                mode_checks[mode] = {
                    'passed': False,
                    'error': '未找到本次新鲜产物或 session 不匹配',
                    **freshness.to_dict(),
                }
                continue
            mode_checks[mode] = analyze_mode_output(
                report_path=freshness.report,
                export_json_path=output_json,
                mode=mode,
                realtime_data=realtime_data,
            )
            mode_checks[mode].update(freshness.to_dict())

        markdown_artifacts = find_mode_artifacts(date_str, 'markdown-report')
        judgment_artifacts = find_mode_artifacts(date_str, 'judgment-cards')
        overlap_check = {
            'markdown_reports': [str(p) for p in markdown_artifacts['reports']],
            'judgment_reports': [str(p) for p in judgment_artifacts['reports']],
            'markdown_metadata': [str(p) for p in markdown_artifacts['metadata']],
            'judgment_metadata': [str(p) for p in judgment_artifacts['metadata']],
            'passed': bool(markdown_artifacts['reports'] and judgment_artifacts['reports']
                           and markdown_artifacts['metadata'] and judgment_artifacts['metadata']),
        }

        degrade_output = out_dir / 'markdown-report_degraded.json'
        degrade_env = env.copy()
        degrade_env['FINANCIAL_REPORT_FORCE_REALTIME_FAILURE'] = '1'
        degrade_cmd = build_analysis_command(
            args.python_bin,
            date_str=date_str,
            mode='markdown-report',
            content_field=args.content_field,
            max_articles=args.max_articles,
            output_json=degrade_output,
        )
        degrade_result = run_command('generate_markdown_degraded', degrade_cmd, env=degrade_env)
        latest_degrade = inspect_mode_artifacts(
            date_str,
            'markdown-report',
            run_started_at=args.run_started_at,
        )
        degrade_analysis = None
        if latest_degrade.report and latest_degrade.metadata:
            degrade_analysis = analyze_mode_output(
                report_path=latest_degrade.report,
                export_json_path=degrade_output,
                mode='markdown-report',
                realtime_data=None,
            )
        degrade_check = {
            'command': {
                'returncode': degrade_result.returncode,
                'passed': degrade_result.passed,
                'stdout_tail': degrade_result.stdout[-4000:],
                'stderr_tail': degrade_result.stderr[-4000:],
            },
            'analysis': degrade_analysis,
            'log_has_degrade_notice': '实时行情接口当前均不可用' in (degrade_result.stdout + degrade_result.stderr),
            'passed': bool(
                degrade_result.passed
                and '实时行情接口当前均不可用' in (degrade_result.stdout + degrade_result.stderr)
                and degrade_analysis
                and not degrade_analysis['suspicious_realtime_phrases']
                and not degrade_analysis['quality']['stats']['has_realtime_data']
            ),
        }

    report['artifacts']['modes'] = mode_checks
    report['artifacts']['same_session_overlap'] = overlap_check
    report['artifacts']['degrade'] = degrade_check
    report['artifacts']['freshness'] = freshness_check

    live_passed = True
    if not args.skip_live:
        live_passed = (
            all(item.get('passed') for item in mode_checks.values())
            and overlap_check.get('passed', False)
            and degrade_check.get('passed', False)
        )
    elif args.run_started_at is not None:
        live_passed = freshness_check['markdown-report'].get('fresh_artifacts', False) and freshness_check['markdown-report'].get('artifact_session_match', False)

    report['passed'] = (
        report['automation']['passed']
        and report['database'].get('passed', False)
        and report['entrypoints'].get('passed', False)
        and (fetch_result.passed if fetch_result is not None else True)
        and live_passed
    )

    acceptance_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(acceptance_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        'acceptance_report': str(acceptance_report_path),
        'passed': report['passed'],
    }, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
