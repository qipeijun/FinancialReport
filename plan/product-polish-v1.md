# 产品化打磨实施方案 v1

## 目标

不扩功能边界，把已有可信链路做成"跑完就知道结果"的产品体验。

---

## 一、新增 `preflight.py` — 统一前置检查

### 文件：`scripts/utils/preflight.py`（新增，~150 行）

抽取可复用的前置检查模块，`interactive_runner.py` 和 `run_daily_digest.py` 共用。

### 检查项（按依赖顺序，并行执行 venv / dep / config / apikey；db / today_data 串行）

| 检查项 | 内容 | 失败分类 | 建议 |
|--------|------|---------|------|
| `venv_check` | `venv/bin/python` 存在 | `environment_blocked` | `python3 -m venv venv` |
| `dep_check` | `import openai, yaml, peewee` 可导入 | `environment_blocked` | `pip install -r requirements.txt` |
| `config_check` | `config/config.yml` 存在且可解析 | `config_blocked` | 检查配置文件 |
| `apikey_check` | 复用 `check_deepseek_key.py` 逻辑 | `config_blocked` | 设置 `DEEPSEEK_API_KEY` 环境变量或 config.yml |
| `db_check` | `news_data.db` 存在，表 `news_articles` 可查询 | `environment_blocked` | `python scripts/init_db.py` |
| `today_data_check` | 今日 `collection_date` 有记录 | `data_missing` | 需先抓取新闻 |
| `network_check` | `api.deepseek.com:443` socket 3s 超时 | `environment_blocked`（不阻塞） | 检查网络/代理 |

`network_check` 标为 **warning**，失败不阻塞流程。

### 数据结构

```python
@dataclass
class CheckItem:
    name: str           # 'apikey_check'
    label: str          # 'DeepSeek API Key'
    passed: bool
    severity: str       # 'blocker' | 'warning'
    failure_type: str   # 'config_blocked' | 'environment_blocked' | 'data_missing'
    detail: str
    suggestion: str

@dataclass
class PreflightResult:
    passed: bool                      # 无 blocker 失败
    checks: list[CheckItem]
    blockers: list[CheckItem]         # severity='blocker' 且未通过
    warnings: list[CheckItem]         # severity='warning' 且未通过
    first_blocker: CheckItem | None
```

### 输出面板（终端）

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 前置检查

  ✅ venv             ✅ 依赖包          ✅ 配置文件
  ✅ API Key          ✅ 数据库          ⚠️ 今日数据 (尚无数据)
  ✅ 网络连接

结果: 1 项警告，可继续运行。建议先抓取数据。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

有 blocker 时：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 前置检查

  ✅ venv             ✅ 依赖包          ❌ API Key (未配置)
  跳过 数据库         ﹣ 今日数据        ﹣ 网络连接

阻塞: DeepSeek API Key 未配置
修复: export DEEPSEEK_API_KEY="your-key"
      或在 config/config.yml 中设置 api_keys.deepseek
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 二、改造 `interactive_runner.py` — 四模式 + 收尾面板

### 顶层入口

```
┌──────────────────────────────────────────────┐
│         财经新闻分析系统   2026-06-09          │
│                                              │
│  🔍 前置检查: ✅ 全部通过                     │
│                                              │
│  请选择:                                      │
│                                              │
│  1. 🚀 一键运行 (推荐)                        │
│     抓取+分析CN/US → 验收 → 摘要 → 打开报告    │
│                                              │
│  2. 🔧 自定义分析                             │
│     指定市场/日期/关键词/模式                  │
│                                              │
│  3. 📥 仅抓取数据                             │
│     只更新新闻数据库，不分析                   │
│                                              │
│  4. ✅ 仅验收                                 │
│     对今日已有产物运行验收                     │
│                                              │
│  5. 📖 预览报告                               │
│     查看最近报告 / 启动 MkDocs                │
│                                              │
│  输入 [1]:                                    │
└──────────────────────────────────────────────┘
```

### 各模式流程

#### 模式 1 — 一键运行

```
1. preflight 通过
2. 如有今日数据 → "今日已抓取 X 篇文章，是否重新抓取？[y/N]"
   无数据 → 自动进入抓取
3. 一行确认: "将抓取并分析 CN+US 双市场，预计 3-5 分钟。Enter 继续 / s 仅 CN / u 仅 US / q 退出: "
4. 串行跑 CN → US（每个市场内部: 抓取 → markdown-report → 验收）
5. 打印收尾面板
6. "打开 MkDocs 预览？[Y/n]"
```

#### 模式 2 — 自定义分析（现有逻辑迁移）

保留现有 ask_market / ask_content_field / 日期范围 / 来源过滤 / 关键词过滤 / 模式选择。

#### 模式 3 — 仅抓取数据

```
1. 确认日期 [默认今天]
2. 确认抓正文 [Y/n]
3. 运行 rss_finance_analyzer.py
4. 打印: "抓取完成，共 X 篇。运行 '模式 1' 可继续分析。"
```

#### 模式 4 — 仅验收

```
1. 确认日期 [默认今天]
2. 确认市场 [CN/US/CN+US]
3. 运行 run_acceptance.py
4. 打印验收摘要
```

#### 模式 5 — 预览报告

```
1. 扫描最近 7 天 archive，列出报告清单
2. 用户选编号 → 打印报告路径 + 可信度概要
3. 或选 "启动 MkDocs 预览"
```

### 收尾面板

