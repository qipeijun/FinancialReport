from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.run_daily_digest import summarize_stock_views
from scripts import run_daily_digest
from scripts.application import daily_digest


def test_classify_failure_text_detects_network_block():
    result = daily_digest.classify_failure_text(
        "openai.APIConnectionError: Connection error. Failed to resolve api.deepseek.com"
    )

    assert result['failure_type'] == 'environment_blocked'
    assert 'api.deepseek.com' in result['matched_hosts']


def test_inspect_mode_artifacts_marks_stale_when_files_are_older(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_digest, 'PROJECT_ROOT', tmp_path)
    base = tmp_path / 'docs' / 'archive' / '2026-05' / '2026-05-07'
    reports = base / 'reports'
    metadata = base / 'metadata'
    reports.mkdir(parents=True)
    metadata.mkdir(parents=True)

    report_path = reports / '📅 2026-05-07 财经分析报告_morning_markdown-report-cn_deepseek.md'
    meta_path = metadata / 'analysis_meta_morning_markdown-report-cn_deepseek.json'
    report_path.write_text('# report', encoding='utf-8')
    meta_path.write_text('{"session":"morning","live_data_degraded":false}', encoding='utf-8')

    inspection = daily_digest.inspect_mode_artifacts(
        '2026-05-07',
        'markdown-report',
        run_started_at=report_path.stat().st_mtime + 10,
    )

    assert inspection.stale_artifacts is True
    assert inspection.complete is False
    assert inspection.session_match is True


def test_summarize_stock_views_skips_theme_only_watch_list():
    lines = summarize_stock_views(
        [
            {
                'name': '中科曙光',
                'grade': '观察',
                'grade_caps': ['theme_mapping_watch_only'],
                'source_type': 'theme_mapping',
                'total_score': 78,
                'evidence_strength': {'direct_mentions': 0, 'independent_evidence_count': 3},
                'risks': [],
            }
        ]
    )

    assert lines == ['暂无高确信标的，当前推荐以观察名单为主。']


def test_daily_digest_main_uses_noninteractive_runner(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(run_daily_digest, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(
        run_daily_digest,
        'parse_args',
        lambda: SimpleNamespace(date='2026-05-07', content_field='summary', markets='CN,US', output=None),
    )
    monkeypatch.setattr(run_daily_digest, 'choose_python', lambda: '/tmp/fake-python')

    captured = []

    def fake_run_command(name, cmd):
        captured.append((name, cmd))
        if name == 'check_deepseek_key':
            return {'name': name, 'cmd': cmd, 'returncode': 0, 'passed': True, 'stdout_tail': '', 'stderr_tail': '', 'failure': None}
        if name == 'run_start_noninteractive':
            return {'name': name, 'cmd': cmd, 'returncode': 0, 'passed': True, 'stdout_tail': '', 'stderr_tail': '', 'failure': None}
        if name == 'run_acceptance':
            out_path = tmp_path / 'data' / 'acceptance' / '2026-05-07' / 'acceptance_summary.json'
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                '{"passed": true, "markets": {"CN": {"passed": true}, "US": {"passed": true}}}',
                encoding='utf-8',
            )
            return {'name': name, 'cmd': cmd, 'returncode': 0, 'passed': True, 'stdout_tail': '', 'stderr_tail': '', 'failure': None}
        raise AssertionError(name)

    monkeypatch.setattr(run_daily_digest, 'run_command', fake_run_command)

    class FakeInspection:
        complete = True
        metadata_payload = {}

        def to_dict(self):
            return {
                'report_path': None,
                'metadata_path': None,
                'fresh_artifacts': True,
                'artifact_session_match': True,
                'stale_artifacts': False,
                'complete': True,
            }

    monkeypatch.setattr(run_daily_digest, 'inspect_mode_artifacts', lambda *args, **kwargs: FakeInspection())
    monkeypatch.setattr(run_daily_digest, 'archive_dirs_for_date', lambda date_str: {'base': tmp_path / 'docs' / 'archive' / '2026-05' / date_str})
    monkeypatch.setattr(run_daily_digest, 'load_json', lambda path: {'passed': True, 'markets': {'CN': {'passed': True}, 'US': {'passed': True}}})
    monkeypatch.setattr(run_daily_digest, 'build_digest_summary', lambda **kwargs: 'ok')

    code = run_daily_digest.main()

    assert code == 0
    assert [name for name, _ in captured] == ['check_deepseek_key', 'run_start_noninteractive', 'run_acceptance']
    assert captured[1][1] == [str(tmp_path / 'scripts' / 'run_start_noninteractive.sh')]
    assert '--all-markets' in captured[2][1]
    assert '--output' not in captured[2][1]
