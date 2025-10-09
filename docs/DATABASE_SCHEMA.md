# 数据库表结构文档

> 财经新闻数据收集系统 - SQLite 数据库设计文档
> 
> **数据库位置**: `/data/news_data.db`
> 
> **最后更新**: 2025-10-09

---

## 📋 目录

- [数据库概览](#数据库概览)
- [表结构详解](#表结构详解)
  - [rss_sources - RSS源表](#rss_sources---rss源表)
  - [news_articles - 新闻文章表](#news_articles---新闻文章表)
  - [news_tags - 新闻标签表](#news_tags---新闻标签表)
  - [news_articles_fts - 全文搜索表](#news_articles_fts---全文搜索表)
- [索引说明](#索引说明)
- [关系图](#关系图)
- [常用查询示例](#常用查询示例)
- [数据维护](#数据维护)

---

## 数据库概览

### 基本信息

| 项目 | 说明 |
|------|------|
| 数据库类型 | SQLite 3 |
| 字符编码 | UTF-8 |
| 主要用途 | 存储从多个RSS源采集的财经新闻数据 |
| 表数量 | 3个主表 + 1个虚拟表 |
| 索引数量 | 7个 |

### 数据统计（示例）

```sql
-- RSS源总数
SELECT COUNT(*) FROM rss_sources;        -- 25个源

-- 文章总数
SELECT COUNT(*) FROM news_articles;      -- 721篇文章

-- 标签总数  
SELECT COUNT(*) FROM news_tags;          -- 0个标签（待启用）
```

---

## 表结构详解

### `rss_sources` - RSS源表

存储所有RSS新闻源的基本信息。

#### 表结构

```sql
CREATE TABLE rss_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT UNIQUE NOT NULL,
    rss_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 字段说明

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | RSS源唯一标识 |
| `source_name` | TEXT | UNIQUE, NOT NULL | RSS源名称（如"华尔街见闻"） |
| `rss_url` | TEXT | NOT NULL | RSS订阅地址 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

#### 示例数据

```sql
INSERT INTO rss_sources (source_name, rss_url) VALUES 
('华尔街见闻', 'https://wallstreetcn.com/rss'),
('36氪', 'https://36kr.com/feed');
```

#### 注意事项

- `source_name` 必须唯一，用于关联新闻文章
- 添加新源时会自动分配ID
- 删除源不会级联删除关联的文章（需手动处理）

---

### `news_articles` - 新闻文章表

存储从各RSS源采集的新闻文章详细信息。

#### 表结构

```sql
CREATE TABLE news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_date TEXT NOT NULL,           -- 收集日期: YYYY-MM-DD
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,
    source_id INTEGER NOT NULL,
    published TEXT,
    published_parsed TEXT,                   -- JSON格式时间
    summary TEXT,
    content TEXT,
    category TEXT,
    sentiment_score REAL DEFAULT 0,          -- 情感分数（预留）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES rss_sources (id)
);
```

#### 字段说明

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | 文章唯一标识 |
| `collection_date` | TEXT | NOT NULL | 采集日期（格式：YYYY-MM-DD） |
| `title` | TEXT | NOT NULL | 文章标题 |
| `link` | TEXT | UNIQUE, NOT NULL | 文章链接（唯一性保证去重） |
| `source_id` | INTEGER | NOT NULL, FOREIGN KEY | 关联到RSS源ID |
| `published` | TEXT | NULL | 发布时间（原始格式） |
| `published_parsed` | TEXT | NULL | 解析后的时间（JSON格式） |
| `summary` | TEXT | NULL | 文章摘要/简介 |
| `content` | TEXT | NULL | 文章正文（可选抓取） |
| `category` | TEXT | NULL | 文章分类 |
| `sentiment_score` | REAL | DEFAULT 0 | 情感分析分数（-1到1，预留字段） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 入库时间 |

#### 外键关系

```sql
FOREIGN KEY (source_id) REFERENCES rss_sources(id)
```

#### 索引

```sql
CREATE INDEX idx_articles_collection_date ON news_articles(collection_date);
CREATE INDEX idx_articles_source ON news_articles(source_id);
CREATE INDEX idx_articles_published ON news_articles(published);
CREATE INDEX idx_articles_title ON news_articles(title);
CREATE INDEX idx_articles_link ON news_articles(link);
```

#### 示例数据

```sql
INSERT INTO news_articles (
    collection_date, title, link, source_id, 
    published, summary, content
) VALUES (
    '2025-10-09',
    'AI技术推动金融科技创新',
    'https://example.com/news/123',
    1,
    '2025-10-09 10:00:00',
    '人工智能正在改变金融行业...',
    '详细正文内容...'
);
```

#### 注意事项

- `link` 字段保证唯一性，避免重复采集
- `content` 字段可能为空（根据配置决定是否抓取正文）
- `sentiment_score` 为预留字段，当前默认为0
- 通过 `collection_date` 索引可快速查询特定日期的文章

---

### `news_tags` - 新闻标签表

存储文章的标签信息（关键词、分类、话题等）。

#### 表结构

```sql
CREATE TABLE news_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,
    tag_type TEXT,                           -- 'keyword', 'category', 'topic'等
    tag_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES news_articles (id) ON DELETE CASCADE
);
```

#### 字段说明

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, AUTO_INCREMENT | 标签唯一标识 |
| `article_id` | INTEGER | FOREIGN KEY | 关联到文章ID |
| `tag_type` | TEXT | NULL | 标签类型（keyword/category/topic等） |
| `tag_value` | TEXT | NULL | 标签值 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

#### 外键关系

```sql
FOREIGN KEY (article_id) REFERENCES news_articles(id) ON DELETE CASCADE
```

- 级联删除：删除文章时会自动删除关联的标签

#### 索引

```sql
CREATE INDEX idx_tags_article ON news_tags(article_id);
CREATE INDEX idx_tags_value ON news_tags(tag_value);
```

#### 标签类型说明

| 类型 | 说明 | 示例 |
|------|------|------|
| `keyword` | 关键词 | "人工智能", "美联储", "加息" |
| `category` | 分类 | "科技", "宏观经济", "股市" |
| `topic` | 话题 | "中美贸易", "能源危机" |
| `entity` | 实体 | "苹果公司", "特斯拉" |

#### 示例数据

```sql
INSERT INTO news_tags (article_id, tag_type, tag_value) VALUES
(1, 'keyword', '人工智能'),
(1, 'keyword', '金融科技'),
(1, 'category', '科技'),
(1, 'topic', 'AI应用');
```

#### 注意事项

- 当前版本暂未启用（表中无数据）
- 预留用于未来的AI文章分析和标签提取功能
- 支持一篇文章多个标签（一对多关系）

---

### `news_articles_fts` - 全文搜索表

基于SQLite FTS5的虚拟表，用于高效全文搜索。

#### 表结构

```sql
CREATE VIRTUAL TABLE news_articles_fts USING fts5(
    title, 
    summary, 
    content, 
    content='news_articles',    -- 关联主表
    content_rowid='id'          -- 关联主表ID
);
```

#### 字段说明

| 字段名 | 说明 |
|--------|------|
| `title` | 文章标题（可搜索） |
| `summary` | 文章摘要（可搜索） |
| `content` | 文章正文（可搜索） |

#### 使用示例

```sql
-- 全文搜索示例
SELECT a.id, a.title, a.published
FROM news_articles_fts fts
JOIN news_articles a ON fts.rowid = a.id
WHERE news_articles_fts MATCH '人工智能 OR AI'
ORDER BY a.published DESC
LIMIT 10;

-- 搜索特定字段
SELECT * FROM news_articles_fts 
WHERE title MATCH '美联储';

-- 短语搜索
SELECT * FROM news_articles_fts 
WHERE content MATCH '"利率上升"';
```

#### 注意事项

- 自动与 `news_articles` 表同步
- 支持中文分词（需配置tokenizer）
- 比LIKE查询快数倍到数十倍
- 占用额外存储空间

---

## 索引说明

### 索引列表

| 索引名 | 表 | 字段 | 用途 |
|--------|----|----|------|
| `idx_articles_collection_date` | news_articles | collection_date | 按日期查询文章 |
| `idx_articles_source` | news_articles | source_id | 按来源查询文章 |
| `idx_articles_published` | news_articles | published | 按发布时间排序 |
| `idx_articles_title` | news_articles | title | 标题搜索优化 |
| `idx_articles_link` | news_articles | link | 去重检查优化 |
| `idx_tags_article` | news_tags | article_id | 查询文章标签 |
| `idx_tags_value` | news_tags | tag_value | 按标签查询文章 |

### 索引优化建议

- 定期使用 `VACUUM` 整理数据库碎片
- 更新统计信息：`ANALYZE;`
- 监控查询性能，根据实际使用添加索引

---

## 关系图

```
┌─────────────────┐
│  rss_sources    │
│─────────────────│
│ id (PK)         │───┐
│ source_name     │   │
│ rss_url         │   │
│ created_at      │   │
└─────────────────┘   │
                      │ 1:N
                      ↓
┌─────────────────────────┐
│  news_articles          │
│─────────────────────────│
│ id (PK)                 │───┐
│ collection_date         │   │
│ title                   │   │
│ link (UNIQUE)           │   │
│ source_id (FK)          │   │
│ published               │   │
│ summary                 │   │
│ content                 │   │
│ ...                     │   │
└─────────────────────────┘   │
        │                     │
        │ 1:N                 │
        ↓                     │
┌─────────────────┐           │
│  news_tags      │           │
│─────────────────│           │
│ id (PK)         │           │
│ article_id (FK) │           │
│ tag_type        │           │
│ tag_value       │           │
└─────────────────┘           │
                              │
                              │ FTS5同步
                              ↓
                    ┌──────────────────────┐
                    │ news_articles_fts    │
                    │──────────────────────│
                    │ (虚拟表)              │
                    │ title, summary,      │
                    │ content              │
                    └──────────────────────┘
```

---

## 常用查询示例

### 1. 查询最新文章

```sql
SELECT 
    a.id,
    a.title,
    a.published,
    s.source_name
FROM news_articles a
JOIN rss_sources s ON a.source_id = s.id
ORDER BY a.published DESC
LIMIT 20;
```

### 2. 按日期统计文章数

```sql
SELECT 
    collection_date,
    COUNT(*) as article_count,
    COUNT(DISTINCT source_id) as source_count
FROM news_articles
GROUP BY collection_date
ORDER BY collection_date DESC;
```

### 3. 查询特定来源的文章

```sql
SELECT 
    a.title,
    a.published,
    a.summary
FROM news_articles a
JOIN rss_sources s ON a.source_id = s.id
WHERE s.source_name = '华尔街见闻'
ORDER BY a.published DESC
LIMIT 10;
```

### 4. 全文搜索关键词

```sql
SELECT 
    a.id,
    a.title,
    a.published,
    s.source_name,
    snippet(news_articles_fts, 2, '...', '...', '', 30) as excerpt
FROM news_articles_fts fts
JOIN news_articles a ON fts.rowid = a.id
JOIN rss_sources s ON a.source_id = s.id
WHERE news_articles_fts MATCH '人工智能'
ORDER BY rank
LIMIT 10;
```

### 5. 检测重复文章

```sql
SELECT 
    title,
    COUNT(*) as count
FROM news_articles
GROUP BY title
HAVING count > 1;
```

### 6. 按来源统计

```sql
SELECT 
    s.source_name,
    COUNT(a.id) as article_count,
    MIN(a.published) as first_article,
    MAX(a.published) as latest_article
FROM rss_sources s
LEFT JOIN news_articles a ON s.id = a.source_id
GROUP BY s.id, s.source_name
ORDER BY article_count DESC;
```

### 7. 查询有正文的文章占比

```sql
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN content IS NOT NULL AND content != '' THEN 1 ELSE 0 END) as with_content,
    ROUND(100.0 * SUM(CASE WHEN content IS NOT NULL AND content != '' THEN 1 ELSE 0 END) / COUNT(*), 2) as percentage
FROM news_articles;
```

---

## 数据维护

### 备份数据库

```bash
# 完整备份
sqlite3 data/news_data.db ".backup data/news_data_backup.db"

# 导出SQL
sqlite3 data/news_data.db .dump > data/news_data_backup.sql

# 压缩备份
tar -czf news_data_$(date +%Y%m%d).tar.gz data/news_data.db
```

### 数据库优化

```sql
-- 分析表统计信息
ANALYZE;

-- 清理碎片，回收空间
VACUUM;

-- 完整性检查
PRAGMA integrity_check;

-- 查看数据库大小
SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();
```

### 清理旧数据

```sql
-- 删除30天前的数据（谨慎操作）
DELETE FROM news_articles 
WHERE collection_date < date('now', '-30 day');

-- 清理孤立的标签
DELETE FROM news_tags 
WHERE article_id NOT IN (SELECT id FROM news_articles);
```

### 重建全文索引

```sql
-- 删除并重建FTS索引
DROP TABLE IF EXISTS news_articles_fts;

CREATE VIRTUAL TABLE news_articles_fts USING fts5(
    title, summary, content, 
    content='news_articles', 
    content_rowid='id'
);

-- 重新填充数据
INSERT INTO news_articles_fts(rowid, title, summary, content)
SELECT id, title, summary, content FROM news_articles;
```

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2025-09-28 | 初始版本，建立基础表结构 |
| 1.1 | 2025-10-09 | 添加索引优化，启用FTS5全文搜索 |

---

## 相关文档

- [项目README](../README.md)
- [部署文档](DEPLOYMENT.md)
- [RSS源配置](../config/rss.json)
- [数据质量监控脚本](../scripts/monitor_data_quality.py)

---

**维护者**: Financial Report Team  
**联系方式**: [项目Issues](https://github.com/your-repo/issues)

