#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量监控工具

功能：
- 分析数据完整性
- 检测重复数据
- 统计来源覆盖率
- 监控数据质量指标
- 生成质量报告
"""

import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import json

from utils.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_statistics, print_table_header, print_table_row
)
from utils.logger import get_logger
from utils.config_manager import get_db_path

logger = get_logger('data_quality')


@dataclass
class DataQualityReport:
    """数据质量报告"""
    # 基本统计
    total_articles: int
    date_range: tuple[str, str]
    
    # 内容完整性
    articles_with_content: int
    articles_with_summary: int
    empty_title_count: int
    empty_link_count: int
    
    # 数据质量
    duplicate_count: int
    avg_title_length: float
    avg_summary_length: float
    avg_content_length: float
    
    # 来源统计
    sources_coverage: Dict[str, int]
    total_sources: int
    
    # 时间分布
    daily_distribution: Dict[str, int]
    
    @property
    def content_coverage(self) -> float:
        """内容覆盖率"""
        if self.total_articles == 0:
            return 0.0
        return (self.articles_with_content / self.total_articles) * 100
    
    @property
    def summary_coverage(self) -> float:
        """摘要覆盖率"""
        if self.total_articles == 0:
            return 0.0
        return (self.articles_with_summary / self.total_articles) * 100
    
    @property
    def quality_score(self) -> float:
        """
        数据质量评分（0-100）
        
        计算公式：
        - 内容完整性 40%
        - 摘要完整性 30%
        - 无重复率 20%
        - 必填字段完整性 10%
        """
        if self.total_articles == 0:
            return 0.0
        
        # 内容完整性得分
        content_score = self.content_coverage * 0.4
        
        # 摘要完整性得分
        summary_score = self.summary_coverage * 0.3
        
        # 无重复率得分
        duplicate_rate = (self.duplicate_count / self.total_articles) * 100
        no_duplicate_score = max(0, 100 - duplicate_rate) * 0.2
        
        # 必填字段完整性得分
        empty_required = self.empty_title_count + self.empty_link_count
        required_rate = max(0, 100 - (empty_required / self.total_articles * 100))
        required_score = required_rate * 0.1
        
        return content_score + summary_score + no_duplicate_score + required_score
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'basic': {
                'total_articles': self.total_articles,
                'date_range': {
                    'start': self.date_range[0],
                    'end': self.date_range[1]
                }
            },
            'completeness': {
                'content_coverage': f'{self.content_coverage:.1f}%',
                'summary_coverage': f'{self.summary_coverage:.1f}%',
                'articles_with_content': self.articles_with_content,
                'articles_with_summary': self.articles_with_summary,
                'empty_title_count': self.empty_title_count,
                'empty_link_count': self.empty_link_count
            },
            'quality': {
                'quality_score': f'{self.quality_score:.1f}',
                'duplicate_count': self.duplicate_count,
                'avg_title_length': f'{self.avg_title_length:.1f}',
                'avg_summary_length': f'{self.avg_summary_length:.1f}',
                'avg_content_length': f'{self.avg_content_length:.1f}'
            },
            'sources': {
                'total_sources': self.total_sources,
                'coverage': self.sources_coverage
            },
            'distribution': {
                'daily': self.daily_distribution
            }
        }


def analyze_data_quality(db_path: Path, days: int = 7, 
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> DataQualityReport:
    """
    分析数据质量
    
    Args:
        db_path: 数据库路径
        days: 分析最近多少天（如果未指定日期范围）
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）
    
    Returns:
        DataQualityReport: 质量报告
    """
    logger.info(f"开始分析数据质量，数据库: {db_path}")
    
    if not db_path.exists():
        raise FileNotFoundError(f'数据库不存在: {db_path}')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 确定日期范围
    if start_date and end_date:
        date_start = start_date
        date_end = end_date
    else:
        date_start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        date_end = datetime.now().strftime('%Y-%m-%d')
    
    logger.info(f"分析日期范围: {date_start} 至 {date_end}")
    
    # 1. 总文章数
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE collection_date BETWEEN ? AND ?",
        (date_start, date_end)
    ).fetchone()['cnt']
    
    logger.debug(f"总文章数: {total}")
    
    # 2. 内容完整性
    with_content = conn.execute(
        """SELECT COUNT(*) as cnt FROM news_articles 
           WHERE collection_date BETWEEN ? AND ? 
           AND content IS NOT NULL AND content != ''""",
        (date_start, date_end)
    ).fetchone()['cnt']
    
    with_summary = conn.execute(
        """SELECT COUNT(*) as cnt FROM news_articles 
           WHERE collection_date BETWEEN ? AND ? 
           AND summary IS NOT NULL AND summary != ''""",
        (date_start, date_end)
    ).fetchone()['cnt']
    
    empty_title = conn.execute(
        """SELECT COUNT(*) as cnt FROM news_articles 
           WHERE collection_date BETWEEN ? AND ? 
           AND (title IS NULL OR title = '')""",
        (date_start, date_end)
    ).fetchone()['cnt']
    
    empty_link = conn.execute(
        """SELECT COUNT(*) as cnt FROM news_articles 
           WHERE collection_date BETWEEN ? AND ? 
           AND (link IS NULL OR link = '')""",
        (date_start, date_end)
    ).fetchone()['cnt']
    
    # 3. 重复检测（基于标题完全匹配）
    duplicates = conn.execute(
        """SELECT COUNT(*) - COUNT(DISTINCT title) as dup FROM news_articles 
           WHERE collection_date BETWEEN ? AND ?""",
        (date_start, date_end)
    ).fetchone()['dup']
    
    # 4. 平均长度统计
    avg_stats = conn.execute(
        """SELECT 
           AVG(LENGTH(title)) as avg_title,
           AVG(LENGTH(summary)) as avg_summary,
           AVG(LENGTH(content)) as avg_content
           FROM news_articles 
           WHERE collection_date BETWEEN ? AND ?""",
        (date_start, date_end)
    ).fetchone()
    
    avg_title = avg_stats['avg_title'] or 0
    avg_summary = avg_stats['avg_summary'] or 0
    avg_content = avg_stats['avg_content'] or 0
    
    # 5. 来源覆盖率
    sources = conn.execute(
        """SELECT s.source_name, COUNT(a.id) as cnt
           FROM news_articles a
           JOIN rss_sources s ON a.source_id = s.id
           WHERE a.collection_date BETWEEN ? AND ?
           GROUP BY s.source_name
           ORDER BY cnt DESC""",
        (date_start, date_end)
    ).fetchall()
    
    sources_coverage = {row['source_name']: row['cnt'] for row in sources}
    total_sources = len(sources_coverage)
    
    # 6. 每日分布
    daily_dist = conn.execute(
        """SELECT collection_date, COUNT(*) as cnt
           FROM news_articles
           WHERE collection_date BETWEEN ? AND ?
           GROUP BY collection_date
           ORDER BY collection_date""",
        (date_start, date_end)
    ).fetchall()
    
    daily_distribution = {row['collection_date']: row['cnt'] for row in daily_dist}
    
    conn.close()
    
    report = DataQualityReport(
        total_articles=total,
        date_range=(date_start, date_end),
        articles_with_content=with_content,
        articles_with_summary=with_summary,
        empty_title_count=empty_title,
        empty_link_count=empty_link,
        duplicate_count=duplicates,
        avg_title_length=avg_title,
        avg_summary_length=avg_summary,
        avg_content_length=avg_content,
        sources_coverage=sources_coverage,
        total_sources=total_sources,
        daily_distribution=daily_distribution
    )
    
    logger.info(f"数据质量分析完成，质量评分: {report.quality_score:.1f}")
    
    return report


def print_quality_report(report: DataQualityReport):
    """打印质量报告"""
    print_header("数据质量监控报告")
    
    # 基本信息
    print_info(f"📅 分析时间范围: {report.date_range[0]} 至 {report.date_range[1]}")
    print_info(f"📊 文章总数: {report.total_articles:,} 篇")
    print()
    
    # 质量评分
    score = report.quality_score
    if score >= 80:
        print_success(f"✨ 数据质量评分: {score:.1f}/100 (优秀)")
    elif score >= 60:
        print_warning(f"⚠️  数据质量评分: {score:.1f}/100 (良好)")
    else:
        print_error(f"❌ 数据质量评分: {score:.1f}/100 (需改进)")
    print()
    
    # 完整性统计
    stats = {
        '内容覆盖率': f'{report.content_coverage:.1f}%',
        '摘要覆盖率': f'{report.summary_coverage:.1f}%',
        '有内容文章': f'{report.articles_with_content:,} 篇',
        '有摘要文章': f'{report.articles_with_summary:,} 篇',
        '空标题': f'{report.empty_title_count:,} 篇',
        '空链接': f'{report.empty_link_count:,} 篇',
        '重复文章': f'{report.duplicate_count:,} 篇'
    }
    print_statistics(stats)
    print()
    
    # 平均长度
    print_info("📏 平均长度统计:")
    length_stats = {
        '平均标题长度': f'{report.avg_title_length:.0f} 字符',
        '平均摘要长度': f'{report.avg_summary_length:.0f} 字符',
        '平均内容长度': f'{report.avg_content_length:.0f} 字符'
    }
    print_statistics(length_stats)
    print()
    
    # 来源分布
    print_info(f"📰 来源分布 (共 {report.total_sources} 个来源):")
    print_table_header(['来源', '文章数', '占比'], [30, 15, 15])
    
    total = report.total_articles
    for source, count in sorted(report.sources_coverage.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        print_table_row([source, f'{count:,}', f'{percentage:.1f}%'], [30, 15, 15])
    print()
    
    # 每日分布
    if report.daily_distribution:
        print_info("📈 每日文章数分布:")
        print_table_header(['日期', '文章数'], [20, 15])
        for date, count in sorted(report.daily_distribution.items()):
            print_table_row([date, f'{count:,}'], [20, 15])


def export_report(report: DataQualityReport, output_path: Path):
    """导出报告为JSON"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    print_success(f"报告已导出到: {output_path}")
    logger.info(f"质量报告已导出: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据质量监控工具')
    parser.add_argument('--days', type=int, default=7, help='分析最近几天的数据（默认7天）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--output', type=str, help='导出JSON报告到指定路径')
    parser.add_argument('--db', type=str, help='数据库路径（默认使用配置文件）')
    args = parser.parse_args()
    
    # 获取数据库路径
    if args.db:
        db_path = Path(args.db)
    else:
        db_path = get_db_path()
    
    # 分析数据质量
    try:
        report = analyze_data_quality(
            db_path,
            days=args.days,
            start_date=args.start,
            end_date=args.end
        )
        
        # 打印报告
        print_quality_report(report)
        
        # 导出报告
        if args.output:
            output_path = Path(args.output)
            export_report(report, output_path)
        
    except Exception as e:
        logger.exception(f"数据质量分析失败: {e}")
        print_error(f"分析失败: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

