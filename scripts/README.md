# 财经新闻数据收集工具

## 概述

此工具用于从多个财经RSS源收集新闻数据，为AI分析提供原始数据。该系统专注于数据收集和预处理，不进行任何分析，分析工作留给AI完成。

## 功能

- 收集14个财经RSS源的数据
- 按日期创建归档目录
- 保存原始RSS数据
- 保存新闻内容摘要
- 生成单一SQLite数据库供AI分析（推荐）
- 生成JSON数据文件作为备份
- 所有数据集中存储于单一数据库，便于跨日期查询和分析
- 数据库文件存储在独立的 `data/` 目录中

## 目录结构

```
docs/archive/
└── YYYY-MM/
    └── YYYY-MM-DD/
        ├── rss_data/          # 原始RSS数据
        ├── news_content/      # 新闻内容摘要
        ├── analysis/          # AI分析结果
        ├── reports/           # 最终报告
        └── collected_data.json # 统一数据文件
```

## 数据源

- 华尔街见闻
- 36氪
- 东方财富
- 百度股票焦点
- 中新网
- 国家统计局-最新发布
- ZeroHedge华尔街新闻
- ETF Trends
- Federal Reserve Board
- BBC全球经济
- FT中文网
- Wall Street Journal
- Investing.com
- Thomson Reuters

## 使用方法

```bash
python3 rss_finance_analyzer.py
```

### 按日期范围查询工具

新增 `query_news_by_date.py` 脚本，可按日期范围从 `data/news_data.db` 查询新闻，默认查询当天。

```bash
# 查询当天
python3 scripts/query_news_by_date.py

# 指定某天
python3 scripts/query_news_by_date.py --date 2025-09-29

# 指定范围（含端点）
python3 scripts/query_news_by_date.py --start 2025-09-28 --end 2025-09-29

# 按来源过滤
python3 scripts/query_news_by_date.py --source 华尔街见闻 --limit 20

# 标题/摘要关键字搜索
python3 scripts/query_news_by_date.py --keyword 人工智能

# 输出为 JSON 到文件
python3 scripts/query_news_by_date.py --format json --output /tmp/news.json

# 输出为 CSV 到文件
python3 scripts/query_news_by_date.py --format csv --output /tmp/news.csv
```

参数说明：

- `--date`：指定单日（与 `--start=day --end=day` 等价）
- `--start`/`--end`：开始/结束日期（YYYY-MM-DD），默认均为当天
- `--source`：来源名称精确匹配（见 `rss_sources.source_name`）
- `--keyword`：在 `title` 与 `summary` 中模糊匹配
- `--format`：`table`（默认）/`json`/`csv`
- `--limit`：返回记录上限，0 表示不限制
- `--order`：排序方向（`asc`/`desc`），基于 `published` 优先、否则 `created_at`

## JSON数据格式

生成的 `collected_data.json` 包含以下字段：

- `collection_date`: 数据收集日期
- `total_sources`: 总RSS源数量
- `successful_sources`: 成功收集的源数量
- `failed_sources`: 失败的源列表
- `total_articles`: 总文章数
- `articles`: 文章列表，每篇文章包含标题、链接、发布时间、摘要和来源

## 数据库结构

单一SQLite数据库 (docs/news_data.db) 包含以下表：

- `rss_sources`: RSS数据源信息
  - id: 主键
  - source_name: 源名称
  - rss_url: RSS URL
- `news_articles`: 新闻文章
  - id: 主键
  - collection_date: 收集日期（格式: YYYY-MM-DD）
  - title: 标题
  - link: 链接（唯一）
  - source_id: 源ID（外键）
  - published: 发布时间
  - published_parsed: 解析后的时间（JSON格式）
  - summary: 摘要
  - content: 内容
  - category: 分类
  - sentiment_score: 情绪分数
- `news_tags`: 新闻标签
  - id: 主键
  - article_id: 文章ID（外键）
  - tag_type: 标签类型
  - tag_value: 标签值

数据库文件位置: `data/news_data.db`

## 工作流程

1. 运行数据收集脚本
2. 数据自动追加到单一数据库 `data/news_data.db`
3. AI工具读取 `data/news_data.db` 数据库（推荐）或 `collected_data.json`
4. AI进行财经分析
5. AI生成分析报告并保存到相应目录