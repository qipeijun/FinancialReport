# GitHub Actions 工作流说明

## 🎯 配置命名规范

本项目采用**混合命名**策略，符合业界最佳实践：

| 配置位置 | 命名规范 | 示例 | 说明 |
|---------|---------|------|------|
| 📁 `config.yml`（本地） | 小写+下划线 | `api_keys.gemini` | Python配置文件惯例 |
| 🔐 GitHub Secrets（云端） | 大写+下划线 | `GEMINI_API_KEY` | 环境变量标准 |

### 📊 配置映射表

程序会自动读取配置，优先级：**环境变量（大写） > 配置文件（小写）**

| 本地配置 (config.yml) | GitHub Secrets | 说明 |
|---------------------|----------------|------|
| `api_keys.gemini` | `GEMINI_API_KEY` | Gemini API密钥 |
| `api_keys.deepseek` | `DEEPSEEK_API_KEY` | DeepSeek API密钥 |
| `notify.email.username` | `EMAIL_USERNAME` | 邮箱账号 |
| `notify.email.password` | `EMAIL_PASSWORD` | 邮箱授权码 |
| `notify.email.smtp_server` | `SMTP_SERVER` | SMTP服务器 |
| `notify.email.smtp_port` | `SMTP_PORT` | SMTP端口 |
| `notify.email.to` | `EMAIL_TO` | 收件人邮箱（支持多个，逗号分隔） |

💡 **小提示**: 
- 本地开发使用 `config.yml`（小写配置）
- GitHub Actions 使用 Secrets（大写环境变量）
- 两者可以共存，程序会自动选择正确的配置

---

## 📋 工作流概览

### `daily-financial-report.yml` - 每日自动财经报告

**功能**: 完整的自动化流程：抓取 → 分析 → 部署

**触发方式**:
- ⏰ 定时：每天两次（北京时间 08:30、20:30）
- 🖱️ 手动：在 GitHub Actions 页面点击"Run workflow"

**工作流程**:
```
1️⃣ 抓取RSS新闻 (5-10分钟)
   ├─ 从配置的RSS源抓取最新财经新闻
   ├─ 智能去重、质量过滤
   └─ 更新 data/news_data.db 并提交

2️⃣ AI分析报告 (并行，各5-10分钟)
   ├─ Gemini模型分析
   ├─ DeepSeek模型分析
   └─ 生成Markdown报告到 docs/archive/

3️⃣ 提交报告 (1分钟)
   └─ 将生成的报告提交到仓库

4️⃣ 构建部署 (3-5分钟)
   ├─ 生成MkDocs导航
   ├─ 构建静态网站
   └─ 部署到GitHub Pages

5️⃣ 发送通知
   └─ 汇总执行结果
```

**预计总时长**: 20-30分钟

**手动触发选项**:
- `skip_fetch`: 跳过数据抓取（用于只重新分析现有数据）
- `skip_analysis`: 跳过AI分析（用于只更新网站样式/配置）

---

## 🔧 配置步骤

### 1. 设置GitHub Secrets

在仓库的 `Settings` → `Secrets and variables` → `Actions` 中添加：

#### 必需的Secrets（AI功能）

| Secret名称 | 说明 | 如何获取 |
|-----------|------|---------|
| `GEMINI_API_KEY` | Google Gemini API密钥 | https://makersuite.google.com/app/apikey |
| `DEEPSEEK_API_KEY` | DeepSeek API密钥 | https://platform.deepseek.com/api_keys |

#### 可选的Secrets（邮件通知）

| Secret名称 | 说明 | 示例 |
|-----------|------|------|
| `EMAIL_USERNAME` | 发送邮箱账号 | `your-email@gmail.com` |
| `EMAIL_PASSWORD` | 邮箱授权密码 | Gmail需要使用应用专用密码 |
| `EMAIL_TO` | 接收邮箱地址（支持多个，逗号分隔） | `user1@example.com, user2@example.com` |
| `EMAIL_FROM` | 发件人显示名称（可选） | `财经报告机器人 <bot@example.com>` |
| `SMTP_SERVER` | SMTP服务器（可选，默认Gmail） | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP端口（可选，默认587） | `587` |

