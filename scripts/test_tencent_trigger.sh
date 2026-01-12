#!/bin/bash
# 腾讯云函数触发器本地测试脚本
#
# 使用方法：
# 1. 设置环境变量：
#    export GITHUB_TOKEN='ghp_your_token'
#    export GITHUB_REPO='qipeijun/FinancialReport'
# 2. 运行测试：./scripts/test_tencent_trigger.sh

set -e

echo "=================================="
echo "🧪 腾讯云函数触发器本地测试"
echo "=================================="
echo ""

# 检查环境变量
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ 错误: 未设置 GITHUB_TOKEN 环境变量"
    echo ""
    echo "请先设置:"
    echo "  export GITHUB_TOKEN='ghp_your_token'"
    echo "  export GITHUB_REPO='qipeijun/FinancialReport'"
    exit 1
fi

if [ -z "$GITHUB_REPO" ]; then
    echo "⚠️  警告: 未设置 GITHUB_REPO，使用默认值"
    export GITHUB_REPO="qipeijun/FinancialReport"
fi

echo "📋 配置信息:"
echo "  仓库: $GITHUB_REPO"
echo "  Token: ${GITHUB_TOKEN:0:10}..."
echo ""

# 运行测试
echo "🚀 开始测试..."
echo ""

python3 scripts/tencent_scf_trigger.py

echo ""
echo "=================================="
echo "✅ 测试完成"
echo "=================================="
echo ""
echo "📝 下一步:"
echo "1. 检查上方输出是否显示 '✅ 成功触发 GitHub Actions'"
echo "2. 访问 https://github.com/$GITHUB_REPO/actions"
echo "3. 确认是否有新的工作流运行记录"
echo ""
