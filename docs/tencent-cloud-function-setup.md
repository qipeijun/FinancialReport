# 腾讯云函数配置指南

本文档说明如何配置腾讯云函数来定时触发 GitHub Actions 工作流。

## 为什么使用腾讯云函数？

- ✅ **更准时**：GitHub Actions 的 schedule 触发经常延迟 5-15 分钟
- ✅ **更可靠**：腾讯云函数触发稳定性更高
- ✅ **免费额度**：每月100万次调用免费，足够使用

## 配置步骤

### 1. 创建 GitHub Personal Access Token

1. 登录 GitHub → 点击右上角头像 → Settings
2. 左侧菜单：Developer settings → Personal access tokens → Tokens (classic)
3. 点击 **Generate new token (classic)**
4. 配置：
   - Note: `Tencent SCF Trigger`
   - Expiration: `No expiration`（或选择更长的有效期）
   - 权限勾选：
     - ✅ `repo` (完整仓库权限) 或
     - ✅ `workflow` (只需要触发工作流)
5. 点击 **Generate token**
6. **重要**：复制生成的 token（格式：`ghp_xxxxxxxxxxxxx`），离开页面后无法再次查看

### 2. 创建腾讯云函数

#### 2.1 登录腾讯云控制台

1. 访问 [腾讯云函数控制台](https://console.cloud.tencent.com/scf/list)
2. 如果没有账号，需要先注册（需要实名认证）

#### 2.2 创建新函数

1. 点击左上角 **新建**
2. 选择 **从头开始**
3. 基本配置：

```
函数名称: github-actions-trigger
地域: 建议选择 ap-guangzhou（广州）或 ap-shanghai（上海）
运行环境: Python 3.9
函数类型: 事件函数
```

4. 函数代码：
   - 提交方法：**本地上传文件夹** 或 **在线编辑**
   - 将 `scripts/tencent_scf_trigger.py` 的完整内容复制到编辑器
   - 执行方法：`index.main_handler`（如果文件名是 index.py）

#### 2.3 高级配置

```
内存: 128 MB（足够使用）
超时时间: 15 秒
环境变量: 见下一步配置
```

### 3. 配置环境变量（关键步骤）

在函数配置页面，找到 **环境变量** 部分，添加以下三个变量：

| 键 | 值 | 说明 |
|---|---|---|
| `GITHUB_TOKEN` | `ghp_your_token_here` | 步骤1生成的 GitHub Token |
| `GITHUB_REPO` | `qipeijun/FinancialReport` | 你的 GitHub 仓库（注意大小写） |
| `WORKFLOW_ID` | `daily-financial-report.yml` | 工作流文件名 |

**注意**：
- 仓库名大小写要准确（可在 GitHub 仓库页面确认）
- Token 不要泄露给他人

### 4. 配置定时触发器

#### 4.1 创建触发器

1. 在函数详情页，点击 **触发管理** 标签
2. 点击 **创建触发器**

#### 4.2 配置早上触发（08:15 北京时间）

```
触发方式: 定时触发
触发周期: 自定义触发周期
Cron 表达式: 15 0 * * * * *
```

**Cron 格式说明**（腾讯云是7位）：
- `15 0 * * * * *` = 秒 分 时 日 月 周 年
- `15 0` = 每天 00:15 UTC（北京时间 08:15）

#### 4.3 再创建一个晚上触发（20:15 北京时间）

重复步骤 4.1，使用不同的 Cron 表达式：

```
Cron 表达式: 15 12 * * * * *
```

- `15 12` = 每天 12:15 UTC（北京时间 20:15）

### 5. 测试函数

#### 5.1 手动测试

1. 在函数详情页，点击 **测试** 标签
2. 点击 **测试**（测试模板选择默认即可）
3. 查看执行结果：
   - ✅ 成功：返回 `statusCode: 200`，消息显示 "成功触发 GitHub Actions"
   - ❌ 失败：检查错误信息，通常是环境变量配置问题

#### 5.2 验证 GitHub Actions

1. 访问你的 GitHub 仓库
2. 点击 **Actions** 标签
3. 应该能看到新触发的工作流运行记录

### 6. 查看日志（可选）

1. 在函数详情页，点击 **日志查询** 标签
2. 可以查看每次触发的详细日志
3. 如果触发失败，日志中会显示具体错误信息

## 常见问题排查

### Q1: 测试返回 401 Unauthorized

**原因**：GitHub Token 无效或权限不足

**解决**：
1. 检查 `GITHUB_TOKEN` 环境变量是否正确
2. 确认 Token 有 `workflow` 或 `repo` 权限
3. Token 是否过期（可重新生成）

### Q2: 测试返回 404 Not Found

**原因**：仓库名或工作流文件名错误

**解决**：
1. 检查 `GITHUB_REPO` 格式是否正确（`owner/repo`）
2. 检查 `WORKFLOW_ID` 是否与文件名完全一致
3. 注意大小写

### Q3: 定时触发器没有运行

**原因**：Cron 表达式配置错误或时区问题

**解决**：
1. 确认 Cron 表达式是7位（腾讯云格式）
2. UTC 时间与北京时间相差 8 小时
3. 在触发器列表中检查"下次触发时间"

### Q4: GitHub Actions 没有被触发

**原因**：workflow_dispatch 未正确配置

**解决**：
1. 确认工作流文件中有 `workflow_dispatch:` 配置
2. 检查分支名是否正确（默认是 `master`）
3. 查看云函数日志，确认返回 204 或 200

## 监控建议

### 设置告警（可选）

1. 在云函数控制台 → 告警配置
2. 配置错误率告警：
   - 错误次数 > 0
   - 持续时间 > 5分钟
3. 可以配置邮件或短信通知

### 定期检查

建议每周检查一次：
1. GitHub Actions 运行记录（应该每天2次）
2. 云函数调用日志（查看是否有错误）
3. Token 有效期（避免过期）

## 成本说明

腾讯云函数免费额度（每月）：
- 调用次数：100万次
- 资源使用量：40万 GBs

本项目使用情况：
- 调用次数：每天2次 × 30天 = 60次/月
- 远低于免费额度，**完全免费**

## 备注

- 配置文件：`scripts/tencent_scf_trigger.py`
- GitHub Actions 工作流：`.github/workflows/daily-financial-report.yml`
- 如需切换回 GitHub Actions 原生 schedule，取消注释工作流中的 `schedule` 部分即可

---

**配置完成后，系统将自动在每天 08:15 和 20:15（北京时间）执行新闻抓取和AI分析！**
