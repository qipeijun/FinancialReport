#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
增强版报告质量检查器 v2.0

核心升级:
1. 集成事实核查 - 验证所有可验证断言
2. 多维度评分 - 准确性(60%) + 时效性(20%) + 可靠性(20%)
3. 严格约束检查 - 自动检测AI编造内容
4. 实时数据验证 - 要求报告基于实时数据

目标: 杜绝AI幻觉,提升报告可信度
"""

import re
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def check_report_quality_v2(
    report_text: str,
    claims: Optional[List] = None,
    realtime_data: Optional[Dict] = None
) -> Dict:
    """
    增强版质量检查 (集成事实核查)

    评分维度:
    1. 准确性(60分) - 基于事实核查通过率
    2. 时效性(20分) - 数据新鲜度
    3. 可靠性(20分) - 来源标注完整性

    Args:
        report_text: 报告文本
        claims: 事实核查结果(来自FactChecker)
        realtime_data: 实时数据(用于验证时效性)

    Returns:
        {
            'score': 总分(0-100),
            'passed': 是否通过(>=80),
            'accuracy_score': 准确性得分,
            'timeliness_score': 时效性得分,
            'reliability_score': 可靠性得分,
            'issues': 问题列表,
            'warnings': 警告列表
        }
    """
    score = 0
    issues = []
    warnings = []
    accuracy_score = 0
    timeliness_score = 0
    reliability_score = 0

    # ============================================================
    # 1. 准确性评分 (60分) - 核心指标
    # ============================================================
    if claims:
        verified_count = sum(1 for c in claims if c.verified)
        total_count = len(claims)
        error_count = sum(1 for c in claims if c.error)

        if total_count > 0:
            accuracy_rate = verified_count / total_count
            accuracy_score = accuracy_rate * 60

            # 记录准确性情况
            if accuracy_rate < 0.5:
                issues.append(f"❌ 准确性严重不足: 仅{accuracy_rate:.0%}的断言得到验证 ({verified_count}/{total_count})")
            elif accuracy_rate < 0.7:
                warnings.append(f"⚠️ 准确性偏低: {accuracy_rate:.0%}的断言得到验证 ({verified_count}/{total_count})")
            else:
                logger.info(f"准确性良好: {accuracy_rate:.0%} ({verified_count}/{total_count})")

            # 错误惩罚
            if error_count > 0:
                penalty = min(error_count * 10, 30)
                accuracy_score = max(0, accuracy_score - penalty)
                issues.append(f"❌ 检测到 {error_count} 个错误或违规断言,扣分 {penalty}")
        else:
            warnings.append("⚠️ 缺少可验证的具体断言,无法评估准确性")
            accuracy_score = 30  # 给基础分
    else:
        warnings.append("⚠️ 未进行事实核查,准确性无法保证")
        accuracy_score = 30  # 给基础分

    score += accuracy_score

    # ============================================================
    # 2. 时效性评分 (20分)
    # ============================================================
    has_realtime_data = False
    data_age_hours = None

    # 检查是否包含实时数据标注
    if '数据来源' in report_text and '更新时间' in report_text:
        has_realtime_data = True

        # 提取更新时间
        time_match = re.search(r'更新时间.*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', report_text)
        if time_match:
            try:
                update_time_str = time_match.group(1)
                update_time = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M')
                data_age_hours = (datetime.now() - update_time).total_seconds() / 3600

                if data_age_hours < 1:
                    timeliness_score = 20  # 数据非常新鲜
                    logger.info("实时数据: 非常新鲜 (<1小时)")
                elif data_age_hours < 4:
                    timeliness_score = 15  # 数据较新
                    logger.info(f"实时数据: 较新 ({data_age_hours:.1f}小时)")
                elif data_age_hours < 24:
                    timeliness_score = 10  # 数据有些陈旧
                    warnings.append(f"⚠️ 数据更新于{data_age_hours:.1f}小时前,时效性一般")
                else:
                    timeliness_score = 5
                    warnings.append(f"⚠️ 数据更新于{data_age_hours:.1f}小时前,时效性较差")
            except Exception as e:
                timeliness_score = 10
                logger.warning(f"时间解析失败: {e}")
        else:
            timeliness_score = 10
    else:
        # 检查是否注入了实时数据
        if realtime_data and realtime_data.get('timestamp'):
            has_realtime_data = True
            timeliness_score = 10
            warnings.append("⚠️ 报告中缺少实时数据标注,但系统已注入数据")
        else:
            issues.append("❌ 缺少实时数据注入,报告时效性差")
            timeliness_score = 0

    score += timeliness_score

    # ============================================================
    # 3. 可靠性评分 (20分) - 来源标注
    # ============================================================
    # 检查引用来源
    citations = re.findall(r'【新闻\d+】', report_text)
    citation_count = len(citations)

    # 检查数据来源标注
    has_source_annotation = '数据来源' in report_text or '来源：' in report_text

    # 计算可靠性得分
    if citation_count >= 15 and has_source_annotation:
        reliability_score = 20
    elif citation_count >= 10 and has_source_annotation:
        reliability_score = 15
    elif citation_count >= 5 or has_source_annotation:
        reliability_score = 10
        warnings.append(f"⚠️ 引用来源偏少 ({citation_count}处),建议增加到15处以上")
    else:
        reliability_score = 5
        issues.append(f"❌ 引用来源严重不足 ({citation_count}处),缺乏可信度")

    score += reliability_score

    # ============================================================
    # 4. 禁止编造内容检查 (严重违规 - 直接扣分)
    # ============================================================
    fabrication_detected = False

    # 检测1: 目标涨幅 (最严重违规)
    target_gains = re.findall(r'目标涨幅\s*[:：]?\s*(\d+\.?\d*)\s*%', report_text)
    if target_gains:
        score -= 30  # 严重扣分
        fabrication_detected = True
        issues.append(f"❌❌❌ 严重违规: AI编造目标涨幅 ({', '.join(target_gains)}%),明确禁止!")

    # 检测2: 未来具体价格预测
    target_prices = re.findall(r'目标价(?:格)?\s*[:：]?\s*([¥$]\d+\.?\d*)', report_text)
    if target_prices:
        score -= 20
        fabrication_detected = True
        issues.append(f"❌❌ 违规: AI编造目标价格 ({', '.join(target_prices)}),禁止!")

    # 检测3: 编造的未来业绩预测
    future_predictions = re.findall(r'预计.*?(?:增长|下降)\s*(\d+\.?\d*)\s*%', report_text)
    if len(future_predictions) > 3:
        warnings.append(f"⚠️ 检测到多处未来预测 ({len(future_predictions)}处),请确认是否有依据")

    # 检测4: 无依据的具体断言
    if 'N/A' in report_text or '待定' in report_text:
        score -= 10
        issues.append("❌ 检测到N/A或待定占位符,未填写完整")

    # ============================================================
    # 5. 基础结构检查 (额外加分项)
    # ============================================================
    required_sections = ["市场概况", "投资主题", "风险", "建议"]
    missing_sections = [s for s in required_sections if s not in report_text]

    if missing_sections:
        warnings.append(f"⚠️ 缺少章节: {', '.join(missing_sections)}")
        score -= len(missing_sections) * 5

    # ============================================================
    # 6. 确保得分在合理范围
    # ============================================================
    score = max(0, min(100, score))

    # ============================================================
    # 7. 判断是否通过
    # ============================================================
    # 通过标准: 总分>=80 且 无严重问题 且 未检测到编造内容
    passed = score >= 80 and len(issues) == 0 and not fabrication_detected

    # ============================================================
    # 8. 返回结果
    # ============================================================
    return {
        'score': round(score, 1),
        'passed': passed,
        'accuracy_score': round(accuracy_score, 1),
        'timeliness_score': round(timeliness_score, 1),
        'reliability_score': round(reliability_score, 1),
        'issues': issues,
        'warnings': warnings,
        'stats': {
            'has_realtime_data': has_realtime_data,
            'data_age_hours': data_age_hours,
            'citation_count': citation_count,
            'verified_claims': sum(1 for c in claims if c.verified) if claims else 0,
            'total_claims': len(claims) if claims else 0,
            'fabrication_detected': fabrication_detected
        },
        'timestamp': datetime.now().isoformat()
    }


def print_quality_report_v2(quality_result: Dict, verbose: bool = True):
    """
    打印增强版质量检查报告

    Args:
        quality_result: check_report_quality_v2的返回结果
        verbose: 是否显示详细信息
    """
    print("\n" + "="*70)
    print("📊 报告质量检查结果 (v2.0 - 集成事实核查)")
    print("="*70)

    # 总分
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

    # 分项得分
    if verbose:
        print(f"\n📈 分项评分:")
        print(f"  • 准确性: {quality_result['accuracy_score']:.1f}/60 (基于事实核查)")
        print(f"  • 时效性: {quality_result['timeliness_score']:.1f}/20 (数据新鲜度)")
        print(f"  • 可靠性: {quality_result['reliability_score']:.1f}/20 (来源标注)")

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
        stats = quality_result['stats']
        print(f"\n📊 统计数据:")
        print(f"  • 实时数据: {'是' if stats.get('has_realtime_data') else '否'}")
        if stats.get('data_age_hours') is not None:
            print(f"  • 数据时效: {stats['data_age_hours']:.1f} 小时前")
        print(f"  • 引用来源: {stats.get('citation_count', 0)}处")
        print(f"  • 验证断言: {stats.get('verified_claims', 0)}/{stats.get('total_claims', 0)}")
        if stats.get('fabrication_detected'):
            print(f"  • ⚠️ 检测到编造内容")

    # 最终判断
    print(f"\n{'='*70}")
    if quality_result['passed']:
        print("✅ 质量检查通过,可以发布")
    else:
        print("❌ 质量检查未通过,建议优化后再发布")
        print("\n改进建议:")
        print("  1. 确保所有断言基于实时数据")
        print("  2. 删除所有编造的目标涨幅/价格")
        print("  3. 增加引用来源标注(【新闻X】)")
        print("  4. 在报告中标注数据来源和更新时间")

    print("="*70 + "\n")


def compare_quality_scores(old_score: Dict, new_score: Dict) -> str:
    """
    对比优化前后的质量评分

    Args:
        old_score: 旧版评分结果
        new_score: 新版评分结果

    Returns:
        对比报告文本
    """
    comparison = "\n## 📊 质量评分对比\n\n"
    comparison += "| 维度 | 优化前 | 优化后 | 提升 |\n"
    comparison += "|------|--------|--------|------|\n"

    old_total = old_score.get('score', 0)
    new_total = new_score.get('score', 0)
    improvement = new_total - old_total

    comparison += f"| **总分** | {old_total:.1f} | {new_total:.1f} | "
    comparison += f"**{improvement:+.1f}** |\n"

    # 如果新版有分项得分
    if 'accuracy_score' in new_score:
        comparison += f"| 准确性(/60) | - | {new_score['accuracy_score']:.1f} | 新增 |\n"
        comparison += f"| 时效性(/20) | - | {new_score['timeliness_score']:.1f} | 新增 |\n"
        comparison += f"| 可靠性(/20) | - | {new_score['reliability_score']:.1f} | 新增 |\n"

    # 统计对比
    old_issues = len(old_score.get('issues', []))
    new_issues = len(new_score.get('issues', []))

    comparison += f"\n**问题数对比**: {old_issues} → {new_issues} "
    comparison += f"({'减少' if new_issues < old_issues else '增加'} {abs(new_issues - old_issues)})\n"

    return comparison


# ============================================================
# 使用示例和测试
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )

    print("="*70)
    print("增强版质量检查器 v2.0 - 功能测试")
    print("="*70)

    # 模拟报告
    test_report_bad = """
    # 财经分析报告

    ## 投资建议

    | 股票 | 目标涨幅 | 风险 |
    |------|---------|------|
    | 紫金矿业 | 25% | 中 |

    金价突破3800美元,建议关注黄金板块。
    """

    test_report_good = """
    # 财经分析报告

    ## 📊 实时市场数据

    **数据来源**: 新浪财经
    **更新时间**: 2026-01-07 15:00

    ## 市场概况

    今日A股市场活跃,紫金矿业(sh601899)现价¥15.23,涨幅+2.34%【新闻1】。
    国际金价$2650/盎司,较昨日+1.2%【新闻2】。

    ## 投资主题

    黄金板块表现强势,建议关注紫金矿业等龙头【新闻3】【新闻4】。

    ## 风险提示

    需警惕金价回调风险【新闻5】,建议设置止损【新闻6】。

    ## 操作建议

    建议逢低配置,仓位控制在30%以内【新闻7】【新闻8】【新闻9】【新闻10】。
    """

    # 模拟事实核查结果
    from dataclasses import dataclass
    from enum import Enum

    class ClaimType(Enum):
        PRICE_CHANGE = "涨跌幅"

    @dataclass
    class MockClaim:
        type: ClaimType
        content: str
        verified: bool
        confidence: float
        error: str = ""

    # 测试1: 低质量报告(有编造内容)
    print("\n【测试1】低质量报告(有目标涨幅)")
    print("-"*70)

    bad_claims = [
        MockClaim(ClaimType.PRICE_CHANGE, "目标涨幅25%", False, 0.0, "编造内容")
    ]

    bad_result = check_report_quality_v2(
        report_text=test_report_bad,
        claims=bad_claims,
        realtime_data=None
    )

    print_quality_report_v2(bad_result)

    # 测试2: 高质量报告(有实时数据)
    print("\n【测试2】高质量报告(有实时数据和事实核查)")
    print("-"*70)

    good_claims = [
        MockClaim(ClaimType.PRICE_CHANGE, "涨幅+2.34%", True, 0.98),
        MockClaim(ClaimType.PRICE_CHANGE, "金价+1.2%", True, 0.95),
    ]

    good_realtime = {
        'timestamp': '2026-01-07 15:00:00',
        'stocks': {'sh601899': {'price': 15.23, 'change_pct': 2.34}}
    }

    good_result = check_report_quality_v2(
        report_text=test_report_good,
        claims=good_claims,
        realtime_data=good_realtime
    )

    print_quality_report_v2(good_result)

    # 测试3: 对比
    print("\n【测试3】质量评分对比")
    print("-"*70)
    comparison = compare_quality_scores(bad_result, good_result)
    print(comparison)

    print("\n" + "="*70)
    print("✅ 测试完成")
    print("="*70)
