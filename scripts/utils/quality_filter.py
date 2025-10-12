#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻质量筛选和排序模块

功能：
- 基于来源权重的质量评分
- 重要关键词检测和加权
- 垃圾内容识别和过滤
- 标题党检测
- 智能去重（基于相似度）
- 综合质量评分和排序
"""

import re
import sys
import yaml
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from pathlib import Path

# 添加scripts目录到路径（用于直接运行测试）
if __name__ == '__main__':
    scripts_path = Path(__file__).resolve().parents[1]
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

# 尝试相对导入，失败则使用绝对导入
try:
    from .logger import get_logger
    from .deduplication import deduplicate_items
except ImportError:
    from utils.logger import get_logger
    from utils.deduplication import deduplicate_items

logger = get_logger('quality_filter')

# 获取项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / 'config' / 'quality_filter_config.yml'


# ============================================================================
# 配置管理类
# ============================================================================

class QualityFilterConfig:
    """质量筛选配置管理类"""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化配置
        
        Args:
            config_path: 配置文件路径，None则使用默认路径
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"已加载质量筛选配置: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（备用）"""
        return {
            'quality_threshold': 2.5,
            'dedup_threshold': 0.85,
            'enable_dedup': True,
            'max_articles': 0,
            'source_weights': {'default': 1.0},
            'important_keywords': {},
            'spam_keywords': [],
            'low_quality_patterns': [],
            'scoring_weights': {
                'keyword_contribution': 0.3,
                'spam_penalty_per_keyword': 0.5,
                'spam_penalty_max': 3.0,
                'title_penalty_per_pattern': 0.5,
                'title_penalty_max': 2.0,
            },
            'content_length_scoring': {'summary': [], 'content': []},
            'timeliness_scoring': [],
            'advanced': {
                'enable_debug_log': False,
                'show_top_articles': True,
                'top_articles_count': 10,
                'dedup_priority_keys': ['content', 'summary', 'quality_score'],
                'use_fast_dedup': True,
            }
        }
    
    @property
    def quality_threshold(self) -> float:
        """质量阈值"""
        return self.config.get('quality_threshold', 2.5)
    
    @property
    def dedup_threshold(self) -> float:
        """去重相似度阈值"""
        return self.config.get('dedup_threshold', 0.85)
    
    @property
    def enable_dedup(self) -> bool:
        """是否启用去重"""
        return self.config.get('enable_dedup', True)
    
    @property
    def max_articles(self) -> int:
        """最大文章数"""
        return self.config.get('max_articles', 0)
    
    @property
    def source_weights(self) -> Dict[str, float]:
        """来源权重"""
        return self.config.get('source_weights', {})
    
    @property
    def important_keywords(self) -> Dict[str, float]:
        """重要关键词"""
        return self.config.get('important_keywords', {})
    
    @property
    def spam_keywords(self) -> List[str]:
        """垃圾关键词"""
        return self.config.get('spam_keywords', [])
    
    @property
    def low_quality_patterns(self) -> List[str]:
        """低质量标题模式"""
        return self.config.get('low_quality_patterns', [])
    
    @property
    def scoring_weights(self) -> Dict[str, float]:
        """评分权重"""
        return self.config.get('scoring_weights', {})
    
    @property
    def content_length_scoring(self) -> Dict[str, List[Dict]]:
        """内容长度评分规则"""
        return self.config.get('content_length_scoring', {})
    
    @property
    def timeliness_scoring(self) -> List[Dict]:
        """时效性评分规则"""
        return self.config.get('timeliness_scoring', [])
    
    @property
    def advanced(self) -> Dict[str, Any]:
        """高级选项"""
        return self.config.get('advanced', {})
    
    def get_source_weight(self, source_name: str) -> float:
        """获取来源权重"""
        return self.source_weights.get(source_name, self.source_weights.get('default', 1.0))


# 全局配置实例（延迟初始化）
_global_config: Optional[QualityFilterConfig] = None


def get_config(config_path: Optional[Path] = None) -> QualityFilterConfig:
    """
    获取全局配置实例
    
    Args:
        config_path: 配置文件路径，None则使用默认
    
    Returns:
        配置实例
    """
    global _global_config
    if _global_config is None or config_path is not None:
        _global_config = QualityFilterConfig(config_path)
    return _global_config


# ============================================================================
# 核心功能：质量评分
# ============================================================================

