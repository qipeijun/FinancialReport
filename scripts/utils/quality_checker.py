#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
报告质量自动检查模块

功能：
1. 多维度质量评分（8大指标）
2. 自动检测常见问题
3. 生成改进建议
4. 支持全自动模式（无需人工干预）
"""

import re
from typing import Dict, List
from datetime import datetime


def check_report_quality(report_text: str) -> Dict:
    """
    检查报告质量
    
    Args:
        report_text: 报告内容（markdown格式）
        
    Returns:
        {
            'score': 质量评分(0-100),
            'passed': 是否通过(bool),
            'issues': 严重问题列表,
            'warnings': 警告列表,
            'stats': 统计信息
        }
    """
    
    issues = []
    warnings = []
    stats = {}
    
    # ============ 1. 基本结构检查 ============
    required_sections = [
        "市场概况",
        "投资主题",
        "风险",
        "建议"
    ]
    
    missing_sections = []
    for section in required_sections:
        if section not in report_text:
            missing_sections.append(section)
    
    if missing_sections:
        issues.append(f"❌ 缺少必要章节: {', '.join(missing_sections)}")
    
    # ============ 2. 证据引用检查 ============
    citations = re.findall(r'【新闻\d+】', report_text)
    stats['citations_count'] = len(citations)
    
    if len(citations) < 10:
        warnings.append(f"⚠️ 引用来源较少({len(citations)}处)，建议增加到10处以上")
    elif len(citations) < 5:
        issues.append(f"❌ 引用来源严重不足({len(citations)}处)，缺乏证据支撑")
    
    # ============ 3. 模糊表述检查 ============
    vague_phrases = ["可能", "或许", "据说", "有人认为", "也许", "似乎", "大概"]
    vague_count = sum(report_text.count(p) for p in vague_phrases)
    stats['vague_count'] = vague_count
    
    if vague_count > 20:
        issues.append(f"❌ 模糊表述过多({vague_count}处)，缺乏确定性")
    elif vague_count > 15:
        warnings.append(f"⚠️ 模糊表述较多({vague_count}处)，建议用具体数据替代")
    
    # ============ 4. 数据支撑检查 ============
    data_patterns = [
        r'\d+\.?\d*%',           # 百分比: 12.5%
        r'\d+\.?\d*亿',          # 金额: 100亿
        r'\d+\.?\d*万亿',        # 金额: 5万亿
        r'\$\d+\.?\d*',          # 美元: $50
        r'¥\d+\.?\d*',           # 人民币: ¥100
        r'\d+\.?\d*元',          # 元: 1000元
        r'\d+\.?\d*美元',        # 美元: 100美元
    ]
    
    data_count = 0
    for pattern in data_patterns:
        data_count += len(re.findall(pattern, report_text))
    
    stats['data_points'] = data_count
    
    if data_count < 5:
        warnings.append(f"⚠️ 具体数据支撑较少({data_count}处)，建议增加")
    
    # ============ 5. 可操作性检查 ============
    actionable_keywords = [
        "建议", "策略", "操作", "配置", 
        "时间窗口", "仓位", "止损", "买入", "卖出"
    ]
    
    actionable_count = sum(report_text.count(kw) for kw in actionable_keywords)
    stats['actionable_count'] = actionable_count
    
    if actionable_count < 3:
        issues.append("❌ 可操作性严重不足，缺少具体建议")
    elif actionable_count < 5:
        warnings.append("⚠️ 可操作性不足，建议增加操作指引")
    
    # ============ 6. 风险提示检查 ============
    risk_count = report_text.count("风险")
    stats['risk_mentions'] = risk_count
    
    if risk_count < 3:
        issues.append(f"❌ 风险提示严重不足({risk_count}处)")
    elif risk_count < 5:
        warnings.append(f"⚠️ 风险提示较少({risk_count}处)，建议增加")
    
    # ============ 7. 长度检查 ============
    word_count = len(report_text)
    stats['word_count'] = word_count
    
    if word_count < 2000:
        issues.append(f"❌ 报告过短({word_count}字)，内容不够充实")
    elif word_count < 3000:
        warnings.append(f"⚠️ 报告较短({word_count}字)，建议增加分析深度")
    elif word_count > 20000:
        warnings.append(f"⚠️ 报告过长({word_count}字)，建议精简")
    
    # ============ 8. 编造内容检测 ============
    # 检测可疑的具体涨幅预测
    suspicious_patterns = [
        (r'目标涨幅[:：]\s*\d+%', '目标涨幅预测'),
        (r'预计上涨[:：]\s*\d+%', '具体涨幅预测'),
        (r'涨幅预期[:：]\s*\d+%', '涨幅预期数字'),
    ]
    
    for pattern, desc in suspicious_patterns:
        matches = re.findall(pattern, report_text)
        if matches:
            warnings.append(f"⚠️ 检测到{desc}: {matches[0]}（请确认是否有数据支撑）")
    
    # 检测N/A占位符（不应该出现）
    if 'N/A' in report_text or '待定' in report_text:
        issues.append("❌ 检测到N/A或待定占位符，未填写完整")
    
    # ============ 9. 计算总评分 ============
    quality_score = 100
    
    # 严重问题扣分
    quality_score -= len(issues) * 15
    
    # 警告扣分
    quality_score -= len(warnings) * 5
    
    # 确保不低于0
    quality_score = max(0, quality_score)
    
    # 判断是否通过（评分>=70 且无严重问题）
    passed = quality_score >= 70 and len(issues) == 0
    
    # ============ 10. 返回结果 ============
    result = {
        'score': quality_score,
        'passed': passed,
        'issues': issues,
        'warnings': warnings,
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    }
    
    return result


def generate_quality_feedback(quality_result: Dict) -> str:
    """
    根据质量检查结果生成改进建议
    
    Args:
        quality_result: check_report_quality的返回结果
        
    Returns:
        改进建议文本
    """
    
    feedback_items = []
    
    # 根据问题类型生成针对性建议
    all_problems = quality_result['issues'] + quality_result['warnings']
    
    for problem in all_problems:
        if '引用来源' in problem:
            feedback_items.append('请增加【新闻X】引用标注，每个重要观点都要注明具体来源')
        
        if '可操作性' in problem:
            feedback_items.append('请在"操作建议"部分增加：具体时间窗口、仓位建议、止损策略、买入/卖出时机')
        
        if '风险提示' in problem:
            feedback_items.append('请详细说明风险因素：系统性风险、行业风险、个股风险，并给出应对策略')
        
        if '模糊表述' in problem:
            feedback_items.append('请减少"可能"、"或许"等模糊词汇，多使用具体数据、事实和明确判断')
        
        if '数据支撑' in problem:
            feedback_items.append('请增加具体数据：涨跌幅百分比、交易金额、估值指标等')
        
        if '报告过短' in problem or '报告较短' in problem:
            feedback_items.append('请增加分析深度：详细阐述投资逻辑、催化剂分析、产业链机会')
        
        if '缺少必要章节' in problem:
            feedback_items.append('请补全报告结构：市场概况、投资主题、风险提示、操作建议')
        
        if 'N/A' in problem:
            feedback_items.append('请填写所有表格内容，不要使用N/A或待定，必须推荐具体股票代码和公司名称')
    
    # 去重
    feedback_items = list(set(feedback_items))
    
    if not feedback_items:
        feedback_items.append('请全面提升报告质量：增强逻辑性、完善证据链、提升可操作性')
    
    # 格式化输出
    feedback = '\n\n## 📝 质量改进建议\n\n' + '\n'.join([f'{i+1}. {item}' for i, item in enumerate(feedback_items)])
    
    return feedback


def print_quality_report(quality_result: Dict, verbose: bool = True):
    """
    打印质量检查报告
    
    Args:
        quality_result: 质量检查结果
        verbose: 是否显示详细信息
    """
    
    print("\n" + "="*70)
    print("📊 报告质量检查结果")
    print("="*70)
    
    # 评分
    score = quality_result['score']
    if score >= 90:
        score_emoji = "🌟"
        score_desc = "优秀"
    elif score >= 80:
        score_emoji = "✅"
        score_desc = "良好"
    elif score >= 70:
        score_emoji = "👍"
        score_desc = "合格"
    elif score >= 60:
        score_emoji = "⚠️"
        score_desc = "待改进"
    else:
        score_emoji = "❌"
        score_desc = "不合格"
    
    print(f"\n{score_emoji} 总体评分: {score}/100 ({score_desc})")
    
    # 严重问题
    if quality_result['issues']:
        print(f"\n❌ 严重问题 ({len(quality_result['issues'])}个):")
        for issue in quality_result['issues']:
            print(f"  {issue}")
    
    # 警告
    if quality_result['warnings']:
        print(f"\n⚠️ 警告 ({len(quality_result['warnings'])}个):")
        for warning in quality_result['warnings']:
            print(f"  {warning}")
    
    # 统计信息
    if verbose:
        print(f"\n📈 统计信息:")
        stats = quality_result['stats']
        print(f"  • 字数: {stats.get('word_count', 0):,}")
        print(f"  • 引用来源: {stats.get('citations_count', 0)}处")
        print(f"  • 数据点: {stats.get('data_points', 0)}个")
        print(f"  • 可操作性关键词: {stats.get('actionable_count', 0)}次")
        print(f"  • 风险提及: {stats.get('risk_mentions', 0)}次")
        print(f"  • 模糊表述: {stats.get('vague_count', 0)}次")
    
    # 最终判断
    if quality_result['passed']:
        print("\n✅ 质量检查通过，可以发布")
    else:
        print("\n❌ 质量检查未通过，建议优化后再发布")
    
    print("="*70 + "\n")


def print_quality_summary(quality_result: Dict):
    """
    打印简化版质量摘要（用于全自动模式）
    
    Args:
        quality_result: 质量检查结果
    """
    
    score = quality_result['score']
    passed = quality_result['passed']
    
    if passed:
        print(f"  ✅ 质量检查: {score}/100 (通过)")
    else:
        issue_count = len(quality_result['issues'])
        warning_count = len(quality_result['warnings'])
        print(f"  ⚠️ 质量检查: {score}/100 (问题:{issue_count}, 警告:{warning_count})")


def add_quality_warning(report_text: str, quality_result: Dict) -> str:
    """
    在报告开头添加质量警告
    
    Args:
        report_text: 报告内容
        quality_result: 质量检查结果
        
    Returns:
        添加了警告的报告
    """
    
    warning_block = f"""
> ⚠️ **质量提示**: 本报告质量评分为 {quality_result['score']}/100，可能存在以下问题：
"""
    
    for issue in quality_result['issues'][:3]:  # 最多显示3个
        warning_block += f"> - {issue}\n"
    
    warning_block += "> \n> 请结合其他信息源谨慎决策。\n\n"
    
    return warning_block + report_text
