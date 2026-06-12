#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS财经新闻数据收集工具（优化版）

优化内容：
- ✅ 集成日志系统
- ✅ 配置管理集中化  
- ✅ 并发抓取RSS源
- ✅ 进度条显示
- ✅ 改进的错误处理
- ✅ 数据库批量操作
- ✅ 智能去重

用法示例：
  python3 scripts/rss_finance_analyzer_optimized.py --fetch-content
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import html as html_lib

try:
    from scripts.bootstrap import ensure_project_root
except ModuleNotFoundError:
    from bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

import feedparser
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup
from readability import Document

from scripts.infrastructure.logger import get_logger
from scripts.infrastructure.config_manager import get_config
from scripts.infrastructure.db_manager import DatabaseManager, retry_on_db_error
from scripts.application.deduplication import deduplicate_items
from scripts.domain.investment_signal import (
    classify_source_tier,
    detect_content_quality_status,
    is_original_source,
    score_investment_relevance,
)
from scripts.infrastructure.print_utils import (
    print_header, print_success, print_warning, print_error,
    print_info, print_statistics
)

logger = get_logger('rss_analyzer')


class RSSAnalyzer:
    """RSS抓取分析器"""
    
    def __init__(self, db_path: Path, http_cache_path: Path):
        self.db = DatabaseManager(db_path)
        self.http_cache_path = http_cache_path
        self.http_cache = self._load_http_cache()
    
    def _load_http_cache(self) -> dict:
        """加载HTTP缓存"""
        if self.http_cache_path.exists():
            try:
                with open(self.http_cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    logger.debug(f"加载HTTP缓存: {len(cache)} 条")
                    return cache
            except Exception as e:
                logger.warning(f"加载HTTP缓存失败: {e}")
                return {}
        return {}
    
    def _save_http_cache(self):
        """保存HTTP缓存"""
        try:
            import builtins
            self.http_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with builtins.open(self.http_cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.http_cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存HTTP缓存: {len(self.http_cache)} 条")
        except Exception as e:
            logger.error(f"保存HTTP缓存失败: {e}")
    
    @staticmethod
    def normalize_link(raw_url: str) -> str:
        """规范化链接"""
        if not raw_url:
            return raw_url
        try:
            parsed = urlparse(raw_url)
            netloc = (parsed.netloc or '').lower()
            tracked_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 
                             'utm_content', 'spm', 'from', 'ref', 'ref_src'}
            q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) 
                 if k not in tracked_params]
            query = urlencode(q, doseq=True)
            path = parsed.path.rstrip('/')
            normalized = urlunparse((parsed.scheme, netloc, path, '', query, ''))
            return normalized
        except Exception as e:
            logger.warning(f"链接规范化失败: {raw_url}, {e}")
            return raw_url
    
    @staticmethod
    def normalize_title(title: str) -> str:
        """标题规范化"""
        if not title:
            return ''
        t = title.strip()
        t = re.sub(r'\s+', ' ', t)
        t = re.sub(r'^[\-\s·【\[]+', '', t)
        t = re.sub(r'[\-\s·】\]]+$', '', t)
        return t
    
    @staticmethod
    def enhance_text_quality(text: str) -> str:
        """增强文本清洗"""
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
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    @staticmethod
    def clean_html_to_text(raw_html: str) -> str:
        """HTML转文本"""
        if not raw_html:
            return ''
        raw_html = re.sub(r'<(script|style)[\s\S]*?>[\s\S]*?</\1>', ' ', raw_html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        text = html_lib.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_with_custom_rules(self, soup: BeautifulSoup, url: str) -> str:
        """使用自定义规则提取正文（针对特定网站）"""
        domain = urlparse(url).netloc.lower()
        
        # 中新网财经
        if 'chinanews.com' in domain:
            # 优先使用 .left_zw（最精确的正文容器）
            content_div = soup.select_one('.left_zw')
            if content_div:
                # 移除不需要的元素
                for tag in content_div.select('script, style, .editor, .adEditor, .keywords, .share, .pictext, div.pictext'):
                    tag.decompose()
                
                # 只保留p标签的文本（正文通常在p标签中）
                paragraphs = content_div.find_all('p', recursive=True)
                text_parts = []
                for p in paragraphs:
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) > 10:  # 忽略太短的段落
                        text_parts.append(p_text)
                
                text = ' '.join(text_parts)
                if len(text) > 100:
                    return text
            
            # 备选方案
            for selector in ['.content_maincontent_content', '.content', '#content']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .editor, .keywords, .share'):
                        tag.decompose()
                    text = content_div.get_text(separator=' ', strip=True)
                    if len(text) > 100:
                        return text
        
        # 华尔街见闻（需要特殊处理，可能是动态加载）
        elif 'wallstreetcn.com' in domain:
            # 华尔街见闻的内容可能是React渲染的，直接提取可见文本
            # 尝试从summary或description中获取内容
            for selector in ['meta[property="og:description"]', 'meta[name="description"]']:
                meta = soup.select_one(selector)
                if meta and meta.get('content'):
                    text = meta['content'].strip()
                    if len(text) > 100:
                        return text
            
            # 尝试其他可能的容器
            for selector in ['.article-content', '[class*="content"]', 'article']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad, .advertisement, .related, aside'):
                        tag.decompose()
                    text = content_div.get_text(separator=' ', strip=True)
                    if len(text) > 100:
                        return text
        
        # 36氪
        elif '36kr.com' in domain:
            for selector in ['.articleDetailContent', 'article', '.common-width', '[class*="article"]']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad, aside'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all(['p', 'div'], recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # 东方财富
        elif 'eastmoney.com' in domain:
            for selector in ['#ContentBody', '.Body', 'article']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all('p', recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # 第一财经
        elif 'yicai.com' in domain:
            for selector in ['.m-txt', 'article', '.article-content']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all('p', recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # 新浪财经
        elif 'sina.com' in domain or 'finance.sina.com' in domain:
            for selector in ['#artibody', '.article', 'article']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad, .show_author'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all('p', recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # 百度百家号
        elif 'baijiahao.baidu.com' in domain:
            for selector in ['.article-content', '#article', '[class*="article"]']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all('p', recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # 虎嗅网
        elif 'huxiu.com' in domain:
            for selector in ['.article__content', '.article-content-wrap', 'article']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, .ad'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all(['p', 'div'], recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        # Investing.com
        elif 'investing.com' in domain:
            for selector in ['.article_WYSIWYG__O0uhW', 'article', '[class*="article"]']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style'):
                        tag.decompose()
                    
                    paragraphs = content_div.find_all('p', recursive=True)
                    text_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and len(p_text) > 10:
                            text_parts.append(p_text)
                    
                    text = ' '.join(text_parts)
                    if len(text) > 100:
                        return text
        
        return ''
    
    def fetch_article_content(self, url: str, timeout: int = 10) -> str:
        """抓取文章正文（智能提取）"""
        try:
            resp = requests.get(url, timeout=timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            resp.raise_for_status()
            
            # 处理编码
            if resp.encoding and resp.encoding.lower() not in ['utf-8', 'utf8']:
                for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
                    try:
                        html_content = resp.content.decode(encoding)
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                else:
                    html_content = resp.content.decode('utf-8', errors='ignore')
            else:
                html_content = resp.text
            
            # 策略1：使用自定义规则（针对特定网站）
            soup = BeautifulSoup(html_content, 'lxml')
            custom_text = self._extract_with_custom_rules(soup, url)
            if custom_text and len(custom_text) > 100:
                logger.debug(f"使用自定义规则提取正文: {url}")
                return custom_text
            
            # 策略2：使用 readability-lxml（通用智能提取）
            try:
                doc = Document(html_content)
                article_html = doc.summary()
                
                # 解析提取的HTML
                article_soup = BeautifulSoup(article_html, 'lxml')
                
                # 移除不需要的标签
                for tag in article_soup.select('script, style, iframe, nav, header, footer, aside'):
                    tag.decompose()
                
                # 提取文本
                text = article_soup.get_text(separator=' ', strip=True)
                
                # 清理多余空白
                text = re.sub(r'\s+', ' ', text).strip()
                
                if len(text) > 100:
                    logger.debug(f"使用Readability提取正文: {url}")
                    return text
            except Exception as e:
                logger.debug(f"Readability提取失败 {url}: {e}")
            
            # 策略3：通用规则（作为后备）
            # 尝试常见的正文容器
            for selector in ['article', '.article', '#article', '.content', '#content', 
                           '.post-content', '.entry-content', 'main']:
                content_div = soup.select_one(selector)
                if content_div:
                    for tag in content_div.select('script, style, nav, header, footer, aside'):
                        tag.decompose()
                    text = content_div.get_text(separator=' ', strip=True)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if len(text) > 100:
                        logger.debug(f"使用通用规则提取正文: {url}")
                        return text
            
            # 如果所有策略都失败，返回空
            logger.debug(f"无法提取有效正文: {url}")
            return ''
            
        except Exception as e:
            # 静默失败，正文抓取失败很常见（403/404等）
            logger.debug(f"正文抓取异常 {url}: {e}")
            return ''
    
    def fetch_rss_feed(self, url: str, source_name: str, limit: int = 5) -> List[Any]:
        """获取RSS源内容（支持缓存和重试）"""
        # 使用更真实的浏览器User-Agent（提高成功率）
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        # 条件GET（暂时禁用，避免304导致的"无数据"假象）
        # cache_entry = self.http_cache.get(url, {})
        # if cache_entry.get('etag'):
        #     headers['If-None-Match'] = cache_entry['etag']
        # if cache_entry.get('last_modified'):
        #     headers['If-Modified-Since'] = cache_entry['last_modified']
        
        last_err = None
        for attempt in range(1, 5):  # 增加到5次重试
            try:
                # 增加超时到30秒（GitHub Actions网络环境可能较慢）
                response = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
                if response.status_code == 304:
                    logger.debug(f"{source_name}: 无更新（304 Not Modified）")
                    return []
                response.raise_for_status()
                
                # 更新缓存
                self.http_cache[url] = {
                    'etag': response.headers.get('ETag'),
                    'last_modified': response.headers.get('Last-Modified')
                }
                
                feed = feedparser.parse(response.content)
                
                # 检查feed是否有效
                if not feed.entries:
                    logger.debug(f"{source_name}: RSS解析成功但无条目")
                    return []
                
                entries = feed.entries[:limit] if len(feed.entries) > limit else feed.entries
                logger.debug(f"{source_name}: 成功获取 {len(entries)} 条")
                return entries
                
            except requests.exceptions.Timeout as e:
                last_err = f"超时: {e}"
                logger.warning(f"{source_name} 第{attempt}次尝试超时")
            except requests.exceptions.HTTPError as e:
                last_err = f"HTTP错误: {e}"
                # 对于403错误（反爬虫），增加更长的等待时间
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
                    logger.warning(f"{source_name} 第{attempt}次遭遇403（反爬虫），等待后重试")
                    if attempt < 5:
                        wait_time = min(30, 5 * attempt)  # 5s, 10s, 15s, 20s
                        logger.debug(f"{source_name} 403错误，等待 {wait_time} 秒...")
                        time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"{source_name} 第{attempt}次HTTP错误: {str(e)[:60]}")
            except requests.exceptions.RequestException as e:
                last_err = f"请求失败: {e}"
                logger.warning(f"{source_name} 第{attempt}次尝试失败: {str(e)[:60]}")
            except Exception as e:
                last_err = f"未知错误: {e}"
                logger.warning(f"{source_name} 第{attempt}次尝试异常: {str(e)[:60]}")
            
            # 指数退避，增加等待时间
            if attempt < 5:
                wait_time = min(15, 3 ** attempt)  # 3秒, 9秒, 15秒, 15秒
                logger.debug(f"{source_name} 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        
        # 所有尝试失败，记录错误
        logger.error(f"{source_name} 抓取失败（重试5次）: {last_err}")
        return []
    
    def fetch_all_sources_parallel(self, rss_sources: dict, limit: int = 5, 
                                   max_workers: int = 5) -> List[Any]:
        """并发抓取所有RSS源"""
        all_entries = []
        
        # 记录开始时间
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_source = {
                executor.submit(self.fetch_rss_feed, meta['url'], name, limit): name
                for name, meta in rss_sources.items()
            }
            
            # 使用进度条
            success_count = 0
            fail_count = 0
            success_sources = []
            failed_sources = []
            
            with tqdm(
                total=len(rss_sources), 
                desc="📡 抓取RSS",
                bar_format='{desc}: {percentage:3.0f}%|{bar:25}| {n}/{total}',
                ncols=70,
                leave=False,
                dynamic_ncols=False
            ) as pbar:
                for future in as_completed(future_to_source):
                    source_name = future_to_source[future]
                    try:
                        # 获取结果，设置超时以避免永久阻塞
                        entries = future.result(timeout=120)  # 2分钟超时
                        if entries:
                            for entry in entries:
                                entry.source = source_name
                            all_entries.extend(entries)
                            success_count += 1
                            success_sources.append((source_name, len(entries)))
                            logger.info(f"✅ {source_name}: {len(entries)} 篇")
                        else:
                            fail_count += 1
                            failed_sources.append(source_name)
                            # 当返回空列表时，查看是否有异常信息
                            exc_info = future.exception()
                            if exc_info:
                                logger.warning(f"⚠️ {source_name}: 返回空结果，异常: {str(exc_info)[:80]}")
                            else:
                                logger.warning(f"⚠️ {source_name}: 返回空结果（可能是RSS源无内容或所有重试失败）")
                    except Exception as e:
                        fail_count += 1
                        failed_sources.append(source_name)
                        logger.error(f"❌ {source_name}: 并发异常 - {type(e).__name__}: {str(e)[:60]}", exc_info=True)
                    
                    pbar.update(1)
        
        # 计算耗时
        elapsed = time.time() - start_time
        
        # 打印摘要
        print(f"✓ 抓取完成: {success_count}/{len(rss_sources)} 个源，{len(all_entries)} 篇文章（耗时 {elapsed:.1f}s）")
        
        # 打印详细列表（用于GitHub Actions日志）
        if success_sources:
            print(f"\n  ✅ 成功的源 ({success_count}):")
            for source, count in success_sources:
                print(f"     • {source}: {count} 篇")
        
        if failed_sources:
            print(f"\n  ⚠️ 失败或无数据的源 ({fail_count}):")
            for source in failed_sources:
                print(f"     • {source}")
        
        return all_entries
    
    @retry_on_db_error(max_retries=3)
    def save_to_database(self, entries: List[Any], collection_date: str,
                        rss_sources: dict, fetch_content: bool = False,
                        content_max_length: int = 0) -> int:
        """批量保存到数据库"""
        if not entries:
            return 0
        
        # 初始化数据库表
        self._init_database()
        
        # 获取或创建来源映射
        source_map = self._get_source_map(rss_sources)
        
        # 准备文章数据
        article_data = []
        
        for entry in tqdm(
            entries, 
            desc="📝 处理数据", 
            ncols=70, 
            bar_format='{desc}: {percentage:3.0f}%|{bar:25}| {n}/{total}',
            leave=False,
            dynamic_ncols=False
        ):
            source_name = getattr(entry, 'source', 'Unknown')
            source_id = source_map.get(source_name)
            
            if source_id is None:
                continue

            source_meta = rss_sources.get(source_name, {})
            source_category = source_meta.get('category', '')
            source_tier = classify_source_tier(source_name, source_category)
            original_source = is_original_source(source_tier, source_name)
            
            # 处理发布时间
            published = entry.get('published', 'N/A')
            published_parsed = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_parsed = json.dumps(list(entry.published_parsed))
            
            # 抓取正文（可选）
            content_text = ''
            if fetch_content:
                content_text = self.fetch_article_content(entry.get('link', ''))
                if not content_text:
                    content_text = entry.get('summary', 'N/A') or ''
            
            # 截断长度
            if content_text and content_max_length > 0:
                content_text = content_text[:content_max_length]
            
            # 文本增强
            summary_text = self.enhance_text_quality(entry.get('summary', 'N/A') or '')
            if content_text:
                content_text = self.enhance_text_quality(content_text)

            content_quality_status = detect_content_quality_status(
                summary_text,
                content_text,
                fetch_content
            )
            
            # 规范化
            norm_title = self.normalize_title(entry.get('title', 'N/A'))
            norm_link = self.normalize_link(entry.get('link', 'N/A'))
            investment_relevance = score_investment_relevance({
                'title': norm_title,
                'summary': summary_text,
                'content': content_text if fetch_content else '',
                'source_tier': source_tier,
                'content_quality_status': content_quality_status,
            })
            
            article_data.append((
                collection_date,
                norm_title,
                norm_link,
                source_id,
                published,
                published_parsed,
                summary_text,
                content_text if fetch_content else None,
                None,  # category
                source_tier,
                content_quality_status,
                investment_relevance,
                original_source,
            ))
        
        # 批量插入
        sql = '''
            INSERT OR IGNORE INTO news_articles 
            (collection_date, title, link, source_id, published, published_parsed, summary, content, category,
             source_tier, content_quality_status, investment_relevance, is_original_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        inserted = self.db.execute_batch(sql, article_data, batch_size=100)
        print(f"✓ 保存完成: {inserted} 篇新文章入库")
        
        return inserted
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self.db.transaction() as conn:
            cursor = conn.cursor()
            
            # 创建数据源表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT UNIQUE NOT NULL,
                    rss_url TEXT NOT NULL,
                    source_category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建新闻文章表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT UNIQUE NOT NULL,
                    source_id INTEGER NOT NULL,
                    published TEXT,
                    published_parsed TEXT,
                    summary TEXT,
                    content TEXT,
                    category TEXT,
                    source_tier TEXT DEFAULT 'mainstream',
                    content_quality_status TEXT DEFAULT 'summary_only',
                    investment_relevance TEXT DEFAULT 'medium',
                    is_original_source INTEGER DEFAULT 0,
                    sentiment_score REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES rss_sources (id)
                )
            ''')

            self._ensure_column(cursor, 'rss_sources', 'source_category', 'TEXT')
            self._ensure_column(cursor, 'news_articles', 'source_tier', "TEXT DEFAULT 'mainstream'")
            self._ensure_column(cursor, 'news_articles', 'content_quality_status', "TEXT DEFAULT 'summary_only'")
            self._ensure_column(cursor, 'news_articles', 'investment_relevance', "TEXT DEFAULT 'medium'")
            self._ensure_column(cursor, 'news_articles', 'is_original_source', 'INTEGER DEFAULT 0')
            
            # 创建标签表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER,
                    tag_type TEXT,
                    tag_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES news_articles (id) ON DELETE CASCADE
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_collection_date ON news_articles(collection_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_source ON news_articles(source_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_published ON news_articles(published)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_title ON news_articles(title)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_link ON news_articles(link)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_source_tier ON news_articles(source_tier)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_relevance ON news_articles(investment_relevance)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_article ON news_tags(article_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_value ON news_tags(tag_value)')
            
            # FTS5全文检索
            try:
                cursor.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS news_articles_fts USING fts5(
                        title, summary, content, content='news_articles', content_rowid='id'
                    )
                ''')
            except Exception as e:
                logger.debug(f"FTS5不可用: {e}")
        
        logger.debug("数据库表结构初始化完成")

    @staticmethod
    def _ensure_column(cursor, table_name: str, column_name: str, column_def: str):
        columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {column[1] for column in columns}
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
    
    def _get_source_map(self, rss_sources: dict) -> Dict[str, int]:
        """获取或创建来源映射"""
        source_data = [
            (name, meta['url'], meta.get('category'))
            for name, meta in rss_sources.items()
        ]
        
        with self.db.transaction() as conn:
            cursor = conn.cursor()
            # 批量插入
            cursor.executemany(
                "INSERT OR IGNORE INTO rss_sources (source_name, rss_url, source_category) VALUES (?, ?, ?)",
                source_data
            )
            for name, meta in rss_sources.items():
                cursor.execute(
                    "UPDATE rss_sources SET rss_url = ?, source_category = ? WHERE source_name = ?",
                    (meta['url'], meta.get('category'), name)
                )
            
            # 获取映射
            rows = cursor.execute("SELECT source_name, id FROM rss_sources").fetchall()
            source_map = {row['source_name']: row['id'] for row in rows}
        
        logger.debug(f"来源映射: {len(source_map)} 个来源")
        return source_map
    
    def __del__(self):
        """析构时保存缓存"""
        self._save_http_cache()


def load_rss_sources(config_path: Path) -> dict:
    """从配置文件加载RSS源"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 扁平化分类结构
        rss_sources = {}
        for category, sources in config.items():
            for source_name, url in sources.items():
                rss_sources[source_name] = {
                    'url': url,
                    'category': category,
                }
        
        return rss_sources
        
    except FileNotFoundError:
        print_error(f"配置文件未找到: {config_path}")
        return {}
    except Exception as e:
        print_error(f"读取配置失败: {e}")
        return {}


def create_directory_structure(base_path: Path):
    """创建目录结构（仅创建必要的目录）"""
    # 只创建基础目录，其他目录在需要时按需创建
    base_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"目录结构创建: {base_path}")


def export_to_json(entries: List[Any], output_dir: Path, stats: dict):
    """导出数据到JSON（静默）"""
    try:
        data_file = output_dir / "collected_data.json"
        
        serialized_entries = []
        for entry in entries:
            serialized_entry = {
                'title': entry.get('title', 'N/A'),
                'link': entry.get('link', 'N/A'),
                'published': entry.get('published', 'N/A'),
                'summary': entry.get('summary', 'N/A'),
                'source': getattr(entry, 'source', 'Unknown')
            }
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                serialized_entry['published_parsed'] = list(entry.published_parsed)
            serialized_entries.append(serialized_entry)
        
        data = {
            'collection_date': datetime.now().strftime('%Y-%m-%d'),
            'total_sources': stats.get('total', 0),
            'successful_sources': stats.get('success', 0),
            'failed_sources': stats.get('failed', 0),
            'total_articles': len(serialized_entries),
            'articles': serialized_entries
        }
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"导出JSON失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='RSS财经新闻数据收集工具')
    parser.add_argument('--fetch-content', action='store_true', help='抓取正文')
    parser.add_argument('--content-max-length', type=int, default=0, help='正文最大长度')
    parser.add_argument('--only-source', type=str, help='仅抓取指定来源（逗号分隔）')
    parser.add_argument('--max-workers', type=int, default=5, help='最大并发数')
    parser.add_argument('--deduplicate', action='store_true', help='启用智能去重')
    args = parser.parse_args()
    
    print_header("财经新闻数据收集系统")
    
    # 获取配置
    config = get_config()
    project_root = config.project_root
    
    # 获取当前日期
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 创建目录结构
    base_path = project_root / "docs" / "archive" / f"{today[:7]}" / today
    create_directory_structure(base_path)
    
    # 数据库路径
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "news_data.db"
    http_cache_path = data_dir / 'http_cache.json'
    
    # 加载RSS源
    rss_config_path = config.get_rss_sources_config()
    rss_sources = load_rss_sources(rss_config_path)
    
    if not rss_sources:
        print_error("未能加载RSS源配置")
        return 1
    
    print(f"📚 已加载 {len(rss_sources)} 个RSS源")
    
    # 过滤来源
    if args.only_source:
        names = {s.strip() for s in args.only_source.split(',') if s.strip()}
        rss_sources = {k: v for k, v in rss_sources.items() if k in names}
        if not rss_sources:
            print_warning('未匹配到任何来源')
            return 1
        print(f"🔍 筛选后保留 {len(rss_sources)} 个源")
    
    print()
    
    # 创建分析器
    analyzer = RSSAnalyzer(db_path, http_cache_path)
    
    # 并发抓取
    all_entries = analyzer.fetch_all_sources_parallel(
        rss_sources,
        limit=5,
        max_workers=args.max_workers
    )
    
    if not all_entries:
        print_warning("未获取到任何文章")
        return 0
    
    print()
    
    # 智能去重（可选）
    if args.deduplicate:
        before_count = len(all_entries)
        
        # 转换为字典格式
        articles_dict = [
            {
                'title': e.get('title', ''),
                'link': e.get('link', ''),
                'summary': e.get('summary', ''),
                'source': getattr(e, 'source', ''),
                '_original': e
            }
            for e in all_entries
        ]
        
        unique_articles, dedup_stats = deduplicate_items(
            articles_dict,
            threshold=0.85,
            priority_keys=['summary']
        )
        
        # 恢复原始格式
        all_entries = [a['_original'] for a in unique_articles]
        
        print(f"✓ 去重完成: {before_count} → {len(all_entries)} 篇（移除 {dedup_stats['removed']} 篇）")
        print()
    
    # 保存到数据库
    inserted = analyzer.save_to_database(
        all_entries,
        today,
        rss_sources,
        fetch_content=args.fetch_content,
        content_max_length=max(0, args.content_max_length)
    )
    
    # 导出JSON
    export_to_json(all_entries, base_path, {
        'total': len(rss_sources),
        'success': len(rss_sources),
        'failed': 0
    })
    
    # 统计信息
    print()
    print("=" * 60)
    print(f"  📊 采集统计")
    print("=" * 60)
    print(f"  日期: {today}")
    print(f"  来源: {len(rss_sources)} 个RSS源")
    print(f"  获取: {len(all_entries)} 篇文章")
    print(f"  入库: {inserted} 篇新文章")
    print(f"  路径: {db_path}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
