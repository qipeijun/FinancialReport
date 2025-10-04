#!/bin/bash

# macOS/Linux 一键启动脚本 - 财经报告系统

echo "========================================"
echo "  财经报告系统 - macOS/Linux 一键启动"
echo "========================================"
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python 3.10+"
    echo "   下载地址: https://www.python.org/downloads/"
    exit 1
fi

# 检查虚拟环境是否存在
if [ ! -d "venv" ]; then
    echo "⚠️ 虚拟环境不存在，正在创建..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ 虚拟环境创建失败"
        exit 1
    fi
    echo "✅ 虚拟环境创建成功"
fi

# 激活虚拟环境
echo "🐍 激活Python虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📦 检查并安装项目依赖..."
if [ -f "requirements.txt" ]; then
    python3 -m pip install --upgrade --quiet pip >/dev/null 2>&1 || true
    pip install --quiet --disable-pip-version-check -r requirements.txt || pip install -r requirements.txt
    echo "✅ 依赖安装完成"
else
    echo "⚠️ 未找到requirements.txt，跳过依赖安装"
fi

echo
echo "========================================"
echo "  启动选项"
echo "========================================"
echo
echo "1. 交互式运行器 (推荐)"
echo "2. AI分析脚本"
echo "3. RSS财经抓取器"
echo "4. 启动文档网站"
echo "5. 退出"
echo

read -p "请选择功能 (1-5): " choice

case $choice in
    1)
        echo "🚀 启动交互式运行器..."
        python3 scripts/interactive_runner.py
        ;;
    2)
        echo "🤖 启动AI分析脚本..."
        echo "🤖 选择AI模型："
        echo "  • 1 = Gemini（默认）"
        echo "  • 2 = DeepSeek"
        echo
        read -p "请选择模型 [1/2，默认1]: " model_choice
        if [ -z "$model_choice" ] || [ "$model_choice" = "1" ]; then
            echo "已选择：Gemini"
            python3 scripts/ai_analyze.py
        elif [ "$model_choice" = "2" ]; then
            echo "已选择：DeepSeek"
            python3 scripts/ai_analyze_deepseek.py
        else
            echo "❌ 无效选择，使用默认Gemini"
            python3 scripts/ai_analyze.py
        fi
        ;;
    3)
        echo "📰 启动RSS财经抓取器..."
        python3 scripts/rss_finance_analyzer.py
        ;;
    4)
        echo "🌐 启动文档网站..."
        mkdocs serve
        ;;
    5)
        echo "👋 再见！"
        exit 0
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo
echo "💡 提示：使用 'deactivate' 退出虚拟环境"
echo