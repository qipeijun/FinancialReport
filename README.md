# 📊 财经新闻分析系统

一个基于 MCP (Model Context Protocol) 的智能财经新闻抓取与分析系统，能够自动抓取多个财经RSS源，进行专业分析，并提供股票推荐。

## 🌟 项目特色

- **🤖 智能分析**：基于AI的财经新闻分析和热点识别
- **📈 股票推荐**：为每个热点提供相关股票推荐和详细理由
- **📁 自动归档**：按日期自动创建文件夹，有序管理分析数据
- **🌐 多源抓取**：覆盖国内外9个主要财经RSS源
- **📊 专业报告**：生成适合专业投资者的分析报告

## 📋 功能特性

### 🔍 数据抓取
- 自动抓取9个财经RSS源的最新新闻
- 支持华尔街见闻、36氪、东方财富、BBC等权威媒体
- 智能解析新闻内容，提取关键信息

### 🧠 智能分析
- **热点识别**：自动识别近1天涨幅TOP3和潜力TOP3行业/主题
- **深度分析**：提供催化剂、复盘、展望三维分析
- **股票推荐**：为每个热点推荐3-5只相关股票
- **风险评估**：提供风险评级和投资建议

### 📁 文件管理
- 按日期自动创建文件夹（YYYY-MM-DD格式）
- 分类存储：RSS数据、新闻内容、分析结果、最终报告
- 便于历史数据查询和对比分析

## 🗂️ 项目结构

```
Financial-report/
├── mkdocs.yml                                  # MkDocs 配置文件
├── requirements.txt                            # Python 依赖
├── docs/                                       # 文档源文件目录
│   ├── index.md                               # 首页
│   ├── index.md                               # 首页文档
│   ├── DEPLOYMENT.md                          # 部署指南
│   ├── prompts/                               # 提示词配置
│   │   ├── mcp_finance_analysis_prompt.md     # 完整版提示词
│   │   ├── mcp_finance_analysis_prompt_optimized.md  # 优化版提示词
│   │   └── mcp_finance_analysis_prompt_minimal.md    # 精简版提示词
│   └── archive/                               # 分析报告存档
│       └── [YYYY-MM]/                         # 按月份组织
│           └── [YYYY-MM-DD_model]/            # 按日期和模型组织
│               ├── rss_data/                  # RSS原始数据
│               ├── news_content/              # 新闻正文内容
│               ├── analysis/                  # 分析结果
│               └── reports/                   # 最终报告
├── .github/workflows/                         # GitHub Actions
│   └── deploy-mkdocs.yml                     # 部署工作流
├── scripts/                                   # 辅助脚本
│   ├── generate_mkdocs_nav.py                # 导航生成
│   └── deploy.sh                             # 部署脚本
└── site/                                      # 构建输出（自动生成）
```

## 📡 数据源

### 💲 华尔街见闻
- **华尔街见闻**: `https://dedicated.wallstreetcn.com/rss.xml`

### 💻 36氪  
- **36氪**: `https://36kr.com/feed`

### 🇨🇳 中国经济
- **东方财富**: `http://rss.eastmoney.com/rss_partener.xml`
- **百度股票焦点**: `http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0`
- **中新网**: `https://www.chinanews.com.cn/rss/finance.xml`
- **国家统计局-最新发布**: `https://www.stats.gov.cn/sj/zxfb/rss.xml`

### 🇺🇸 美国经济
- **ZeroHedge华尔街新闻**: `https://feeds.feedburner.com/zerohedge/feed`
- **ETF Trends**: `https://www.etftrends.com/feed/`

### 🌍 世界经济
- **BBC全球经济**: `http://feeds.bbci.co.uk/news/business/rss.xml`

## 🚀 使用方法（脚本化）

### 1) 准备配置（必要）

项目提供可提交模板：`config/config.example.yml`

```bash
cp config/config.example.yml config/config.yml
# 编辑 config/config.yml，填入真实密钥
```

最小配置仅需两部分：

```yaml
api_keys:
  gemini: "YOUR_GEMINI_API_KEY"

notify:
  server_chan_keys:
    - "SCT_xxx_1"
    - "SCT_xxx_2"
```

注意：实际配置文件 `config/config.yml` 已加入 `.gitignore`，不会被提交。

### 2) 数据抓取（收集RSS 并入库）

```bash
python3 scripts/rss_finance_analyzer.py                # 仅抓取摘要
python3 scripts/rss_finance_analyzer.py --fetch-content  # 抓取正文写入数据库 content（推荐）
# 可选限制正文最大长度（默认0不限制，仅当>0时截断）
python3 scripts/rss_finance_analyzer.py --fetch-content --content-max-length 8000
```

