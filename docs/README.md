# Financial Report 项目文档

> 最后更新：2026-05-06  
> 当前主链路：DeepSeek + 验证增强版 + 双模式输出 + 验收脚本

---

## 快速导航

- [快速开始](#快速开始)
- [当前推荐链路](#当前推荐链路)
- [核心脚本](#核心脚本)
- [质量控制](#质量控制)
- [验收机制](#验收机制)
- [部署与运维](#部署与运维)

---

## 快速开始

### 环境要求

- Python 3.10+
- SQLite 3
- DeepSeek API Key

### 安装

```bash
git clone https://github.com/your-username/Financial-report.git
cd Financial-report

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置

推荐使用环境变量：

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

也支持在 `config/config.yml` 中配置：

```yaml
api_keys:
  deepseek: "YOUR_KEY"
```

---

## 当前推荐链路

### 方式一：交互式入口

```bash
python3 scripts/interactive_runner.py
```

或：

```bash
./start.sh
```

### 方式二：显式脚本入口

1. 先抓新闻：

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

2. 再分析：

```bash
# 完整报告
python3 scripts/ai_analyze_deepseek_verified.py --date $(date +%Y-%m-%d) --mode markdown-report

# 判断卡片
python3 scripts/ai_analyze_deepseek_verified.py --date $(date +%Y-%m-%d) --mode judgment-cards
```

---

## 核心脚本

### 1. RSS 采集：`rss_finance_analyzer.py`

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

常用参数：

- `--fetch-content`：抓取正文
- `--deduplicate`：启用去重
- `--max-workers`：控制并发
- `--only-source`：限制来源

### 2. AI 分析主入口：`ai_analyze_deepseek_verified.py`

这是当前推荐的主分析脚本，支持两种输出模式。

#### 完整报告模式

```bash
python3 scripts/ai_analyze_deepseek_verified.py \
  --date 2026-05-06 \
  --mode markdown-report \
  --content-field summary
```

#### 判断卡片模式

```bash
python3 scripts/ai_analyze_deepseek_verified.py \
  --date 2026-05-06 \
  --mode judgment-cards \
  --max-theses 5
```

常用参数：

- `--mode markdown-report|judgment-cards`
- `--content-field summary|content|auto`
- `--min-score`
- `--max-retries`
- `--skip-verification`
- `--filter-source`
- `--filter-keyword`
- `--output`

### 3. 验收入口：`run_acceptance.py`

```bash
# 轻量验收
python3 scripts/run_acceptance.py --date 2026-05-06 --skip-live

# 全量验收
python3 scripts/run_acceptance.py --date 2026-05-06
```

输出：

```text
data/acceptance/YYYY-MM-DD/acceptance_report.json
```

---

## 质量控制

当前质量控制分四层：

### 1. 实时数据注入

- 股票：Yahoo Finance
- 黄金：Gold-API / Yahoo Finance
- 外汇：Frankfurter

如果三类行情全部失败，系统会自动降级，不再伪装成“有实时数据”。

### 2. 事实核查

系统会从报告中提取可验证断言，例如：

- 股价
- 涨跌幅
- 金价
- 汇率

再用实时数据做校验，并生成附加的核查报告。

### 3. 质量评分

`check_report_quality_v2()` 会从三个维度评分：

- 准确性：60 分
- 时效性：20 分
- 可靠性：20 分

通过标准默认是：

- 总分 `>= 80`
- `issues = []`
- 未检测到明显编造内容

### 4. 弱证据降级

判断卡片模式下，若证据不足：

- 不应强行输出高置信度结论
- 应优先降级为 `观察项`

---

## 产物与归档

分析结果默认保存到：

```text
docs/archive/YYYY-MM/YYYY-MM-DD/
```

主要产物包括：

- `collected_data.json`
- `reports/*.md`
- `metadata/*.json`

当前文件名会区分：

- 时段（morning / afternoon / evening / overnight）
- 模式（markdown-report / judgment-cards）
- 模型（deepseek）

这样同一时段连续跑两种模式时不会互相覆盖。

---

## 部署与运维

### 本地查看文档

```bash
mkdocs serve
```

### 构建文档

```bash
mkdocs build
```

### 数据库维护

```bash
python3 scripts/utils/db_maintenance.py --health-check
python3 scripts/utils/db_maintenance.py --optimize
python3 scripts/utils/db_maintenance.py --cleanup 90
```

---

## 说明

- 当前文档默认描述的是 **DeepSeek 主链路**。
- `scripts/archive/` 下的文件仅作为历史备份参考。
- 如果某份旧文档仍提到 Gemini 主入口、`ai_analyze.py` 或 `ai_analyze_verified.py`，应视为历史背景，而不是当前推荐用法。
