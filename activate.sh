#!/bin/bash
# 激活虚拟环境的便捷脚本

echo "🐍 激活Python虚拟环境..."
source venv/bin/activate

echo "✅ 虚拟环境已激活！"

# 自动安装项目依赖
if [ -f requirements.txt ]; then
  echo "📦 正在升级 pip 并安装依赖..."
  python -m pip install --upgrade --quiet pip >/dev/null 2>&1 || true
  pip install --quiet --disable-pip-version-check -r requirements.txt || pip install -r requirements.txt
  echo "🔎 校验依赖完整性（pip check）..."
  pip check || echo "⚠️ 依赖校验发现问题，请根据提示修复或重新安装。"
else
  echo "⚠️ 未找到 requirements.txt，跳过批量依赖安装。"
fi

# 展示已安装的包
echo "📦 已安装的包："
pip list

echo ""
echo "🚀 可用的命令："
echo "  python3 scripts/interactive_runner.py  # 交互式运行器"
echo "  python3 scripts/ai_analyze.py --help   # AI分析脚本帮助"
echo "  python3 scripts/rss_finance_analyzer.py --help  # RSS抓取脚本帮助"
echo ""
echo "💡 提示：使用 'deactivate' 退出虚拟环境"
