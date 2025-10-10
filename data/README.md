# 数据目录说明

> 存储财经新闻采集系统的所有数据文件

---

## 📁 目录结构

```
data/
├── README.md              # 本文档
├── news_data.db          # SQLite数据库（主数据存储）
└── http_cache.json       # HTTP缓存文件（优化RSS抓取）
```

---

## 📄 文件说明

### `news_data.db`

**类型**: SQLite 3 数据库  
**大小**: ~8.8 MB（示例）  
**用途**: 存储所有采集的财经新闻数据

#### 包含数据

- **RSS源信息** (~25个源)
- **新闻文章** (~700+篇)
- **文章标签** (预留功能)
- **全文搜索索引** (FTS5)

#### 详细文档

完整的数据库表结构和使用说明请查看：[DATABASE_SCHEMA.md](../docs/DATABASE_SCHEMA.md)

#### 快速查询

```bash
# 查看数据库信息
sqlite3 data/news_data.db ".schema"

# 统计文章数
sqlite3 data/news_data.db "SELECT COUNT(*) FROM news_articles;"

# 查看最新10篇文章
sqlite3 data/news_data.db "SELECT title, published FROM news_articles ORDER BY published DESC LIMIT 10;"
```

#### 备份建议

```bash
# 每日备份
sqlite3 data/news_data.db ".backup backups/news_data_$(date +%Y%m%d).db"

# 导出SQL
sqlite3 data/news_data.db .dump > backups/news_data_$(date +%Y%m%d).sql
```

---

### `http_cache.json`

**类型**: JSON 文件  
**大小**: ~2.7 KB  
**用途**: HTTP条件请求缓存，优化RSS抓取性能

#### 文件结构

```json
{
  "RSS_URL": {
    "etag": "ETag值或null",
    "last_modified": "Last-Modified时间或null"
  }
}
```

#### 工作原理

1. **首次请求**：正常GET请求，服务器返回ETag和Last-Modified
2. **缓存记录**：保存ETag和Last-Modified到此文件
3. **后续请求**：
   - 发送If-None-Match（ETag）和If-Modified-Since头
   - 若内容未变，服务器返回304 Not Modified
   - 节省带宽和处理时间

#### 示例内容

```json
{
  "https://www.ftchinese.com/rss/feed": {
    "etag": "W/\"2a79-OdrFeRMlta/nVBrrf6Pt6RE0RtQ\"",
    "last_modified": null
  },
  "https://www.chinanews.com.cn/rss/finance.xml": {
    "etag": "\"68e79944-419d\"",
    "last_modified": "Thu, 09 Oct 2025 11:15:16 GMT"
  }
}
```

#### 性能优势

| 场景 | 无缓存 | 有缓存(304) | 节省 |
|------|--------|-------------|------|
| 响应时间 | 500-2000ms | 100-300ms | ~70% |
| 流量消耗 | 全量 | 几乎为0 | ~95% |
| 服务器负载 | 正常 | 极低 | ~90% |

#### 维护说明

- **自动维护**：每次RSS抓取后自动更新
- **手动清理**：删除文件会导致下次全量抓取（性能影响）
- **文件损坏**：程序会自动重建，不影响功能

```bash
# 清理缓存（强制全量抓取）
rm data/http_cache.json

# 查看缓存状态
cat data/http_cache.json | jq '.'

# 统计缓存条目
cat data/http_cache.json | jq 'length'
```

---

## 🔒 数据安全

### 权限设置

```bash
# 推荐权限
chmod 644 data/news_data.db      # 数据库可读写
chmod 644 data/http_cache.json   # 缓存可读写
chmod 755 data/                  # 目录可访问
```

### 备份策略

#### 自动备份（推荐）

在crontab中添加：

```bash
# 每天凌晨2点备份数据库
0 2 * * * /path/to/backup.sh
```

备份脚本示例：

```bash
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
sqlite3 /path/to/data/news_data.db ".backup $BACKUP_DIR/news_data_$DATE.db"

# 压缩
gzip $BACKUP_DIR/news_data_$DATE.db

# 删除30天前的备份
find $BACKUP_DIR -name "news_data_*.db.gz" -mtime +30 -delete
```

#### 云备份

```bash
# 上传到对象存储（示例：阿里云OSS）
ossutil cp data/news_data.db oss://your-bucket/backups/news_data_$(date +%Y%m%d).db

# 或使用rsync同步
rsync -avz data/ user@backup-server:/backups/financial-report/
```

---

## 📊 数据统计

### 查看数据增长

```sql
-- 按日期统计文章数
SELECT 
    collection_date,
    COUNT(*) as articles,
    COUNT(DISTINCT source_id) as sources
FROM news_articles
GROUP BY collection_date
ORDER BY collection_date DESC
LIMIT 7;
```

### 数据库大小监控

```bash
# 查看文件大小
ls -lh data/news_data.db

# SQLite内部统计
sqlite3 data/news_data.db "
SELECT 
    page_count * page_size / 1024 / 1024 as 'Size (MB)',
    page_count as 'Pages',
    page_size as 'Page Size'
FROM pragma_page_count(), pragma_page_size();
"
```

### 性能优化

```sql
-- 分析表
ANALYZE;

-- 清理碎片（回收空间）
VACUUM;

-- 查看索引使用情况
SELECT * FROM sqlite_stat1;
```

---

## 🚨 故障排除

### 数据库锁定

```bash
# 查看是否有进程占用
lsof data/news_data.db

# 强制解锁（谨慎！）
fuser -k data/news_data.db
```

### 数据库损坏

```bash
# 完整性检查
sqlite3 data/news_data.db "PRAGMA integrity_check;"

# 修复数据库
sqlite3 data/news_data.db ".recover" | sqlite3 data/news_data_recovered.db
```

### 缓存文件异常

```bash
# 验证JSON格式
cat data/http_cache.json | jq '.' > /dev/null && echo "OK" || echo "Invalid JSON"

# 重建缓存（直接删除即可）
rm data/http_cache.json
# 下次运行会自动创建
```

---

## 📈 容量规划

### 预估增长

假设每日采集：

| 项目 | 数量/大小 |
|------|-----------|
| RSS源 | 25个 |
| 每源文章数 | 5篇 |
| 每日总文章 | ~125篇 |
| 平均文章大小 | ~5KB（仅摘要）/ ~50KB（含正文） |

**存储预估**：

- **仅摘要模式**: 125篇 × 5KB × 365天 ≈ 228 MB/年
- **含正文模式**: 125篇 × 50KB × 365天 ≈ 2.28 GB/年

### 清理策略

```sql
-- 删除3个月前的数据
DELETE FROM news_articles 
WHERE collection_date < date('now', '-90 days');

-- 清理后执行VACUUM回收空间
VACUUM;
```

---

## 🔗 相关文档

- [数据库表结构文档](../docs/DATABASE_SCHEMA.md)
- [项目主README](../README.md)
- [RSS抓取脚本](../scripts/rss_finance_analyzer.py)
- [数据质量监控](../scripts/monitor_data_quality.py)

---

**最后更新**: 2025-10-09  
**维护者**: Financial Report Team

