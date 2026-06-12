# 财经新闻采集与 AI 分析系统

一个面向日常财经研究的自动化工具：抓取财经新闻、补充实时市场数据、生成 DeepSeek 分析报告，并对产出做事实核查与质量验收。

---

## 这个项目现在能做什么

- 自动采集 20+ 财经 RSS 源
- 为文章补充来源等级、内容质量、投资相关性标签
- 生成两类 AI 输出：
  - 完整财经分析报告
  - 高信号投资判断卡片
- 注入股票、黄金、外汇实时数据
- 自动做事实核查与质量评分
- 输出结构化验收报告

---

## 如何开始

### 1. 一键启动

```bash
./start.sh
```

### 2. 手动使用

```bash
# 抓取新闻
python3 scripts/rss_finance_analyzer.py --fetch-content

# 生成完整报告
python3 scripts/ai_analyze_deepseek.py --date $(date +%Y-%m-%d) --mode markdown-report

# 生成判断卡片
python3 scripts/ai_analyze_deepseek.py --date $(date +%Y-%m-%d) --mode judgment-cards
```

### 3. 查看报告

```bash
mkdocs serve
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

---

## API Key 配置

推荐使用环境变量：

```bash
export DEEPSEEK_API_KEY="YOUR_KEY"
```

也可以在 `config/config.yml` 中配置：

```yaml
api_keys:
  deepseek: "YOUR_KEY"
```

---

## 当前推荐模型与入口

- AI 主模型：DeepSeek
- 主分析脚本：`scripts/ai_analyze_deepseek.py`
- 交互式入口：`scripts/interactive_runner.py`
- 验收入口：`scripts/run_acceptance.py`

历史 Gemini 脚本和归档内容不再作为当前主入口。

---

## 主要功能

### 数据采集
- RSS 抓取
- 正文提取
- 去重
- SQLite 存储

### AI 分析
- `markdown-report`：完整报告
- `judgment-cards`：判断卡片
- 事实核查
- 质量评分

### 质量验收
- 自动化测试
- 编译检查
- 数据入库校验
- 产物结构校验
- 质量评分校验
- 降级场景专项校验

---

## 适用场景

- 个人投资研究
- 财经信息整理
- AI 报告生成与验收实验
- 新闻驱动的市场观察

---

## 免责声明

本项目输出仅供学习、研究与信息整理使用，不构成投资建议。
