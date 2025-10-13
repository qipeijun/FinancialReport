# 财经新闻采集与 AI 分析

一个可落地的财经新闻数据管道：多源 RSS 采集 → SQLite 汇总存储 → 可查询导出 → 调用大模型生成专业分析报告。

## 特性
- **多源 RSS 采集**：统一入库到 `data/news_data.db`
- **灵活内容抓取**：支持抓取正文 `content`（默认不截断）与摘要 `summary`
- **智能字段选择**：AI分析时可选择摘要优先、正文优先或智能选择
- **便捷查询导出**：按日期/来源/关键词查询并导出 CSV/JSON
- **AI 分析报告**：一键调用大模型生成专业 Markdown 报告
- **多模型支持**：支持 Gemini 与 DeepSeek，可在交互脚本中选择
- **虚拟环境支持**：完整的 Python 虚拟环境配置，确保依赖隔离
- **交互式体验**：简化上手的交互式脚本，支持字段选择界面

## 快速开始

### 方式A：一键启动脚本（推荐）
```bash
# macOS/Linux
./start.sh

# Windows
start.bat
```
一键启动脚本会自动：
- 检查Python环境
- 创建虚拟环境（如不存在）
- 安装项目依赖
- 提供交互式菜单选择功能
  - 交互式运行器
  - AI分析脚本
  - RSS财经抓取器
  - 数据质量监控
  - 启动文档网站（本地预览）
  - 构建部署文档（生成静态网站）

### 方式B：使用虚拟环境
```bash
# 1. 激活虚拟环境（自动安装依赖 + 依赖校验）
./activate.sh                    # Linux/macOS
# 或
activate.bat                     # Windows

# 2. 配置API密钥
cp config/config.example.yml config/config.yml
# 编辑 config/config.yml，填写你的 Gemini 与/或 DeepSeek API Key

# 3. 运行交互式脚本（可选择 Gemini 或 DeepSeek 模型）
python scripts/interactive_runner.py
```

### 方式C：手动安装
```bash
# Python ≥ 3.10
pip3 install -r requirements.txt
cp config/config.example.yml config/config.yml
# 编辑 config/config.yml，填写你的 Gemini 与/或 DeepSeek API Key
python3 scripts/interactive_runner.py
```
- 若今天已抓取过数据，可直接选择"AI 分析"。
- 若未抓取，脚本会询问是否立即抓取（可选抓取正文），完成后再询问是否分析。

## 常用命令

> 💡 **提示**：以下命令需要在虚拟环境中运行。先执行 `./activate.sh`（Linux/macOS）或 `activate.bat`（Windows）激活虚拟环境。

### 虚拟环境管理
```bash
# 激活虚拟环境
./activate.sh                    # Linux/macOS
activate.bat                     # Windows

# 退出虚拟环境
deactivate

# 查看已安装的包
pip list

# 重新安装依赖
pip install -r requirements.txt
```

### 数据采集
```bash
# 仅摘要
python scripts/rss_finance_analyzer.py

# 抓取正文写入 content（推荐）
python scripts/rss_finance_analyzer.py --fetch-content

# 仅抓取指定来源（与 scripts/config/rss.json 名称一致，逗号分隔）
python scripts/rss_finance_analyzer.py --only-source "华尔街见闻,36氪"
```

### 查询与导出
```bash
# 表格查看当天
python scripts/query_news_by_date.py

# 导出JSON格式（包含正文）
python scripts/query_news_by_date.py --format json --output news.json --include-content

# 导出CSV格式（包含正文）
python scripts/query_news_by_date.py --format csv --output news.csv --include-content

# 全文检索（需 FTS5，匹配 title/summary/content）
python scripts/query_news_by_date.py --search "新能源 OR AI" --format json --output search.json
```

### AI 分析（生成 Markdown 报告）
```bash
# 分析当天
python scripts/ai_analyze.py

# 指定日期范围
python scripts/ai_analyze.py --start 2025-09-28 --end 2025-09-29

# 控量/过滤（降成本）
python scripts/ai_analyze.py --filter-source "华尔街见闻,36氪" --filter-keyword "新能源,AI" --max-articles 50 --max-chars 150000

# 选择分析字段（新增功能）
python scripts/ai_analyze.py --content-field summary    # 摘要优先（推荐）
python scripts/ai_analyze.py --content-field content    # 正文优先
python scripts/ai_analyze.py --content-field auto       # 智能选择（默认）

# 使用 DeepSeek 模型（可直接运行 DeepSeek 版本脚本）
python scripts/ai_analyze_deepseek.py                   # 使用 config.yml 的 api_keys.deepseek
python scripts/ai_analyze_deepseek.py --model deepseek-chat --base-url https://api.deepseek.com/v3.1_terminus_expires_on_20251015
```

### 文档网站构建与部署
```bash
# 构建静态网站（生成到 site/ 目录）
bash scripts/deploy.sh

# 本地预览文档网站
mkdocs serve                  # 访问 http://127.0.0.1:8000

# 或使用交互式启动脚本
./start.sh                    # 选择选项 5（本地预览）或选项 6（构建部署）
```

部署脚本会自动：
- 生成 MkDocs 导航配置
- 构建静态 HTML 网站
- 复制安全验证文件到 site/ 目录
- 准备部署到 GitHub Pages