#### 邮件通知配置详细说明

**多个收件人配置**:

在GitHub Secrets中，使用逗号分隔多个邮箱：
```
EMAIL_TO = user1@example.com, user2@example.com, user3@example.com
```

在配置文件 `config.yml` 中，支持三种方式：
```yaml
# 方式1: 单个收件人
notify:
  email:
    to: "recipient@example.com"

# 方式2: 多个收件人（逗号分隔）
notify:
  email:
    to: "user1@example.com, user2@example.com, user3@example.com"

# 方式3: 多个收件人（YAML列表，推荐）
notify:
  email:
    to:
      - "user1@example.com"
      - "user2@example.com"
      - "user3@example.com"
```

---

**Gmail配置示例**:
1. 前往 https://myaccount.google.com/apppasswords
2. 生成应用专用密码
3. 在GitHub Secrets中设置：
   - `EMAIL_USERNAME`: `your-email@gmail.com`
   - `EMAIL_PASSWORD`: `生成的16位应用密码`
   - `EMAIL_TO`: `接收邮箱`

**QQ邮箱配置**:
- `SMTP_SERVER`: `smtp.qq.com`
- `SMTP_PORT`: `587`
- `EMAIL_PASSWORD`: QQ邮箱授权码（不是QQ密码）

**163邮箱配置**:
- `SMTP_SERVER`: `smtp.163.com`
- `SMTP_PORT`: `25`
- `EMAIL_PASSWORD`: 邮箱授权码

### 2. 启用邮件通知（可选）

在仓库的 `Settings` → `Secrets and variables` → `Actions` → `Variables` 中添加：

| Variable名称 | 值 | 说明 |
|-------------|-----|------|
| `EMAIL_NOTIFICATION_ENABLED` | `true` | 启用邮件通知 |

**设置流程**:
1. 进入 `Settings` → `Secrets and variables` → `Actions`
2. 点击 `Variables` 标签页
3. 点击 `New repository variable`
4. Name: `EMAIL_NOTIFICATION_ENABLED`
5. Value: `true`
6. 点击 `Add variable`

**注意**: 
- 不设置此变量或设置为 `false` = 禁用邮件通知
- 设置为 `true` = 启用邮件通知（需要先配置邮箱Secrets）

### 3. 启用GitHub Pages

1. 进入 `Settings` → `Pages`
2. Source: 选择 "GitHub Actions"
3. 保存

### 4. 启用Actions

1. 进入 `Actions` 标签页
2. 如果看到提示，点击 "I understand my workflows, go ahead and enable them"

### 5. 配置RSS源（可选）

编辑 `scripts/config/rss.json`，添加你关注的RSS源：

```json
{
  "sources": [
    {
      "name": "财新网",
      "url": "https://www.caixin.com/rss/index.xml",
      "category": "综合财经"
    }
  ]
}
```

---

## 🚀 使用方法

本工作流支持 **自动运行** 和 **手动触发** 两种方式：

### 🤖 方法1: 自动运行（推荐）

**无需任何操作**，每天自动运行两次完整流程：
- 🌅 **早盘场**: 北京时间 08:30（A股开盘前1小时，掌握隔夜美股+亚洲早盘动态）
- 🌙 **美股场**: 北京时间 20:30（美股开盘前1小时，汇总全天A股+准备美股交易）

**自动执行内容**:
1. ✅ 抓取最新RSS新闻
2. ✅ 使用Gemini和DeepSeek并行分析
3. ✅ 生成Markdown报告
4. ✅ 构建并部署MkDocs网站
5. ✅ 发送执行摘要通知（如已启用）

**适合场景**: 
- ✅ 同时关注A股和美股
- ✅ 早上：获取隔夜美股、亚洲市场动态，准备A股开盘
- ✅ 晚上：复盘全天A股走势，获取美股开盘前瞻
- ✅ 全天候跟踪财经动态，无需人工干预

