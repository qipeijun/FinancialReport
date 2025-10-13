# 腾讯云函数定时触发 - 配置指南

## 🎯 解决什么问题

GitHub Actions 定时任务延迟 15-60 分钟 → 改用腾讯云函数准时触发（延迟 < 1 分钟）

---

## 📋 配置步骤（10分钟）

### 1️⃣ 获取 GitHub Token

访问：https://github.com/settings/tokens

1. 点击 **Generate new token (classic)**
2. 勾选权限：`repo` + `workflow`
3. 复制 Token（格式：`ghp_xxxxx`）

### 2️⃣ 创建腾讯云函数

访问：https://console.cloud.tencent.com/scf

**基础配置：**
- 函数名称：`github-trigger`
- 运行环境：`Python 3.9`
- 执行超时：`10秒`

**代码（完整复制）：**

```python
import os
import json
import requests
from datetime import datetime

def main_handler(event, context):
    """触发 GitHub Actions"""
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo = os.environ.get('GITHUB_REPO')
    workflow_id = os.environ.get('WORKFLOW_ID', 'daily-financial-report.yml')
    
    if not github_token or not github_repo:
        return {'statusCode': 400, 'body': '缺少配置'}
    
    api_url = f"https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_id}/dispatches"
    
    response = requests.post(
        api_url,
        headers={
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        },
        json={'ref': 'master', 'inputs': {}},
        timeout=10
    )
    
    if response.status_code == 204:
        print(f"✅ 触发成功: {datetime.now()}")
        return {'statusCode': 200, 'body': '成功'}
    else:
        print(f"❌ 失败: {response.status_code}")
        return {'statusCode': 500, 'body': response.text}
```

**环境变量（在函数配置页面添加）：**

```bash
GITHUB_TOKEN=ghp_你的Token
GITHUB_REPO=qipeijun/Financial-report
WORKFLOW_ID=daily-financial-report.yml
```

### 3️⃣ 设置定时触发

添加 2 个触发器：

| 名称 | Cron 表达式 | 触发时间 |
|-----|------------|---------|
| morning | `0 0 * * *` | 北京 08:00 |
| evening | `0 12 * * *` | 北京 20:00 |

> ⚠️ 腾讯云用 UTC 时间，北京时间 = UTC + 8 小时

### 4️⃣ 测试

点击"测试"按钮 → 查看日志是否显示"✅ 触发成功" → 访问 https://github.com/qipeijun/Financial-report/actions 确认

✅ **完成！**

---

## ⏰ 时区转换表

| 北京时间 | Cron 表达式 |
|---------|------------|
| 06:00 | `0 22 * * *` |
| 08:00 | `0 0 * * *` |
| 12:00 | `0 4 * * *` |
| 20:00 | `0 12 * * *` |

---

## 🔧 常见问题

**401 错误** → Token 无效，检查权限是否包含 `workflow`  
**404 错误** → 工作流文件名错误，确认 `WORKFLOW_ID` 正确  
**时间不对** → 使用上面的转换表  

---

## 💰 成本

完全免费（免费额度：100万次/月，本项目用 60次/月）

---

📅 2025-10-13 | 触发器代码：`scripts/tencent_scf_trigger.py`
