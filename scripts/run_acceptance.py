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
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

try:
    from scripts.bootstrap import ensure_project_root
except ModuleNotFoundError:
    from bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from scripts.application.fact_checker import FactChecker
from scripts.application.quality_checker_v2 import check_report_quality_v2
from scripts.infrastructure.realtime_data_fetcher import RealtimeDataFetcher
from scripts.domain.cross_verification import (
    CROSS_STATUS_CONFIRMED,
    CROSS_STATUS_WEAK,
    CROSS_STATUS_CONFLICTED,
)
from scripts.application.daily_digest import (
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
    parser.add_argument('--stock-market', type=str, default='CN', choices=['CN', 'US'], help='股票市场: CN=A股, US=美股')
    parser.add_argument('--all-markets', action='store_true', help='依次验收 CN/US 并生成双市场总账')
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


def market_acceptance_report_path(date_str: str, market: str) -> Path:
    return acceptance_output_dir(date_str) / f'acceptance_report-{market.lower()}.json'


def acceptance_summary_path(date_str: str) -> Path:
    return acceptance_output_dir(date_str) / 'acceptance_summary.json'


def update_acceptance_summary(date_str: str, market: str, report_path: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    path = acceptance_summary_path(date_str)
    if path.exists():
        try:
            summary = load_json(path)
        except (OSError, json.JSONDecodeError):
            summary = {}
    else:
        summary = {}

    markets = summary.setdefault('markets', {})
    mode_checks = ((report.get('artifacts') or {}).get('modes') or {})
    markdown = mode_checks.get('markdown-report') or {}
    freshness = ((report.get('artifacts') or {}).get('freshness') or {}).get('markdown-report') or {}
    source_citations = markdown.get('source_citations') or {}
    claim_ledger = markdown.get('claim_ledger') or {}
    coverage_matrix = markdown.get('coverage_matrix') or {}
    evidence_diversity = markdown.get('evidence_diversity') or {}
    counter_evidence = markdown.get('counter_evidence') or {}
    evidence_audit = markdown.get('evidence_audit') or {}

    def required_passed(check: Dict[str, Any]) -> Optional[bool]:
        if not check.get('required'):
            return None
        return bool(check.get('passed'))

    def issues_from(label: str, check: Dict[str, Any], limit: int = 3) -> List[str]:
        if not isinstance(check, dict):
            return []
        return [
            f'{label}: {issue}'
            for issue in (check.get('issues') or [])[:limit]
        ]

    failure_reasons: List[str] = []
    if not freshness.get('fresh_artifacts'):
        failure_reasons.append('freshness: 未找到同日新鲜 markdown-report 产物')
    if (markdown.get('quality') or {}).get('passed') is False:
        failure_reasons.append('quality: 质量门禁未通过')
    if (markdown.get('stock_scoring') or {}).get('passed') is False:
        failure_reasons.append('stock_scoring: 结构化推荐门禁未通过')
    for label, check in (
        ('quality', markdown.get('quality') or {}),
        ('stock_scoring', markdown.get('stock_scoring') or {}),
        ('source_citations', source_citations),
        ('claim_ledger', claim_ledger),
        ('coverage_matrix', coverage_matrix),
        ('evidence_diversity', evidence_diversity),
        ('counter_evidence', counter_evidence),
        ('evidence_audit', evidence_audit),
    ):
        failure_reasons.extend(issues_from(label, check))
    failure_reasons = failure_reasons[:12]

    markets[market] = {
        'acceptance_report_path': str(report_path),
        'passed': bool(report.get('passed')),
        'report_path': markdown.get('report_path') or freshness.get('report_path'),
        'metadata_path': markdown.get('metadata_path') or freshness.get('metadata_path'),
        'fresh_artifacts': freshness.get('fresh_artifacts'),
        'quality_passed': (markdown.get('quality') or {}).get('passed'),
        'stock_scoring_passed': (markdown.get('stock_scoring') or {}).get('passed'),
        'cross_verification_required': ((markdown.get('metadata') or {}).get('cross_verification_required')),
        'source_citations_required': bool(source_citations.get('required')),
        'source_citations_passed': required_passed(source_citations),
        'claim_ledger_required': bool(claim_ledger.get('required')),
        'claim_ledger_passed': required_passed(claim_ledger),
        'coverage_matrix_required': bool(coverage_matrix.get('required')),
        'coverage_matrix_passed': required_passed(coverage_matrix),
        'evidence_diversity_required': bool(evidence_diversity.get('required')),
        'evidence_diversity_passed': required_passed(evidence_diversity),
        'counter_evidence_required': bool(counter_evidence.get('required')),
        'counter_evidence_passed': required_passed(counter_evidence),
        'evidence_audit_required': bool(evidence_audit.get('required')),
        'evidence_audit_passed': required_passed(evidence_audit),
        'failure_reasons': failure_reasons,
    }
    summary['date'] = date_str
    summary['generated_at'] = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    summary['passed'] = all(item.get('passed') for item in markets.values()) if markets else False
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def find_mode_artifacts(date_str: str, mode: str, model_suffix: str = 'deepseek', market: str = 'CN') -> Dict[str, List[Path]]:
    dirs = archive_dirs_for_date(date_str)
    mode_with_market = f"{mode}-{market.lower()}"
    # 新格式优先（含市场后缀）
    reports = sorted(dirs['reports'].glob(f"*_{mode_with_market}_{model_suffix}.md"), key=lambda p: p.stat().st_mtime)
    metadata = sorted(dirs['metadata'].glob(f"analysis_meta_*_{mode_with_market}_{model_suffix}.json"), key=lambda p: p.stat().st_mtime)
    # 回退旧格式（仅 CN 兼容无市场后缀的历史归档）
    if not reports and market == 'CN':
        reports = sorted(dirs['reports'].glob(f"*_{mode}_{model_suffix}.md"), key=lambda p: p.stat().st_mtime)
    if not metadata and market == 'CN':
        metadata = sorted(dirs['metadata'].glob(f"analysis_meta_*_{mode}_{model_suffix}.json"), key=lambda p: p.stat().st_mtime)
    return {'reports': reports, 'metadata': metadata}


def latest_artifact(date_str: str, mode: str, model_suffix: str = 'deepseek', market: str = 'CN') -> Dict[str, Optional[Path]]:
    artifacts = find_mode_artifacts(date_str, mode, model_suffix=model_suffix, market=market)
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
    checks['interactive_runner_entrypoint'] = 'ai_analyze_deepseek.py' in interactive_text
    checks['start_sh_markdown'] = '--mode markdown-report' in start_text
    checks['start_sh_entrypoint'] = 'ai_analyze_deepseek.py' in start_text

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
    stock_market: str = 'CN',
) -> List[str]:
    cmd = [
        python_bin,
        str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek.py'),
        '--date', date_str,
        '--mode', mode,
        '--content-field', content_field,
        '--max-articles', str(max_articles),
        '--max-retries', '1',
        '--min-score', '80',
        '--verify',
        '--output', str(output_json),
        '--stock-market', stock_market,
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
            'decision_views': payload.get('decision_views') or {},
            'judgment_candidates': payload.get('judgment_candidates') or [],
            'data_quality_stats': payload.get('data_quality_stats') or {},
            'output_mode': payload.get('output_mode'),
            'articles_used': payload.get('articles_used'),
            'verification_enabled': payload.get('verification_enabled'),
            'quality_check': payload.get('quality_check'),
            'market': payload.get('market'),
            'cross_verification': payload.get('cross_verification') or {},
            'cross_verification_required': payload.get('cross_verification_required') is True,
            'source_references': payload.get('source_references') or {},
            'source_references_required': payload.get('source_references_required') is True,
            'claim_ledger': payload.get('claim_ledger') or {},
            'claim_ledger_required': payload.get('claim_ledger_required') is True,
            'coverage_matrix': payload.get('coverage_matrix') or {},
            'coverage_matrix_required': payload.get('coverage_matrix_required') is True,
            'evidence_diversity': payload.get('evidence_diversity') or {},
            'evidence_diversity_required': payload.get('evidence_diversity_required') is True,
            'counter_evidence_ledger': payload.get('counter_evidence_ledger') or {},
            'counter_evidence_required': payload.get('counter_evidence_required') is True,
            'evidence_audit_path': payload.get('evidence_audit_path'),
            'evidence_audit_required': payload.get('evidence_audit_required') is True,
            'candidate_evidence_audit': payload.get('candidate_evidence_audit') or {},
            'scoring_calibration': payload.get('scoring_calibration') or {},
            'rejected_false_positive_mentions': payload.get('rejected_false_positive_mentions') or [],
        },
        'stock_recommendations': payload.get('stock_recommendations') or [],
        'score_distribution': payload.get('score_distribution') or {},
        'scoring_config': payload.get('scoring_config') or {},
        'decision_views': payload.get('decision_views') or {},
        'judgment_candidates': payload.get('judgment_candidates') or [],
        'data_quality_stats': payload.get('data_quality_stats') or {},
        'cross_verification': payload.get('cross_verification') or {},
        'cross_verification_required': payload.get('cross_verification_required') is True,
        'source_references': payload.get('source_references') or {},
        'source_references_required': payload.get('source_references_required') is True,
        'claim_ledger': payload.get('claim_ledger') or {},
        'claim_ledger_required': payload.get('claim_ledger_required') is True,
        'coverage_matrix': payload.get('coverage_matrix') or {},
        'coverage_matrix_required': payload.get('coverage_matrix_required') is True,
        'evidence_diversity': payload.get('evidence_diversity') or {},
        'evidence_diversity_required': payload.get('evidence_diversity_required') is True,
        'counter_evidence_ledger': payload.get('counter_evidence_ledger') or {},
        'counter_evidence_required': payload.get('counter_evidence_required') is True,
        'evidence_audit_path': payload.get('evidence_audit_path'),
        'evidence_audit_required': payload.get('evidence_audit_required') is True,
        'candidate_evidence_audit': payload.get('candidate_evidence_audit') or {},
        'scoring_calibration': payload.get('scoring_calibration') or {},
        'rejected_false_positive_mentions': payload.get('rejected_false_positive_mentions') or [],
    }


