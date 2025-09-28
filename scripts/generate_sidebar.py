#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动生成侧边栏目录脚本
扫描项目中的分析报告，自动生成 _sidebar.md 文件
"""

import os
import re
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path('archive')

def _is_date_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}-\d{2}', name) is not None

def _is_month_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}$', name) is not None

def get_date_directories():
    """兼容旧结构：获取根目录下所有日期目录"""
    date_dirs = []
    for item in os.listdir('.'):
        if os.path.isdir(item) and re.match(r'^\d{4}-\d{2}-\d{2}', item):
            date_dirs.append(item)
    return sorted(date_dirs, reverse=True)

def get_archive_structure():
    """扫描 archive 目录，返回 {month: [date_dir_paths]} 结构，按时间倒序"""
    result = {}
    if not ARCHIVE_ROOT.exists():
        return result
    for month_dir in ARCHIVE_ROOT.iterdir():
        if month_dir.is_dir() and _is_month_dir_name(month_dir.name):
            date_dirs = [p for p in month_dir.iterdir() if p.is_dir() and _is_date_dir_name(p.name)]
            if date_dirs:
                result[month_dir.name] = sorted(date_dirs, key=lambda p: p.name, reverse=True)
    return dict(sorted(result.items(), key=lambda kv: kv[0], reverse=True))

def get_analysis_files(date_dir):
    """获取指定日期目录下的分析文件"""
    analysis_dir = os.path.join(date_dir, 'analysis')
    reports_dir = os.path.join(date_dir, 'reports')
    
    files = {
        'analysis': [],
        'reports': [],
        'news': [],
        'rss': []
    }
    
    # 分析文件
    if os.path.exists(analysis_dir):
        for file in os.listdir(analysis_dir):
            if file.endswith('.md'):
                files['analysis'].append(file)
    
    # 报告文件
    if os.path.exists(reports_dir):
        for file in os.listdir(reports_dir):
            if file.endswith('.md'):
                files['reports'].append(file)
    
    # 新闻内容
    news_dir = os.path.join(date_dir, 'news_content')
    if os.path.exists(news_dir):
        for file in os.listdir(news_dir):
            if file.endswith('.txt'):
                files['news'].append(file)
    
    # RSS数据
    rss_dir = os.path.join(date_dir, 'rss_data')
    if os.path.exists(rss_dir):
        for file in os.listdir(rss_dir):
            if file.endswith('.txt'):
                files['rss'].append(file)
    
    return files

def generate_sidebar():
    """生成侧边栏内容"""
    sidebar_content = """# 📊 财经分析报告

## 📋 项目介绍
- [项目说明](README.md)

## 📅 分析报告

"""
    
    archive = get_archive_structure()
    if archive:
        # 新结构：按月份→日期列出报告
        for month in archive.keys():
            sidebar_content += f"### {month} 报告\n"
            for date_path in archive[month]:
                files = get_analysis_files(date_path.as_posix())
                for report_file in files['reports']:
                    report_path = f"{date_path.as_posix()}/reports/{report_file}"
                    report_name = report_file.replace('.md', '').replace('📅 ', '').replace('财经分析报告_', '')
                    sidebar_content += f"- [{report_name}]({report_path})\n"
            sidebar_content += "\n"
    else:
        # 旧结构兼容
        date_dirs = get_date_directories()
        if not date_dirs:
            sidebar_content += "暂无分析报告\n"
            return sidebar_content
        years = {}
        for date_dir in date_dirs:
            year = date_dir[:4]
            years.setdefault(year, []).append(date_dir)
        for year in sorted(years.keys(), reverse=True):
            sidebar_content += f"### {year}年报告\n"
            for date_dir in years[year]:
                files = get_analysis_files(date_dir)
                for report_file in files['reports']:
                    report_path = f"{date_dir}/reports/{report_file}"
                    report_name = report_file.replace('.md', '').replace('📅 ', '').replace('财经分析报告_', '')
                    sidebar_content += f"- [{report_name}]({report_path})\n"
            sidebar_content += "\n"
    
    # 添加详细分析部分
    sidebar_content += "## 🔍 分析详情\n\n"
    
    # 收集最近5个日期路径
    recent_date_paths = []
    if archive:
        for month in archive.keys():
            for p in archive[month]:
                recent_date_paths.append(p)
        recent_date_paths = recent_date_paths[:5]
    else:
        recent_date_paths = [Path(p) for p in get_date_directories()[:5]]

    for date_path in recent_date_paths:
        files = get_analysis_files(date_path.as_posix())
        date_name = date_path.name.replace('_', ' ').title()
        
        sidebar_content += f"### {date_name}\n"
        
        # 分析文件
        if files['analysis']:
            for analysis_file in files['analysis']:
                analysis_path = f"{date_path.as_posix()}/analysis/{analysis_file}"
                analysis_name = analysis_file.replace('.md', '').replace('_', ' ').title()
                sidebar_content += f"- [{analysis_name}]({analysis_path})\n"
        
        # 报告文件
        if files['reports']:
            for report_file in files['reports']:
                report_path = f"{date_path.as_posix()}/reports/{report_file}"
                report_name = report_file.replace('.md', '').replace('📅 ', '').replace('财经分析报告_', '')
                sidebar_content += f"- [报告: {report_name}]({report_path})\n"
        
        sidebar_content += "\n"
    
    # 添加新闻内容部分
    sidebar_content += "## 📰 新闻内容\n\n"
    
    for date_path in recent_date_paths[:3]:  # 只显示最近3个日期的新闻
        files = get_analysis_files(date_path.as_posix())
        date_name = date_path.name.replace('_', ' ').title()
        
        sidebar_content += f"### {date_name}\n"
        
        if files['news']:
            for news_file in files['news'][:5]:  # 只显示前5个新闻文件
                news_path = f"{date_path.as_posix()}/news_content/{news_file}"
                news_name = news_file.replace('.txt', '').replace('_', ' ').title()
                sidebar_content += f"- [{news_name}]({news_path})\n"
        
        sidebar_content += "\n"
    
    # 添加RSS数据部分
    sidebar_content += "## 📡 RSS数据源\n\n"
    
    for date_path in recent_date_paths[:3]:  # 只显示最近3个日期的RSS
        files = get_analysis_files(date_path.as_posix())
        date_name = date_path.name.replace('_', ' ').title()
        
        sidebar_content += f"### {date_name}\n"
        
        if files['rss']:
            for rss_file in files['rss'][:8]:  # 只显示前8个RSS文件
                rss_path = f"{date_path.as_posix()}/rss_data/{rss_file}"
                rss_name = rss_file.replace('.txt', '').replace('_', ' ').title()
                sidebar_content += f"- [{rss_name}]({rss_path})\n"
        
        sidebar_content += "\n"
    
    # 添加工具配置部分
    sidebar_content += """## 🛠️ 工具配置
- [完整版提示词](prompts/mcp_finance_analysis_prompt.md)
- [优化版提示词](prompts/mcp_finance_analysis_prompt_optimized.md)
- [精简版提示词](prompts/mcp_finance_analysis_prompt_minimal.md)
"""
    
    return sidebar_content

def main():
    """主函数"""
    print("🔄 正在生成侧边栏目录...")
    
    # 生成侧边栏内容
    sidebar_content = generate_sidebar()
    
    # 写入文件
    with open('web/_sidebar.md', 'w', encoding='utf-8') as f:
        f.write(sidebar_content)
    
    print("✅ 侧边栏目录生成完成！")
    print("📝 已更新 _sidebar.md 文件")

if __name__ == "__main__":
    main()