每次运行结束（无论哪个模式）打印：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 运行完成 · 用时 4m12s

  CN 报告  docs/archive/2026-06/2026-06-09/reports/...cn_deepseek.md
  US 报告  docs/archive/2026-06/2026-06-09/reports/...us_deepseek.md

  验收     ✅ 通过 (87/100)
  事实核查  12/15 CN  ·  10/13 US
  实时行情  ⚠️ 降级 —— 结论依赖新闻与快照

  下一步
    mkdocs serve          预览文档站
    模式 4                重新验收
    模式 2                自定义重新分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 记忆上次选择

在项目根目录写 `.last_run` JSON（已 gitignore）：

```json
{"market": "CN+US", "mode": 1, "content_field": "summary"}
```

下次启动时默认预填上次选择。

---

## 三、报告顶部可信度摘要卡

### 实现方式

在 `report_generator.py` 的 `_save_result()` 调用前，新增 `_prepend_trust_card()` 方法，从已有 metadata JSON 读取数据，拼接摘要卡插入到报告标题行之后。

不经过 AI 模型，纯代码拼接。

### 摘要卡设计（分层而不是平铺表格）

```markdown
> 📋 **可信度摘要** · 系统根据实际数据源状态自动生成

🟢 **验收通过** · 评分 87/100

| 维度 | 状态 |
|------|------|
| 事实核查 | 12/15 断言通过验证 |
| 交叉验真 | 标的 3 confirmed / 2 weak |
| 覆盖缺口 | 宏观流动性、风险事件 |

⚠️ **1 项注意**：实时行情数据降级，价格相关结论依赖新闻与本地快照，不反映盘中最新价。

---
```

字段来源：

| 展示字段 | metadata 路径 |
|---------|--------------|
| 验收评分 | `acceptance_summary.json` → `score` |
| 事实核查 | `quality_check.stats.verified_claims` / `total_claims` |
| 交叉验真 | `cross_verification.summary` |
| 覆盖缺口 | `coverage_matrix.coverage_gaps` |
| 实时行情降级 | `live_data_degraded`（仅在为 true 时展示） |
| 旧产物复用 | `ArtifactInspection.stale_artifacts`（仅在为 true 时展示） |

规则：
- 仅在异常时展示的字段：实时行情降级、旧产物复用、覆盖缺口（空时不展示）
- 正常字段始终展示：验收结果、事实核查、交叉验真
- 字段数量动态收缩，避免信息过载

---

## 四、MkDocs 首页最新报告面板

### 实现方式

不直接改写 `docs/index.md`，改为：

1. `generate_mkdocs_nav.py` 新增函数 `generate_latest_panel()`，扫描最近 3 天 archive metadata，生成面板 Markdown 写入 `docs/_latest_panel.md`
2. `docs/index.md` 在头部用 MkDocs 支持的 `--8<--` (pymdownx.snippets) 引入该文件
3. 或者在 `mkdocs.yml` 构建流程中先跑 `generate_mkdocs_nav.py` 再跑 `mkdocs build`

实际上 pymdownx.snippets 需要额外插件。更简单的方案：`generate_mkdocs_nav.py` 在生成 nav 的同时，生成 `docs/_latest_panel.md`，`docs/index.md` 不引入（避免依赖），而是在 `mkdocs.yml` 的 nav 顶部增加一个"最新报告"条目直接指向该文件。

最终方案：`generate_mkdocs_nav.py` 追加一个步骤，在 `docs/` 下生成 `latest.md`，nav 顶部加 `{"📊 最新报告": "latest.md"}`。

### 面板内容

```markdown
# 最新报告

## 2026-06-09 (今天)

| 市场 | 模式 | 可信度 | 报告 |
|------|------|--------|------|
| 🇨🇳 A股 | markdown-report | 🟢 验收通过 87分 · 核查 12/15 | [查看](archive/2026-06/2026-06-09/reports/...cn.md) |
| 🇺🇸 美股 | markdown-report | 🟢 验收通过 82分 · 核查 10/13 | [查看](archive/2026-06/2026-06-09/reports/...us.md) |

## 2026-06-08

...
```

### 改动文件

| 文件 | 改动 |
|------|------|
| `scripts/utils/preflight.py` | **新增** — 统一前置检查模块 |
| `scripts/interactive_runner.py` | 重构 main() 为五模式 + 收尾面板 + 记忆上次选择 |
| `scripts/utils/report_generator.py` | 新增 `_prepend_trust_card()` |
| `scripts/generate_mkdocs_nav.py` | 新增 `generate_latest_md()` + nav 顶部插入入口 |
| `docs/latest.md` | **新增** — 由脚本自动生成 |

---

## 五、实现顺序

| # | 模块 | 改动量 | 依赖 |
|---|------|--------|------|
| 1 | `preflight.py` | ~150 行新增 | 无 |
| 2 | `interactive_runner.py` 重构 | ~300 行改动 | preflight.py |
| 3 | 报告可信度摘要卡 | ~80 行新增 | 无（独立改动） |
| 4 | MkDocs 最新面板 | ~100 行新增 | 无（独立改动） |

1 和 2 可以连续做；3 和 4 可以并行。

---

## 六、不改的东西

- 不扩 contract / 仓位 / 止损 / 目标价
- 不改变 acceptance 判定逻辑
- 不对已有 metadata JSON schema 做 breaking change（只读）
- `extra.css` 排版优化不在本次范围