def calculate_quality_score(article: Dict[str, Any], config: Optional[QualityFilterConfig] = None) -> float:
    """
    计算单篇文章的质量得分
    
    Args:
        article: 文章数据字典，需包含以下字段：
            - source_name: 来源名称
            - title: 标题
            - summary: 摘要（可选）
            - content: 正文（可选）
            - published: 发布时间（可选）
        config: 配置对象，None则使用默认配置
    
    Returns:
        质量得分（0-10分）
    
    评分规则：
        - 基础分：来源权重（1-5分）
        - 内容长度：+0-2分
        - 重要关键词：+0-3分
        - 垃圾内容：-0-3分
        - 标题党：-0-2分
        - 时效性：+0-1分
    """
    if config is None:
        config = get_config()
    
    score = 0.0
    scoring_weights = config.scoring_weights
    
    # 1. 来源权重（1-5分）
    source_name = article.get('source_name', '')
    source_weight = config.get_source_weight(source_name)
    score += source_weight * scoring_weights.get('source_weight_multiplier', 1.0)
    
    # 2. 内容长度（质量指标，0-2分）
    content_score = 0.0
    summary = article.get('summary') or ''
    content = article.get('content') or ''
    
    # 使用配置中的内容长度评分规则
    length_rules = config.content_length_scoring
    for rule in length_rules.get('summary', []):
        if len(summary) > rule.get('threshold', 0):
            content_score += rule.get('score', 0)
    
    for rule in length_rules.get('content', []):
        if content and len(content) > rule.get('threshold', 0):
            content_score += rule.get('score', 0)
    
    content_score = min(content_score, scoring_weights.get('content_length_max_score', 2.0))
    score += content_score
    
    # 3. 重要关键词检测（0-3分）
    title = article.get('title', '')
    full_text = f"{title} {summary}"
    
    keyword_score = 0.0
    matched_keywords = []
    keyword_contribution = scoring_weights.get('keyword_contribution', 0.3)
    
    for keyword, weight in config.important_keywords.items():
        if keyword in full_text:
            keyword_score += weight * keyword_contribution
            matched_keywords.append(keyword)
    
    # 关键词得分上限
    keyword_max = scoring_weights.get('keyword_max_score', 3.0)
    keyword_score = min(keyword_score, keyword_max)
    score += keyword_score
    
    # 4. 垃圾内容检测（-0到-3分）
    spam_penalty = 0.0
    spam_found = []
    spam_penalty_per = scoring_weights.get('spam_penalty_per_keyword', 0.5)
    
    for spam_keyword in config.spam_keywords:
        if spam_keyword in full_text:
            spam_penalty += spam_penalty_per
            spam_found.append(spam_keyword)
    
    # 垃圾内容惩罚上限
    spam_max = scoring_weights.get('spam_penalty_max', 3.0)
    spam_penalty = min(spam_penalty, spam_max)
    score -= spam_penalty
    
    # 5. 标题党检测（-0到-2分）
    title_penalty = 0.0
    title_penalty_per = scoring_weights.get('title_penalty_per_pattern', 0.5)
    
    for pattern in config.low_quality_patterns:
        if re.search(pattern, title):
            title_penalty += title_penalty_per
    
    # 标题党惩罚上限
    title_max = scoring_weights.get('title_penalty_max', 2.0)
    title_penalty = min(title_penalty, title_max)
    score -= title_penalty
    
    # 6. 时效性加分（0-1分）
    published = article.get('published')
    timeliness_score = 0.0
    if published:
        try:
            # 尝试解析时间
            if isinstance(published, str):
                # 支持多种时间格式
                from dateutil import parser
                pub_time = parser.parse(published)
            else:
                pub_time = published
            
            now = datetime.now()
            hours_diff = (now - pub_time.replace(tzinfo=None)).total_seconds() / 3600
            
            # 使用配置中的时效性评分规则
            timeliness_rules = config.timeliness_scoring
            for rule in timeliness_rules:
                if hours_diff <= rule.get('hours', 0):
                    timeliness_score = rule.get('score', 0)
                    break
            
            timeliness_weight = scoring_weights.get('timeliness_weight', 1.0)
            score += timeliness_score * timeliness_weight
        except Exception:
            pass
    
    # 确保分数在合理范围内（0-10）
    score = max(0.0, min(score, 10.0))
    
    # 记录调试信息
    if config.advanced.get('enable_debug_log', False):
        if matched_keywords or spam_found or title_penalty > 0:
            logger.debug(
                f"质量评分: {score:.2f} | {source_name} | {title[:30]}...\n"
                f"  来源权重={source_weight:.1f}, 内容={content_score:.1f}, "
                f"关键词={keyword_score:.1f}, 垃圾=-{spam_penalty:.1f}, "
                f"标题党=-{title_penalty:.1f}, 时效={timeliness_score:.1f}"
            )
    
    return score


