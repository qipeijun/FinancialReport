#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动生成 MkDocs 导航配置脚本
扫描项目中的分析报告，自动生成 mkdocs.yml 中的 nav 配置
"""

import os
import re
import yaml
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path('docs/archive')

def _is_date_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}-\d{2}', name) is not None

def _is_month_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}$', name) is not None

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
    
    return files

def format_date_name(date_str):
    """格式化日期显示名称"""
    if len(date_str) == 8 and date_str.isdigit():
        # 处理 20250928 格式
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    elif '-' in date_str:
        # 处理 2025-09-28 格式
        return date_str
    else:
        return date_str

def generate_nav_structure():
    """生成导航结构"""
    nav = [
        {"首页": "index.md"},
        {"分析报告": []}
    ]
    
    archive = get_archive_structure()
    if archive:
        # 按月份排序（最新的在前）
        sorted_months = sorted(archive.keys(), reverse=True)
        
        for month in sorted_months:
            year, month_num = month.split('-')
            month_display = f"{year}年{month_num}月"
            month_nav = {month_display: []}
            
            # 按日期排序（最新的在前）
            sorted_dates = sorted(archive[month], key=lambda x: x.name, reverse=True)
            
            for date_path in sorted_dates:
                files = get_analysis_files(date_path.as_posix())
                date_name = format_date_name(date_path.name)
                date_nav = {date_name: []}
                
                # 添加报告文件
                if files['reports']:
                    for report_file in files['reports']:
                        report_path = f"archive/{month}/{date_path.name}/reports/{report_file}"
                        report_name = report_file.replace('.md', '').replace('📅 ', '').replace('财经分析报告_', '').replace('_', ' ')
                        if not report_name or report_name == date_name:
                            report_name = "📊 2025-09-28 财经分析报告"
                        date_nav[date_name].append({report_name: report_path})
                
                # 分组分析文件：热门话题和潜力话题
                hot_topics = []
                potential_topics = []
                
                if files['analysis']:
                    for analysis_file in files['analysis']:
                        analysis_path = f"archive/{month}/{date_path.name}/analysis/{analysis_file}"
                        analysis_name = analysis_file.replace('.md', '').replace('_', ' ')
                        
                        if '热门话题' in analysis_name:
                            hot_topics.append({analysis_name: analysis_path})
                        elif '潜力话题' in analysis_name:
                            potential_topics.append({analysis_name: analysis_path})
                        else:
                            # 其他分析文件直接添加
                            date_nav[date_name].append({analysis_name: analysis_path})
                
                # 添加分组的话题
                if hot_topics:
                    # 按数字排序热门话题
                    hot_topics.sort(key=lambda x: list(x.keys())[0])
                    date_nav[date_name].append({"🔥 热门话题": hot_topics})
                
                if potential_topics:
                    # 按数字排序潜力话题
                    potential_topics.sort(key=lambda x: list(x.keys())[0])
                    date_nav[date_name].append({"💎 潜力话题": potential_topics})
                
                if date_nav[date_name]:  # 只有当有内容时才添加
                    month_nav[month_display].append(date_nav)
            
            if month_nav[month_display]:  # 只有当有内容时才添加
                nav[1]["分析报告"].append(month_nav)
    
    return nav

def update_mkdocs_config():
    """更新 mkdocs.yml 配置文件"""
    # 读取现有的 mkdocs.yml
    with open('mkdocs.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 生成新的导航结构
    new_nav = generate_nav_structure()
    
    # 更新配置
    config['nav'] = new_nav
    
    # 写回文件
    with open('mkdocs.yml', 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print("✅ MkDocs 导航配置已更新！")

def main():
    """主函数"""
    print("🔄 正在生成 MkDocs 导航配置...")
    update_mkdocs_config()
    print("📝 已更新 mkdocs.yml 文件")

if __name__ == "__main__":
    main()
