#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财经日报自动化辅助工具。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SH_TZ = pytz.timezone('Asia/Shanghai')

NETWORK_ERROR_MARKERS = (
    'NameResolutionError',
    'nodename nor servname provided',
    'httpx.ConnectError',
    'openai.APIConnectionError: Connection error',
    'Connection error.',
    'Failed to resolve',
)

KNOWN_EXTERNAL_HOSTS = (
    'api.deepseek.com',
    'query1.finance.yahoo.com',
    'api.gold-api.com',
    'api.frankfurter.dev',
)


def shanghai_now() -> datetime:
    return datetime.now(SH_TZ)


def shanghai_today() -> str:
    return shanghai_now().strftime('%Y-%m-%d')


def archive_dirs_for_date(date_str: str) -> Dict[str, Path]:
    year_month = date_str[:7]
    base_dir = PROJECT_ROOT / 'docs' / 'archive' / year_month / date_str
    return {
        'base': base_dir,
        'reports': base_dir / 'reports',
        'metadata': base_dir / 'metadata',
    }


def parse_session_from_name(path: Path) -> Optional[str]:
    name = path.name
    if 'morning_' in name:
        return 'morning'
    if 'afternoon_' in name:
        return 'afternoon'
    if 'evening_' in name:
        return 'evening'
    if 'overnight_' in name:
        return 'overnight'
    return None


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


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


@dataclass
class ArtifactInspection:
    report: Optional[Path]
    metadata: Optional[Path]
    report_mtime: Optional[float]
    metadata_mtime: Optional[float]
    fresh_report: bool
    fresh_metadata: bool
    session_match: bool
    stale_artifacts: bool
    complete: bool
    session: Optional[str]
    metadata_payload: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'report_path': str(self.report) if self.report else None,
            'metadata_path': str(self.metadata) if self.metadata else None,
            'report_mtime': self.report_mtime,
            'metadata_mtime': self.metadata_mtime,
            'fresh_report': self.fresh_report,
            'fresh_metadata': self.fresh_metadata,
            'fresh_artifacts': self.fresh_report and self.fresh_metadata,
            'artifact_session_match': self.session_match,
            'stale_artifacts': self.stale_artifacts,
            'complete': self.complete,
            'session': self.session,
            'live_data_degraded': bool((self.metadata_payload or {}).get('live_data_degraded')),
        }


def inspect_mode_artifacts(
    date_str: str,
    mode: str,
    *,
    run_started_at: Optional[float] = None,
    model_suffix: str = 'deepseek',
    market: str = 'CN',
) -> ArtifactInspection:
    artifacts = find_mode_artifacts(date_str, mode, model_suffix=model_suffix, market=market)
    report = artifacts['reports'][-1] if artifacts['reports'] else None
    metadata = artifacts['metadata'][-1] if artifacts['metadata'] else None

    report_mtime = report.stat().st_mtime if report else None
    metadata_mtime = metadata.stat().st_mtime if metadata else None
    fresh_report = bool(report and (run_started_at is None or report_mtime >= run_started_at))
    fresh_metadata = bool(metadata and (run_started_at is None or metadata_mtime >= run_started_at))
    stale_artifacts = bool((report or metadata) and not (fresh_report and fresh_metadata))

    metadata_payload = load_json(metadata) if metadata and metadata.exists() else None
    report_session = parse_session_from_name(report) if report else None
    metadata_session = (
        (metadata_payload or {}).get('session')
        or (parse_session_from_name(metadata) if metadata else None)
    )
    session_match = bool(report_session and metadata_session and report_session == metadata_session)
    complete = bool(report and metadata and fresh_report and fresh_metadata and session_match)

    return ArtifactInspection(
        report=report,
        metadata=metadata,
        report_mtime=report_mtime,
        metadata_mtime=metadata_mtime,
        fresh_report=fresh_report,
        fresh_metadata=fresh_metadata,
        session_match=session_match,
        stale_artifacts=stale_artifacts,
        complete=complete,
        session=report_session or metadata_session,
        metadata_payload=metadata_payload,
    )


def classify_failure_text(text: str) -> Dict[str, Any]:
    text = text or ''
    matches = [marker for marker in NETWORK_ERROR_MARKERS if marker in text]
    hosts = sorted({host for host in KNOWN_EXTERNAL_HOSTS if host in text})
    rss_hosts = sorted(set(re.findall(r'https?://([^/\s]+)', text)))

    if matches:
        return {
            'failure_type': 'environment_blocked',
            'matched_markers': matches,
            'matched_hosts': hosts or rss_hosts,
        }

    if 'DEEPSEEK_API_KEY unavailable' in text or '未找到 DeepSeek API Key' in text:
        return {
            'failure_type': 'config_blocked',
            'matched_markers': ['missing_deepseek_key'],
            'matched_hosts': [],
        }

    return {
        'failure_type': 'logic_failed',
        'matched_markers': [],
        'matched_hosts': [],
    }


def strip_markdown(text: str) -> str:
    text = re.sub(r'`([^`]*)`', r'\1', text or '')
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text.strip()


def extract_section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf'^\#{{2,3}}\s+.*{re.escape(heading)}.*$([\s\S]*?)(?=^\#{{2,3}}\s+|\Z)',
        re.MULTILINE,
    )
    match = pattern.search(markdown or '')
    return match.group(1).strip() if match else ''


def first_meaningful_lines(block: str, limit: int) -> List[str]:
    results: List[str] = []
    for raw in (block or '').splitlines():
        line = strip_markdown(raw).lstrip('- ').strip()
        if not line or line.startswith('>') or line.startswith('|') or line.startswith('---'):
            continue
        if line.startswith('###'):
            line = line.lstrip('#').strip()
        if len(line) < 6:
            continue
        results.append(line)
        if len(results) >= limit:
            break
    return results


def extract_theme_titles(markdown: str, limit: int = 4) -> List[str]:
    section = extract_section(markdown, '重点投资主题分析')
    titles = []
    for line in section.splitlines():
        line = line.strip()
        if line.startswith('### '):
            titles.append(strip_markdown(line[4:]))
        if len(titles) >= limit:
            break
    return titles


def extract_risk_points(markdown: str, limit: int = 3) -> List[str]:
    section = extract_section(markdown, '风险提示')
    return first_meaningful_lines(section, limit)


def extract_watch_points(markdown: str, limit: int = 3) -> List[str]:
    for heading in ('本周重点关注', '短期策略', '重要事件日历'):
        section = extract_section(markdown, heading)
        if section:
            lines = first_meaningful_lines(section, limit)
            if lines:
                return lines
    return []

