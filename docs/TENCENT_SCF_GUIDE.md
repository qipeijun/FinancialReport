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
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云函数（SCF）触发器 - 定时触发 GitHub Actions
用途：解决 GitHub Actions schedule 不准时的问题

使用方法：
1. 在腾讯云函数中创建新函数，复制此代码
2. 配置环境变量：GITHUB_TOKEN, GITHUB_REPO, WORKFLOW_ID (可选)
3. 设置定时触发器（Cron 表达式）

注意：
- 使用 Python 内置库 urllib，无需安装额外依赖
- 腾讯云函数已验证可用
"""

import os
import json
from urllib import request, error
from urllib.request import HTTPRedirectHandler
from datetime import datetime


class HTTPPostRedirectHandler(HTTPRedirectHandler):
    """处理 POST 请求的重定向
    
    GitHub API 可能返回 307 重定向，需要保持 POST 方法和数据
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code in [301, 302, 303, 307, 308]:
            # 保持原始请求的 method、data 和 headers
            return request.Request(
                newurl,
                data=req.data,
                headers=req.headers,
                method=req.get_method()
            )
        return None


def main_handler(event, context):
    """
    腾讯云函数入口
    
    Args:
        event: 触发事件数据
        context: 运行时上下文
    
    Returns:
        dict: 执行结果
    """
    print("=" * 60)
    print("🚀 腾讯云函数触发器启动")
    print(f"⏰ 触发时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 从环境变量获取配置
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo = os.environ.get('GITHUB_REPO')  # 格式: owner/repo
    workflow_id = os.environ.get('WORKFLOW_ID', 'daily-financial-report.yml')
    
    # 参数校验
    if not github_token:
        error_msg = "❌ 错误: 未设置 GITHUB_TOKEN 环境变量"
        print(error_msg)
        return {
            'statusCode': 400,
            'body': json.dumps({'error': error_msg}, ensure_ascii=False)
        }
    
    if not github_repo:
        error_msg = "❌ 错误: 未设置 GITHUB_REPO 环境变量"
        print(error_msg)
        return {
            'statusCode': 400,
            'body': json.dumps({'error': error_msg}, ensure_ascii=False)
        }
    
    print(f"📦 仓库: {github_repo}")
    print(f"📄 工作流: {workflow_id}")
    
    # 构建 GitHub API 请求
    api_url = f"https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_id}/dispatches"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'Tencent-SCF-Trigger/1.0'
    }
    
    # 请求体（可选参数）
    payload = {
        'ref': 'master',  # 触发的分支
        'inputs': {
            'skip_fetch': 'false',
            'skip_analysis': 'false'
        }
    }
    
    payload_encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    
    try:
        print(f"📡 发送请求到: {api_url}")
        print(f"📋 请求体: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        # 使用自定义重定向处理器
        opener = request.build_opener(HTTPPostRedirectHandler())
        request.install_opener(opener)
        
        req = request.Request(api_url, data=payload_encoded, headers=headers, method='POST')
        response = request.urlopen(req, timeout=10)
        status = response.status
        
        print(f"📊 响应状态码: {status}")
        
        if status == 204 or status == 200:
            success_msg = "✅ 成功触发 GitHub Actions!"
            print(success_msg)
            print(f"🔗 查看工作流: https://github.com/{github_repo}/actions")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': success_msg,
                    'trigger_time': datetime.now().isoformat(),
                    'repo': github_repo,
                    'workflow': workflow_id
                }, ensure_ascii=False)
            }
        else:
            error_msg = f"⚠️ 意外状态码: {status}"
            print(error_msg)
            return {
                'statusCode': status,
                'body': json.dumps({'message': error_msg}, ensure_ascii=False)
            }
    
    except error.HTTPError as e:
        # GitHub API 的 204 响应可能被当作错误处理
        if e.code == 204:
            success_msg = "✅ 成功触发 GitHub Actions (204)!"
            print(success_msg)
            print(f"🔗 查看工作流: https://github.com/{github_repo}/actions")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': success_msg,
                    'trigger_time': datetime.now().isoformat()
                }, ensure_ascii=False)
            }
        else:
            error_msg = f"❌ HTTP 错误: {e.code} - {e.reason}"
            print(error_msg)
            # 尝试读取错误详情
            try:
                error_body = e.read().decode('utf-8')
                print(f"📄 错误详情: {error_body}")
            except:
                pass
            return {
                'statusCode': e.code,
                'body': json.dumps({
                    'error': error_msg,
                    'code': e.code
                }, ensure_ascii=False)
            }
    
    except error.URLError as e:
        error_msg = f"⏱️ 网络错误: {str(e.reason)}"
        print(error_msg)
        return {
            'statusCode': 408,
            'body': json.dumps({'error': error_msg}, ensure_ascii=False)
        }
    
    except Exception as e:
        error_msg = f"❌ 发生异常: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg,
                'traceback': traceback.format_exc()
            }, ensure_ascii=False)
        }


# 本地测试（需要设置环境变量）
if __name__ == '__main__':
    print("🧪 本地测试模式")
    print("请先设置环境变量:")
    print("  export GITHUB_TOKEN='your_github_token'")
    print("  export GITHUB_REPO='owner/repo'")
    print("  export WORKFLOW_ID='daily-financial-report.yml'")
    print("")
    
    # 模拟腾讯云函数调用
    result = main_handler({}, None)
    print("")
    print("=" * 60)
    print("📊 执行结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60)

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
