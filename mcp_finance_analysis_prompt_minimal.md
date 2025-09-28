# 财经新闻MCP分析任务

## 任务
MCP抓取财经RSS→分析热点→生成报告

## RSS源

### 💲 华尔街见闻
- 华尔街见闻: `https://dedicated.wallstreetcn.com/rss.xml`

### 💻 36氪
- 36氪: `https://36kr.com/feed`

### 🇨🇳 中国经济
- 东方财富: `http://rss.eastmoney.com/rss_partener.xml`
- 百度股票焦点: `http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0`
- 中新网: `https://www.chinanews.com.cn/rss/finance.xml`
- 国家统计局-最新发布: `https://www.stats.gov.cn/sj/zxfb/rss.xml`

### 🇺🇸 美国经济
- ZeroHedge华尔街新闻: `https://feeds.feedburner.com/zerohedge/feed`
- ETF Trends: `https://www.etftrends.com/feed/`
- Federal Reserve Board: `https://www.federalreserve.gov/feeds/press_all.xml`

### 🌍 世界经济
- BBC全球经济: `http://feeds.bbci.co.uk/news/business/rss.xml`
- FT中文网: `https://www.ftchinese.com/rss/feed`
- Wall Street Journal: `https://feeds.a.dj.com/rss/RSSWorldNews.xml`
- Investing.com: `https://www.investing.com/rss/news.rss`
- Thomson Reuters: `https://ir.thomsonreuters.com/rss/news-releases.xml`

## 分析要求
作为财经分析师，找出：
1. 近1天涨幅TOP3行业/主题
2. 近3天潜力TOP3行业/主题
3. 每个热点：催化剂/复盘/展望/相关股票
4. 股票推荐：每个热点推荐3-5只股票，提供推荐理由和风险评级
5. 文件管理：按当天日期创建文件夹（YYYY-MM-DD），包含子文件夹：rss_data/、news_content/、analysis/、reports/

## 输出格式
```markdown
# 📅 2025-XX-XX 财经分析

## 📊 概览
成功源: X/13 | 新闻: XX条

## 🔥 热点分析
### 涨幅TOP3
1. [行业] - 催化剂/复盘/展望/相关股票
2. [行业] - 催化剂/复盘/展望/相关股票
3. [行业] - 催化剂/复盘/展望/相关股票

### 潜力TOP3
1. [行业] - 催化剂/复盘/展望/相关股票
2. [行业] - 催化剂/复盘/展望/相关股票
3. [行业] - 催化剂/复盘/展望/相关股票

## 💰 股票推荐
### 涨幅热点股票
1. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议
2. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议
3. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议

### 潜力热点股票
1. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议
2. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议
3. [行业] - [股票代码] [股票名称] - 推荐理由 - 风险评级 - 投资建议

## 📝 专业摘要
[1500字内分析]

## 📰 新闻摘要
### 今日
- 华尔街见闻: [标题](链接)
- 36氪: [标题](链接)
- 中国经济: [标题](链接)
- 美国经济: [标题](链接)
- 世界经济: [标题](链接)
- 国际财经: [标题](链接)

### 昨日
[同上格式]

## 🎯 投资建议
- **短期机会**: [基于涨幅热点的短期投资建议]
- **中期机会**: [基于潜力热点的中期投资建议]
- **强烈推荐**: [列出3-5只强烈推荐的股票及理由]
- **谨慎推荐**: [列出3-5只谨慎推荐的股票及理由]
- **风险提示**: [市场风险/行业风险/个股风险]
- **重点关注**: [政策事件/数据发布/公司公告]

---
*生成: 2025-XX-XX | 源: 13个RSS*
```

## 执行要求
- 按当天日期创建文件夹归类（YYYY-MM-DD）
- 股票推荐和理由说明
- 文件保存到对应子文件夹

**开始执行。**
