#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS财经新闻数据收集工具
抓取多个财经RSS源，保存原始数据到单一SQLite数据库供AI分析

用法示例：
  - 直接运行，收集今日数据并写入 `data/news_data.db`，同时在 `docs/archive/YYYY-MM/YYYY-MM-DD/` 下生成文件：
      python3 scripts/rss_finance_analyzer.py

输出内容：
  - docs/archive/YYYY-MM/YYYY-MM-DD/rss_data/*.txt   # 各源RSS条目摘要
  - docs/archive/YYYY-MM/YYYY-MM-DD/news_content/*   # 简要内容文件
  - docs/archive/YYYY-MM/YYYY-MM-DD/collected_data.json  # 汇总JSON
  - data/news_data.db                                 # 主SQLite数据库（推荐查询来源）

数据库关键表结构（参见 init_database）：
  - rss_sources(id, source_name, rss_url, created_at)
  - news_articles(id, collection_date, title, link[unique], source_id, published, summary, created_at, ...)
    · 常用查询日期字段：collection_date = YYYY-MM-DD
    · 常用连接：news_articles.source_id -> rss_sources.id

注意：
  - 抓取数量为每源最新若干条（见 fetch_rss_feed(limit)）。
  - 如果多次运行同一天，数据库会去重 `link`（INSERT OR IGNORE）。
  - 配合 `scripts/query_news_by_date.py` 可进行日期范围/关键词/来源的查询。
"""

import os
import sys
import time
import requests
import feedparser
from datetime import datetime
from pathlib import Path
import json
import re
from urllib.parse import urlparse
import sqlite3

# 添加RSS源列表
RSS_SOURCES = {
    "华尔街见闻": "https://dedicated.wallstreetcn.com/rss.xml",
    "36氪": "https://36kr.com/feed",
    "东方财富": "http://rss.eastmoney.com/rss_partener.xml",
    "百度股票焦点": "http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
    "中新网": "https://www.chinanews.com.cn/rss/finance.xml",
    "国家统计局-最新发布": "https://www.stats.gov.cn/sj/zxfb/rss.xml",
    "ZeroHedge华尔街新闻": "https://feeds.feedburner.com/zerohedge/feed",
    "ETF Trends": "https://www.etftrends.com/feed/",
    "Federal Reserve Board": "https://www.federalreserve.gov/feeds/press_all.xml",
    "BBC全球经济": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "FT中文网": "https://www.ftchinese.com/rss/feed",
    "Wall Street Journal": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "Thomson Reuters": "https://ir.thomsonreuters.com/rss/news-releases.xml"
}

def create_directory_structure(base_path):
    """创建目录结构"""
    subdirs = ['rss_data', 'news_content', 'analysis', 'reports']
    for subdir in subdirs:
        (base_path / subdir).mkdir(parents=True, exist_ok=True)
    print(f"✅ 目录结构创建完成: {base_path}")


def init_database(db_path):
    """初始化SQLite数据库并创建表结构"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建数据源表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rss_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT UNIQUE NOT NULL,
            rss_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建新闻文章表（添加日期字段，便于按日期查询）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_date TEXT NOT NULL,  -- 收集日期，格式: YYYY-MM-DD
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            source_id INTEGER NOT NULL,
            published TEXT,
            published_parsed TEXT,  -- JSON格式存储parsed时间
            summary TEXT,
            content TEXT,
            category TEXT,
            sentiment_score REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES rss_sources (id)
        )
    ''')
    
    # 创建新闻标签表（用于关键词、主题等）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            tag_type TEXT,  -- 'keyword', 'category', 'topic', etc.
            tag_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES news_articles (id) ON DELETE CASCADE
        )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_collection_date ON news_articles(collection_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_source ON news_articles(source_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_published ON news_articles(published)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_title ON news_articles(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_link ON news_articles(link)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_article ON news_tags(article_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_value ON news_tags(tag_value)')
    
    conn.commit()
    return conn


def fetch_rss_feed(url, source_name, limit=5):
    """获取RSS源内容"""
    try:
        print(f"🔍 正在抓取 {source_name} RSS 源...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        
        # 只取最新的limit篇文章
        entries = feed.entries[:limit] if len(feed.entries) > limit else feed.entries
        
        print(f"📊 从 {source_name} 获取到 {len(entries)} 篇文章")
        return entries
    except Exception as e:
        print(f"❌ 抓取 {source_name} 失败: {str(e)}")
        return None


def save_rss_data(entries, source_name, output_dir):
    """保存RSS数据到文件"""
    try:
        # 清理文件名中的特殊字符
        safe_name = re.sub(r'[^\w\s-]', '_', source_name)
        file_path = output_dir / f"{safe_name}.txt"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"RSS源: {source_name}\n")
            f.write(f"URL: {RSS_SOURCES[source_name]}\n")
            f.write(f"获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("-" * 50 + "\n\n")
            
            for i, entry in enumerate(entries, 1):
                f.write(f"文章 {i}:\n")
                f.write(f"标题: {entry.get('title', 'N/A')}\n")
                f.write(f"链接: {entry.get('link', 'N/A')}\n")
                f.write(f"发布时间: {entry.get('published', 'N/A')}\n")
                f.write(f"摘要: {entry.get('summary', 'N/A')}\n")
                f.write("-" * 30 + "\n\n")
        
        print(f"💾 {source_name} RSS数据已保存到: {file_path}")
        return True
    except Exception as e:
        print(f"❌ 保存 {source_name} RSS数据失败: {str(e)}")
        return False


def save_to_database(all_entries, collection_date, db_path):
    """保存所有收集的数据到单一SQLite数据库"""
    try:
        conn = init_database(db_path)
        cursor = conn.cursor()
        
        # 插入或获取数据源ID
        source_map = {}
        for source_name in RSS_SOURCES.keys():
            cursor.execute(
                "INSERT OR IGNORE INTO rss_sources (source_name, rss_url) VALUES (?, ?)",
                (source_name, RSS_SOURCES[source_name])
            )
            cursor.execute("SELECT id FROM rss_sources WHERE source_name = ?", (source_name,))
            source_id = cursor.fetchone()[0]
            source_map[source_name] = source_id
        
        # 插入文章数据
        inserted_count = 0
        for entry in all_entries:
            source_name = getattr(entry, 'source', 'Unknown')
            source_id = source_map.get(source_name, None)
            
            # 跳过没有有效源ID的条目
            if source_id is None:
                continue
                
            # 处理发布时间
            published = entry.get('published', 'N/A')
            published_parsed = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_parsed = json.dumps(list(entry.published_parsed))
            
            # 准备文章数据
            article_data = (
                collection_date,  # 添加收集日期字段
                entry.get('title', 'N/A'),
                entry.get('link', 'N/A'),
                source_id,
                published,
                published_parsed,
                entry.get('summary', 'N/A')[:5000],  # 限制摘要长度
                None,  # content 字段
                None   # category 字段
            )
            
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO news_articles 
                    (collection_date, title, link, source_id, published, published_parsed, summary, content, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', article_data)
                inserted_count += cursor.rowcount
            except sqlite3.IntegrityError:
                # 如果链接已存在，跳过
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ 数据库保存完成: {inserted_count} 篇文章已保存到数据库: {db_path}")
        return True
    except Exception as e:
        print(f"❌ 保存到数据库失败: {str(e)}")
        return False


def export_to_json(all_entries, output_dir, total_sources, successful_sources, failed_sources):
    """导出数据到JSON文件（备用）"""
    try:
        data_file = output_dir / "collected_data.json"
        
        # 转换所有数据为可序列化的格式
        serialized_entries = []
        for entry in all_entries:
            serialized_entry = {
                'title': entry.get('title', 'N/A'),
                'link': entry.get('link', 'N/A'),
                'published': entry.get('published', 'N/A'),
                'summary': entry.get('summary', 'N/A'),
                'source': getattr(entry, 'source', 'Unknown')
            }
            # 添加 published_parsed if it exists
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                serialized_entry['published_parsed'] = list(entry.published_parsed)
            serialized_entries.append(serialized_entry)
        
        data = {
            'collection_date': datetime.now().strftime('%Y-%m-%d'),
            'total_sources': total_sources,
            'successful_sources': successful_sources,
            'failed_sources': failed_sources,
            'total_articles': len(serialized_entries),
            'articles': serialized_entries
        }
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ JSON数据已保存到: {data_file}")
        return True
    except Exception as e:
        print(f"❌ 保存JSON数据失败: {str(e)}")
        return False


def main():
    """主函数 - 仅收集数据并保存到单一SQLite数据库"""
    print("🚀 开始执行财经新闻数据收集任务...")
    
    # 获取当前日期并创建目录
    today = datetime.now().strftime('%Y-%m-%d')
    
    base_path = Path("docs/archive") / f"{today[:7]}" / today
    create_directory_structure(base_path)
    
    # 设置目录和使用单一数据库
    rss_data_dir = base_path / "rss_data"
    news_content_dir = base_path / "news_content"
    analysis_dir = base_path / "analysis"
    reports_dir = base_path / "reports"
    
    # 使用单一主数据库，存储在data目录
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)  # 创建data目录
    main_db_path = data_dir / "news_data.db"
    
    # 初始化结果统计
    successful_sources = 0
    failed_sources = []
    all_entries = []
    
    # 获取所有RSS源
    total_sources = len(RSS_SOURCES)
    
    for source_name, url in RSS_SOURCES.items():
        entries = fetch_rss_feed(url, source_name)
        
        if entries:
            # 为每个条目添加源信息
            for entry in entries:
                if not hasattr(entry, 'source'):
                    entry.source = source_name
            
            # 保存RSS数据
            if save_rss_data(entries, source_name, rss_data_dir):
                successful_sources += 1
                all_entries.extend(entries)
                
                # 保存到news_content目录（保存原文内容）
                for i, entry in enumerate(entries, 1):
                    try:
                        safe_name = re.sub(r'[^\w\s-]', '_', source_name)
                        content_file = news_content_dir / f"{safe_name}_{i}.txt"
                        
                        with open(content_file, 'w', encoding='utf-8') as f:
                            f.write(f"Title: {entry.get('title', 'N/A')}\n")
                            f.write(f"Link: {entry.get('link', 'N/A')}\n")
                            f.write(f"Source: {source_name}\n")
                            f.write(f"Published: {entry.get('published', 'N/A')}\n")
                            f.write(f"Summary: {entry.get('summary', 'N/A')}\n")
                            f.write("-" * 50 + "\n")
                            f.write(f"Full Content: {entry.get('summary', 'N/A')[:2000]}...\n")  # Truncate if too long
                        
                    except Exception as e:
                        print(f"❌ 保存 {source_name} 内容失败: {str(e)}")
            else:
                failed_sources.append(source_name)
        else:
            failed_sources.append(source_name)
    
    # 保存所有收集的数据到单一数据库
    save_to_database(all_entries, today, main_db_path)
    
    # 同时导出JSON作为备用（可选）
    export_to_json(all_entries, base_path, total_sources, successful_sources, failed_sources)
    
    print(f"✅ 数据收集完成: 成功处理 {successful_sources}/{total_sources} 个RSS源")
    print(f"📊 总共收集到 {len(all_entries)} 篇文章")
    
    if failed_sources:
        print(f"⚠️ 以下源抓取失败: {', '.join(failed_sources)}")

    print("\n💡 数据已保存到:")
    print(f"   - RSS数据: {rss_data_dir}")
    print(f"   - 新闻内容: {news_content_dir}")
    print(f"   - 主数据库: {main_db_path}")
    print(f"   - JSON备份: {base_path}/collected_data.json")


if __name__ == "__main__":
    main()