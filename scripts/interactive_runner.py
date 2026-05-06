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
        try:
            ans = input(prompt + suffix + ': ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            if default is not None:
                print()
                print_info('使用默认设置')
                return default
            print()
            print_warning('未收到输入，请输入 y/n')
            continue
        if not ans and default is not None:
            return default
        if ans in ('y', 'yes', '是', '好', 'ok'):
            return True
        if ans in ('n', 'no', '否', '不'):
            return False
        print('请输入 y/n')


def ask_content_field() -> str:
    """询问用户选择分析字段"""
    print_info('📝 分析字段选择：')
    print('  选择AI分析时使用的新闻内容字段：')
    print()
    print('  1. summary - 摘要优先（推荐，默认）')
    print('     • 使用新闻摘要进行分析')
    print('     • 速度快，成功率高（85.7%）')
    print('     • 内容质量足够AI分析')
    print('     • 推荐日常使用')
    print()
    print('  2. content - 正文优先')
    print('     • 使用完整新闻正文进行分析')
    print('     • 信息更详细，但成功率较低（76.5%）')
    print('     • 抓取速度较慢')
    print('     • 适合深度分析特定文章')
    print()
    print('  3. auto - 智能选择')
    print('     • 根据内容长度自动选择')
    print('     • 正文过长时使用摘要')
    print('     • 正文较短时使用正文')
    print('     • 平衡速度和质量')
    print()

    while True:
        choice = input('请选择 [1/2/3，默认1-摘要]: ').strip()
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
        print_info('🎯 分析选项：')
        print('  1. 自定义分析 - 可以指定日期范围、新闻来源、关键词等')
        print('  2. 标准分析 - 分析当天的所有新闻（推荐）')
        print()
        if ask_yes_no('是否仅分析指定范围/来源/关键词？', default=False):
            print_info('📋 自定义分析参数配置：')
            print('   • 可以指定日期范围、新闻来源、关键词等')
            print('   • 所有参数都是可选的，直接回车跳过')
            print('   • 多个值用逗号分隔')
            print()
            
            date_mode = ask_yes_no('仅分析当天？（否则可指定起止日期）', default=True)
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'judgment-cards']
            
            if not date_mode:
                print_info('📅 日期范围设置：')
                print('   • 格式：YYYY-MM-DD（如：2025-09-28）')
                print('   • 开始日期：分析从这个日期开始的新闻')
                print('   • 结束日期：分析到这个日期结束的新闻')
                print('   • 直接回车使用默认值（当天）')
                print()
                
                start = input('开始日期 YYYY-MM-DD: ').strip()
                end = input('结束日期 YYYY-MM-DD: ').strip()
                if start:
                    cmd += ['--start', start]
                if end:
                    cmd += ['--end', end]
            
            print_info('📰 新闻来源过滤：')
            print('   • 可用的来源：华尔街见闻、36氪、东方财富、国家统计局、中新网等')
            print('   • 多个来源用逗号分隔（如：华尔街见闻,36氪）')
            print('   • 直接回车分析所有来源')
            print()
            fsrc = input('仅分析来源（逗号分隔，可空）: ').strip()
            if fsrc:
                cmd += ['--filter-source', fsrc]
            
            print_info('🔍 关键词过滤：')
            print('   • 只分析包含指定关键词的新闻')
            print('   • 多个关键词用逗号分隔（如：AI,新能源,房地产）')
            print('   • 直接回车分析所有新闻')
            print()
            fkw = input('仅分析关键词（逗号分隔，可空）: ').strip()
            if fkw:
                cmd += ['--filter-keyword', fkw]
            
            print_info('📊 文章数量限制：')
            print('   • 限制参与分析的文章数量（如：50）')
            print('   • 有助于控制分析时间和成本')
            print('   • 直接回车不限制数量')
            print()
            maxa = input('最多文章数（可空）: ').strip()
            if maxa.isdigit():
                cmd += ['--max-articles', maxa]
            
            # 添加字段选择
            content_field = ask_content_field()
            cmd += ['--content-field', content_field]
            
            print_info('🚀 开始执行自定义分析...')
            print(f'   命令：{" ".join(cmd)}')
            print()
            code = run_script(cmd)
        elif ask_yes_no('是否立即进行 AI 分析？', default=True):
            print_info('📊 标准分析模式：')
            print('  • 分析当天的所有新闻数据')
            print('  • 生成完整的财经分析报告')
            print('  • 包含热门话题和潜力话题分析')
            print()
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'markdown-report', '--content-field', content_field]
            print_info('🚀 开始执行标准分析...')
            print(f'   命令：{" ".join(cmd)}')
            print()
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
    print_info('📥 数据抓取选项：')
    print('  • 需要先抓取新闻数据才能进行分析')
    print('  • 可以从多个财经RSS源获取最新新闻')
    print('  • 抓取完成后可以立即进行AI分析')
    print()
    
    if ask_yes_no('是否现在开始抓取今天的数据？', default=True):
        print_info('📰 抓取配置：')
        print('  • 抓取正文：获取完整新闻内容（推荐，分析更准确）')
        print('  • 仅摘要：只获取新闻摘要（速度快，但分析可能不够详细）')
        print()
        fetch_content = ask_yes_no('抓取正文写入数据库（推荐）？', default=True)
        
        print_info('🎯 来源过滤：')
        print('  • 可用的来源：华尔街见闻、36氪、东方财富、国家统计局、中新网等')
        print('  • 多个来源用逗号分隔（如：华尔街见闻,36氪）')
        print('  • 直接回车抓取所有来源')
        print()
        only_src = input('仅抓取某些来源（逗号分隔，可空）: ').strip()
        
        cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'rss_finance_analyzer.py')]
        if fetch_content:
            cmd.append('--fetch-content')
        if only_src:
            cmd += ['--only-source', only_src]
        
        print_info('🚀 开始抓取数据...')
        print(f'   命令：{" ".join(cmd)}')
        print()
        code = run_script(cmd)
        if code != 0:
            print_error('抓取失败，请重试或检查网络。')
            return
        print_success('抓取完成。')

        # 抓取成功后再次确认是否分析
        print_info('✅ 数据抓取完成！')
        print('  • 新闻数据已保存到数据库')
        print('  • 现在可以进行AI分析生成报告')
        print()
        if ask_yes_no('是否立即进行 AI 分析？', default=True):
            print_info('📊 开始AI分析：')
            print('  • 将使用AI模型分析抓取的新闻')
            print('  • 生成专业的财经分析报告')
            print('  • 包含市场趋势和投资建议')
            print()
            # 添加字段选择
            content_field = ask_content_field()
            cmd = ['python3', str(PROJECT_ROOT / 'scripts' / 'ai_analyze_deepseek_verified.py'), '--mode', 'markdown-report', '--content-field', content_field]
            print_info('🚀 开始执行AI分析...')
            print(f'   命令：{" ".join(cmd)}')
            print()
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
