#!/bin/bash
# 激活虚拟环境的便捷脚本

echo "🐍 激活Python虚拟环境..."
source venv/bin/activate

echo "✅ 虚拟环境已激活！"
echo "📦 已安装的包："
pip list

echo ""
echo "🚀 可用的命令："
echo "  python scripts/interactive_runner.py  # 交互式运行器"
echo "  python scripts/ai_analyze.py --help   # AI分析脚本帮助"
echo "  python scripts/rss_finance_analyzer.py --help  # RSS抓取脚本帮助"
echo ""
echo "💡 提示：使用 'deactivate' 退出虚拟环境"