---

### 🖱️ 方法2: 手动触发

**操作步骤**:
1. 进入仓库的 `Actions` 标签页
2. 选择左侧的 "Daily Financial Report"
3. 点击右侧 "Run workflow" 按钮
4. 选择分支（通常是 `main`）
5. （可选）配置高级选项
6. 点击绿色 "Run workflow" 确认

**高级选项说明**:

| 选项 | 用途 | 何时使用 |
|-----|------|---------|
| `skip_fetch` | 跳过数据抓取 | 只想重新分析现有数据，节省时间 |
| `skip_analysis` | 跳过AI分析 | 只修改了网站样式/配置，快速部署 |

**适合场景**:
- 🔧 测试工作流配置
- 🔄 补漏：自动运行失败后重试
- ⚡ 加急：等不及定时任务，立即生成报告
- 🎨 快速部署：只更新了网站样式

---

## 📊 监控和调试

### 查看执行日志

1. 进入 `Actions` 标签页
2. 点击某次运行记录
3. 展开具体的Job查看详细日志

### 常见问题

**Q: 工作流运行失败怎么办？**

A: 点击失败的Job，查看错误日志：
- 如果是API Key错误 → 检查Secrets配置
- 如果是数据库错误 → 检查 `data/news_data.db` 是否正常
- 如果是网络超时 → 重新运行workflow

**Q: 如何停止自动运行？**

A: 
1. 进入 `.github/workflows/daily-financial-report.yml`
2. 删除或注释 `schedule` 部分
3. 提交更改

**Q: 如何修改运行时间？**

A: 编辑 `daily-financial-report.yml` 中的 cron 表达式：
```yaml
schedule:
  - cron: '30 0 * * *'   # 每天 00:30 UTC (08:30 北京时间) - A股开盘前
  - cron: '30 12 * * *'  # 每天 12:30 UTC (20:30 北京时间) - 美股开盘前
```

**Cron时间转换**（北京时间 = UTC + 8小时）:
- UTC 00:30 = 北京 08:30（A股开盘前）
- UTC 04:00 = 北京 12:00（午休时间）
- UTC 12:30 = 北京 20:30（美股开盘前）
- UTC 14:00 = 北京 22:00（美股盘中）

**当前配置**: 每天两次（早上8:30 A股前、晚上20:30 美股前）

**其他推荐时间**:
- `0 4 * * *` = 12:00 午休，适合看上午A股新闻
- `0 14 * * *` = 22:00 美股盘中，适合夜间交易者

---

## 💰 成本估算

### GitHub Actions 免费额度
- 公开仓库：✅ 无限制
- 私有仓库：2,000分钟/月

### 单次运行时长
- 完整流程：约 20-30分钟
- 每天运行：2次
- 每月运行：30天 × 2次 × 25分钟 = 1,500分钟

### AI API成本
- Gemini: $0.015/次 × 60次/月 = $0.90
- DeepSeek: $0.005/次 × 60次/月 = $0.30
- 每月总计：约 $1.20

**结论**: 
- ✅ 公开仓库完全免费（无限Actions时长）
- ✅ 私有仓库在免费额度内（1,500 < 2,000分钟）
- 💰 AI API成本：约$1.2/月（可接受）

---

## 🔄 工作流内部结构

`daily-financial-report.yml` 包含5个Job，按顺序执行：

```
触发（定时/手动）
    ↓
┌─────────────────────────────────────┐
│ Job 1: fetch-news                   │
│ ├─ 抓取RSS新闻                      │
│ ├─ 智能去重和质量过滤               │
│ ├─ 更新 data/news_data.db          │
│ └─ 输出: news-database (artifact)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Job 2: ai-analysis (矩阵并行)       │
│ ├─ Gemini 模型分析  → reports-gemini │
│ └─ DeepSeek 模型分析 → reports-deepseek │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Job 3: commit-reports               │
│ ├─ 合并两个模型的报告                │
│ ├─ 提交到 docs/archive/             │
│ └─ 推送到 GitHub 仓库               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Job 4: build-and-deploy             │
│ ├─ 生成 MkDocs 导航                 │
│ ├─ 构建静态网站                     │
│ └─ 部署到 GitHub Pages              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Job 5: notify                       │
│ └─ 汇总执行结果并发送通知            │
└─────────────────────────────────────┘
```

