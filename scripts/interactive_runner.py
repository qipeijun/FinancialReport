#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式运行器

功能：
- 检查今天是否已有数据（data/news_data.db 是否存在今日 collection_date）
- 询问是否抓取今天数据；若需要则调用 rss_finance_analyzer.py
- 询问是否进行 AI 分析；若需要则调用 ai_analyze_deepseek_verified.py

提示：本脚本为简洁交互，不依赖第三方库。
"""

import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    from utils.print_utils import (
        print_header, print_success, print_warning, print_error,
        print_info, print_progress, print_plain,
        configure_dashboard, start_stage, update_stage, finish_stage,
        note_event, heartbeat, suspend_status, resume_status,
        prompt_input, prompt_yes_no,
    )
except ModuleNotFoundError:
    from scripts.utils.print_utils import (  # type: ignore
        print_header, print_success, print_warning, print_error,
        print_info, print_progress, print_plain,
        configure_dashboard, start_stage, update_stage, finish_stage,
        note_event, heartbeat, suspend_status, resume_status,
        prompt_input, prompt_yes_no,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def ask_yes_no(prompt: str, default: bool | None = None) -> bool:
    return prompt_yes_no(prompt, default=default)


def ask_content_field() -> str:
    """询问用户选择分析字段"""
    print_info('📝 分析字段选择：')
    print_plain('  选择AI分析时使用的新闻内容字段：')
    print_plain()
    print_plain('  1. summary - 摘要优先（推荐，默认）')
    print_plain('     • 使用新闻摘要进行分析')
    print_plain('     • 速度快，成功率高（85.7%）')
    print_plain('     • 内容质量足够AI分析')
    print_plain('     • 推荐日常使用')
    print_plain()
    print_plain('  2. content - 正文优先')
    print_plain('     • 使用完整新闻正文进行分析')
    print_plain('     • 信息更详细，但成功率较低（76.5%）')
    print_plain('     • 抓取速度较慢')
    print_plain('     • 适合深度分析特定文章')
    print_plain()
    print_plain('  3. auto - 智能选择')
    print_plain('     • 根据内容长度自动选择')
    print_plain('     • 正文过长时使用摘要')
    print_plain('     • 正文较短时使用正文')
    print_plain('     • 平衡速度和质量')
    print_plain()

    while True:
        choice = prompt_input('请选择 [1/2/3，默认1-摘要]: ').strip()
        if not choice or choice == '1':
            print_info('使用默认设置：摘要优先')
            return 'summary'
        elif choice == '2':
            print_info('已选择：正文优先')
            return 'content'
        elif choice == '3':
            print_info('已选择：智能选择')
            return 'auto'
        print_warning('请输入 1、2 或 3')


def has_today_data(db_path: Path, today: str) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute('SELECT COUNT(1) FROM news_articles WHERE collection_date = ?', (today,))
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def run_script(cmd: list[str], task_label: str = '执行任务') -> int:
    cmd = _normalize_python_command(cmd)
    start_stage('执行所选任务', step=4, total=4, detail=f'启动 {task_label}')
    print_progress(f'执行命令: {" ".join(cmd)}')
    started_at = time.time()
    code = _run_streaming_command(
        cmd,
        heartbeat_label=task_label,
        interval_seconds=6.0,
        details=('整理执行上下文', '等待命令返回', '继续等待输出'),
    )

    elapsed = time.time() - started_at
    if code == 0:
        finish_stage(f'{task_label}完成，用时 {_format_duration(elapsed)}', duration=False)
        note_event(f'{task_label}已完成')
    else:
        finish_stage(f'{task_label}失败，退出码 {code}，用时 {_format_duration(elapsed)}', duration=False)
        note_event(f'{task_label}失败')
    return code


def _normalize_python_command(cmd: list[str]) -> list[str]:
    normalized = list(cmd)
    venv_python = PROJECT_ROOT / 'venv' / 'bin' / 'python'
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / 'venv' / 'Scripts' / 'python.exe'
    if normalized and normalized[0] in ('python3', 'python', 'py'):
        normalized[0] = str(venv_python)
    return normalized


def _run_streaming_command(
    cmd: list[str],
    *,
    heartbeat_label: str,
    interval_seconds: float,
    details: tuple[str, ...],
    cwd: Path | None = None,
) -> int:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'},
        cwd=cwd,
    )
    last_output_at = time.monotonic()
    with heartbeat(
        heartbeat_label,
        interval_seconds=interval_seconds,
        details=details,
        should_emit=lambda _elapsed: time.monotonic() - last_output_at >= interval_seconds,
        before_emit=resume_status,
    ):
        if proc.stdout is not None:
            for line in proc.stdout:
                last_output_at = time.monotonic()
                suspend_status()
                print_plain(line.rstrip('\n'))
        code = proc.wait()
    resume_status()
    return code


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours:02d}:{minutes:02d}:{secs:02d}'
    return f'{minutes:02d}:{secs:02d}'


def run_mkdocs_deploy():
    """运行MkDocs部署"""
    start_stage('执行所选任务', step=4, total=4, detail='准备部署 MkDocs 文档站点')
    print_info('开始生成文档网站...')
    
    # 运行部署脚本
    deploy_script = PROJECT_ROOT / 'scripts' / 'deploy.sh'
    if deploy_script.exists():
        print_progress('执行MkDocs部署脚本...')
        code = _run_streaming_command(
            ['bash', str(deploy_script)],
            heartbeat_label='构建 MkDocs 站点',
            interval_seconds=5.0,
            details=('生成静态页面', '整理导航配置', '等待构建结果'),
            cwd=PROJECT_ROOT,
        )
        if code == 0:
            print_success('文档网站生成成功！')
            finish_stage('MkDocs 文档构建完成', duration=True)
            
            # 询问是否启动预览服务器
            if ask_yes_no('是否启动本地预览服务器？', default=True):
                print_info('启动MkDocs预览服务器...')
                print_info('访问地址: http://127.0.0.1:8000')
                print_info('按 Ctrl+C 停止服务器')
                try:
                    suspend_status()
                    subprocess.run(['mkdocs', 'serve'], cwd=PROJECT_ROOT)
                except KeyboardInterrupt:
                    print_info('预览服务器已停止')
                finally:
                    resume_status()
        else:
            print_error('文档网站生成失败')
            finish_stage('MkDocs 文档构建失败', duration=True)
    else:
        print_error(f'部署脚本不存在: {deploy_script}')
        finish_stage('MkDocs 部署脚本不存在', duration=False)


def main() -> int:
    today = datetime.now().strftime('%Y-%m-%d')
    configure_dashboard(title='Financial Report', total_steps=4)
    start_stage('进入功能选择', step=3, total=4, detail='加载交互式运行器')
    print_header("财经新闻分析系统")
    print_info(f'今天日期：{today}')
    note_event(f'当前分析日期: {today}')

    exists = has_today_data(DB_PATH, today)
    if exists:
        print_success('检测到今天的数据已存在于 data/news_data.db')
        # 允许用户选择重新抓取（覆盖式追加新增内容）
        if ask_yes_no('是否重新抓取今天的数据（追加最新内容）？', default=False):
            fetch_content = ask_yes_no('抓取正文写入数据库（推荐）？', default=True)
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
            if fetch_content:
                cmd.append('--fetch-content')
            code = run_script(cmd)
            if code != 0:
                print_error('重新抓取失败，请查看日志后重试。')
                return code
            print_success('重新抓取完成。')

        # 分支：仅分析指定范围/来源/关键词
        print_info('🎯 分析选项：')
        print_plain('  1. 自定义分析 - 可以指定日期范围、新闻来源、关键词等')
        print_plain('  2. 标准分析 - 分析当天的所有新闻（推荐）')
        print_plain()
        if ask_yes_no('是否仅分析指定范围/来源/关键词？', default=False):
            print_info('📋 自定义分析参数配置：')
            print_plain('   • 可以指定日期范围、新闻来源、关键词等')
            print_plain('   • 所有参数都是可选的，直接回车跳过')
            print_plain('   • 多个值用逗号分隔')
            print_plain()
            
            date_mode = ask_yes_no('仅分析当天？（否则可指定起止日期）', default=True)
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'judgment-cards']
            
            if not date_mode:
                print_info('📅 日期范围设置：')
                print_plain('   • 格式：YYYY-MM-DD（如：2025-09-28）')
                print_plain('   • 开始日期：分析从这个日期开始的新闻')
                print_plain('   • 结束日期：分析到这个日期结束的新闻')
                print_plain('   • 直接回车使用默认值（当天）')
                print_plain()
                
                start = prompt_input('开始日期 YYYY-MM-DD: ').strip()
                end = prompt_input('结束日期 YYYY-MM-DD: ').strip()
                if start:
                    cmd += ['--start', start]
                if end:
                    cmd += ['--end', end]
            
            print_info('📰 新闻来源过滤：')
            print_plain('   • 可用的来源：华尔街见闻、36氪、东方财富、国家统计局、中新网等')
            print_plain('   • 多个来源用逗号分隔（如：华尔街见闻,36氪）')
            print_plain('   • 直接回车分析所有来源')
            print_plain()
            fsrc = prompt_input('仅分析来源（逗号分隔，可空）: ').strip()
            if fsrc:
                cmd += ['--filter-source', fsrc]
            
            print_info('🔍 关键词过滤：')
            print_plain('   • 只分析包含指定关键词的新闻')
            print_plain('   • 多个关键词用逗号分隔（如：AI,新能源,房地产）')
            print_plain('   • 直接回车分析所有新闻')
            print_plain()
            fkw = prompt_input('仅分析关键词（逗号分隔，可空）: ').strip()
            if fkw:
                cmd += ['--filter-keyword', fkw]
            
            print_info('📊 文章数量限制：')
            print_plain('   • 限制参与分析的文章数量（如：50）')
            print_plain('   • 有助于控制分析时间和成本')
            print_plain('   • 直接回车不限制数量')
            print_plain()
            maxa = prompt_input('最多文章数（可空）: ').strip()
            if maxa.isdigit():
                cmd += ['--max-articles', maxa]
            
            # 添加字段选择
            content_field = ask_content_field()
            cmd += ['--content-field', content_field]
            
            print_info('🚀 开始执行自定义分析...')
            print_plain(f'   命令：{" ".join(cmd)}')
            print_plain()
            code = run_script(cmd, task_label='执行自定义 AI 分析')
        elif ask_yes_no('是否立即进行 AI 分析？', default=True):
            print_info('📊 标准分析模式：')
            print_plain('  • 分析当天的所有新闻数据')
            print_plain('  • 生成完整的财经分析报告')
            print_plain('  • 包含热门话题和潜力话题分析')
            print_plain()
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'markdown-report', '--content-field', content_field]
            print_info('🚀 开始执行标准分析...')
            print_plain(f'   命令：{" ".join(cmd)}')
            print_plain()
            code = run_script(cmd, task_label='执行标准 AI 分析')
            if code == 0:
                print_success('分析完成。')
                # 询问是否生成文档网站
                if ask_yes_no('是否生成并预览文档网站？', default=True):
                    run_mkdocs_deploy()
            else:
                print_error('分析失败，请查看上方日志。')
                return code
        else:
            print_info('已跳过分析。')
        return 0

    print_warning('未检测到今天的数据。')
    print_info('📥 数据抓取选项：')
    print_plain('  • 需要先抓取新闻数据才能进行分析')
    print_plain('  • 可以从多个财经RSS源获取最新新闻')
    print_plain('  • 抓取完成后可以立即进行AI分析')
    print_plain()
    
    if ask_yes_no('是否现在开始抓取今天的数据？', default=True):
        print_info('📰 抓取配置：')
        print_plain('  • 抓取正文：获取完整新闻内容（推荐，分析更准确）')
        print_plain('  • 仅摘要：只获取新闻摘要（速度快，但分析可能不够详细）')
        print_plain()
        fetch_content = ask_yes_no('抓取正文写入数据库（推荐）？', default=True)
        
        print_info('🎯 来源过滤：')
        print_plain('  • 可用的来源：华尔街见闻、36氪、东方财富、国家统计局、中新网等')
        print_plain('  • 多个来源用逗号分隔（如：华尔街见闻,36氪）')
        print_plain('  • 直接回车抓取所有来源')
        print_plain()
        only_src = prompt_input('仅抓取某些来源（逗号分隔，可空）: ').strip()
        
        cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
        if fetch_content:
            cmd.append('--fetch-content')
        if only_src:
            cmd += ['--only-source', only_src]
        
        print_info('🚀 开始抓取数据...')
        print_plain(f'   命令：{" ".join(cmd)}')
        print_plain()
        code = run_script(cmd, task_label='抓取财经 RSS 数据')
        if code != 0:
            print_error('抓取失败，请重试或检查网络。')
            return code
        print_success('抓取完成。')

        # 抓取成功后再次确认是否分析
        print_info('✅ 数据抓取完成！')
        print_plain('  • 新闻数据已保存到数据库')
        print_plain('  • 现在可以进行AI分析生成报告')
        print_plain()
        if ask_yes_no('是否立即进行 AI 分析？', default=True):
            print_info('📊 开始AI分析：')
            print_plain('  • 将使用AI模型分析抓取的新闻')
            print_plain('  • 生成专业的财经分析报告')
            print_plain('  • 包含市场趋势和投资建议')
            print_plain()
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'markdown-report', '--content-field', content_field]
            print_info('🚀 开始执行AI分析...')
            print_plain(f'   命令：{" ".join(cmd)}')
            print_plain()
            code = run_script(cmd, task_label='执行标准 AI 分析')
            if code == 0:
                print_success('分析完成。')
                # 询问是否生成文档网站
                if ask_yes_no('是否生成并预览文档网站？', default=True):
                    run_mkdocs_deploy()
            else:
                print_error('分析失败，请查看上方日志。')
                return code
        else:
            print_info('已跳过分析。')
    else:
        print_info('已取消抓取与分析。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
