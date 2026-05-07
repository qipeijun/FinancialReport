from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts import interactive_runner


def test_main_returns_analysis_failure_code(monkeypatch):
    monkeypatch.setattr(interactive_runner, 'has_today_data', lambda *_: True)

    answers = iter([False, False, True])
    monkeypatch.setattr(interactive_runner, 'ask_yes_no', lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(interactive_runner, 'ask_content_field', lambda: 'summary')
    monkeypatch.setattr(interactive_runner, 'run_script', lambda cmd, task_label='执行任务': 7)

    code = interactive_runner.main()

    assert code == 7
