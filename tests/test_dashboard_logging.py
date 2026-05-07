from io import StringIO
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))


from scripts import interactive_runner
from scripts.utils import print_utils
from scripts.utils.report_generator import ReportGenerator


def test_terminal_dashboard_non_tty_falls_back_to_plain_text(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = False

    dashboard.start_stage('获取实时数据', step=1, total=6, detail='检查行情接口')
    dashboard.emit_heartbeat(label='AI 报告生成', elapsed='00:08', frame='[==  ]', tty_dynamic=False)

    output = stream.getvalue()
    assert '[1/6] 获取实时数据 - 检查行情接口' in output
    assert '[心跳] AI 报告生成 进行中 [==  ] 已耗时 00:08' in output


def test_terminal_dashboard_tty_renders_ansi_panel(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = True
    dashboard.configure(title='Financial Report', total_steps=4)
    dashboard.start_stage('执行所选任务', step=4, total=4, detail='执行标准 AI 分析')

    output = stream.getvalue()
    assert 'Financial Report' in output
    assert '执行所选任务' in output
    assert '\033[2K' in output


def test_run_script_reports_success(monkeypatch):
    events = []

    class FakeProc:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        def poll(self):
            self.calls += 1
            return 0 if self.calls > 1 else None

    class FakeHeartbeat:
        def __enter__(self):
            events.append(('heartbeat', 'enter'))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(('heartbeat', 'exit'))

    monkeypatch.setattr(interactive_runner, 'start_stage', lambda *args, **kwargs: events.append(('start', kwargs.get('detail'))))
    monkeypatch.setattr(interactive_runner, 'finish_stage', lambda summary, duration=False: events.append(('finish', summary, duration)))
    monkeypatch.setattr(interactive_runner, 'note_event', lambda message: events.append(('event', message)))
    monkeypatch.setattr(interactive_runner, 'heartbeat', lambda *args, **kwargs: FakeHeartbeat())
    monkeypatch.setattr(interactive_runner.subprocess, 'Popen', FakeProc)
    monkeypatch.setattr(interactive_runner.time, 'sleep', lambda *_args, **_kwargs: None)

    code = interactive_runner.run_script(['python3', 'demo.py'], task_label='执行标准 AI 分析')

    assert code == 0
    assert ('start', '执行标准 AI 分析') in events
    assert any(item[0] == 'finish' and '执行标准 AI 分析完成' in item[1] for item in events)
    assert ('event', '执行标准 AI 分析已完成') in events


def test_report_generator_emits_stage_sequence(monkeypatch):
    class FakeProvider:
        def get_provider_name(self):
            return 'DeepSeek'

        def generate(self, prompt, content, **kwargs):
            return '# report', {'model': 'deepseek-v4-pro', 'total_tokens': 12}

    generator = ReportGenerator(provider=FakeProvider(), enable_verification=False)
    events = []

    monkeypatch.setattr(print_utils, 'configure_dashboard', lambda **kwargs: events.append(('configure', kwargs)))
    monkeypatch.setattr('scripts.utils.report_generator.configure_dashboard', lambda **kwargs: events.append(('configure', kwargs)))
    monkeypatch.setattr('scripts.utils.report_generator.start_stage', lambda name, **kwargs: events.append(('start', name, kwargs.get('step'))))
    monkeypatch.setattr('scripts.utils.report_generator.update_stage', lambda detail: events.append(('update', detail)))
    monkeypatch.setattr('scripts.utils.report_generator.finish_stage', lambda summary=None, duration=True: events.append(('finish', summary)))
    monkeypatch.setattr('scripts.utils.report_generator.note_event', lambda detail: events.append(('event', detail)))

    class FakeHeartbeat:
        def __enter__(self):
            events.append(('heartbeat', 'enter'))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(('heartbeat', 'exit'))

    monkeypatch.setattr('scripts.utils.report_generator.heartbeat', lambda *args, **kwargs: FakeHeartbeat())
    monkeypatch.setattr('scripts.utils.report_generator.resolve_date_range', lambda _args: ('2026-05-07', '2026-05-07'))
    monkeypatch.setattr('scripts.utils.report_generator.open_connection', lambda _path: object())
    monkeypatch.setattr('scripts.utils.report_generator.query_articles', lambda conn, *args: [{'id': 1, 'title': 'A', 'summary': 's'}])
    monkeypatch.setattr('scripts.utils.report_generator.filter_articles', lambda rows, **kwargs: rows)
    monkeypatch.setattr('scripts.utils.report_generator.filter_and_rank_articles', lambda rows: (rows, {'kept': 1}))
    monkeypatch.setattr('scripts.utils.report_generator.build_corpus', lambda rows, *args, **kwargs: ([('A', ['chunk'])], 5))
    monkeypatch.setattr('scripts.utils.report_generator.build_source_stats_block', lambda *args, **kwargs: 'stats')
    monkeypatch.setattr('scripts.utils.report_generator.save_markdown', lambda *args, **kwargs: Path('/tmp/report.md'))
    monkeypatch.setattr('scripts.utils.report_generator.save_metadata', lambda *args, **kwargs: None)
    monkeypatch.setattr(generator, 'load_prompt', lambda _version: 'prompt')
    monkeypatch.setattr(generator, '_run_fact_check', lambda *args, **kwargs: ([], ''))

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr('scripts.utils.report_generator.open_connection', lambda _path: FakeConn())

    result = generator.generate(mode='markdown-report', quality_check=False)

    assert result['success'] is True
    starts = [item for item in events if item[0] == 'start']
    assert [item[1] for item in starts[:4]] == ['获取实时数据', '查询与筛选文章', '构建语料', '调用 AI 模型']
    assert any(item[1] == '保存报告与元数据' for item in starts)