## 结果位置
- 主数据库：`data/news_data.db`
- 当日归档：`docs/archive/YYYY-MM/YYYY-MM-DD/`
  - `rss_data/` 原始 RSS 文本
  - `news_content/` 内容文件
  - `reports/` 分析报告（Markdown）
  - `collected_data.json` 备份
- 静态网站：`site/`（通过 `bash scripts/deploy.sh` 生成）
  - 包含所有分析报告的静态 HTML 网站
  - 可直接部署到 GitHub Pages 或其他静态托管服务

## 配置说明
- 实际配置：`config/config.yml`（已加入 `.gitignore`）
- 模板示例：`config/config.example.yml`
```yaml
api_keys:
  gemini: "YOUR_GEMINI_API_KEY"
  deepseek: "YOUR_DEEPSEEK_API_KEY"

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
  - 读取数据库，支持字段选择（`--content-field`：`summary`/`content`/`auto`）
  - 固定提示词 `task/financial_analysis_prompt_pro.md`，生成 Markdown 报告
  - 智能内容选择：当正文过长时自动使用摘要
- `scripts/ai_analyze_deepseek.py`
  - 与 `ai_analyze.py` 相同逻辑，但调用 DeepSeek（OpenAI SDK）
  - 从 `config/config.yml` 读取 `api_keys.deepseek` 或 `deepseek.api_key`（不再读取环境变量）
  - 区分不同AI模型生成的财经分析报告文件名
- `scripts/interactive_runner.py`
  - 交互式问答：检测 → 抓取 → 分析，一站式体验
  - 支持字段选择与模型选择（Gemini/DeepSeek）
- `scripts/deploy.sh`
  - 自动生成导航配置、构建文档网站并准备部署
  - 自动复制安全验证文件到网站根目录
- `scripts/generate_mkdocs_nav.py`
  - 自动扫描归档目录，生成 MkDocs 导航配置

## 目录结构
```
Financial-report/
├── config/
│   ├── config.example.yml
│   └── config.yml                 # 本地私密配置（git 忽略）
├── data/
│   └── news_data.db               # 主 SQLite 数据库
├── docs/
│   ├── archive/YYYY-MM/YYYY-MM-DD/{rss_data,news_content,reports}
│   └── index.md                   # 文档首页
├── scripts/
│   ├── rss_finance_analyzer.py
│   ├── query_news_by_date.py
│   ├── ai_analyze.py
│   ├── ai_analyze_deepseek.py
│   ├── interactive_runner.py
│   ├── deploy.sh                  # 文档网站构建部署脚本
│   └── generate_mkdocs_nav.py    # MkDocs 导航配置生成器
├── site/                          # 静态网站输出目录（git 忽略）
├── venv/                          # Python虚拟环境（git 忽略）
├── mkdocs.yml                     # MkDocs 配置文件
├── start.sh                       # 一键启动脚本（Linux/macOS）
├── start.bat                      # 一键启动脚本（Windows）
├── activate.sh                    # 虚拟环境激活脚本（Linux/macOS）
├── activate.bat                   # 虚拟环境激活脚本（Windows）
├── VENV_README.md                 # 虚拟环境详细使用指南
├── requirements.txt               # Python依赖列表
└── README.md                      # 项目说明文档
```

## 小贴士

### 启动方式选择
- **一键启动脚本（推荐）**：使用 `./start.sh`（Linux/macOS）或 `start.bat`（Windows）快速启动，自动处理环境检查和依赖安装
- **虚拟环境使用**：如需更多控制，可使用 `./activate.sh`（Linux/macOS）或 `activate.bat`（Windows）手动激活虚拟环境
- **推荐使用虚拟环境**：避免依赖冲突，确保环境一致性
- **详细指南**：查看 `VENV_README.md` 了解虚拟环境的完整使用方法

### 依赖安装与校验
- `activate.sh` 会自动：
  - 升级 pip
  - 安装 `requirements.txt` 全部依赖
  - 执行 `pip check` 完成依赖一致性校验

### 数据分析优化
- **字段选择**：新增 `--content-field` 参数，可选择 `summary`（摘要优先）、`content`（正文优先）或 `auto`（智能选择）
- **摘要优先**：推荐使用 `summary` 模式，内容简洁且分析质量高
- **正文分析**：抓取正文可显著提升 AI 分析质量；体量大时可先用摘要筛选再分析命中样本
- **成本控制**：如遇长文本过大，可用 `--max-chars` 控制成本；导出时再加 `--include-content`

### 文档网站部署
- **本地预览**：运行 `mkdocs serve` 在本地查看文档网站
- **构建部署**：运行 `bash scripts/deploy.sh` 生成静态网站到 `site/` 目录
- **GitHub Pages**：推送到 GitHub 后会自动部署到 GitHub Pages
- **安全验证**：部署时自动复制安全验证文件到网站根目录

### 自动化部署
- **定时任务**：可将命令接入 CI/定时器实现自动化
- **依赖管理**：`requirements.txt` 已固定小版本，建议使用虚拟环境安装

## 定时触发方案

### 问题
GitHub Actions 定时任务延迟 15-60 分钟，成功率 95%

### 解决方案
使用**腾讯云函数**准时触发，延迟 < 1 分钟，成功率 99.9%，完全免费

### 配置指南
📖 **[腾讯云函数配置指南](docs/TENCENT_SCF_GUIDE.md)** - 10分钟完成配置

## 许可与声明
- License：MIT
- 免责声明：本项目输出仅供参考，不构成任何投资建议；投资有风险，入市需谨慎。
