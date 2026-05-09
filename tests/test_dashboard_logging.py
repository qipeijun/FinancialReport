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
    assert '[阶段] [1/6] 获取实时数据 - 检查行情接口' in output
    assert '[心跳] AI 报告生成 - 检查行情接口 (00:08)' in output
    assert '[状态]' not in output


def test_terminal_dashboard_tty_renders_single_line_status(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = True
    dashboard.configure(title='Financial Report', total_steps=4)
    assert stream.getvalue() == ''
    dashboard.start_stage('执行所选任务', step=4, total=4, detail='执行标准 AI 分析')

    output = stream.getvalue()
    assert '执行所选任务' in output
    assert '\r\033[2K' in output
    assert '总 ' in output
    assert '阶段 ' in output
    assert '┌─' not in output


def test_print_info_temporarily_clears_and_restores_status(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.printer.dashboard
    dashboard.interactive = True
    dashboard.total_steps = 4
    dashboard.current_step = 2
    dashboard.current_stage = '调用 AI 模型'
    dashboard.current_detail = '等待模型返回'
    dashboard._active_stage = True
    dashboard._suspend_depth = 0
    dashboard._status_visible = False

    print_utils.print_info('一条普通日志')

    output = stream.getvalue()
    assert 'INFO 一条普通日志' in output
    assert '调用 AI 模型' in output
    assert output.count('\r\033[2K') >= 1


def test_prompt_input_suspends_status_while_waiting(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)
    monkeypatch.setattr('builtins.input', lambda prompt='': prompt + 'ok')

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = True
    dashboard.start_stage('进入功能选择', step=3, total=4, detail='等待用户选择启动模式')
    before_prompt = stream.getvalue()
    assert '进入功能选择' in before_prompt

    with dashboard.prompt_context():
        result = input('请选择功能 (1-7): ')

    after_prompt = stream.getvalue()
    assert result == '请选择功能 (1-7): ok'
    assert after_prompt.count('\r\033[2K') >= 2
    assert '进入功能选择' in after_prompt


def test_run_script_reports_success(monkeypatch):
    events = []

    class FakeProc:
        def __init__(self, *_args, **_kwargs):
            self.stdout = iter(['第一行日志\n', '第二行日志\n'])

        def wait(self):
            return 0

    class FakeHeartbeat:
        def __enter__(self):
            events.append(('heartbeat', 'enter'))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(('heartbeat', 'exit'))

    monkeypatch.setattr(interactive_runner, 'start_stage', lambda *args, **kwargs: events.append(('start', kwargs.get('detail'))))
    monkeypatch.setattr(interactive_runner, 'finish_stage', lambda summary, duration=False: events.append(('finish', summary, duration)))
    monkeypatch.setattr(interactive_runner, 'note_event', lambda message: events.append(('event', message)))
    monkeypatch.setattr(interactive_runner, 'print_plain', lambda message='': events.append(('plain', message)))
    monkeypatch.setattr(interactive_runner, 'suspend_status', lambda: events.append(('suspend',)))
    monkeypatch.setattr(interactive_runner, 'resume_status', lambda: events.append(('resume',)))
    monkeypatch.setattr(interactive_runner, 'heartbeat', lambda *args, **kwargs: FakeHeartbeat())
    monkeypatch.setattr(interactive_runner.subprocess, 'Popen', FakeProc)

    code = interactive_runner.run_script(['python3', 'demo.py'], task_label='执行标准 AI 分析')

    assert code == 0
    assert ('start', '启动 执行标准 AI 分析') in events
    assert ('plain', '第一行日志') in events
    assert ('plain', '第二行日志') in events
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


def test_report_generator_save_result_persists_enhanced_context(monkeypatch, tmp_path):
    class FakeProvider:
        def get_provider_name(self):
            return 'DeepSeek'

    generator = ReportGenerator(provider=FakeProvider(), enable_verification=False)
    captured = {}

    monkeypatch.setattr('scripts.utils.report_generator.save_markdown', lambda *args, **kwargs: tmp_path / 'report.md')
    monkeypatch.setattr('scripts.utils.report_generator.save_metadata', lambda *args, **kwargs: captured.setdefault('metadata_saved', True))
    monkeypatch.setattr('scripts.utils.report_generator.save_enhanced_context', lambda *args, **kwargs: tmp_path / 'enhanced.json')
    monkeypatch.setattr('scripts.utils.report_generator.update_stage', lambda detail: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_progress', lambda detail: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_success', lambda detail: None)
    monkeypatch.setattr('scripts.utils.report_generator.note_event', lambda detail: None)
    monkeypatch.setattr('scripts.utils.report_generator.finish_stage', lambda *args, **kwargs: None)

    meta = {}
    saved = generator._save_result(
        end_date='2026-05-09',
        report_text='# report',
        usage={'model': 'deepseek'},
        meta=meta,
        output_json=None,
        json_payload={'summary_markdown': '# report'},
        enhanced_context_payload={'selected_articles': [], 'judgment_candidates': []},
        artifact_suffix='markdown-report',
    )

    assert saved == tmp_path / 'report.md'
    assert meta['enhanced_context_path'] == str(tmp_path / 'enhanced.json')
    assert captured['metadata_saved'] is True


def test_report_generator_judgment_cards_enhanced_context_contains_candidate_stocks(monkeypatch):
    class FakeProvider:
        def get_provider_name(self):
            return 'DeepSeek'

        def generate(self, prompt, content, **kwargs):
            return '{"theses":[],"watch_items":[],"evidence_summary":"","market_scope":"中国与全球联动","time_horizon":"1-4周","degraded":false}', {'model': 'deepseek-v4-pro', 'total_tokens': 12}

    generator = ReportGenerator(provider=FakeProvider(), enable_verification=False)
    captured = {}

    monkeypatch.setattr(generator, 'load_prompt', lambda _version: 'prompt')
    monkeypatch.setattr('scripts.utils.report_generator.build_judgment_candidates', lambda *args, **kwargs: [
        {
            'topic': '科技与产业主题',
            'independent_evidence_count': 2,
            'evidence_count': 2,
            'source_tier_max': 'mainstream',
            'high_relevance_article_count': 1,
            'high_confidence_topic': True,
            'topic_article_count': 3,
            'articles': [{'id': 1, 'title': '景气支撑', 'source_tier': 'mainstream'}],
        }
    ])
    monkeypatch.setattr(generator.security_master_provider, 'build_candidates', lambda **kwargs: [
        type('Candidate', (), {'to_dict': lambda self: {'symbol': 'sh603019', 'direct_mentions': 1}})()
    ])
    monkeypatch.setattr('scripts.utils.report_generator.build_judgment_prompt_context', lambda *args, **kwargs: 'context')
    monkeypatch.setattr('scripts.utils.report_generator.extract_json_payload', lambda raw: {'theses': [], 'watch_items': [], 'evidence_summary': '', 'market_scope': '中国与全球联动', 'time_horizon': '1-4周', 'degraded': False})
    monkeypatch.setattr('scripts.utils.report_generator.enforce_judgment_rules', lambda payload, *args, **kwargs: payload)
    monkeypatch.setattr('scripts.utils.report_generator.render_judgment_markdown', lambda payload: '# judgment')
    monkeypatch.setattr(generator, '_run_fact_check', lambda *args, **kwargs: ([], ''))
    monkeypatch.setattr('scripts.utils.report_generator.check_report_quality_v2', lambda *args, **kwargs: {'score': 85, 'passed': True, 'issues': [], 'warnings': []})
    monkeypatch.setattr('scripts.utils.report_generator.start_stage', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.finish_stage', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_warning', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_success', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_statistics', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.note_event', lambda *args, **kwargs: None)

    class FakeHeartbeat:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('scripts.utils.report_generator.heartbeat', lambda *args, **kwargs: FakeHeartbeat())
    monkeypatch.setattr(generator, '_save_result', lambda *args, **kwargs: captured.setdefault('enhanced', kwargs.get('enhanced_context_payload') if 'enhanced_context_payload' in kwargs else args[6]) or Path('/tmp/judgment.md'))

    result = generator._generate_judgment_cards(
        start_date='2026-05-09',
        end_date='2026-05-09',
        selected=[{'id': 1, 'title': 'A', 'summary': 's'}],
        realtime_data=None,
        max_retries=0,
        min_score=80,
        output_json=None,
        max_theses=3,
        min_source_tier='mainstream',
        min_independent_evidence=2,
        degrade_on_weak_evidence=True,
        output_observation_only_when_weak=True,
    )

    assert result['success'] is True
    assert captured['enhanced']['candidate_stocks'] == [{'symbol': 'sh603019', 'direct_mentions': 1}]


def test_report_generator_markdown_report_uses_structured_truth_sources(monkeypatch):
    class FakeProvider:
        def get_provider_name(self):
            return 'DeepSeek'

        def generate(self, prompt, content, **kwargs):
            return (
                "## 市场概况\n\n### 市场状态\n- 市场偏震荡【新闻1】。\n\n"
                "## 投资主题\n\n### 高置信主题\n- **科技与产业主题**: 跟踪 AI 基建【新闻2】。\n\n"
                "## 建议\n\n### 推荐摘要\n- 聚焦结构化推荐。\n\n"
                "## 风险\n\n- 警惕追高【新闻3】。\n",
                {'model': 'deepseek-v4-pro', 'total_tokens': 12},
            )

    generator = ReportGenerator(provider=FakeProvider(), enable_verification=False)
    captured = {}

    monkeypatch.setattr(generator, 'load_prompt', lambda _version: 'prompt')
    monkeypatch.setattr('scripts.utils.report_generator.resolve_date_range', lambda _args: ('2026-05-09', '2026-05-09'))
    monkeypatch.setattr('scripts.utils.report_generator.filter_articles', lambda rows, **kwargs: rows)
    monkeypatch.setattr('scripts.utils.report_generator.filter_and_rank_articles', lambda rows: (rows, {'kept': 2}))
    monkeypatch.setattr('scripts.utils.report_generator.build_corpus', lambda rows, *args, **kwargs: ([('A', ['chunk'])], 5))
    monkeypatch.setattr('scripts.utils.report_generator.build_source_stats_block', lambda *args, **kwargs: 'stats')
    monkeypatch.setattr('scripts.utils.report_generator.summarize_content_quality', lambda rows: {
        'counts': {'full': 1, 'partial': 1, 'summary_only': 0},
        'ratios': {'full': 50.0, 'partial': 50.0, 'summary_only': 0.0},
        'total': 2,
    })
    monkeypatch.setattr(generator.security_master_provider, 'build_candidates', lambda **kwargs: [])
    monkeypatch.setattr('scripts.utils.report_generator.build_judgment_candidates', lambda *args, **kwargs: [
        {'topic': '科技与产业主题', 'high_confidence_topic': True, 'topic_article_count': 3, 'independent_evidence_count': 2, 'source_tier_max': 'mainstream'},
    ])
    monkeypatch.setattr('scripts.utils.report_generator.RecommendationScorer', lambda **kwargs: type('Scorer', (), {
        'score_candidates': lambda self, _candidates: {
            'recommendations': [
                {'symbol': 'sh603019', 'name': '中科曙光', 'grade': '关注', 'total_score': 72, 'source_type': 'direct_news', 'grade_caps': []}
            ],
            'score_distribution': {'strong_focus': 0, 'focus': 1, 'watch': 0, 'avoid': 0},
            'decision_views': {
                'actionable_candidates': [{'symbol': 'sh603019', 'name': '中科曙光', 'grade': '关注', 'total_score': 72}],
                'conditional_watchlist': [],
                'stale_or_rejected': [],
            },
            'scoring_config': {'market': 'CN', 'style': 'balanced', 'lookback_days': 60},
        }
    })())
    monkeypatch.setattr('scripts.utils.report_generator.render_stock_recommendation_markdown', lambda *args, **kwargs: '## 股票推荐评分\n')
    monkeypatch.setattr(generator, '_run_fact_check', lambda *args, **kwargs: ([], ''))
    monkeypatch.setattr('scripts.utils.report_generator.check_report_quality_v2', lambda *args, **kwargs: {'score': 85, 'passed': True, 'issues': [], 'warnings': []})
    monkeypatch.setattr('scripts.utils.report_generator.start_stage', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.finish_stage', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.update_stage', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.note_event', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_info', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_progress', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_success', lambda *args, **kwargs: None)
    monkeypatch.setattr('scripts.utils.report_generator.print_statistics', lambda *args, **kwargs: None)

    class FakeConn:
        def close(self):
            return None

    class FakeHeartbeat:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('scripts.utils.report_generator.open_connection', lambda _path: FakeConn())
    monkeypatch.setattr('scripts.utils.report_generator.query_articles', lambda conn, *args: [{'id': 1, 'title': 'A', 'summary': 's'}])
    monkeypatch.setattr('scripts.utils.report_generator.heartbeat', lambda *args, **kwargs: FakeHeartbeat())
    monkeypatch.setattr(generator, '_save_result', lambda *args, **kwargs: captured.setdefault('payload', kwargs.get('json_payload') if 'json_payload' in kwargs else args[5]) or Path('/tmp/report.md'))

    result = generator.generate(mode='markdown-report', quality_check=False)

    assert result['success'] is True
    assert 'judgment_candidates' in captured['payload']
    assert 'data_quality_stats' in captured['payload']


def test_heartbeat_with_details_emits_single_visible_line_per_tick(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = False

    dashboard.emit_heartbeat(
        label='调用 AI 模型',
        elapsed='00:06',
        frame='•',
        tty_dynamic=False,
        detail_override='等待模型返回',
    )

    output = stream.getvalue().strip().splitlines()
    assert output == ['[心跳] 调用 AI 模型 - 等待模型返回 (00:06)']


def test_heartbeat_can_skip_noisy_periods(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = False

    dashboard.emit_heartbeat(
        label='调用 AI 模型',
        elapsed='00:12',
        frame='•',
        tty_dynamic=False,
        detail_override='等待模型返回',
    )

    assert '[心跳] 调用 AI 模型 - 等待模型返回 (00:12)' in stream.getvalue()


def test_stage_start_and_finish_plain_text_format(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)

    dashboard = print_utils.TerminalDashboard()
    dashboard.interactive = False
    dashboard.start_stage('查询与筛选文章', step=2, total=6, detail='读取数据库候选文章')
    dashboard.finish_stage('查询与筛选文章', duration=False)

    output = stream.getvalue()
    assert '[阶段] [2/6] 查询与筛选文章 - 读取数据库候选文章' in output
    assert '[完成] 查询与筛选文章' in output
