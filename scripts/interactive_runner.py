#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式运行器

功能：
- 检查今天是否已有数据（data/news_data.db 是否存在今日 collection_date）
- 询问是否抓取今天数据；若需要则调用 rss_finance_analyzer.py
- 询问是否进行 AI 分析；若需要则调用 ai_analyze.py

提示：本脚本为简洁交互，不依赖第三方库。
"""

import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from utils.print_utils import (
    print_header, print_success, print_warning, print_error, 
    print_info, print_progress
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'news_data.db'


def ask_yes_no(prompt: str, default: bool | None = None) -> bool:
    suffix = ' [y/n]' if default is None else (' [Y/n]' if default else ' [y/N]')
    while True:
        ans = input(prompt + suffix + ': ').strip().lower()
        if not ans and default is not None:
            return default
        if ans in ('y', 'yes', '是', '好', 'ok'):
            return True
        if ans in ('n', 'no', '否', '不'):
            return False
        print('请输入 y/n')


def ask_content_field() -> str:
    """询问用户选择分析字段"""
    print_info('请选择分析字段：')
    print('  1. summary - 摘要优先（推荐，内容简洁）')
    print('  2. content - 正文优先（详细，但可能包含冗余信息）')
    print('  3. auto - 智能选择（根据内容长度自动选择）')
    
    while True:
        choice = input('请选择 [1/2/3，默认auto]: ').strip()
        if not choice:
            return 'auto'
        if choice == '1':
            return 'summary'
        elif choice == '2':
            return 'content'
        elif choice == '3':
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


def run_script(cmd: list[str]) -> int:
    # 使用虚拟环境中的Python
    venv_python = PROJECT_ROOT / 'venv' / 'bin' / 'python'
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / 'venv' / 'Scripts' / 'python.exe'  # Windows
    
    if cmd and cmd[0] in ('python3', 'python', 'py'):
        cmd[0] = str(venv_python)
    print_progress(f'执行命令: {" ".join(cmd)}')
    proc = subprocess.run(cmd)
    return proc.returncode


def run_mkdocs_deploy():
    """运行MkDocs部署"""
    print_info('开始生成文档网站...')
    
    # 运行部署脚本
    deploy_script = PROJECT_ROOT / 'scripts' / 'deploy.sh'
    if deploy_script.exists():
        print_progress('执行MkDocs部署脚本...')
        code = subprocess.run(['bash', str(deploy_script)]).returncode
        if code == 0:
            print_success('文档网站生成成功！')
            
            # 询问是否启动预览服务器
            if ask_yes_no('是否启动本地预览服务器？', default=True):
                print_info('启动MkDocs预览服务器...')
                print_info('访问地址: http://127.0.0.1:8000')
                print_info('按 Ctrl+C 停止服务器')
                try:
                    subprocess.run(['mkdocs', 'serve'], cwd=PROJECT_ROOT)
                except KeyboardInterrupt:
                    print_info('预览服务器已停止')
        else:
            print_error('文档网站生成失败')
    else:
        print_error(f'部署脚本不存在: {deploy_script}')


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print_header("财经新闻分析系统")
    print_info(f'今天日期：{today}')

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
                return
            print_success('重新抓取完成。')

        # 分支：仅分析指定范围/来源/关键词
        if ask_yes_no('是否仅分析指定范围/来源/关键词？', default=False):
            date_mode = ask_yes_no('仅分析当天？（否则可指定起止日期）', default=True)
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze.py')]
            if not date_mode:
                start = input('开始日期 YYYY-MM-DD: ').strip()
                end = input('结束日期 YYYY-MM-DD: ').strip()
                if start:
                    cmd += ['--start', start]
                if end:
                    cmd += ['--end', end]
            fsrc = input('仅分析来源（逗号分隔，可空）: ').strip()
            if fsrc:
                cmd += ['--filter-source', fsrc]
            fkw = input('仅分析关键词（逗号分隔，可空）: ').strip()
            if fkw:
                cmd += ['--filter-keyword', fkw]
            maxa = input('最多文章数（可空）: ').strip()
            if maxa.isdigit():
                cmd += ['--max-articles', maxa]
            # 添加字段选择
            content_field = ask_content_field()
            cmd += ['--content-field', content_field]
            code = run_script(cmd)
        elif ask_yes_no('是否立即进行 AI 分析？', default=True):
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze.py'), '--content-field', content_field]
            code = run_script(cmd)
            if code == 0:
                print_success('分析完成。')
                # 询问是否生成文档网站
                if ask_yes_no('是否生成并预览文档网站？', default=True):
                    run_mkdocs_deploy()
            else:
                print_error('分析失败，请查看上方日志。')
        else:
            print_info('已跳过分析。')
        return

    print_warning('未检测到今天的数据。')
    if ask_yes_no('是否现在开始抓取今天的数据？', default=True):
        fetch_content = ask_yes_no('抓取正文写入数据库（推荐）？', default=True)
        only_src = input('仅抓取某些来源（逗号分隔，可空）: ').strip()
        cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
        if fetch_content:
            cmd.append('--fetch-content')
        if only_src:
            cmd += ['--only-source', only_src]
        code = run_script(cmd)
        if code != 0:
            print_error('抓取失败，请重试或检查网络。')
            return
        print_success('抓取完成。')

        # 抓取成功后再次确认是否分析
        if ask_yes_no('是否立即进行 AI 分析？', default=True):
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze.py'), '--content-field', content_field]
            code = run_script(cmd)
            if code == 0:
                print_success('分析完成。')
                # 询问是否生成文档网站
                if ask_yes_no('是否生成并预览文档网站？', default=True):
                    run_mkdocs_deploy()
            else:
                print_error('分析失败，请查看上方日志。')
        else:
            print_info('已跳过分析。')
    else:
        print_info('已取消抓取与分析。')


if __name__ == '__main__':
    main()