**容错设计**:
- 某个模型失败不影响另一个（`fail-fast: false`）
- 前面步骤失败仍尝试部署现有内容（`if: !cancelled()`）
- Job之间通过artifacts传递数据

---

## 🎯 最佳实践

### 1. 监控频率
- ✅ 每周检查一次工作流运行状态
- ✅ 关注失败通知
- ❌ 不需要每天查看

### 2. 数据备份
- ✅ `data/news_data.db` 已自动提交到Git
- ✅ GitHub保留完整历史记录
- 💡 可定期导出数据库做额外备份

### 3. 报告质量
- ✅ 定期查看生成的报告质量
- ✅ 根据需要调整Prompt
- ✅ 优化RSS源配置

### 4. 成本优化
- ✅ 保持每天1次运行
- ✅ 失败时手动重试而非自动
- ❌ 避免频繁测试（消耗API额度）

---

## 📧 邮件通知系统

### 🎯 设计理念

使用**Python脚本**实现通知功能，而非第三方GitHub Action：

**优势**:
- ✅ **灵活可扩展**: 易于添加新的通知渠道（企业微信/钉钉/Telegram）
- ✅ **完全可控**: 自定义邮件模板、格式、样式
- ✅ **易于调试**: 本地测试方便，日志清晰
- ✅ **无依赖风险**: 不依赖第三方Action的更新和维护
- ✅ **统一管理**: 通知逻辑集中在一个脚本中

### 📝 Python脚本功能

**位置**: `scripts/send_notification.py`

**功能特性**:
- 🎨 精美的HTML邮件模板（响应式设计）
- 📱 移动端自适应
- 🎯 智能状态判断（成功/失败/跳过）
- 📊 执行统计展示
- 🔗 快速访问链接（网站/日志）
- 🔧 支持多种SMTP服务器（Gmail/QQ/163等）

**已实现**:
- ✅ 邮件通知（HTML+纯文本）
- ✅ GitHub摘要显示

**待扩展**:
- 🚧 企业微信通知
- 🚧 钉钉通知
- 🚧 Telegram通知
- 🚧 Slack通知

### 🔧 本地测试

```bash
# 设置环境变量
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export EMAIL_TO="recipient@example.com"

# 运行测试
python3 scripts/send_notification.py \
  --fetch-status success \
  --analysis-status success \
  --deploy-status success \
  --news-count 45 \
  --trigger manual \
  --website-url "https://example.com" \
  --run-url "https://github.com/..." \
  --repository "user/repo" \
  --branch "main" \
  --channels email
```

### 📮 邮件样式预览

发送的邮件包含：
- 🎨 渐变色顶部横幅
- 📊 清晰的状态卡片
- 📈 数据统计展示
- 🔘 快捷操作按钮
- 📱 移动端友好设计

### 🔌 添加新通知渠道

在 `scripts/send_notification.py` 中添加：

```python
def send_wechat(self) -> bool:
    """发送企业微信通知"""
    webhook_url = os.getenv('WECHAT_WEBHOOK')
    if not webhook_url:
        return False
    
    # 实现企业微信通知逻辑
    # ...
    
    return True
```

然后在workflow中使用：
```yaml
--channels email wechat
```

---

## 📞 技术支持

如有问题，请：
1. 查看 [工作流执行日志](../../actions)
2. 阅读 [项目文档](../../README.md)
3. 提交 [Issue](../../issues)
4. 查看 [通知脚本源码](../../scripts/send_notification.py)

