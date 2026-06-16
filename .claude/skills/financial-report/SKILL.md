---
name: financial-report
description: Run or summarize the Financial-report daily market analysis workflow. Use this when the user asks to run today's financial report, daily analysis, 财经分析, 日报, 分析任务, 提炼今天的报告, 总结今天的报告, or wants a CN/US market analysis summary. The workflow must check CN and US reports together, inspect same-day logs and acceptance results, and downgrade conclusions when verification/acceptance is weak.
---

# 财经日报分析

处理 Financial-report 仓库里的每日财经分析。根据用户意图分两类：

- **生成日报**：数据采集 → AI 分析（A股+美股并行） → acceptance/日志检查 → 提炼总结报告。
- **提炼已有日报**：不重跑流水线，直接按目标日期读取 CN/US 报告、日志和 acceptance，再输出中文业务摘要。

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

## 先判断任务类型

1. 如果用户说“跑日报”“生成报告”“执行分析任务”，走 **生成日报流程**。
2. 如果用户说“提炼今天的报告”“总结今天的报告”“看看今天报告写了啥”，走 **提炼已有日报流程**。
3. 如果用户没有说清是生成还是提炼，先按“提炼已有日报”检查当天产物；缺报告时再说明缺什么，并询问是否要运行生成流程。

不要把本地草稿、单份报告或质量评分当作最终结论。最终总结必须同时参考同日 CN/US 报告、日志和 acceptance。

## 日期和归档路径

如果用户没有指定日期，默认使用当前日期，格式：`YYYY-MM-DD`。涉及“今天/昨天”时，在回答中使用绝对日期，避免相对日期歧义。

常用变量：

```bash
DATE="YYYY-MM-DD"
DATE_MM="YYYY-MM"
REPORT_DIR="docs/archive/$DATE_MM/$DATE/reports"
LOG_FILE="logs/$DATE.log"
ACCEPTANCE_FILE="data/acceptance/$DATE/acceptance_summary.json"
```

报告通常有两份：

- CN 报告：`docs/archive/YYYY-MM/YYYY-MM-DD/reports/📅 YYYY-MM-DD 财经分析报告_morning_markdown-report-cn_deepseek.md`
- US 报告：`docs/archive/YYYY-MM/YYYY-MM-DD/reports/📅 YYYY-MM-DD 财经分析报告_morning_markdown-report-us_deepseek.md`

第一跳优先直达日期目录，不要先全仓库搜索历史归档：

```bash
ls -la "$REPORT_DIR"
```

## 生成日报流程

### 第一步：检查当天数据

先查询数据库确认当天是否已有数据：

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('data/news_data.db')
cursor = db.execute(\"SELECT COUNT(*) FROM news_articles WHERE collection_date = 'YYYY-MM-DD'\")
print(f'当天文章数: {cursor.fetchone()[0]}')
"
```

### 第二步：采集新闻数据（如需要）

如果当天没有数据，运行：

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

20/21 个 RSS 源会被抓取，通常可获得 60-100 篇文章。此步耗时约 1 分钟。

### 第三步：并行运行 AI 分析

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

### 第四步：等待完成并确认产物

两个后台任务完成后，系统会发送 `<task-notification>`。收到通知后检查输出文件确认成功：

```bash
ls -la docs/archive/YYYY-MM/YYYY-MM-DD/reports/
```

确认同日 CN / US 两份报告都存在。只生成出一份时，不要硬凑双市场总结；先说明缺失的一侧。

## 提炼已有日报流程

1. 确认 `REPORT_DIR` 存在，并确认同日 CN / US 两份报告是否都存在。
2. 读取两份报告的完整内容，重点看：
   - 总览/市场概况
   - 核心主题或重点标的
   - 风险
   - 后续验证点
   - evidence audit / quality gate / validation / stock scoring
3. 如有 `LOG_FILE`，检查当天抓取、生成和验证是否有异常。
4. 如有 `ACCEPTANCE_FILE`，读取 acceptance 结果，并以它约束最终结论强度。
5. 如果没有 acceptance 文件，明确说明“未找到 acceptance 结果”，只按报告正文和日志做低一档的观察性总结，不要给强交易建议。

## Acceptance 降级规则

`acceptance_summary.json` 是最终质量闸门，可能比报告正文里的 quality check 更保守。结论强度以 acceptance 为上限：

- `passed=false`、验证率低、cross-verification 弱、`actionable_count = 0`：把股票结论降级为“观察/验证框架”，不要写成买入清单。
- 报告写明 `no high-signal actionable names`、`continue watching`、`do not chase higher`、`不追高`、`观察`：总结必须保留这些边界。
- 只有当报告正文、日志和 acceptance 同时支持较高置信度时，才可以写“可行动”建议；仍需标注关键风险和验证条件。
- 不确定字段含义时先按原文描述，不要脑补计算口径或补造替代指标。

## 输出总结报告

根据两份报告、日志和 acceptance，生成一份精炼的中文每日总结。默认结构：

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
| Acceptance | passed=true/false；关键降级原因 |

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

如果用户只要“提炼”，可以压缩为：

1. 一句总览
2. A股
3. 美股
4. 风险
5. 接下来验证点

## 重要提醒

- CN/US 两个 AI 分析必须真正**并行**启动。不要先后启动，否则总耗时翻倍。
- 阅读报告时使用 Read 工具读取**完整文件**，不要只读片段，否则会遗漏关键信息。
- 总结必须从报告、日志或 acceptance 中**提取事实**，不要编造数据。每一条关键判断都要能找到出处。
- 不要只看报告正文里的“质量检查通过”就给强结论；acceptance 失败时必须主动降级。
- 如果某天的分析不需要抓取数据（已有数据），可以跳过第三步。
- 用中文撰写所有输出。
