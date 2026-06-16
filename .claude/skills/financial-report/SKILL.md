---
name: financial-report
description: Run the daily financial analysis pipeline — fetch RSS news, run DeepSeek AI analysis for CN (A-share) and US markets in parallel, then generate a consolidated Chinese-language summary report. Use when the user asks to run today's financial report, daily analysis, 财经分析, 日报, 分析任务, or wants a market analysis summary.
---

# 财经日报分析

运行每日财经分析全流程：数据采集 → AI 分析（A股+美股并行） → 提炼总结报告。

## 项目路径

```
/Users/qipeijun/code/githubProject/Financial-report
```

所有命令必须在该目录下执行，同时激活虚拟环境和 PYTHONPATH。

## 前置准备

```bash
cd /Users/qipeijun/code/githubProject/Financial-report
source venv/bin/activate
export PYTHONPATH="/Users/qipeijun/code/githubProject/Financial-report:$PYTHONPATH"
```

## 流程

### 第一步：确定分析日期

如果用户没有指定日期，默认使用当天日期。格式：`YYYY-MM-DD`。

### 第二步：检查当天数据

先查询数据库确认当天是否已有数据：

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('data/news_data.db')
cursor = db.execute(\"SELECT COUNT(*) FROM news_articles WHERE collection_date = 'YYYY-MM-DD'\")
print(f'当天文章数: {cursor.fetchone()[0]}')
"
```

### 第三步：采集新闻数据（如需要）

如果当天没有数据，运行：

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

20/21 个 RSS 源会被抓取，通常可获得 60-100 篇文章。此步耗时约 1 分钟。

### 第四步：并行运行 AI 分析

使用 `run_in_background: true` 同时启动两个市场的分析，这样它们并行执行而不会相互阻塞。

**参数说明：**
- `--date YYYY-MM-DD`：分析日期
- `--mode markdown-report`：生成完整报告
- `--content-field summary`：使用摘要字段（速度快，适合日常）
- `--stock-market CN|US`：目标市场
- `--verify`：启用事实核查和实时数据验证
- `--enable-stock-scoring`：附结构化股票推荐评分

**CN (A股) 分析：**
```bash
python3 scripts/ai_analyze_deepseek.py --date YYYY-MM-DD --mode markdown-report --content-field summary --stock-market CN --verify --enable-stock-scoring
```

**US (美股) 分析：**
```bash
python3 scripts/ai_analyze_deepseek.py --date YYYY-MM-DD --mode markdown-report --content-field summary --stock-market US --verify --enable-stock-scoring
```

**关键**：两个命令必须同时以 `run_in_background: true` 启动（在同一个 tool call batch 中），以便并行执行。每个耗时约 2-4 分钟（取决于 DeepSeek 模型响应速度）。

### 第五步：等待完成

两个后台任务完成后，系统会发送 `<task-notification>`。收到通知后检查输出文件确认成功：

```bash
ls -la docs/archive/YYYY-MM/YYYY-MM-DD/reports/
```

### 第六步：阅读报告并提炼总结

阅读两个报告的**完整内容**（使用 Read 工具）：

1. CN 报告：`docs/archive/YYYY-MM/YYYY-MM-DD/reports/📅 YYYY-MM-DD 财经分析报告_morning_markdown-report-cn_deepseek.md`
2. US 报告：`docs/archive/YYYY-MM/YYYY-MM-DD/reports/📅 YYYY-MM-DD 财经分析报告_morning_markdown-report-us_deepseek.md`

### 第七步：输出总结报告

根据两份报告的内容，生成一份精炼的中文每日总结。总结必须包含以下板块：

```markdown
# 📅 YYYY-MM-DD 财经分析日报 · 总结

## 一、运行概况
| 项目 | 详情 |
|------|------|
| 数据采集 | X/21 RSS源成功，X篇文章抓取，X篇入库 |
| CN (A股) 分析 | X篇文章，语料XXK字符，XXK tokens |
| US (美股) 分析 | X篇文章，语料XXK字符，XXK tokens |
| CN 质量评分 | 🟢/🔴 XX/100 (通过/未通过 — 说明) |
| US 质量评分 | 🟢/🔴 XX/100 (通过/未通过 — 说明) |

## 二、核心主题
用 1-2 段话概括今天最关键的市场驱动力和宏观叙事。

## 三、A股市场
- 市场状态（三大指数涨跌幅、关键点位）
- 高置信主题表格
- 关键宏观数据（如有）
- 股票建议（可行动 / 观察 / 警示）

## 四、美股市场
- 市场状态（三大指数涨跌幅、关键点位）
- 高置信主题表格
- 值得关注的信号
- 股票建议

## 五、跨市场风险矩阵
| 风险 | 严重度 | 影响范围 |
|------|--------|---------|

## 六、未来关键验证点
| 时间窗 | 验证事项 |

## 七、一句话总结

📁 完整报告路径
```

## 重要提醒

- 第四步两个分析必须真正**并行**启动。不要先后启动，否则总耗时翻倍。
- 阅读报告时使用 Read 工具读取**完整文件**，不要只读片段，否则会遗漏关键信息。
- 总结必须从报告中**提取事实**，不要编造数据。每一条关键判断都要能在原报告中找到出处。
- 如果某天的分析不需要抓取数据（已有数据），可以跳过第三步。
- 用中文撰写所有输出。