def annotate_articles_with_scores(articles: List[Dict[str, Any]], config: Optional[QualityFilterConfig] = None) -> List[Dict[str, Any]]:
    """
    为文章列表添加质量评分
    
    Args:
        articles: 文章列表
        config: 配置对象，None则使用默认配置
    
    Returns:
        添加了 'quality_score' 字段的文章列表
    """
    if not articles:
        return articles
    
    if config is None:
        config = get_config()
    
    logger.info(f"开始计算质量评分，共 {len(articles)} 篇文章")
    
    for article in articles:
        article['quality_score'] = calculate_quality_score(article, config)
    
    # 统计信息
    scores = [a['quality_score'] for a in articles]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0
    
    logger.info(
        f"评分统计: 平均={avg_score:.2f}, 最高={max_score:.2f}, 最低={min_score:.2f}"
    )
    
    return articles


# ============================================================================
# 核心功能：质量筛选和排序
# ============================================================================

def filter_and_rank_articles(
    articles: List[Dict[str, Any]],
    quality_threshold: Optional[float] = None,
    deduplicate: Optional[bool] = None,
    dedup_threshold: Optional[float] = None,
    max_articles: Optional[int] = None,
    config: Optional[QualityFilterConfig] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    质量筛选 + 智能去重 + 排序
    
    Args:
        articles: 原始文章列表
        quality_threshold: 质量阈值（None则使用配置文件）
        deduplicate: 是否执行去重（None则使用配置文件）
        dedup_threshold: 去重相似度阈值（None则使用配置文件）
        max_articles: 最多保留文章数（None则使用配置文件，0表示不限制）
        config: 配置对象（None则使用默认配置）
    
    Returns:
        (筛选后的文章列表, 统计信息)
    
    处理流程：
        1. 计算质量评分
        2. 过滤低质量文章
        3. 智能去重（可选）
        4. 按质量得分排序
        5. 截取指定数量（可选）
    """
    if not articles:
        return articles, {
            'original_count': 0,
            'after_quality_filter': 0,
            'after_dedup': 0,
            'final_count': 0,
            'removed_by_quality': 0,
            'removed_by_dedup': 0,
            'removed_by_limit': 0
        }
    
    # 加载配置
    if config is None:
        config = get_config()
    
    # 使用配置的默认值（如果参数未提供）
    if quality_threshold is None:
        quality_threshold = config.quality_threshold
    if deduplicate is None:
        deduplicate = config.enable_dedup
    if dedup_threshold is None:
        dedup_threshold = config.dedup_threshold
    if max_articles is None:
        max_articles = config.max_articles
    
    original_count = len(articles)
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 开始新闻质量筛选和排序")
    logger.info(f"{'='*70}")
    logger.info(f"原始文章数: {original_count}")
    
    # 1. 计算质量评分
    articles = annotate_articles_with_scores(articles, config)
    
    # 2. 过滤低质量文章
    logger.info(f"\n🔍 质量过滤: 阈值 >= {quality_threshold:.1f}")
    
    filtered_articles = [
        a for a in articles 
        if a.get('quality_score', 0) >= quality_threshold
    ]
    
    after_quality_filter = len(filtered_articles)
    removed_by_quality = original_count - after_quality_filter
    
    logger.info(f"  保留: {after_quality_filter} 篇")
    logger.info(f"  过滤: {removed_by_quality} 篇 (低质量)")
    
    if not filtered_articles:
        logger.warning("⚠️  所有文章都被质量过滤器过滤，请降低阈值")
        return [], {
            'original_count': original_count,
            'after_quality_filter': 0,
            'after_dedup': 0,
            'final_count': 0,
            'removed_by_quality': removed_by_quality,
            'removed_by_dedup': 0,
            'removed_by_limit': 0
        }
    
    # 3. 智能去重
    after_dedup = after_quality_filter
    removed_by_dedup = 0
    
    if deduplicate:
        logger.info(f"\n🔄 智能去重: 相似度阈值 >= {dedup_threshold:.2f}")
        
        # 从配置读取去重选项
        advanced_opts = config.advanced
        priority_keys = advanced_opts.get('dedup_priority_keys', ['content', 'summary', 'quality_score'])
        use_fast_mode = advanced_opts.get('use_fast_dedup', True)
        
        deduped_articles, dedup_stats = deduplicate_items(
            filtered_articles,
            key='title',
            threshold=dedup_threshold,
            priority_keys=priority_keys,
            use_fast_mode=use_fast_mode
        )
        
        filtered_articles = deduped_articles
        after_dedup = dedup_stats['after']
        removed_by_dedup = dedup_stats['removed']
        
        logger.info(f"  保留: {after_dedup} 篇")
        logger.info(f"  移除: {removed_by_dedup} 篇 (重复)")
    
    # 4. 按质量得分排序（降序）
    logger.info(f"\n📈 按质量得分排序...")
    filtered_articles.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
    
    # 5. 截取指定数量
    removed_by_limit = 0
    if max_articles > 0 and len(filtered_articles) > max_articles:
        removed_by_limit = len(filtered_articles) - max_articles
        logger.info(f"\n✂️  限制数量: 最多保留 {max_articles} 篇")
        logger.info(f"  移除: {removed_by_limit} 篇 (超出限制)")
        filtered_articles = filtered_articles[:max_articles]
    
    final_count = len(filtered_articles)
    
    # 统计信息
    stats = {
        'original_count': original_count,
        'after_quality_filter': after_quality_filter,
        'after_dedup': after_dedup,
        'final_count': final_count,
        'removed_by_quality': removed_by_quality,
        'removed_by_dedup': removed_by_dedup,
        'removed_by_limit': removed_by_limit,
        'retention_rate': f"{(final_count / original_count * 100):.1f}%",
    }
    
    # 打印摘要
    logger.info(f"\n{'='*70}")
    logger.info(f"✅ 筛选完成")
    logger.info(f"{'='*70}")
    logger.info(f"原始文章:     {original_count} 篇")
    logger.info(f"质量过滤后:   {after_quality_filter} 篇 (移除 {removed_by_quality})")
    logger.info(f"去重后:       {after_dedup} 篇 (移除 {removed_by_dedup})")
    logger.info(f"最终保留:     {final_count} 篇 (保留率 {stats['retention_rate']})")
    
    # 显示Top文章（使用配置）
    if filtered_articles and config.advanced.get('show_top_articles', True):
        top_count = config.advanced.get('top_articles_count', 10)
        logger.info(f"\n🏆 质量 Top {top_count}:")
        for i, article in enumerate(filtered_articles[:top_count], 1):
            source = article.get('source_name', 'Unknown')
            title = article.get('title', 'No Title')
            score = article.get('quality_score', 0)
            logger.info(f"  {i:2d}. [{score:.2f}] {source} | {title[:60]}...")
    
    logger.info(f"{'='*70}\n")
    
    return filtered_articles, stats


def quick_filter(
    articles: List[Dict[str, Any]],
    quality_threshold: Optional[float] = None,
    max_articles: Optional[int] = None,
    config: Optional[QualityFilterConfig] = None
) -> List[Dict[str, Any]]:
    """
    快速筛选（简化版，用于命令行快速调用）
    
    Args:
        articles: 文章列表
        quality_threshold: 质量阈值（None则使用配置）
        max_articles: 最多保留文章数（None则使用配置）
        config: 配置对象（None则使用默认配置）
    
    Returns:
        筛选后的文章列表
    """
    filtered, stats = filter_and_rank_articles(
        articles,
        quality_threshold=quality_threshold,
        deduplicate=True,
        dedup_threshold=None,  # 使用配置
        max_articles=max_articles,
        config=config
    )
    return filtered


# ============================================================================
# 辅助功能：质量报告
# ============================================================================

def generate_quality_report(articles: List[Dict[str, Any]]) -> str:
    """
    生成质量分析报告
    
    Args:
        articles: 文章列表（需已评分）
    
    Returns:
        Markdown格式的质量报告
    """
    if not articles:
        return "# 质量报告\n\n无文章数据"
    
    # 统计各来源的文章数和平均质量
    source_stats = {}
    for article in articles:
        source = article.get('source_name', 'Unknown')
        score = article.get('quality_score', 0)
        
        if source not in source_stats:
            source_stats[source] = {'count': 0, 'total_score': 0, 'articles': []}
        
        source_stats[source]['count'] += 1
        source_stats[source]['total_score'] += score
        source_stats[source]['articles'].append(article)
    
    # 计算平均分
    for source, data in source_stats.items():
        data['avg_score'] = data['total_score'] / data['count']
    
    # 生成报告
    report = "# 📊 新闻质量分析报告\n\n"
    
    report += "## 总体统计\n\n"
    report += f"- 文章总数: {len(articles)}\n"
    report += f"- 来源数: {len(source_stats)}\n"
    
    scores = [a.get('quality_score', 0) for a in articles]
    avg_score = sum(scores) / len(scores)
    report += f"- 平均质量: {avg_score:.2f}\n"
    report += f"- 质量范围: {min(scores):.2f} - {max(scores):.2f}\n\n"
    
    report += "## 各来源质量统计\n\n"
    report += "| 来源 | 文章数 | 平均质量 | 占比 |\n"
    report += "|------|--------|----------|------|\n"
    
    # 按平均质量排序
    sorted_sources = sorted(
        source_stats.items(),
        key=lambda x: x[1]['avg_score'],
        reverse=True
    )
    
    for source, data in sorted_sources:
        count = data['count']
        avg = data['avg_score']
        ratio = count / len(articles) * 100
        report += f"| {source} | {count} | {avg:.2f} | {ratio:.1f}% |\n"
    
    return report


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    # 修复模块导入问题
    import sys
    from pathlib import Path
    scripts_path = Path(__file__).resolve().parents[1]
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    
    print("=== 测试新闻质量筛选模块 ===\n")
    
    # 测试数据
    test_articles = [
        {
            'id': 1,
            'source_name': '华尔街见闻',
            'title': '美联储宣布加息50个基点，市场暴跌',
            'summary': '美联储在今日凌晨宣布加息50个基点，超出市场预期。' * 10,
            'content': '详细内容' * 100,
            'published': '2025-10-11 10:00:00',
            'link': 'http://example.com/1'
        },
        {
            'id': 2,
            'source_name': '36氪',
            'title': '震惊！！！这只股票要翻倍了！！！',
            'summary': '点击购买，限时优惠，包赚不赔',
            'content': None,
            'published': '2025-10-10 10:00:00',
            'link': 'http://example.com/2'
        },
        {
            'id': 3,
            'source_name': '国家统计局',
            'title': '2025年9月CPI同比上涨2.1%',
            'summary': '国家统计局今日发布数据...' * 20,
            'content': '详细统计数据' * 200,
            'published': '2025-10-11 09:00:00',
            'link': 'http://example.com/3'
        },
        {
            'id': 4,
            'source_name': 'FT中文网',
            'title': '人工智能芯片需求暴涨，英伟达财报超预期',
            'summary': 'AI芯片市场持续火热...' * 15,
            'content': '详细分析' * 150,
            'published': '2025-10-11 11:00:00',
            'link': 'http://example.com/4'
        },
        {
            'id': 5,
            'source_name': '东方财富',
            'title': '今日股市行情',
            'summary': '简短内容',
            'content': None,
            'published': '2025-10-11 12:00:00',
            'link': 'http://example.com/5'
        },
        {
            'id': 6,
            'source_name': '华尔街见闻',
            'title': '美联储加息50基点，股市大跌',  # 与第1条相似
            'summary': '美联储昨日宣布加息...' * 8,
            'content': '详细内容' * 80,
            'published': '2025-10-11 10:30:00',
            'link': 'http://example.com/6'
        },
    ]
    
    print(f"原始文章数: {len(test_articles)}\n")
    
    # 测试1: 质量评分
    print("=" * 70)
    print("测试1: 质量评分")
    print("=" * 70)
    scored_articles = annotate_articles_with_scores(test_articles)
    
    print("\n评分结果:")
    for article in scored_articles:
        print(f"  [{article['id']}] {article['quality_score']:.2f} | "
              f"{article['source_name']} | {article['title'][:40]}...")
    
    # 测试2: 质量筛选和排序
    print("\n" + "=" * 70)
    print("测试2: 质量筛选和排序")
    print("=" * 70)
    
    filtered, stats = filter_and_rank_articles(
        test_articles,
        quality_threshold=3.0,
        deduplicate=True,
        dedup_threshold=0.80,
        max_articles=5
    )
    
    print("\n筛选结果:")
    for i, article in enumerate(filtered, 1):
        print(f"  {i}. [{article['quality_score']:.2f}] "
              f"{article['source_name']} | {article['title'][:40]}...")
    
    # 测试3: 质量报告
    print("\n" + "=" * 70)
    print("测试3: 质量报告")
    print("=" * 70)
    report = generate_quality_report(scored_articles)
    print(report)
    
    print("\n✅ 测试完成")

