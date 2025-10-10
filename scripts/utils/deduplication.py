#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去重工具模块

提供智能去重功能，支持：
- 基于标题的相似度计算
- 模糊匹配去重
- 批量去重处理
- 保留信息最完整的版本
"""

import re
from difflib import SequenceMatcher
from typing import List, Tuple, Dict, Any, Set
from collections import defaultdict

from .logger import get_logger

logger = get_logger('deduplication')


def normalize_text(text: str) -> str:
    """
    文本规范化（用于相似度比较）
    
    Args:
        text: 原始文本
    
    Returns:
        规范化后的文本
    """
    if not text:
        return ''
    
    # 转小写
    text = text.lower()
    
    # 移除标点和特殊字符
    text = re.sub(r'[^\w\s]', '', text)
    
    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def calculate_similarity(text1: str, text2: str, normalize: bool = True) -> float:
    """
    计算两个文本的相似度（基于编辑距离）
    
    Args:
        text1: 文本1
        text2: 文本2
        normalize: 是否先规范化文本
    
    Returns:
        相似度（0-1之间）
    
    Example:
        >>> similarity = calculate_similarity("中国经济增长", "中国经济持续增长")
        >>> print(f"相似度: {similarity:.2%}")
    """
    if not text1 or not text2:
        return 0.0
    
    if normalize:
        text1 = normalize_text(text1)
        text2 = normalize_text(text2)
    
    return SequenceMatcher(None, text1, text2).ratio()


def find_similar_pairs(items: List[Dict[str, Any]], 
                       key: str = 'title',
                       threshold: float = 0.85,
                       use_normalize: bool = True) -> List[Tuple[int, int, float]]:
    """
    查找相似项对
    
    Args:
        items: 数据项列表
        key: 用于比较的字段名
        threshold: 相似度阈值
        use_normalize: 是否规范化文本
    
    Returns:
        相似项对列表 [(索引1, 索引2, 相似度), ...]
    
    Example:
        >>> articles = [
        ...     {'id': 1, 'title': '中国经济增长'},
        ...     {'id': 2, 'title': '中国经济持续增长'}
        ... ]
        >>> pairs = find_similar_pairs(articles, threshold=0.8)
    """
    if not items:
        return []
    
    similar_pairs = []
    n = len(items)
    
    logger.info(f"开始查找相似项，共 {n} 个项目，阈值={threshold}")
    
    # 两两比较
    for i in range(n):
        text1 = items[i].get(key, '')
        if not text1:
            continue
        
        for j in range(i + 1, n):
            text2 = items[j].get(key, '')
            if not text2:
                continue
            
            similarity = calculate_similarity(text1, text2, normalize=use_normalize)
            
            if similarity >= threshold:
                similar_pairs.append((i, j, similarity))
                logger.debug(f"发现相似项: [{i}] vs [{j}], 相似度={similarity:.2%}")
    
    logger.info(f"发现 {len(similar_pairs)} 对相似项")
    return similar_pairs


def find_duplicates_fast(items: List[Dict[str, Any]], 
                        key: str = 'title',
                        threshold: float = 0.85) -> List[Tuple[int, int, float]]:
    """
    快速查找重复项（基于首字符分组优化）
    
    Args:
        items: 数据项列表
        key: 用于比较的字段名
        threshold: 相似度阈值
    
    Returns:
        重复项对列表
    """
    if not items:
        return []
    
    # 按首字符分组（优化性能）
    groups = defaultdict(list)
    for i, item in enumerate(items):
        text = normalize_text(item.get(key, ''))
        if text:
            first_char = text[0] if text else ''
            groups[first_char].append((i, text))
    
    similar_pairs = []
    
    logger.info(f"使用快速模式查找重复，分为 {len(groups)} 组")
    
    # 仅在同组内比较
    for group_items in groups.values():
        if len(group_items) < 2:
            continue
        
        for i, (idx1, text1) in enumerate(group_items):
            for idx2, text2 in group_items[i + 1:]:
                similarity = SequenceMatcher(None, text1, text2).ratio()
                if similarity >= threshold:
                    similar_pairs.append((idx1, idx2, similarity))
    
    logger.info(f"快速模式发现 {len(similar_pairs)} 对相似项")
    return similar_pairs


def select_best_item(items: List[Dict[str, Any]], 
                    indices: List[int],
                    priority_keys: List[str] = ['content', 'summary', 'published']) -> int:
    """
    从重复项中选择最佳项
    
    Args:
        items: 数据项列表
        indices: 重复项索引列表
        priority_keys: 优先级字段（越靠前优先级越高）
    
    Returns:
        最佳项的索引
    
    Example:
        >>> articles = [...]
        >>> duplicates = [0, 1, 2]  # 重复项索引
        >>> best = select_best_item(articles, duplicates, priority_keys=['content', 'summary'])
    """
    if not indices:
        return -1
    
    if len(indices) == 1:
        return indices[0]
    
    # 计算每个项的得分
    scores = []
    for idx in indices:
        item = items[idx]
        score = 0
        
        # 根据优先级字段计算得分
        for i, key in enumerate(priority_keys):
            value = item.get(key, '')
            if value:
                # 优先级越高，权重越大
                weight = len(priority_keys) - i
                score += len(str(value)) * weight
        
        scores.append((idx, score))
    
    # 返回得分最高的项
    best_idx = max(scores, key=lambda x: x[1])[0]
    logger.debug(f"从 {len(indices)} 个重复项中选择最佳项: {best_idx}")
    
    return best_idx


def deduplicate_items(items: List[Dict[str, Any]], 
                     key: str = 'title',
                     threshold: float = 0.85,
                     priority_keys: List[str] = ['content', 'summary'],
                     use_fast_mode: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    去重处理（保留最佳项）
    
    Args:
        items: 数据项列表
        key: 用于比较的字段名
        threshold: 相似度阈值
        priority_keys: 选择最佳项的优先级字段
        use_fast_mode: 是否使用快速模式
    
    Returns:
        (去重后的列表, 统计信息)
    
    Example:
        >>> articles = [...]
        >>> unique_articles, stats = deduplicate_items(
        ...     articles,
        ...     threshold=0.85,
        ...     priority_keys=['content', 'summary']
        ... )
        >>> print(f"去重前: {stats['before']}, 去重后: {stats['after']}")
    """
    if not items:
        return items, {'before': 0, 'after': 0, 'removed': 0}
    
    original_count = len(items)
    logger.info(f"开始去重处理，原始项目数: {original_count}")
    
    # 查找相似项
    if use_fast_mode:
        similar_pairs = find_duplicates_fast(items, key, threshold)
    else:
        similar_pairs = find_similar_pairs(items, key, threshold)
    
    if not similar_pairs:
        logger.info("未发现重复项")
        return items, {
            'before': original_count,
            'after': original_count,
            'removed': 0,
            'duplicate_groups': 0
        }
    
    # 构建重复组（使用并查集）
    parent = list(range(len(items)))
    
    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # 合并重复项
    for idx1, idx2, _ in similar_pairs:
        union(idx1, idx2)
    
    # 分组
    groups = defaultdict(list)
    for i in range(len(items)):
        root = find(i)
        groups[root].append(i)
    
    # 从每组中选择最佳项
    indices_to_keep = set()
    for group_indices in groups.values():
        best_idx = select_best_item(items, group_indices, priority_keys)
        indices_to_keep.add(best_idx)
    
    # 保留选中的项
    unique_items = [items[i] for i in sorted(indices_to_keep)]
    
    stats = {
        'before': original_count,
        'after': len(unique_items),
        'removed': original_count - len(unique_items),
        'duplicate_groups': len(groups),
        'similar_pairs': len(similar_pairs)
    }
    
    logger.info(f"去重完成: {stats['before']} -> {stats['after']}, 移除 {stats['removed']} 项, {stats['duplicate_groups']} 个重复组")
    
    return unique_items, stats


