from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts import interactive_runner


def test_main_with_preflight_blocker_returns_1(monkeypatch):
    """前置检查有 blocker 时 main 应直接返回 1"""
    from scripts.utils.preflight import PreflightResult, CheckItem

    blocker = CheckItem(
        name='apikey_check', label='API Key', passed=False,
        severity='blocker', failure_type='config_blocked',
        detail='未配置', suggestion='请配置',
    )
    fake_result = PreflightResult(
        passed=False, checks=[blocker],
        blockers=[blocker], warnings=[],
        first_blocker=blocker,
    )
    monkeypatch.setattr(interactive_runner, 'run_preflight', lambda _: fake_result)
    monkeypatch.setattr(interactive_runner, 'print_preflight_panel', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_header', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_info', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_error', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'note_event', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'configure_dashboard', lambda **kw: None)

    code = interactive_runner.main()
    assert code == 1


def test_main_returns_custom_flow_code(monkeypatch):
    """模式 2 自定义分析：子进程失败时 main 应传递退出码"""
    from scripts.utils.preflight import PreflightResult

    fake_result = PreflightResult(passed=True, checks=[], blockers=[], warnings=[])
    monkeypatch.setattr(interactive_runner, 'run_preflight', lambda _: fake_result)
    monkeypatch.setattr(interactive_runner, 'print_preflight_panel', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_header', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_info', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_warning', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_error', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_success', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'print_plain', lambda _='': None)
    monkeypatch.setattr(interactive_runner, 'note_event', lambda _: None)
    monkeypatch.setattr(interactive_runner, 'configure_dashboard', lambda **kw: None)
    monkeypatch.setattr(interactive_runner, 'prompt_input', lambda prompt: '')
    monkeypatch.setattr(interactive_runner, 'prompt_yes_no', lambda prompt, default=True: False)

    # 选择模式 2
    monkeypatch.setattr(interactive_runner, '_ask_mode', lambda: '2')
    # 在自定义流程中跳过抓取、直接让分析返回失败码
    monkeypatch.setattr(interactive_runner, '_run_streaming', lambda cmd, label, cwd=None: 7)

    code = interactive_runner.main()
    assert code == 7
