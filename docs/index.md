# 财经新闻采集与 AI 分析系统

一个自动化的财经新闻分析工具，每天自动采集财经资讯并生成 AI 分析报告。

---

## 这个项目能做什么

- 自动采集 20+ 主流财经媒体的新闻资讯
- 使用 AI 模型分析市场趋势和投资机会
- 自动生成每日财经分析报告
- 支持历史数据查询和导出

---

## 如何使用

### 第一次使用

```bash
# 1. 下载项目
git clone https://github.com/yourusername/Financial-report.git
cd Financial-report

# 2. 一键启动
./start.sh
```

### 配置 API Key

编辑 `config/config.yml`，填入你的 API Key：

```yaml
api_keys:
  gemini: "YOUR_KEY"      # 在 https://aistudio.google.com 获取
  deepseek: "YOUR_KEY"    # 在 https://platform.deepseek.com 获取
```

至少配置一个即可。

### 日常使用

```bash
# 采集今日新闻
python scripts/rss_finance_analyzer.py --fetch-content

# 生成分析报告
python scripts/ai_analyze.py

# 查看报告
mkdocs serve
```

打开浏览器访问 `http://127.0.0.1:8000` 即可查看报告。

---

## 支持的数据源

华尔街见闻、36氪、东方财富、第一财经、国家统计局、中新网财经、新浪财经、网易财经等 20+ 个财经媒体。

---

## 主要功能

### 数据采集
- 自动抓取多个财经网站的 RSS 订阅
- 智能去重，避免重复内容
- 数据持久化存储

### AI 分析
- 支持 Gemini 和 DeepSeek 两种 AI 模型
- 自动识别市场热点和投资机会
- 生成结构化的分析报告

### 报告生成
- Markdown 格式的专业报告
- 自动按日期归档
- 支持在线浏览和搜索

### 数据查询
- 按日期、来源、关键词查询
- 支持导出为 JSON 或 CSV 格式
- 历史数据回溯分析

---

## 适用场景

- **个人投资者**：每天了解市场动态
- **财经研究**：快速获取行业资讯
- **学习交流**：了解 AI 在金融领域的应用

---

## 免责声明

本项目生成的分析报告仅供学习参考，不构成投资建议。投资有风险，请谨慎决策。

---

## 开源协议

MIT License - 可自由使用和修改

---

<div align="center">

**如果觉得有用，欢迎 Star ⭐**

*最后更新：2025-10-12*

</div>