def mark_duplicates(items: List[Dict[str, Any]], 
                   key: str = 'title',
                   threshold: float = 0.85,
                   mark_field: str = 'is_duplicate') -> List[Dict[str, Any]]:
    """
    标记重复项（不删除，仅添加标记字段）
    
    Args:
        items: 数据项列表
        key: 用于比较的字段名
        threshold: 相似度阈值
        mark_field: 标记字段名
    
    Returns:
        添加了标记的数据项列表
    
    Example:
        >>> articles = [...]
        >>> marked = mark_duplicates(articles, threshold=0.85)
        >>> duplicates = [a for a in marked if a.get('is_duplicate')]
    """
    if not items:
        return items
    
    # 复制列表（避免修改原数据）
    marked_items = [item.copy() for item in items]
    
    # 初始化标记
    for item in marked_items:
        item[mark_field] = False
    
    # 查找相似项
    similar_pairs = find_duplicates_fast(marked_items, key, threshold)
    
    # 标记重复项（保留第一个，标记后续的）
    marked = set()
    for idx1, idx2, _ in similar_pairs:
        if idx1 not in marked:
            marked.add(idx2)
        else:
            marked.add(idx1)
            marked.add(idx2)
    
    # 应用标记
    for idx in marked:
        marked_items[idx][mark_field] = True
    
    duplicate_count = len(marked)
    logger.info(f"标记重复项: {duplicate_count}/{len(items)}")
    
    return marked_items


if __name__ == '__main__':
    # 测试去重功能
    print("=== 测试去重工具 ===\n")
    
    # 测试数据
    test_articles = [
        {'id': 1, 'title': '中国经济持续增长', 'content': '详细内容1...'},
        {'id': 2, 'title': '中国经济增长', 'content': '详细内容2，更长的内容...'},
        {'id': 3, 'title': '美国股市上涨', 'summary': '摘要内容'},
        {'id': 4, 'title': '美国股市大涨', 'content': '详细内容4...'},
        {'id': 5, 'title': '新能源汽车发展', 'content': '详细内容5...'},
    ]
    
    print(f"原始文章数: {len(test_articles)}\n")
    
    # 测试1: 查找相似项
    print("1. 查找相似项对:")
    pairs = find_similar_pairs(test_articles, threshold=0.75)
    for idx1, idx2, sim in pairs:
        print(f"  [{idx1}] vs [{idx2}]: {sim:.2%}")
        print(f"    - {test_articles[idx1]['title']}")
        print(f"    - {test_articles[idx2]['title']}")
    
    # 测试2: 去重处理
    print("\n2. 去重处理:")
    unique_articles, stats = deduplicate_items(
        test_articles,
        threshold=0.75,
        priority_keys=['content', 'summary']
    )
    print(f"  去重前: {stats['before']} 篇")
    print(f"  去重后: {stats['after']} 篇")
    print(f"  移除: {stats['removed']} 篇")
    print(f"  重复组: {stats['duplicate_groups']} 个")
    
    print("\n  保留的文章:")
    for article in unique_articles:
        print(f"    - [{article['id']}] {article['title']}")
    
    # 测试3: 标记重复项
    print("\n3. 标记重复项:")
    marked = mark_duplicates(test_articles, threshold=0.75)
    duplicates = [a for a in marked if a.get('is_duplicate')]
    print(f"  标记为重复: {len(duplicates)} 篇")
    for article in duplicates:
        print(f"    - [{article['id']}] {article['title']}")
    
    print("\n✓ 测试完成")

