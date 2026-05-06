# AI 脚本整合说明

> 更新日期：2026-05-06  
> 当前状态：主链路统一到 DeepSeek，双模式输出与验收链路已接入

---

## 结论

当前仓库中，真正应被当作“主分析入口”的脚本只有：

- `scripts/ai_analyze_deepseek_verified.py`

其余相关脚本的定位如下：

- `scripts/ai_analyze_deepseek.py`
  - 保留的简化入口
  - 适合轻量分析或调试
- `scripts/interactive_runner.py`
  - 面向人工交互使用
  - 内部已经统一调 `ai_analyze_deepseek_verified.py`
- `start.sh`
  - 本地一键入口
  - 内部已经统一调 `ai_analyze_deepseek_verified.py`
- `scripts/archive/*`
  - 历史脚本备份
  - 不属于当前运行链路

---

## 当前架构

```text
入口层
├── start.sh
├── interactive_runner.py
└── ai_analyze_deepseek_verified.py

生成层
└── scripts/utils/report_generator.py

能力层
├── realtime_data_fetcher.py
├── fact_checker.py
├── quality_checker_v2.py
├── investment_signal.py
└── providers/deepseek_provider.py

验收层
└── scripts/run_acceptance.py
```

---

## 为什么这样收敛

之前文档里同时存在：

- Gemini 基础版
- Gemini 验证版
- DeepSeek 基础版
- DeepSeek 验证版

这会带来两个问题：

1. 用户不知道该跑哪个入口。
2. 文档和实际代码状态容易脱节。

现在的收敛原则是：

- **对外只推荐一个主分析入口**
- **把模式差异收敛到参数，而不是分裂成多份脚本**
- **把质量验收沉淀成单独脚本，而不是靠人工记忆清单**

---

## 当前主入口能力

`ai_analyze_deepseek_verified.py` 现在支持：

- `markdown-report`
  - 完整财经分析报告
- `judgment-cards`
  - 高信号投资判断卡片

并统一具备：

- DeepSeek 调用
- 实时数据注入
- 事实核查
- 质量评分
- 自动重试
- metadata 保存
- JSON 导出

---

## 当前验收链路

新增的 `scripts/run_acceptance.py` 负责把原本分散的验收要求收敛成可执行流程，覆盖：

- 自动化测试
- 编译检查
- 数据入库校验
- 报告产物校验
- 判断卡片产物校验
- 双模式不覆盖专项验收
- 实时数据全失败降级专项验收
- 质量评分与人工抽样清单输出

---

## 当前推荐使用方式

### 抓取新闻

```bash
python3 scripts/rss_finance_analyzer.py --fetch-content
```

### 生成完整报告

```bash
python3 scripts/ai_analyze_deepseek_verified.py \
  --date 2026-05-06 \
  --mode markdown-report
```

### 生成判断卡片

```bash
python3 scripts/ai_analyze_deepseek_verified.py \
  --date 2026-05-06 \
  --mode judgment-cards
```

### 执行验收

```bash
python3 scripts/run_acceptance.py --date 2026-05-06 --skip-live
python3 scripts/run_acceptance.py --date 2026-05-06
```

---

## 备注

- 这份文档不再描述 Gemini 旧入口的使用方法。
- 如果后续重新引入新的主模型或新的正式入口，应同步更新：
  - 根 `README.md`
  - `docs/README.md`
  - `docs/index.md`
  - 本文档