输出：
- `data/news_data.db`（主库）
- `docs/archive/YYYY-MM/YYYY-MM-DD/rss_data/`、`news_content/`、`collected_data.json`

### 3) 数据查询（导出为表格/CSV/JSON）

```bash
# 当天数据（表格输出）
python3 scripts/query_news_by_date.py

# JSON 导出（包含正文 content，用于RAG/深度分析）
python3 scripts/query_news_by_date.py --format json --output /tmp/news_with_content.json --include-content

# CSV 导出（包含正文）
python3 scripts/query_news_by_date.py --format csv --output /tmp/news_with_content.csv --include-content
```

### 4) AI 分析（生成 Markdown 报告）

```bash
# 使用 config/config.yml 中的密钥，分析当天（默认使用专业版提示词 pro）
python3 scripts/ai_analyze.py

# 指定日期范围并导出 JSON（summary + 元数据）：
python3 scripts/ai_analyze.py --start 2025-09-28 --end 2025-09-29 --output-json /tmp/analysis.json

# 指定自定义配置路径（默认 config/config.yml）：
python3 scripts/ai_analyze.py --config /path/to/config.yml
```

说明：
- `ai_analyze.py` 优先使用数据库中的 `content`，回退 `summary`；默认通过 `config/config.yml` 读取密钥。
- 提示词使用 `task/financial_analysis_prompt_pro.md` 的专业版金融分析框架。

## 📊 报告内容

### 🔥 市场热点分析
- **涨幅热点TOP3**：近1天涨幅最高的行业/主题
- **潜力热点TOP3**：近3天涨幅较高且此前2周表现平淡的行业/主题

### 💰 股票推荐分析
- **推荐股票**：每个热点推荐3-5只相关股票
- **推荐理由**：基本面、技术面、政策面、资金面分析
- **风险评级**：低风险/中风险/高风险
- **投资建议**：买入/持有/观望/卖出

### 📝 AI专业分析摘要
- 1500字以内的专业财经热点摘要
- 逻辑清晰、重点突出
- 适合专业投资者阅读

### 📰 新闻摘要
- 按日期和来源分类的新闻列表
- 包含标题、链接、发布时间

### 🎯 投资建议与风险提示
- **投资机会**：短期、中期、长期投资建议
- **股票推荐总结**：强烈推荐、谨慎推荐、关注标的
- **风险提示**：市场风险、行业风险、个股风险
- **重点关注**：政策事件、数据发布、公司公告

## 🛠️ 技术特点

### MCP集成
- 基于Model Context Protocol构建
- 支持多种MCP工具和浏览器功能
- 智能错误处理和重试机制

### 智能分析
- 多维度热点识别算法
- 基于新闻内容的情绪分析
- 行业关联度分析

### 数据管理
- 自动文件分类和归档
- 历史数据查询和对比
- 结构化数据存储

## ⚠️ 注意事项

### 访问限制
- 部分RSS源可能存在访问限制
- 系统会自动处理403/401等错误
- 建议使用不同的User-Agent或请求头

### 数据准确性
- 分析结果仅供参考，不构成投资建议
- 请结合其他信息源进行投资决策
- 投资有风险，入市需谨慎

### 时效性
- 重点关注最新发布的新闻内容
- 建议每日执行分析任务
- 及时更新分析结果

## 📈 使用场景

### 个人投资者
- 每日市场热点跟踪
- 投资机会识别
- 风险预警提醒

### 专业分析师
- 市场研究辅助工具
- 行业趋势分析
- 投资组合优化

### 金融机构
- 市场情报收集
- 客户投资建议
- 风险管理系统

## 🔄 更新日志

### v1.0.0 (2025-01-15)
- ✨ 初始版本发布
- 🎯 支持9个财经RSS源抓取
- 📊 智能热点识别和分析
- 💰 股票推荐功能
- 📁 自动文件管理
- 📝 专业分析报告生成

## 📞 技术支持

如有问题或建议，请通过以下方式联系：

- 📧 邮箱：[您的邮箱]
- 💬 问题反馈：[GitHub Issues链接]
- 📖 文档：[项目文档链接]

## 📄 许可证

本项目采用 [MIT License](LICENSE) 许可证。

---

**免责声明**：本系统提供的分析结果和股票推荐仅供参考，不构成投资建议。投资有风险，入市需谨慎。请根据自身情况做出投资决策。

*最后更新：2025-01-15*
