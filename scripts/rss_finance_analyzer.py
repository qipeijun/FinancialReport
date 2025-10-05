#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS财经新闻数据收集工具
抓取多个财经RSS源，保存原始数据到单一SQLite数据库供AI分析

用法示例：
  - 直接运行，收集今日数据并写入 `data/news_data.db`，同时在 `docs/archive/YYYY-MM/YYYY-MM-DD/` 下生成文件：
      python3 scripts/rss_finance_analyzer.py

可选参数：
  - 抓取正文并入库（默认仅摘要）：
      python3 scripts/rss_finance_analyzer.py --fetch-content [--content-max-length N]
        · content-max-length 默认为 0 表示不限制，仅当 N>0 时才截断

输出内容：
  - docs/archive/YYYY-MM/YYYY-MM-DD/rss_data/*.txt   # 各源RSS条目摘要
  - docs/archive/YYYY-MM/YYYY-MM-DD/news_content/*   # 简要内容文件
  - docs/archive/YYYY-MM/YYYY-MM-DD/collected_data.json  # 汇总JSON
  - data/news_data.db                                 # 主SQLite数据库（推荐查询来源）

数据库关键表结构（参见 init_database）：
  - rss_sources(id, source_name, rss_url, created_at)
  - news_articles(id, collection_date, title, link[unique], source_id, published, summary, content, created_at, ...)
    · 常用查询日期字段：collection_date = YYYY-MM-DD
    · 常用连接：news_articles.source_id -> rss_sources.id

注意：
  - 抓取数量为每源最新若干条（见 fetch_rss_feed(limit)）。
  - 如果多次运行同一天，数据库会去重 `link`（INSERT OR IGNORE）。
  - 配合 `scripts/query_news_by_date.py` 可进行日期范围/关键词/来源的查询。
  - 若开启 `--fetch-content`，将尝试抓取文章正文写入 `content`，失败则回退为 `summary`。
"""

import os
import sys
import time
import argparse
import requests
import feedparser
from datetime import datetime
from pathlib import Path
import json
import re
from urllib.parse import urlparse
import html as html_lib
import sqlite3

from utils.print_utils import (
    print_header, print_success, print_warning, print_error, 
    print_info, print_progress, print_step, print_statistics
)
def load_http_cache(cache_path: Path) -> dict:
    """加载HTTP缓存（ETag/Last-Modified）。"""
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_http_cache(cache_path: Path, cache: dict):
    """保存HTTP缓存。"""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def normalize_link(raw_url: str) -> str:
    """规范化链接：去除常见追踪参数、统一大小写域名、去除片段与尾部斜杠。"""
    if not raw_url:
        return raw_url
    try:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

        parsed = urlparse(raw_url)
        # 归一化域名小写
        netloc = (parsed.netloc or '').lower()
        # 去除常见追踪参数
        tracked_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'spm', 'from', 'ref', 'ref_src'}
        q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in tracked_params]
        query = urlencode(q, doseq=True)
        # 去除片段与尾部斜杠
        path = parsed.path.rstrip('/')
        normalized = urlunparse((parsed.scheme, netloc, path, '', query, ''))
        return normalized
    except Exception:
        return raw_url


def normalize_title(title: str) -> str:
    """标题规范化：去除多余空白与常见包裹符号。"""
    if not title:
        return ''
    t = title.strip()
    # 合并空白
    t = re.sub(r'\s+', ' ', t)
    # 清理左右包裹符号
    t = re.sub(r'^[\-\s·【\[]+', '', t)
    t = re.sub(r'[\-\s·】\]]+$', '', t)
    return t


def enhance_text_quality(text: str) -> str:
    """增强文本清洗：移除模板尾注/营销用语等常见噪音。"""
    if not text:
        return ''
    cleaned = text
    patterns = [
        r'点击(阅读|查看).*?(原文|全文).*',
        r'本文(来源|转载).*',
        r'免责声明[:：].*',
        r'责任编辑[:：].*',
        r'微信公众.*',
        r'版权.*(所有|归原作者所有).*',
    ]
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    # 再次压缩空白
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def load_rss_sources():
    """从配置文件加载RSS源"""
    config_path = Path(__file__).parent / "config" / "rss.json"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 将分类结构扁平化为单一字典
        rss_sources = {}
        for category, sources in config.items():
            for source_name, url in sources.items():
                rss_sources[source_name] = url
        
        print_success(f"从配置文件加载了 {len(rss_sources)} 个RSS源")
        return rss_sources
        
    except FileNotFoundError:
        print_error(f"配置文件未找到: {config_path}")
        print_info("使用默认RSS源配置...")
        # 备用默认配置
        return {
            "华尔街见闻": "https://dedicated.wallstreetcn.com/rss.xml",
            "36氪": "https://36kr.com/feed",
            "东方财富": "http://rss.eastmoney.com/rss_partener.xml"
        }
    except Exception as e:
        print_error(f"读取配置文件失败: {str(e)}")
        return {}


def clean_html_to_text(raw_html: str) -> str:
    """将HTML内容粗略清洗为纯文本（无外部依赖）。"""
    if not raw_html:
        return ''
    # 去除脚本和样式
    raw_html = re.sub(r'<(script|style)[\s\S]*?>[\s\S]*?</\1>', ' ', raw_html, flags=re.IGNORECASE)
    # 去标签
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    # HTML实体反转义
    text = html_lib.unescape(text)
    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_article_content(url: str, timeout: int = 10) -> str:
    """抓取文章正文HTML并清洗为文本，失败返回空字符串。"""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; FinanceBot/1.0)'
        })
        resp.raise_for_status()

        # 正确处理编码问题
        if resp.encoding.lower() in ['utf-8', 'utf8']:
            content = resp.text
        else:
            # 尝试多种编码方式
            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                try:
                    content = resp.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # 如果所有编码都失败，使用默认编码
                content = resp.content.decode('utf-8', errors='ignore')

        return clean_html_to_text(content)
    except Exception:
        return ''

def create_directory_structure(base_path):
    """创建目录结构"""
    subdirs = ['rss_data', 'news_content', 'analysis', 'reports']
    for subdir in subdirs:
        (base_path / subdir).mkdir(parents=True, exist_ok=True)
    print_success(f"目录结构创建完成: {base_path}")


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

    # 创建 FTS5 虚表（若支持），用于全文检索。与主表内容联动，rowid 对应 news_articles.id
    try:
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS news_articles_fts USING fts5(
                title, summary, content, content='news_articles', content_rowid='id'
            )
        ''')
    except Exception:
        # 某些 SQLite 构建可能不包含 FTS5，忽略错误
        pass
    
    conn.commit()
    return conn


def fetch_rss_feed(url, source_name, limit=5, cache: dict | None = None):
    """获取RSS源内容（支持条件GET与重试）。"""
    try:
        print(f"🔍 正在抓取 {source_name} RSS 源...")
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; FinanceBot/1.0)'}
        # 条件 GET
        if cache is not None:
            entry = cache.get(url) or {}
            if entry.get('etag'):
                headers['If-None-Match'] = entry['etag']
            if entry.get('last_modified'):
                headers['If-Modified-Since'] = entry['last_modified']

        last_err = None
        for attempt in range(1, 4):
            try:
                response = requests.get(url, timeout=10, headers=headers)
                if response.status_code == 304:
                    print(f"🟡 未修改（304），使用上次数据占位：{source_name}")
                    return []
                response.raise_for_status()
                # 更新缓存
                if cache is not None:
                    cache[url] = {
                        'etag': response.headers.get('ETag'),
                        'last_modified': response.headers.get('Last-Modified')
                    }
                feed = feedparser.parse(response.content)
                entries = feed.entries[:limit] if len(feed.entries) > limit else feed.entries
                print(f"📊 从 {source_name} 获取到 {len(entries)} 篇文章")
                return entries
            except Exception as e:
                last_err = e
                wait = min(10, 2 ** (attempt - 1))
                print(f"⚠️ 第 {attempt} 次尝试失败，{wait}s 后重试：{e}")
                time.sleep(wait)
        print(f"❌ 抓取 {source_name} 失败: {str(last_err)}")
        return None
    except Exception as e:
        print(f"❌ 抓取 {source_name} 失败: {str(e)}")
        return None


def save_rss_data(entries, source_name, source_url, output_dir):
    """保存RSS数据到文件"""
    try:
        # 清理文件名中的特殊字符
        safe_name = re.sub(r'[^\w\s-]', '_', source_name)
        file_path = output_dir / f"{safe_name}.txt"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"RSS源: {source_name}\n")
            f.write(f"URL: {source_url}\n")
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


def save_to_database(all_entries, collection_date, db_path, rss_sources, fetch_content: bool = False, content_max_length: int = 5000):
    """保存所有收集的数据到单一SQLite数据库"""
    try:
        conn = init_database(db_path)
        cursor = conn.cursor()
        
        # 插入或获取数据源ID
        source_map = {}
        for source_name, source_url in rss_sources.items():
            cursor.execute(
                "INSERT OR IGNORE INTO rss_sources (source_name, rss_url) VALUES (?, ?)",
                (source_name, source_url)
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
            
            # 抓取正文（可选）
            content_text = ''
            if fetch_content:
                content_text = fetch_article_content(entry.get('link', ''))
                if not content_text:
                    # 回退为摘要
                    content_text = entry.get('summary', 'N/A') or ''
            # 截断长度（仅当显式给出正数上限时）
            if content_text and content_max_length and content_max_length > 0:
                content_text = content_text[:content_max_length]

            # 文本质量增强
            summary_text = enhance_text_quality(entry.get('summary', 'N/A') or '')
            if content_text:
                content_text = enhance_text_quality(content_text)

            # 规范化标题与链接
            norm_title = normalize_title(entry.get('title', 'N/A'))
            norm_link = normalize_link(entry.get('link', 'N/A'))

            # 准备文章数据
            article_data = (
                collection_date,  # 添加收集日期字段
                norm_title,
                norm_link,
                source_id,
                published,
                published_parsed,
                summary_text,
                (content_text if fetch_content else None),  # content 字段
                None   # category 字段
            )
            
            try:
                # 额外的基于标题的去重：同源、同日、同标题则跳过
                cursor.execute(
                    'SELECT 1 FROM news_articles WHERE collection_date = ? AND source_id = ? AND title = ? LIMIT 1',
                    (collection_date, source_id, norm_title)
                )
                if cursor.fetchone():
                    continue
                cursor.execute('''
                    INSERT OR IGNORE INTO news_articles 
                    (collection_date, title, link, source_id, published, published_parsed, summary, content, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', article_data)
                if cursor.rowcount:
                    inserted_count += cursor.rowcount
                    # 同步写入/更新 FTS（若虚表存在）
                    try:
                        # 获取刚插入的 id（link UNIQUE 保障 row 存在）
                        cursor.execute('SELECT id FROM news_articles WHERE link = ?', (norm_link,))
                        row = cursor.fetchone()
                        if row:
                            article_id = row[0]
                            cursor.execute(
                                'INSERT INTO news_articles_fts(rowid, title, summary, content) VALUES (?, ?, ?, ?)',
                                (article_id, norm_title, summary_text, (content_text if fetch_content else ''))
                            )
                    except Exception:
                        # 若环境不支持 FTS5 或虚表未创建，跳过
                        pass
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
    parser = argparse.ArgumentParser(description='RSS财经新闻数据收集工具')
    parser.add_argument('--fetch-content', action='store_true', help='抓取正文并写入数据库content字段')
    parser.add_argument('--content-max-length', type=int, default=0, help='正文最大存储长度，默认0表示不限制，仅当>0时截断')
    parser.add_argument('--only-source', type=str, help='仅抓取指定来源（逗号分隔，与配置文件中的名称一致）')
    args = parser.parse_args()
    print_header("财经新闻数据收集系统")
    
    # 获取脚本所在目录的父目录（项目根目录）
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # 获取当前日期并创建目录
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 确保在项目根目录下创建目录结构
    base_path = project_root / "docs" / "archive" / f"{today[:7]}" / today
    create_directory_structure(base_path)
    
    # 设置目录和使用单一数据库
    rss_data_dir = base_path / "rss_data"
    news_content_dir = base_path / "news_content"
    analysis_dir = base_path / "analysis"
    reports_dir = base_path / "reports"
    
    # 使用单一主数据库，存储在data目录
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)  # 创建data目录
    main_db_path = data_dir / "news_data.db"
    http_cache_path = data_dir / 'http_cache.json'
    http_cache = load_http_cache(http_cache_path)
    
    # 加载RSS源配置
    rss_sources = load_rss_sources()
    if not rss_sources:
        print_error("未能加载RSS源配置，程序退出")
        return
    
    # 初始化结果统计
    successful_sources = 0
    failed_sources = []
    all_entries = []
    
    # 获取所有RSS源
    total_sources = len(rss_sources)
    
    selected_sources = rss_sources
    if args.only_source:
        names = {s.strip() for s in args.only_source.split(',') if s.strip()}
        selected_sources = {k: v for k, v in rss_sources.items() if k in names}
        if not selected_sources:
            print_warning('未匹配到任何来源名称，退出。')
            return

    for source_name, url in selected_sources.items():
        entries = fetch_rss_feed(url, source_name, cache=http_cache)
        
        if entries:
            # 为每个条目添加源信息
            for entry in entries:
                if not hasattr(entry, 'source'):
                    entry.source = source_name
            
            # 保存RSS数据
            if save_rss_data(entries, source_name, url, rss_data_dir):
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
    save_to_database(
        all_entries,
        today,
        main_db_path,
        rss_sources,
        fetch_content=args.fetch_content,
        content_max_length=max(0, args.content_max_length)
    )
    
    # 写回HTTP缓存
    save_http_cache(http_cache_path, http_cache)

    # 同时导出JSON作为备用（可选）
    export_to_json(all_entries, base_path, total_sources, successful_sources, failed_sources)
    
    print_success(f"数据收集完成: 成功处理 {successful_sources}/{total_sources} 个RSS源")
    
    # 打印统计信息
    stats = {
        '成功源数': f"{successful_sources}/{total_sources}",
        '收集文章数': len(all_entries),
        '失败源数': len(failed_sources)
    }
    print_statistics(stats)
    
    if failed_sources:
        print_warning(f"以下源抓取失败: {', '.join(failed_sources)}")

    print_info("数据已保存到:")
    print(f"   - RSS数据: {rss_data_dir}")
    print(f"   - 新闻内容: {news_content_dir}")
    print(f"   - 主数据库: {main_db_path}")
    print(f"   - JSON备份: {base_path}/collected_data.json")


if __name__ == "__main__":
    main()