# Financial Report 项目文档

> 📅 最后更新: 2026-01-07
> 🎯 版本: v2.0 (已优化)

---

## 📚 快速导航

- [快速开始](#快速开始)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [开发指南](#开发指南)
- [部署运维](#部署运维)
- [更新日志](#更新日志)

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- SQLite 3
- Git

### 快速安装

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
export DEEPSEEK_API_KEY="your-deepseek-api-key"  # 可选
```

### 生成第一份报告

```bash
# 方式1: 抓取新闻并生成报告
python3 scripts/rss_finance_analyzer.py --fetch-content
python3 scripts/ai_analyze_verified.py --date $(date +%Y-%m-%d)

# 方式2: 使用已有数据生成
python3 scripts/ai_analyze_verified.py --date 2026-01-07
```

报告将保存到: `docs/archive/YYYY-MM/YYYY-MM-DD/reports/`

---

## ⭐ 核心功能

### 1. 智能新闻采集

- 📰 **多源RSS聚合** - 支持20+财经RSS源
- 🔄 **智能去重** - MinHash + LSH算法，O(n)复杂度
- 🎯 **内容抓取** - 自动提取正文，智能清洗
- 💾 **SQLite存储** - 高效本地数据库

### 2. AI财经分析

- 🤖 **多模型支持** - Gemini 3.0, DeepSeek, Claude
- ⚡ **实时数据注入** - 股票/黄金/外汇实时行情
- 🔍 **事实核查** - 自动验证AI生成的数据断言
- 📊 **质量评分** - 准确性+时效性+可靠性 (80分以上发布)
- 🔄 **自动重试** - 质量不达标自动优化重试

### 3. 数据库自动维护

- 🏥 **定时健康检查** - 每周一凌晨自动检查
- 🔧 **完整维护** - 每月1号自动VACUUM+索引优化
- 📊 **实时监控** - 每次生成报告时检查碎片率
- 🛠️ **手动工具** - 支持6种维护操作

### 4. 自动化部署

- ⏰ **GitHub Actions** - 定时自动执行
- 📄 **MkDocs网站** - 自动构建部署到GitHub Pages
- 📧 **通知系统** - 邮件/钉钉通知(可选)
- ☁️ **云函数支持** - 腾讯云SCF部署

---

## 🏗️ 系统架构

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.11 | 核心开发语言 |
| 数据库 | SQLite 3 | 轻量级本地数据库 |
| AI模型 | Gemini 3.0, DeepSeek | 多模型支持 |
| 文档 | MkDocs | 静态网站生成 |
| CI/CD | GitHub Actions | 自动化工作流 |
| 部署 | GitHub Pages | 静态托管 |

### 核心模块

```
Financial-report/
├── scripts/                    # 核心脚本
│   ├── rss_finance_analyzer.py        # RSS采集主脚本
│   ├── ai_analyze_verified.py         # AI分析(带验证)
│   ├── test_verification_system.py    # 测试工具
│   └── utils/                         # 工具模块
│       ├── realtime_data_fetcher.py   # 实时数据采集
│       ├── fact_checker.py            # 事实核查
│       ├── quality_checker.py         # 质量评分
│       ├── db_maintenance.py          # 数据库维护
│       └── ...
│
├── .github/workflows/         # 自动化工作流
│   ├── daily-financial-report-verified.yml  # 验证版报告
│   └── database-maintenance.yml             # 数据库维护
│
├── docs/                      # 文档
├── data/                      # 数据文件
│   └── news_data.db          # SQLite数据库
└── config/                    # 配置文件
```

### 数据流程

```
RSS源 → 内容抓取 → 去重 → SQLite
                                ↓
                          AI Prompt ← 实时数据(股票/金价)
                                ↓
                          Gemini 3.0生成报告
                                ↓
                          事实核查 → 质量评分
                                ↓
                    评分<80? → 重试 (最多3次)
                                ↓
                          追加核查报告 → 保存
                                ↓
                          MkDocs构建 → GitHub Pages
```

---

## 👨‍💻 开发指南

### 核心脚本说明

#### 1. RSS采集: `rss_finance_analyzer.py`

```bash
# 基本使用
python3 scripts/rss_finance_analyzer.py --fetch-content

# 完整参数
python3 scripts/rss_finance_analyzer.py \
  --fetch-content \      # 抓取全文
  --deduplicate \        # 去重
  --max-workers 10       # 并发数
```

#### 2. AI分析: `ai_analyze_verified.py`

```bash
# 基本使用
python3 scripts/ai_analyze_verified.py --date 2026-01-07

# 高质量模式
python3 scripts/ai_analyze_verified.py \
  --date 2026-01-07 \
  --min-score 90 \       # 最低评分90
  --max-retries 5        # 最多重试5次

# 跳过验证(测试)
python3 scripts/ai_analyze_verified.py \
  --date 2026-01-07 \
  --skip-verification
```

#### 3. 数据库维护: `db_maintenance.py`

```bash
# 健康检查
python3 scripts/utils/db_maintenance.py --health-check

# 完整维护
python3 scripts/utils/db_maintenance.py --optimize

# VACUUM清理
python3 scripts/utils/db_maintenance.py --vacuum

# 数据清理
python3 scripts/utils/db_maintenance.py --cleanup 90  # 保留90天
```

### AI模型配置

当前模型优先级:

1. **Gemini 3.0 Flash** (最新) - 速度快3倍,成本低
2. **Gemini 3.0 Pro** - 最智能,复杂推理
3. **Gemini 2.0 Flash** - 备用
4. Gemini 1.5 Pro - 备用
5. Gemini 1.5 Flash - 最后备用

### 数据库Schema

参见: [`docs/DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md)

核心表:
- `news_articles` - 新闻文章
- `rss_sources` - RSS源配置
- `minhash_signatures` - 去重签名

---

## 🚀 部署运维

### GitHub Actions 自动化

#### 验证版报告生成

**Workflow**: `.github/workflows/daily-financial-report-verified.yml`

**触发方式**:
- 手动触发 (Actions页面)
- 定时触发 (需取消注释cron)

**参数**:
- `skip_verification` - 跳过验证
- `min_quality_score` - 最低质量评分 (默认80)
- `max_retries` - 最大重试次数 (默认3)

#### 数据库自动维护

**Workflow**: `.github/workflows/database-maintenance.yml`

**自动执行**:
- 每周一凌晨2:00 - 健康检查
- 每月1号凌晨3:00 - 完整维护

**手动操作**:
- health-check - 健康检查
- full-maintenance - 完整维护
- vacuum - VACUUM清理
- rebuild-indexes - 重建索引
- cleanup - 清理旧数据

### 本地开发

```bash
# 1. 安装开发依赖
pip install -r requirements.txt

# 2. 运行测试
python3 scripts/test_verification_system.py

# 3. 本地预览文档
mkdocs serve

# 4. 构建文档
mkdocs build
```

### 环境变量

必需:
- `GEMINI_API_KEY` - Gemini API密钥

可选:
- `DEEPSEEK_API_KEY` - DeepSeek API密钥
- `SMTP_SERVER` - 邮件服务器
- `EMAIL_USERNAME` - 邮件用户名
- `EMAIL_PASSWORD` - 邮件密码

---

## 📝 更新日志

### v2.0 (2026-01-07)

**重大更新**:
- ✅ 升级到Gemini 3.0系列模型
- ✅ 完整的AI报告质量验证系统
- ✅ 数据库自动维护系统
- ✅ 实时数据注入功能
- ✅ 事实核查框架
- ✅ 多维度质量评分

**性能提升**:
- ⚡ AI生成速度提升3倍
- 💰 Token成本降低
- 🎯 报告准确性显著提升
- 📊 数据库性能优化

详见: [`docs/GEMINI_3_UPGRADE.md`](./GEMINI_3_UPGRADE.md)

### v1.0 (2025-09)

- ✅ RSS新闻采集系统
- ✅ 基础AI分析功能
- ✅ MkDocs文档网站
- ✅ GitHub Actions自动化

---

## 🔧 故障排除

### 常见问题

**Q: 实时数据获取失败?**

A: 检查是否交易时间。非交易时间会自动降级使用新闻数据。

**Q: 质量评分总是不通过?**

A:
1. 降低最低评分 `--min-score 70`
2. 增加重试次数 `--max-retries 5`
3. 检查AI是否编造目标涨幅

**Q: Token使用过多?**

A:
1. 限制文章数 `--max-articles 30`
2. 限制读取量 `--limit 50`

### 获取帮助

- 📖 查看详细文档: `docs/`
- 🐛 提交Issue: [GitHub Issues](https://github.com/your-username/Financial-report/issues)
- 💬 讨论交流: [GitHub Discussions](https://github.com/your-username/Financial-report/discussions)

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- Google Gemini API
- DeepSeek API
- MkDocs
- GitHub Actions

---

**文档版本**: v2.0
**最后更新**: 2026-01-07

💪 准备好生成高质量的AI财经报告了吗? [开始使用](#快速开始) 🚀
