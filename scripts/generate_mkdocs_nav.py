#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动生成 MkDocs 导航配置脚本
扫描项目中的分析报告，自动生成 mkdocs.yml 中的 nav 配置和最新报告面板
"""

import json
import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ARCHIVE_ROOT = Path('docs/archive')
LATEST_MD_PATH = Path('docs/latest.md')
LATEST_DAYS = 3  # 最新面板展示天数

def _is_date_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}-\d{2}', name) is not None

def _is_month_dir_name(name: str) -> bool:
    return re.match(r'^\d{4}-\d{2}$', name) is not None

def get_archive_structure():
    """扫描 archive 目录，返回 {month: [date_dir_paths]} 结构，按时间倒序"""
    result = {}
    if not ARCHIVE_ROOT.exists():
        return result
    for month_dir in sorted(ARCHIVE_ROOT.iterdir(), reverse=True):
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
    
    # 报告文件（按照场次和模型排序）
    if os.path.exists(reports_dir):
        all_md_files = [f for f in os.listdir(reports_dir) if f.endswith('.md')]
        
        # 分离新旧格式文件
        new_format_files = []  # 带 session 标识的新格式（_morning_、_afternoon_、_evening_、_overnight_）
        old_format_files = []  # 旧格式（没有 session，只有模型后缀）
        
        session_patterns = ['_morning_', '_afternoon_', '_evening_', '_overnight_']
        
        for file in all_md_files:
            has_session = any(pattern in file for pattern in session_patterns)
            if has_session:
                new_format_files.append(file)
            else:
                old_format_files.append(file)
        
        # ⚠️ 优先使用新格式：如果新格式文件存在，则忽略旧格式文件
        if new_format_files:
            files['reports'] = new_format_files
        else:
            # 降级到旧格式（兼容旧数据）
            files['reports'] = old_format_files
        
        # 自定义排序：按场次（morning < afternoon < evening < overnight）和模型（gemini < deepseek）
        def sort_key(filename):
            session_order = {'morning': 1, 'afternoon': 2, 'evening': 3, 'overnight': 4}
            model_order = {'gemini': 1, 'deepseek': 2}
            
            # 提取场次标识（必须严格匹配 _session_ 格式）
            session = 'unknown'
            for s in session_order.keys():
                if f'_{s}_' in filename:
                    session = s
                    break
            
            # 提取模型标识
            model = 'unknown'
            if 'gemini' in filename:
                model = 'gemini'
            elif 'deepseek' in filename:
                model = 'deepseek'
            
            return (session_order.get(session, 999), model_order.get(model, 999))
        
        files['reports'].sort(key=sort_key)
    
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

def format_report_name(report_file):
    """
    格式化报告文件名为友好的显示名称
    
    输入示例：
    - 📅 2025-10-12 财经分析报告_morning_gemini.md
    - 📅 2025-10-12 财经分析报告_evening_deepseek.md
    - 📅 2025-10-12 财经分析报告_gemini.md (旧格式)
    
    输出示例：
    - AM Gemini
    - PM DeepSeek
    - Gemini报告 (旧格式)
    """
    # 场次映射（简化为 AM/PM）
    session_map = {
        'morning': 'AM',
        'afternoon': 'PM',
        'evening': 'PM',
        'overnight': 'Night'
    }
    
    # 模型映射
    model_map = {
        'gemini': 'Gemini',
        'deepseek': 'DeepSeek'
    }
    
    # 提取场次（严格匹配 _session_ 格式）
    session = None
    for s in session_map.keys():
        if f'_{s}_' in report_file:
            session = s
            break
    
    # 提取模型
    model = None
    for m in model_map.keys():
        if m in report_file:
            model = m
            break
    
    # 生成显示名称
    if session and model:
        # 新格式：AM Gemini报告 / PM DeepSeek报告
        session_label = session_map[session]
        model_name = model_map[model]
        return f"{session_label} {model_name}报告"
    elif model:
        # 旧格式：Gemini报告
        model_name = model_map[model]
        return f"{model_name}报告"
    else:
        # 降级处理：移除常见前缀和后缀
        name = report_file.replace('.md', '').replace('📅 ', '').replace('财经分析报告', '').replace('_', ' ').strip()
        return name if name else "分析报告"

def generate_nav_structure():
    """生成导航结构"""
    nav = [
        {"首页": "index.md"},
        {"📊 最新报告": "latest.md"},
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
                        report_name = format_report_name(report_file)
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
                    # 按数字排序热门话题（提取数字进行排序）
                    hot_topics.sort(key=lambda x: int(re.search(r'热门话题(\d+)', list(x.keys())[0]).group(1)) if re.search(r'热门话题(\d+)', list(x.keys())[0]) else 999)
                    date_nav[date_name].append({"🔥 热门话题": hot_topics})
                
                if potential_topics:
                    # 按数字排序潜力话题（提取数字进行排序）
                    potential_topics.sort(key=lambda x: int(re.search(r'潜力话题(\d+)', list(x.keys())[0]).group(1)) if re.search(r'潜力话题(\d+)', list(x.keys())[0]) else 999)
                    date_nav[date_name].append({"💎 潜力话题": potential_topics})
                
                if date_nav[date_name]:  # 只有当有内容时才添加
                    month_nav[month_display].append(date_nav)
            
            if month_nav[month_display]:  # 只有当有内容时才添加
                # 按 key 名查找"分析报告"条目，避免硬编码索引
                analysis_entry = next((item for item in nav if "分析报告" in item), None)
                if analysis_entry is not None:
                    analysis_entry["分析报告"].append(month_nav)
    
    return nav

def _load_json_safe(path: Path) -> Optional[Dict[str, Any]]:
    """安全加载 JSON，失败返回 None"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _extract_trust_summary(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """从 metadata JSON 提取可信度摘要"""
    quality = metadata.get('quality_check') or {}
    stats = quality.get('stats') or {}
    cv = metadata.get('cross_verification') or {}
    cv_summary = cv.get('summary') or {}
    coverage = metadata.get('coverage_matrix') or {}

    return {
        'score': quality.get('score'),
        'passed': quality.get('passed'),
        'verified_claims': stats.get('verified_claims'),
        'total_claims': stats.get('total_claims'),
        'cv_confirmed': cv_summary.get('stocks_confirmed'),
        'cv_weak': cv_summary.get('stocks_weak'),
        'coverage_gaps': coverage.get('coverage_gaps') or [],
        'live_data_degraded': metadata.get('live_data_degraded', False),
    }


def _render_trust_badge(info: Dict[str, Any]) -> str:
    """根据可信度信息渲染状态徽章"""
    score = info.get('score')
    passed = info.get('passed')
    verified = info.get('verified_claims')
    total = info.get('total_claims')

    parts: List[str] = []
    if passed is True and score is not None:
        parts.append(f'🟢 通过 {score}分')
    elif passed is False:
        parts.append(f'🔴 未通过')
    else:
        parts.append('⚪ 未验收')

    if verified is not None and total is not None:
        parts.append(f'核查 {verified}/{total}')

    return ' · '.join(parts) if parts else '—'


def generate_latest_md() -> None:
    """扫描最近 N 天 archive metadata，生成 docs/latest.md 最新报告面板"""
    if not ARCHIVE_ROOT.exists():
        LATEST_MD_PATH.write_text('# 最新报告\n\n暂无报告数据。\n', encoding='utf-8')
        return

    # 收集所有日期目录（倒序）
    all_dates: List[tuple[str, Path]] = []
    for month_dir in sorted(ARCHIVE_ROOT.iterdir(), reverse=True):
        if not month_dir.is_dir() or not _is_month_dir_name(month_dir.name):
            continue
        for date_dir in sorted(month_dir.iterdir(), reverse=True):
            if date_dir.is_dir() and _is_date_dir_name(date_dir.name):
                all_dates.append((date_dir.name, date_dir))

    # 取最近 N 天
    recent = all_dates[:LATEST_DAYS]

    lines = [
        '# 📊 最新报告',
        '',
        '> 系统自动生成，展示最近 {} 天的报告产物与可信度状态。点击链接直接查看。'.format(LATEST_DAYS),
        '',
    ]

    if not recent:
        lines.append('暂无报告数据。')
        LATEST_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return

    for date_str, date_dir in recent:
        lines.append(f'## {date_str}')
        lines.append('')

        metadata_dir = date_dir / 'metadata'
        reports_dir = date_dir / 'reports'

        if not reports_dir.exists() and not metadata_dir.exists():
            lines.append('*该日无产物*')
            lines.append('')
            continue

        # 收集各市场报告（按 mtime 选最新的一份 metadata）
        rows: List[Dict[str, Any]] = []
        best_by_market: Dict[str, tuple[Path, float]] = {}

        # 扫描 metadata 文件，按 mtime 保留每个市场最新的
        if metadata_dir.exists():
            for meta_file in metadata_dir.iterdir():
                name = meta_file.name
                if not name.endswith('.json') or 'analysis_meta' not in name:
                    continue
                market_match = re.search(r'markdown-report-([a-z]{2})', name, re.IGNORECASE)
                market = market_match.group(1).upper() if market_match else '?'
                mtime = meta_file.stat().st_mtime
                if market not in best_by_market or mtime > best_by_market[market][1]:
                    best_by_market[market] = (meta_file, mtime)

        for market, (meta_file, _mtime) in best_by_market.items():
            meta_data = _load_json_safe(meta_file)
            trust = _extract_trust_summary(meta_data) if meta_data else {}

            # 找对应报告（同样按 mtime 选最新）
            report_path: Optional[str] = None
            best_report_mtime = 0.0
            if reports_dir.exists():
                mkt_lower = market.lower()
                for report_file in reports_dir.iterdir():
                    rn = report_file.name.lower()
                    if f'markdown-report-{mkt_lower}' in rn and report_file.name.endswith('.md'):
                        rmtime = report_file.stat().st_mtime
                        if rmtime > best_report_mtime:
                            best_report_mtime = rmtime
                            report_path = f'archive/{date_str[:7]}/{date_str}/reports/{report_file.name}'

            rows.append({
                'market': market,
                'trust': trust,
                'report_path': report_path,
            })
            seen_markets: set = {m for m in best_by_market}

        # 也扫描 reports 目录，补漏没有 metadata 的情况
        if reports_dir.exists():
            best_report_by_market: Dict[str, tuple[str, float]] = {}
            for report_file in reports_dir.iterdir():
                name = report_file.name
                if not name.endswith('.md'):
                    continue
                market_match = re.search(r'markdown-report-([a-z]{2})', name, re.IGNORECASE)
                market = market_match.group(1).upper() if market_match else '?'
                if market in seen_markets:
                    continue
                rmtime = report_file.stat().st_mtime
                if market not in best_report_by_market or rmtime > best_report_by_market[market][1]:
                    best_report_by_market[market] = (f'archive/{date_str[:7]}/{date_str}/reports/{name}', rmtime)
            for market, (rpath, _) in best_report_by_market.items():
                rows.append({
                    'market': market,
                    'trust': {},
                    'report_path': rpath,
                })

        if not rows:
            lines.append('*该日无可识别产物*')
            lines.append('')
            continue

        # 渲染表格
        lines.append('| 市场 | 可信度 | 报告 |')
        lines.append('|------|--------|------|')
        for row in rows:
            market_label = '🇨🇳 A股' if row['market'] == 'CN' else ('🇺🇸 美股' if row['market'] == 'US' else row['market'])
            badge = _render_trust_badge(row['trust'])
            if row['report_path']:
                link = f'[查看]({row["report_path"]})'
            else:
                link = '—'
            lines.append(f'| {market_label} | {badge} | {link} |')

        # 异常标注
        for row in rows:
            trust = row['trust']
            market_label = 'CN' if row['market'] == 'CN' else 'US'
            if trust.get('live_data_degraded'):
                lines.append(f'\n⚠️ {market_label} 实时行情降级')
            gaps = trust.get('coverage_gaps') or []
            if gaps:
                lines.append(f'\n📋 {market_label} 覆盖缺口: {", ".join(gaps[:3])}')

        lines.append('')

    LATEST_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'✅ 最新报告面板已生成: {LATEST_MD_PATH}')


def update_mkdocs_config():
    """更新 mkdocs.yml 配置文件"""
    # 先生成最新报告面板
    generate_latest_md()

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
