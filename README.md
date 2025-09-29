# 财经新闻采集与 AI 分析

一个可落地的财经新闻数据管道：多源 RSS 采集 → SQLite 汇总存储 → 可查询导出 → 调用大模型生成专业分析报告。

## 特性
- 多源 RSS 采集统一入库到 `data/news_data.db`
- 支持抓取正文 `content`（默认不截断）与摘要 `summary`
- 按日期/来源/关键词查询并导出 CSV/JSON
- 一键调用大模型生成 Markdown 报告
- 交互式脚本简化上手

## 快速开始（优先按一键脚本）
方式A（一键脚本，推荐）
```bash
bash scripts/setup.sh
python3 scripts/interactive_runner.py
```

方式B（手动）
```bash
# Python ≥ 3.10
pip3 install -r requirements.txt
cp config/config.example.yml config/config.yml
# 编辑 config/config.yml，填写你的 Gemini API Key
python3 scripts/interactive_runner.py
```
- 若今天已抓取过数据，可直接选择“AI 分析”。
- 若未抓取，脚本会询问是否立即抓取（可选抓取正文），完成后再询问是否分析。

## 常用命令
- 采集（摘要/正文二选一）
```bash
python3 scripts/rss_finance_analyzer.py                  # 仅摘要
python3 scripts/rss_finance_analyzer.py --fetch-content  # 抓取正文写入 content（推荐）
# 仅抓取指定来源（与 scripts/config/rss.json 名称一致，逗号分隔）
python3 scripts/rss_finance_analyzer.py --only-source "华尔街见闻,36氪"
```
- 查询与导出
```bash
python3 scripts/query_news_by_date.py                               # 表格查看当天
python3 scripts/query_news_by_date.py --format json --output news.json --include-content
python3 scripts/query_news_by_date.py --format csv  --output news.csv  --include-content
# 全文检索（需 FTS5，匹配 title/summary/content）
python3 scripts/query_news_by_date.py --search "新能源 OR AI" --format json --output search.json
```
- AI 分析（生成 Markdown 报告）
```bash
python3 scripts/ai_analyze.py                                      # 分析当天
python3 scripts/ai_analyze.py --start 2025-09-28 --end 2025-09-29   # 指定范围
# 控量/过滤（降成本）
python3 scripts/ai_analyze.py --filter-source "华尔街见闻,36氪" --filter-keyword "新能源,AI" --max-articles 50 --max-chars 150000
```

## 结果位置
- 主数据库：`data/news_data.db`
- 当日归档：`docs/archive/YYYY-MM/YYYY-MM-DD/`
  - `rss_data/` 原始 RSS 文本
  - `news_content/` 内容文件
  - `reports/` 分析报告（Markdown）
  - `collected_data.json` 备份

## 配置说明
- 实际配置：`config/config.yml`（已加入 `.gitignore`）
- 模板示例：`config/config.example.yml`
```yaml
api_keys:
  gemini: "YOUR_GEMINI_API_KEY"

notify:
  server_chan_keys:
    - "SCT_xxx_1"
    - "SCT_xxx_2"
```

## 脚本清单
- `scripts/rss_finance_analyzer.py`
  - 多源 RSS 采集；支持 `--fetch-content` 与 `--content-max-length`（默认 0=不截断）
- `scripts/query_news_by_date.py`
  - 按日期/来源/关键词查询与导出；`--include-content` 在 CSV/JSON 中包含正文
- `scripts/ai_analyze.py`
  - 读取数据库（优先 `content` 回退 `summary`），固定提示词 `task/financial_analysis_prompt_pro.md`，生成 Markdown 报告
- `scripts/interactive_runner.py`
  - 交互式问答：检测 → 抓取 → 分析，一站式体验

## 目录结构（简版）
```
Financial-report/
├── config/
│   ├── config.example.yml
│   └── config.yml                 # 本地私密配置（git 忽略）
├── data/
│   └── news_data.db               # 主 SQLite 数据库
├── docs/
│   └── archive/YYYY-MM/YYYY-MM-DD/{rss_data,news_content,reports}
├── scripts/
│   ├── rss_finance_analyzer.py
│   ├── query_news_by_date.py
│   ├── ai_analyze.py
│   └── interactive_runner.py
└── requirements.txt
```

## 小贴士
- 抓取正文可显著提升 AI 分析质量；体量大时可先用摘要筛选再分析命中样本。
- 如遇长文本过大，可用 `--content-max-length` 控制成本；导出时再加 `--include-content`。
- 需要自动化/定时任务，可将命令接入 CI/定时器。
- 依赖环境：`requirements.txt` 已固定小版本并标注 `python_version e= 3.10`，建议使用虚拟环境或一键脚本安装。

## 许可与声明
- License：MIT
- 免责声明：本项目输出仅供参考，不构成任何投资建议；投资有风险，入市需谨慎。