def validate_source_citations(report_text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    refs = metadata.get('source_references') or {}
    required = metadata.get('source_references_required') is True or refs.get('required') is True
    articles = refs.get('articles') if isinstance(refs, dict) else []
    articles = articles if isinstance(articles, list) else []
    known_ids = {str(item) for item in refs.get('article_ids') or []}
    known_ids.update(str(item.get('article_id')) for item in articles if isinstance(item, dict) and item.get('article_id') is not None)
    real_ids = re.findall(r'【新闻(\d+)】', report_text or '')
    placeholder_count = len(re.findall(r'【新闻X】', report_text or ''))
    unresolved_ids = sorted({item for item in real_ids if known_ids and item not in known_ids})
    issues: List[str] = []
    incomplete_refs: List[str] = []
    for item in articles:
        if not isinstance(item, dict):
            incomplete_refs.append('非对象引用')
            continue
        missing = [
            key for key in ('article_id', 'source', 'title', 'published')
            if item.get(key) in (None, '')
        ]
        if missing:
            incomplete_refs.append(f"{item.get('article_id', '?')}缺少{','.join(missing)}")
    if required and placeholder_count:
        issues.append(f'存在未回溯的新闻占位引用: 【新闻X】 {placeholder_count}处')
    if required and not real_ids:
        issues.append('报告正文缺少真实 article_id 新闻引用')
    if required and unresolved_ids:
        issues.append(f"存在未登记 source_references 的新闻引用: {', '.join(unresolved_ids[:10])}")
    if required and not articles:
        issues.append('metadata.source_references 缺少真实文章索引')
    if required and incomplete_refs:
        issues.append(f"metadata.source_references 存在不完整引用: {', '.join(incomplete_refs[:10])}")
    return {
        'required': required,
        'real_citation_count': len(real_ids),
        'placeholder_citation_count': placeholder_count,
        'registered_article_count': len(articles),
        'unresolved_ids': unresolved_ids,
        'incomplete_refs': incomplete_refs,
        'issues': issues,
        'passed': not issues,
    }


def validate_claim_ledger(metadata: Dict[str, Any]) -> Dict[str, Any]:
    ledger = metadata.get('claim_ledger') or {}
    required = metadata.get('claim_ledger_required') is True or ledger.get('required') is True
    claims = ledger.get('claims') if isinstance(ledger, dict) else None
    issues: List[str] = []
    if required and not isinstance(claims, list):
        issues.append('metadata.claim_ledger.claims 必须是列表')
    if isinstance(claims, list):
        required_fields = {
            'claim_id', 'market', 'claim_type', 'scope', 'content',
            'verified', 'verification_status', 'source', 'realtime_source',
            'timestamp', 'freshness_status', 'failure_reason', 'source_articles',
        }
        for item in claims:
            if not isinstance(item, dict):
                issues.append('claim_ledger 存在非对象条目')
                continue
            missing = sorted(required_fields - set(item.keys()))
            if missing:
                issues.append(f"{item.get('claim_id', '?')} 缺少字段: {', '.join(missing)}")
            if 'source_articles' in item and not isinstance(item.get('source_articles'), list):
                issues.append(f"{item.get('claim_id', '?')} source_articles 必须是列表")
            if item.get('verification_status') not in {'verified', 'failed'}:
                issues.append(f"{item.get('claim_id', '?')} verification_status 非法: {item.get('verification_status')}")
            if item.get('freshness_status') not in {'timestamped', 'missing_timestamp', 'not_applicable'}:
                issues.append(f"{item.get('claim_id', '?')} freshness_status 非法: {item.get('freshness_status')}")
    return {
        'required': required,
        'count': len(claims) if isinstance(claims, list) else 0,
        'summary': ledger.get('summary') if isinstance(ledger, dict) else {},
        'issues': issues,
        'passed': not issues,
    }


def validate_coverage_matrix(metadata: Dict[str, Any]) -> Dict[str, Any]:
    matrix = metadata.get('coverage_matrix') or {}
    required = metadata.get('coverage_matrix_required') is True or matrix.get('required') is True
    categories = matrix.get('categories') if isinstance(matrix, dict) else None
    issues: List[str] = []
    expected = {
        'macro_liquidity', 'policy_regulation', 'company_earnings',
        'industry_theme', 'risk_event', 'realtime_market',
    }
    if required and not isinstance(categories, dict):
        issues.append('metadata.coverage_matrix.categories 必须是对象')
    if isinstance(categories, dict):
        missing = sorted(expected - set(categories.keys()))
        if missing:
            issues.append(f"coverage_matrix 缺少类别: {', '.join(missing)}")
        for key, item in categories.items():
            if not isinstance(item, dict):
                issues.append(f'coverage_matrix.{key} 不是对象')
                continue
            if item.get('status') not in {'sufficient', 'partial', 'missing'}:
                issues.append(f"coverage_matrix.{key}.status 非法: {item.get('status')}")
    return {
        'required': required,
        'coverage_gaps': matrix.get('coverage_gaps') if isinstance(matrix, dict) else [],
        'issues': issues,
        'passed': not issues,
    }


def validate_evidence_diversity(metadata: Dict[str, Any]) -> Dict[str, Any]:
    diversity = metadata.get('evidence_diversity') or {}
    required = metadata.get('evidence_diversity_required') is True or diversity.get('required') is True
    issues: List[str] = []
    if required and not isinstance(diversity, dict):
        issues.append('metadata.evidence_diversity 必须是对象')
        diversity = {}
    if required:
        required_fields = {
            'market', 'total_articles', 'source_count', 'topic_count',
            'max_source_share', 'max_topic_share',
            'source_distribution', 'topic_distribution', 'source_tier_distribution',
            'concentration_flags',
            'passed',
        }
        missing = sorted(required_fields - set(diversity.keys()))
        if missing:
            issues.append(f"metadata.evidence_diversity 缺少字段: {', '.join(missing)}")
    for key in ('source_distribution', 'topic_distribution', 'entity_distribution', 'source_tier_distribution'):
        value = diversity.get(key)
        if value is not None and not isinstance(value, list):
            issues.append(f'metadata.evidence_diversity.{key} 必须是列表')
    for key in ('max_source_share', 'max_topic_share', 'max_entity_share', 'max_aggregator_share', 'original_source_share'):
        value = diversity.get(key)
        if value is not None and not isinstance(value, (int, float)):
            issues.append(f'metadata.evidence_diversity.{key} 必须是数字')
        elif isinstance(value, (int, float)) and not 0 <= float(value) <= 1:
            issues.append(f'metadata.evidence_diversity.{key} 超出0-1范围: {value}')
    flags = diversity.get('concentration_flags') or []
    if not isinstance(flags, list):
        issues.append('metadata.evidence_diversity.concentration_flags 必须是列表')
        flags = []
    if required and flags and diversity.get('passed') is True:
        issues.append('evidence_diversity 有集中度风险但 passed=true')
    if required and not flags and diversity.get('passed') is False:
        issues.append('evidence_diversity 无集中度风险但 passed=false')
    return {
        'required': required,
        'source_count': diversity.get('source_count'),
        'topic_count': diversity.get('topic_count'),
        'max_source_share': diversity.get('max_source_share'),
        'max_topic_share': diversity.get('max_topic_share'),
        'concentration_flags': flags,
        'issues': issues,
        'passed': not issues,
    }


def validate_counter_evidence(metadata: Dict[str, Any]) -> Dict[str, Any]:
    ledger = metadata.get('counter_evidence_ledger') or {}
    required = metadata.get('counter_evidence_required') is True or ledger.get('required') is True
    topics = ledger.get('topics') if isinstance(ledger, dict) else None
    issues: List[str] = []
    if required and not isinstance(topics, list):
        issues.append('metadata.counter_evidence_ledger.topics 必须是列表')
    if isinstance(topics, list):
        required_fields = {
            'topic', 'market', 'high_confidence_topic', 'evidence_article_ids',
            'supporting_article_ids', 'counter_article_ids',
            'counter_evidence_count', 'status',
        }
        for item in topics:
            if not isinstance(item, dict):
                issues.append('counter_evidence_ledger 存在非对象条目')
                continue
            missing = sorted(required_fields - set(item.keys()))
            if missing:
                issues.append(f"{item.get('topic', '?')} 缺少字段: {', '.join(missing)}")
            for key in ('evidence_article_ids', 'supporting_article_ids', 'counter_article_ids'):
                if key in item and not isinstance(item.get(key), list):
                    issues.append(f"{item.get('topic', '?')} {key} 必须是列表")
            if item.get('status') not in {'balanced', 'support_only', 'mixed', 'counter_only'}:
                issues.append(f"{item.get('topic', '?')} status 非法: {item.get('status')}")
            counter_count = item.get('counter_evidence_count')
            if not isinstance(counter_count, int) or counter_count < 0:
                issues.append(f"{item.get('topic', '?')} counter_evidence_count 非法: {counter_count}")
            elif isinstance(item.get('counter_article_ids'), list) and counter_count != len(item.get('counter_article_ids')):
                issues.append(f"{item.get('topic', '?')} counter_evidence_count 与 counter_article_ids 数量不一致")
    summary = ledger.get('summary') if isinstance(ledger, dict) else {}
    if required and not isinstance(summary, dict):
        issues.append('metadata.counter_evidence_ledger.summary 必须是对象')
        summary = {}
    return {
        'required': required,
        'topic_count': summary.get('topic_count') if isinstance(summary, dict) else None,
        'high_confidence_topics_with_counter_evidence': (
            summary.get('high_confidence_topics_with_counter_evidence') if isinstance(summary, dict) else None
        ),
        'issues': issues,
        'passed': not issues,
    }


def validate_evidence_audit(metadata: Dict[str, Any]) -> Dict[str, Any]:
    required = metadata.get('evidence_audit_required') is True
    audit_path = metadata.get('evidence_audit_path')
    issues: List[str] = []
    payload: Dict[str, Any] = {}
    if required and not audit_path:
        issues.append('metadata.evidence_audit_path 缺失')
    if audit_path:
        path = Path(audit_path)
        if not path.exists():
            issues.append(f'evidence_audit_path 不存在: {audit_path}')
        else:
            try:
                payload = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f'evidence_audit_path 无法读取: {exc}')
    if payload:
        required_sections = {
            'source_references', 'claim_ledger', 'coverage_matrix', 'evidence_diversity',
            'counter_evidence_ledger', 'decision_views', 'quality_check',
        }
        scoring_config = metadata.get('scoring_config') or {}
        if (
            metadata.get('candidate_evidence_audit')
            or scoring_config.get('evidence_relevance_enabled') is True
            or scoring_config.get('historical_calibration_enabled') is True
        ):
            required_sections.update({
                'candidate_evidence_audit',
                'scoring_calibration',
                'rejected_false_positive_mentions',
            })
        missing = sorted(required_sections - set(payload.keys()))
        if missing:
            issues.append(f"evidence_audit 缺少字段: {', '.join(missing)}")
        if payload.get('market') != metadata.get('market'):
            issues.append(f"evidence_audit.market={payload.get('market')} != metadata.market={metadata.get('market')}")
        if metadata.get('source_references_required') is True:
            meta_ids = {str(item) for item in ((metadata.get('source_references') or {}).get('article_ids') or [])}
            audit_ids = {str(item) for item in ((payload.get('source_references') or {}).get('article_ids') or [])}
            if meta_ids != audit_ids:
                issues.append('evidence_audit.source_references 与 metadata.source_references 不一致')
        if metadata.get('claim_ledger_required') is True:
            meta_summary = (metadata.get('claim_ledger') or {}).get('summary') or {}
            audit_summary = (payload.get('claim_ledger') or {}).get('summary') or {}
            if meta_summary != audit_summary:
                issues.append('evidence_audit.claim_ledger.summary 与 metadata.claim_ledger.summary 不一致')
        if metadata.get('coverage_matrix_required') is True:
            meta_categories = (metadata.get('coverage_matrix') or {}).get('categories') or {}
            audit_categories = (payload.get('coverage_matrix') or {}).get('categories') or {}
            if meta_categories != audit_categories:
                issues.append('evidence_audit.coverage_matrix.categories 与 metadata.coverage_matrix.categories 不一致')
        if metadata.get('evidence_diversity_required') is True:
            meta_diversity = metadata.get('evidence_diversity') or {}
            audit_diversity = payload.get('evidence_diversity') or {}
            for key in (
                'source_count', 'topic_count', 'max_source_share', 'max_topic_share',
                'max_aggregator_share', 'original_source_share', 'concentration_flags',
            ):
                if meta_diversity.get(key) != audit_diversity.get(key):
                    issues.append(f'evidence_audit.evidence_diversity.{key} 与 metadata.evidence_diversity.{key} 不一致')
        if metadata.get('counter_evidence_required') is True:
            meta_summary = (metadata.get('counter_evidence_ledger') or {}).get('summary') or {}
            audit_summary = (payload.get('counter_evidence_ledger') or {}).get('summary') or {}
            if meta_summary != audit_summary:
                issues.append('evidence_audit.counter_evidence_ledger.summary 与 metadata.counter_evidence_ledger.summary 不一致')
        if metadata.get('stock_recommendations'):
            meta_views = metadata.get('decision_views') or {}
            audit_views = payload.get('decision_views') or {}
            if meta_views != audit_views:
                issues.append('evidence_audit.decision_views 与 metadata.decision_views 不一致')
        if metadata.get('quality_check'):
            meta_quality = metadata.get('quality_check') or {}
            audit_quality = payload.get('quality_check') or {}
            for key in ('passed', 'score'):
                if meta_quality.get(key) != audit_quality.get(key):
                    issues.append(f'evidence_audit.quality_check.{key} 与 metadata.quality_check.{key} 不一致')
        for key in ('candidate_evidence_audit', 'scoring_calibration', 'rejected_false_positive_mentions'):
            meta_value = metadata.get(key)
            if meta_value and payload.get(key) != meta_value:
                issues.append(f'evidence_audit.{key} 与 metadata.{key} 不一致')
    return {
        'required': required,
        'path': audit_path,
        'issues': issues,
        'passed': not issues,
    }


