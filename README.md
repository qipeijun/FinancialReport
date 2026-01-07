# Financial Report - AI驱动的财经分析系统

> 🎯 多源RSS采集 → 智能去重 → 实时数据注入 → AI分析 → 质量验证 → 自动部署

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Gemini](https://img.shields.io/badge/AI-Gemini%203.0-orange.svg)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## ✨ 核心特性

### 🤖 AI智能分析
- **Gemini 3.0** - 速度提升3倍，成本更低
- **实时数据注入** - 股票/黄金/外汇实时行情
- **事实核查** - 自动验证AI生成的数据
- **质量评分** - 多维度评分，80分以上才发布
- **自动重试** - 质量不达标自动优化

### 📰 智能新闻采集
- **20+财经RSS源** - 全面覆盖财经资讯
- **MinHash去重** - O(n)复杂度，极速去重
- **内容提取** - 智能抓取正文
- **SQLite存储** - 高效本地数据库

### 🔧 自动化运维
- **GitHub Actions** - 定时自动执行
- **数据库维护** - 每周健康检查，每月自动优化
- **MkDocs网站** - 自动构建部署
- **质量监控** - 实时监控报告质量

---

## 🚀 快速开始

### 方式一: 一键启动（推荐）

```bash
# macOS/Linux
./start.sh

# Windows
start.bat
```

### 方式二: 手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/Financial-report.git
cd Financial-report

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置API密钥
export GEMINI_API_KEY="your-gemini-api-key"

# 5. 生成报告
python3 scripts/ai_analyze_verified.py --date $(date +%Y-%m-%d)
```

报告保存在: `docs/archive/YYYY-MM/YYYY-MM-DD/reports/`

---

## 📖 文档导航

### 核心文档
- 📘 [完整文档](./docs/README.md) - 系统文档总览
- 🚀 [快速开始](./docs/README.md#快速开始) - 5分钟上手指南
- 🏗️ [系统架构](./docs/README.md#系统架构) - 技术架构说明
- 👨‍💻 [开发指南](./docs/README.md#开发指南) - 开发者文档

### 专题指南
- ⭐ [AI质量验证系统](./docs/README.md#ai智能分析) - 如何确保报告质量
- 🗄️ [数据库维护](./docs/README.md#数据库自动维护) - 自动维护策略
- 📊 [数据库Schema](./docs/DATABASE_SCHEMA.md) - 数据库结构
- 🚀 [部署指南](./docs/DEPLOYMENT.md) - GitHub Actions部署

### 更新日志
- 🆕 [Gemini 3.0升级](./docs/README.md#更新日志) - 最新模型升级
- 📝 [完整变更日志](./docs/README.md#更新日志) - 版本历史

---

## 💡 使用示例

### 采集新闻

```bash
# 基础采集
python3 scripts/rss_finance_analyzer.py --fetch-content

# 高级选项
python3 scripts/rss_finance_analyzer.py \
  --fetch-content \
  --deduplicate \
  --max-workers 10
```

### 生成AI报告

```bash
# 标准模式
python3 scripts/ai_analyze_verified.py --date 2026-01-07

# 高质量模式(评分90+)
python3 scripts/ai_analyze_verified.py \
  --date 2026-01-07 \
  --min-score 90 \
  --max-retries 5

# 测试模式(跳过验证)
python3 scripts/ai_analyze_verified.py \
  --date 2026-01-07 \
  --skip-verification
```

### 数据库维护

```bash
# 健康检查
python3 scripts/utils/db_maintenance.py --health-check

# 完整维护
python3 scripts/utils/db_maintenance.py --optimize

# 清理旧数据(保留90天)
python3 scripts/utils/db_maintenance.py --cleanup 90
```

---

## 🏗️ 项目结构

```
Financial-report/
├── scripts/                # 核心脚本
│   ├── rss_finance_analyzer.py         # RSS采集
│   ├── ai_analyze_verified.py          # AI分析(主版本)
│   ├── test_verification_system.py     # 测试工具
│   └── utils/                          # 工具模块
│       ├── realtime_data_fetcher.py    # 实时数据
│       ├── fact_checker.py             # 事实核查
│       ├── quality_checker.py          # 质量评分
│       └── db_maintenance.py           # 数据库维护
│
├── .github/workflows/      # 自动化工作流
│   ├── daily-financial-report-verified.yml
│   └── database-maintenance.yml
│
├── docs/                   # 文档
│   ├── README.md          # 文档总览
│   ├── DATABASE_SCHEMA.md # 数据库结构
│   └── DEPLOYMENT.md      # 部署指南
│
├── data/                   # 数据文件
│   └── news_data.db       # SQLite数据库
│
└── config/                 # 配置文件
    └── config.yml         # 系统配置
```

---

## 🔧 核心技术

| 组件 | 技术 | 用途 |
|------|------|------|
| AI模型 | Gemini 3.0 Flash/Pro | 报告生成 |
| 数据库 | SQLite 3 | 数据存储 |
| 文档 | MkDocs | 静态网站 |
| CI/CD | GitHub Actions | 自动化 |
| 去重 | MinHash + LSH | 新闻去重 |
| 语言 | Python 3.11+ | 核心开发 |

---

## 📊 系统优势

### v2.0 核心升级

- ⚡ **性能**: AI生成速度提升3倍
- 💰 **成本**: Token使用成本降低
- 🎯 **准确性**: 事实核查+质量评分
- 📊 **可靠性**: 实时数据注入
- 🔄 **自动化**: 自动重试+自动维护

### 数据质量保障

- ✅ 实时市场数据注入
- ✅ 自动事实核查验证
- ✅ 多维度质量评分
- ✅ 质量不达标自动重试
- ✅ 完整可追溯报告

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交变更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📝 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](./LICENSE) 文件

---

## 🙏 致谢

- [Google Gemini API](https://ai.google.dev/) - AI模型支持
- [DeepSeek API](https://www.deepseek.com/) - 备用AI模型
- [MkDocs](https://www.mkdocs.org/) - 文档生成
- [GitHub Actions](https://github.com/features/actions) - CI/CD平台

---

## 📞 联系方式

- 📖 [完整文档](./docs/README.md)
- 🐛 [报告问题](https://github.com/your-username/Financial-report/issues)
- 💬 [讨论交流](https://github.com/your-username/Financial-report/discussions)

---

<div align="center">

**[开始使用](./docs/README.md#快速开始)** | **[查看文档](./docs/README.md)** | **[贡献代码](#贡献)**

Made with ❤️ by Financial Report Team

</div>
