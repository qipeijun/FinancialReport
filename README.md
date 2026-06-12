# Financial Report - AI驱动的财经分析系统

> 多源 RSS 采集 -> 实时数据注入 -> DeepSeek 分析 -> 事实核查 -> 质量验收 -> 文档归档

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![DeepSeek](https://img.shields.io/badge/AI-DeepSeek-orange.svg)](https://www.deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## 项目现状

当前主链路已经统一到 **DeepSeek + 验证增强版分析脚本**：

- 新闻抓取入口：`scripts/rss_finance_analyzer.py`
- AI 分析主入口：`scripts/ai_analyze_deepseek.py`
- 交互入口：`scripts/interactive_runner.py`
- 一键启动入口：`./start.sh`
- 验收入口：`scripts/run_acceptance.py`

目前对外推荐的输出模式有两种：

- `markdown-report`：完整财经分析报告
- `judgment-cards`：高信号投资判断卡片

两种模式都会落盘到 `docs/archive/YYYY-MM/YYYY-MM-DD/`，并且已经支持按模式区分文件名，避免互相覆盖。

---

## 核心能力

### 智能采集
- 聚合 20+ 财经 RSS 源
- 支持正文抓取、清洗、去重
- 入库时补充来源等级、内容质量、投资相关性等标签

### AI 分析
- 基于 DeepSeek 生成完整报告或判断卡片
- 支持 `summary / content / auto` 三种分析字段模式
- 支持事实核查、质量评分、自动重试

### 可信度控制
- 实时数据注入：股票 / 黄金 / 外汇
- 事实核查：提取并验证可验证断言
- 质量评分：准确性 / 时效性 / 可靠性三维评分
- 弱证据降级：证据不足时优先输出观察项而非强结论

### 验收与归档
- 自动化验收脚本覆盖链路、产物、质量和降级场景
- 报告与 metadata 自动归档
- MkDocs 可直接浏览历史报告

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/your-username/Financial-report.git
cd Financial-report

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 API Key

推荐使用环境变量：

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

也可以写入 `config/config.yml`：

```yaml
api_keys:
  deepseek: "YOUR_KEY"
```

### 3. 抓取新闻

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

### 4. 生成报告

```bash
# 完整报告
python3 scripts/ai_analyze_deepseek.py \
  --date $(date +%Y-%m-%d) \
  --mode markdown-report

# 判断卡片
python3 scripts/ai_analyze_deepseek.py \
  --date $(date +%Y-%m-%d) \
  --mode judgment-cards
```

### 5. 本地查看报告

```bash
mkdocs serve
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

---

## 常用命令

### 抓取新闻

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content

python3 scripts/rss_finance_analyzer.py \
  --fetch-content \
  --deduplicate \
  --max-workers 10
```

### 生成 AI 报告

```bash
# 标准完整报告
python3 scripts/ai_analyze_deepseek.py \
  --date 2026-05-06 \
  --mode markdown-report \
  --content-field summary

# 高质量完整报告
python3 scripts/ai_analyze_deepseek.py \
  --date 2026-05-06 \
  --mode markdown-report \
  --min-score 90 \
  --max-retries 5

# 高信号判断卡片
python3 scripts/ai_analyze_deepseek.py \
  --date 2026-05-06 \
  --mode judgment-cards \
  --max-theses 5
```

### 交互式使用

```bash
python3 scripts/interactive_runner.py
```

或：

```bash
./start.sh
```

### 执行验收

```bash
# 轻量验收：测试、编译、入口、数据库，并分别检查 CN/US 产物
python3 scripts/run_acceptance.py --date 2026-05-06 --all-markets --skip-live

# 单市场全量验收：包含真实分析产物、质量评分与降级场景
python3 scripts/run_acceptance.py --date 2026-05-06 --stock-market CN
```

验收结果会输出到：

```text
data/acceptance/YYYY-MM-DD/acceptance_report-cn.json
data/acceptance/YYYY-MM-DD/acceptance_report-us.json
data/acceptance/YYYY-MM-DD/acceptance_summary.json
```

---

## 产物结构

```text
docs/archive/YYYY-MM/YYYY-MM-DD/
├── collected_data.json
├── metadata/
│   ├── analysis_meta_afternoon_markdown-report-cn_deepseek.json
│   ├── afternoon_enhanced-context_markdown-report-cn_deepseek.json
│   └── afternoon_evidence-audit_markdown-report-cn_deepseek.json
└── reports/
    ├── 📅 YYYY-MM-DD 财经分析报告_afternoon_markdown-report-cn_deepseek.md
    └── 📅 YYYY-MM-DD 财经分析报告_afternoon_markdown-report-us_deepseek.md
```

---

## 项目结构

```text
Financial-report/
├── scripts/
│   ├── rss_finance_analyzer.py
│   ├── ai_analyze_deepseek.py
│   ├── ai_analyze_deepseek.py
│   ├── interactive_runner.py
│   ├── run_acceptance.py
│   └── utils/
├── docs/
├── data/
├── config/
└── task/
```

---

## 文档入口

- [项目文档总览](./docs/README.md)
- [站点首页](./docs/index.md)
- [数据库结构](./docs/DATABASE_SCHEMA.md)
- [部署指南](./docs/DEPLOYMENT.md)
- [脚本整合说明](./docs/SCRIPT_INTEGRATION_SUMMARY.md)

---

## 说明

- 当前主链路不再推荐 Gemini 相关旧脚本。
- `scripts/archive/` 下保留的是历史备份，不作为当前运行入口。
- 本项目生成的内容仅供研究、学习和信息整理使用，不构成投资建议。