def validate_stock_recommendations_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_export_payload(payload)
    metadata = normalized.get('metadata') or {}
    recommendations = metadata.get('stock_recommendations') or normalized.get('stock_recommendations') or []
    decision_views = metadata.get('decision_views') or normalized.get('decision_views') or {}
    required_fields = {
        'symbol', 'name', 'grade', 'base_grade', 'grade_caps', 'total_score', 'scores',
        'data_completeness', 'candidate_confidence', 'evidence_strength', 'industry_trend',
        'stale_opportunity_flag', 'crowding_flag', 'fresh_evidence_flag',
        'actionability_passed', 'actionability_reasons',
    }
    issues = []
    warnings = []
    high_grade_without_evidence = 0
    theme_mapping_strong_focus_count = 0
    strong_focus_with_incomplete = 0
    score_mismatch = 0
    missing_grade_caps_count = 0
    candidate_pool_low_quality = False
    stale_high_grade_count = 0
    crowded_high_grade_count = 0
    theme_only_overgraded_count = 0
    missing_forward_fields_count = 0
    decision_views_schema_passed = False
    actionable_count = 0
    actionable_with_fresh_evidence_count = 0
    actionable_without_independent_confirmation_count = 0
    allowed_grade_caps = {
        'insufficient_evidence',
        'insufficient_independent_confirmation',
        'no_direct_stock_evidence',
        'theme_mapping_watch_only',
        'data_incomplete',
        'insufficient_history',
        'missing_valuation_baseline',
        'risk_flag_present',
        'score_gate_not_met',
    }
    allowed_actionability_reasons = {
        'no_fresh_evidence',
        'insufficient_independent_confirmation',
        'theme_only_not_actionable',
        'stale_or_crowded',
        'grade_not_actionable',
        'cross_verification_conflicted',
        'cross_verification_not_confirmed',
    }
    output_json_schema_passed = all(
        key in normalized for key in ('metadata', 'stock_recommendations', 'score_distribution', 'scoring_config', 'decision_views')
    )
    scoring_config = metadata.get('scoring_config') or normalized.get('scoring_config') or {}
    cross_required = metadata.get('cross_verification_required') is True
    evidence_relevance_required = scoring_config.get('evidence_relevance_enabled') is True
    historical_calibration_required = scoring_config.get('historical_calibration_enabled') is True
    allowed_evidence_relevance_statuses = {
        'direct_material_news',
        'incidental_mention',
        'theme_proxy',
        'irrelevant_match',
    }
    expected_decision_view_keys = {'actionable_candidates', 'conditional_watchlist', 'stale_or_rejected'}
    recommendation_by_symbol = {
        item.get('symbol'): item for item in recommendations if item.get('symbol')
    }

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
        if item.get('source_type') == 'theme_mapping' and int((item.get('evidence_strength') or {}).get('direct_mentions') or 0) == 0 and item.get('grade') in {'关注', '强关注'}:
            theme_only_overgraded_count += 1
            issues.append(f"{item.get('symbol')} 纯 theme-only 且无新增直接证据，不得高于观察")
        if item.get('stale_opportunity_flag') and item.get('grade') == '强关注':
            stale_high_grade_count += 1
            issues.append(f"{item.get('symbol')} stale_opportunity_flag=true 不得输出强关注")
        if item.get('crowding_flag') and item.get('grade') in {'关注', '强关注'}:
            crowded_high_grade_count += 1
            issues.append(f"{item.get('symbol')} crowding_flag=true 不得高于观察")

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
        for field in ('validation_points', 'catalyst_path', 'failure_triggers'):
            if field not in item:
                missing_forward_fields_count += 1
                warnings.append(f"{item.get('symbol')} 缺少 {field}")
        if evidence_relevance_required:
            relevance_status = item.get('evidence_relevance_status')
            relevance_reasons = item.get('evidence_relevance_reasons')
            if relevance_status not in allowed_evidence_relevance_statuses:
                issues.append(f"{item.get('symbol')} evidence_relevance_status 非法或缺失: {relevance_status}")
            if relevance_reasons is None or not isinstance(relevance_reasons, list):
                issues.append(f"{item.get('symbol')} evidence_relevance_reasons 必须是列表")
            if item.get('source_type') == 'direct_news' and relevance_status != 'direct_material_news':
                issues.append(f"{item.get('symbol')} direct_news 缺少实质个股证据，不得进入评分池")
            if item.get('source_type') == 'theme_mapping' and relevance_status != 'theme_proxy':
                issues.append(f"{item.get('symbol')} theme_mapping 必须标记为 theme_proxy")
        if historical_calibration_required:
            calibration_status = item.get('historical_calibration_status')
            forward_stats = item.get('historical_forward_stats')
            if calibration_status not in {'样本不足', '未校准', '初步有效', '反向失效'}:
                issues.append(f"{item.get('symbol')} historical_calibration_status 非法或缺失: {calibration_status}")
            if not isinstance(forward_stats, dict):
                issues.append(f"{item.get('symbol')} historical_forward_stats 必须是对象")
            if item.get('grade') in {'关注', '强关注'} and calibration_status == '反向失效':
                issues.append(f"{item.get('symbol')} 历史校准反向失效，不得保持高等级")
        reasons = item.get('actionability_reasons') or []
        if any(reason not in allowed_actionability_reasons for reason in reasons):
            issues.append(f"{item.get('symbol')} 存在非法 actionability_reasons 枚举")

    if recommendations and all(
        item.get('source_type') == 'theme_mapping'
        and item.get('candidate_confidence') == 'low'
        and int((item.get('evidence_strength') or {}).get('direct_mentions') or 0) == 0
        for item in recommendations
    ):
        candidate_pool_low_quality = True
        warnings.append('推荐列表全部为弱证据 theme-only 候选，候选质量偏低')

    if isinstance(decision_views, dict) and expected_decision_view_keys.issubset(decision_views.keys()):
        known_symbols = {item.get('symbol') for item in recommendations if item.get('symbol')}
        decision_view_issues = []
        for key in expected_decision_view_keys:
            items = decision_views.get(key)
            if not isinstance(items, list):
                decision_view_issues.append(f'decision_views.{key} 不是列表')
                continue
            for item in items:
                if not isinstance(item, dict):
                    decision_view_issues.append(f'decision_views.{key} 存在非对象条目')
                    continue
                symbol = item.get('symbol')
                if symbol not in known_symbols:
                    decision_view_issues.append(f'decision_views.{key} 包含未知 symbol: {symbol}')
                    continue
                full_item = recommendation_by_symbol.get(symbol) or {}
                if key == 'actionable_candidates':
                    actionable_count += 1
                    if full_item.get('fresh_evidence_flag'):
                        actionable_with_fresh_evidence_count += 1
                    if int((full_item.get('evidence_strength') or {}).get('independent_evidence_count') or 0) < 1:
                        actionable_without_independent_confirmation_count += 1
                    if int((full_item.get('evidence_strength') or {}).get('direct_mentions') or 0) < 1:
                        decision_view_issues.append(f'{symbol} direct_mentions<1，不得进入 actionable_candidates')
                    if not full_item.get('actionability_passed'):
                        decision_view_issues.append(f'{symbol} 未通过 actionability 门槛却进入 actionable_candidates')
                    if not full_item.get('fresh_evidence_flag'):
                        decision_view_issues.append(f'{symbol} fresh_evidence_flag=false 不得进入 actionable_candidates')
                    if (
                        full_item.get('source_type') == 'theme_mapping'
                        and int((full_item.get('evidence_strength') or {}).get('direct_mentions') or 0) < 1
                    ):
                        decision_view_issues.append(f'{symbol} theme_mapping 且无 direct evidence，不得进入 actionable_candidates')
                    if evidence_relevance_required and full_item.get('evidence_relevance_status') != 'direct_material_news':
                        decision_view_issues.append(f'{symbol} 未通过实质证据相关性，不得进入 actionable_candidates')
                    if historical_calibration_required and full_item.get('historical_calibration_status') in {'未校准', '反向失效'}:
                        decision_view_issues.append(f'{symbol} 历史方向校准不足，不得进入 actionable_candidates')
                    cv_status = (full_item.get('evidence_strength') or {}).get('cross_verification_status')
                    if (cross_required or cv_status is not None) and cv_status != CROSS_STATUS_CONFIRMED:
                        decision_view_issues.append(f'{symbol} cross_verification_status 未 confirmed，不得进入 actionable_candidates')
                elif key == 'conditional_watchlist':
                    if full_item.get('stale_opportunity_flag') or full_item.get('crowding_flag') or full_item.get('grade') == '回避':
                        decision_view_issues.append(f'{symbol} 满足 stale/rejected 条件，不得进入 conditional_watchlist')
        if decision_view_issues:
            issues.extend(decision_view_issues)
        else:
            decision_views_schema_passed = True
    else:
        issues.append('缺少完整 decision_views 结构')

    # ---- 交叉验真 V1 校验 ----
    # 1. 对每个 recommendation 的 evidence_strength 校验
    for item in recommendations:
        evidence_strength = item.get('evidence_strength') or {}
        cv_status = evidence_strength.get('cross_verification_status')

        # Schema: status 枚举合法性
        if cv_status and cv_status not in {CROSS_STATUS_CONFIRMED, CROSS_STATUS_WEAK, CROSS_STATUS_CONFLICTED}:
            issues.append(f"{item.get('symbol')} 非法的 cross_verification_status: {cv_status}")

        # 语义 gate: theme-only 不能 cross confirmed
        source_type = item.get('source_type', '')
        direct_mentions = int(evidence_strength.get('direct_mentions', 0) or 0)
        if cv_status == CROSS_STATUS_CONFIRMED and source_type == 'theme_mapping' and direct_mentions < 1:
            issues.append(f"{item.get('symbol')} theme-only 不能 cross_verification_status=confirmed")

        # 语义 gate: conflicted 标的 actionability_passed 必须为 false
        if cv_status == CROSS_STATUS_CONFLICTED and item.get('actionability_passed'):
            issues.append(f"{item.get('symbol')} conflicted 标的 actionability_passed 必须为 false")

        # Schema: cross_verified_source_count >= 0
        cv_source_count = evidence_strength.get('cross_verified_source_count')
        if cv_source_count is not None and (not isinstance(cv_source_count, int) or cv_source_count < 0):
            issues.append(f"{item.get('symbol')} cross_verified_source_count 值非法: {cv_source_count}")

        # Schema: cross_verification_reasons 必须是 list
        cv_reasons = evidence_strength.get('cross_verification_reasons')
        if cv_reasons is not None and not isinstance(cv_reasons, list):
            issues.append(f"{item.get('symbol')} cross_verification_reasons 必须是 list")

    # 2. metadata 级别的 cross_verification schema 校验（兼容 --skip-fetch --skip-live 模式）
    metadata = normalized.get('metadata') or {}
    cv_meta = metadata.get('cross_verification')
    if cv_meta and isinstance(cv_meta, dict):
        if not isinstance(cv_meta.get('topic_checks'), list):
            issues.append('metadata.cross_verification.topic_checks 必须是 list')
        if not isinstance(cv_meta.get('stock_checks'), list):
            issues.append('metadata.cross_verification.stock_checks 必须是 list')
        if not isinstance(cv_meta.get('summary'), dict):
            issues.append('metadata.cross_verification.summary 必须是 dict')

        # 校验 stock_check 的 evidence_article_ids 可回溯
        for sc in cv_meta.get('stock_checks', []):
            if not isinstance(sc, dict):
                continue
            if not isinstance(sc.get('evidence_article_ids'), list):
                issues.append(
                    f"cross_verification stock_check {sc.get('symbol', '?')} 缺少 evidence_article_ids"
                )
            status = sc.get('status')
            if status not in {CROSS_STATUS_CONFIRMED, CROSS_STATUS_WEAK, CROSS_STATUS_CONFLICTED, None}:
                issues.append(
                    f"cross_verification stock_check {sc.get('symbol', '?')} status 非法: {status}"
                )

    # 3. 新产物强制存在 cross_verification
    metadata = normalized.get('metadata') or {}
    cross_verification_required = metadata.get('cross_verification_required') is True
    if recommendations and cross_verification_required:
        cv_meta = metadata.get('cross_verification')
        if not cv_meta or not isinstance(cv_meta, dict):
            issues.append('❌ 新产物 metadata 缺少 cross_verification 字段')
        else:
            # 检查每个推荐项是否有 cross_verification_status
            missing_cv = []
            for item in recommendations:
                evidence = item.get('evidence_strength') or {}
                if 'cross_verification_status' not in evidence:
                    missing_cv.append(item.get('symbol', '?'))
            if missing_cv:
                issues.append(
                    f"❌ 以下标的 evidence_strength 缺少 cross_verification_status: "
                    f"{', '.join(missing_cv)}"
                )

    return {
        'count': len(recommendations),
        'issues': issues,
        'warnings': warnings,
        'score_mismatch': score_mismatch,
        'high_grade_without_evidence': high_grade_without_evidence,
        'stale_high_grade_count': stale_high_grade_count,
        'crowded_high_grade_count': crowded_high_grade_count,
        'theme_only_overgraded_count': theme_only_overgraded_count,
        'theme_mapping_strong_focus_count': theme_mapping_strong_focus_count,
        'strong_focus_with_incomplete': strong_focus_with_incomplete,
        'missing_grade_caps_count': missing_grade_caps_count,
        'missing_forward_fields_count': missing_forward_fields_count,
        'actionable_count': actionable_count,
        'actionable_with_fresh_evidence_count': actionable_with_fresh_evidence_count,
        'actionable_without_independent_confirmation_count': actionable_without_independent_confirmation_count,
        'candidate_pool_low_quality': candidate_pool_low_quality,
        'output_json_schema_passed': output_json_schema_passed,
        'decision_views_schema_passed': decision_views_schema_passed,
        'passed': bool(output_json_schema_passed) and (not issues if recommendations else True)
                 and decision_views_schema_passed
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
        stock_recommendations=metadata.get('stock_recommendations') or export_payload.get('stock_recommendations') or [],
        judgment_candidates=metadata.get('judgment_candidates') or export_payload.get('judgment_candidates') or [],
        data_quality_stats=metadata.get('data_quality_stats') or export_payload.get('data_quality_stats') or {},
        cross_verification=metadata.get('cross_verification'),
        coverage_matrix=metadata.get('coverage_matrix'),
        evidence_diversity=metadata.get('evidence_diversity'),
        counter_evidence_ledger=metadata.get('counter_evidence_ledger'),
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
    quality_stats = quality_result.get('stats') or {}

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
            'judgment_candidates': metadata.get('judgment_candidates') or [],
            'data_quality_stats': metadata.get('data_quality_stats') or {},
            'cross_verification': metadata.get('cross_verification') or {},
            'cross_verification_required': metadata.get('cross_verification_required') is True,
            'source_references_required': metadata.get('source_references_required') is True,
            'claim_ledger_required': metadata.get('claim_ledger_required') is True,
            'coverage_matrix_required': metadata.get('coverage_matrix_required') is True,
            'evidence_diversity_required': metadata.get('evidence_diversity_required') is True,
            'counter_evidence_required': metadata.get('counter_evidence_required') is True,
            'evidence_audit_required': metadata.get('evidence_audit_required') is True,
            'candidate_evidence_audit': metadata.get('candidate_evidence_audit') or {},
            'scoring_calibration': metadata.get('scoring_calibration') or {},
            'rejected_false_positive_mentions': metadata.get('rejected_false_positive_mentions') or [],
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
        'source_citations': validate_source_citations(report_text, metadata),
        'claim_ledger': validate_claim_ledger(metadata),
        'coverage_matrix': validate_coverage_matrix(metadata),
        'evidence_diversity': validate_evidence_diversity(metadata),
        'counter_evidence': validate_counter_evidence(metadata),
        'evidence_audit': validate_evidence_audit(metadata),
        'suspicious_realtime_phrases': suspicious_realtime_phrases,
        'stock_scoring': validate_stock_recommendations_payload(export_payload) if mode == 'markdown-report' else {},
    }
    # market 一致性校验（judgment-cards 无 scoring_config，仅校验 meta.market 存在）
    meta_market = metadata.get('market')
    if mode == 'markdown-report':
        scoring_market = (metadata.get('scoring_config') or {}).get('market')
        market_consistency = {
            'meta_market': meta_market,
            'scoring_config_market': scoring_market,
            'passed': meta_market is not None and meta_market == scoring_market,
            'issues': [],
        }
        if not market_consistency['passed']:
            market_consistency['issues'].append(
                f"meta.market={meta_market} != scoring_config.market={scoring_market}"
            )
    else:
        # judgment-cards / realtime-monitor 模式：旧归档可能无 market 字段
        # 仅当 mode 名明确标记了市场后缀时才严格要求（如 "judgment-cards-us"）
        market_required = '-' in mode  # mode like "judgment-cards-us" indicates market suffix
        market_consistency = {
            'meta_market': meta_market,
            'passed': meta_market is not None if market_required else True,
            'issues': [] if (meta_market is not None or not market_required) else ['meta.market 缺失（mode 要求 market 后缀但缺失）'],
        }
    payload['market_consistency'] = market_consistency
    payload['passed'] = (
        all(structure.values())
        and quality_result.get('passed', False)
        and not quality_result.get('issues')
        and market_consistency['passed']
        and payload['source_citations']['passed']
        and payload['claim_ledger']['passed']
        and payload['coverage_matrix']['passed']
        and payload['evidence_diversity']['passed']
        and payload['counter_evidence']['passed']
        and payload['evidence_audit']['passed']
    )
    if mode == 'markdown-report':
        stock_scoring = payload['stock_scoring']
        payload['actionability'] = {
            'actionable_count': stock_scoring.get('actionable_count', 0),
            'actionable_with_fresh_evidence_count': stock_scoring.get('actionable_with_fresh_evidence_count', 0),
            'actionable_without_independent_confirmation_count': stock_scoring.get('actionable_without_independent_confirmation_count', 0),
            'watchlist_promoted_in_narrative_count': quality_stats.get('watchlist_promoted_in_narrative_count', 0),
            'verification_boundary_overclaim_count': quality_stats.get('verification_boundary_overclaim_count', 0),
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
    if args.all_markets:
        if args.output:
            raise SystemExit('--all-markets 会生成 market-specific 文件和 acceptance_summary.json，请不要同时传 --output')
        overall_passed = True
        market_reports = {}
        for market in ('CN', 'US'):
            output_path = market_acceptance_report_path(date_str, market)
            cmd = [
                args.python_bin,
                str(PROJECT_ROOT / 'scripts' / 'run_acceptance.py'),
                '--date', date_str,
                '--python', args.python_bin,
                '--max-articles', str(args.max_articles),
                '--content-field', args.content_field,
                '--stock-market', market,
                '--output', str(output_path),
            ]
            if args.skip_fetch:
                cmd.append('--skip-fetch')
            if args.skip_live:
                cmd.append('--skip-live')
            if args.api_key:
                cmd.extend(['--api-key', args.api_key])
            if args.run_started_at is not None:
                cmd.extend(['--run-started-at', str(args.run_started_at)])
            result = run_command(f'acceptance_{market.lower()}', cmd)
            report_payload = load_json(output_path) if output_path.exists() else {}
            market_reports[market] = {
                'command': {
                    'returncode': result.returncode,
                    'passed': result.passed,
                    'stdout_tail': result.stdout[-2000:],
                    'stderr_tail': result.stderr[-2000:],
                },
                'report_path': str(output_path),
                'passed': bool(result.passed and report_payload.get('passed')),
            }
            overall_passed = overall_passed and market_reports[market]['passed']
        summary = load_json(acceptance_summary_path(date_str)) if acceptance_summary_path(date_str).exists() else {}
        summary['market_runs'] = market_reports
        summary['passed'] = bool(overall_passed and all((summary.get('markets') or {}).get(m, {}).get('passed') for m in ('CN', 'US')))
        acceptance_summary_path(date_str).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'acceptance_summary': str(acceptance_summary_path(date_str)),
            'passed': summary['passed'],
        }, ensure_ascii=False))
        return 0 if summary['passed'] else 1

    acceptance_report_path = Path(args.output) if args.output else market_acceptance_report_path(date_str, args.stock_market)

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
        ('pytest', [args.python_bin, '-m', 'pytest', '-q', 'tests/test_fact_checker_quality.py', 'tests/test_investment_signal.py', 'tests/test_run_acceptance.py', 'tests/test_stock_recommendation.py', 'tests/test_cross_verification.py']),
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
        market=args.stock_market,
    )
    judgment_freshness = inspect_mode_artifacts(
        date_str,
        'judgment-cards',
        run_started_at=args.run_started_at,
        market=args.stock_market,
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
                stock_market=args.stock_market,
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
                market=args.stock_market,
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

        markdown_artifacts = find_mode_artifacts(date_str, 'markdown-report', market=args.stock_market)
        judgment_artifacts = find_mode_artifacts(date_str, 'judgment-cards', market=args.stock_market)
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
            stock_market=args.stock_market,
        )
        degrade_result = run_command('generate_markdown_degraded', degrade_cmd, env=degrade_env)
        latest_degrade = inspect_mode_artifacts(
            date_str,
            'markdown-report',
            run_started_at=args.run_started_at,
            market=args.stock_market,
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
        live_passed = (
            all(item.get('passed', True) for item in mode_checks.values()) if mode_checks else False
        ) and (
            freshness_check['markdown-report'].get('fresh_artifacts', False)
            and freshness_check['markdown-report'].get('artifact_session_match', False)
        )
    else:
        live_passed = all(item.get('passed', True) for item in mode_checks.values()) if mode_checks else False

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
    summary = update_acceptance_summary(date_str, args.stock_market, acceptance_report_path, report)

    print(json.dumps({
        'acceptance_report': str(acceptance_report_path),
        'acceptance_summary': str(acceptance_summary_path(date_str)),
        'passed': report['passed'],
        'markets': sorted((summary.get('markets') or {}).keys()),
    }, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
