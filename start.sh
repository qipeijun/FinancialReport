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
echo "2. AI分析脚本 (DeepSeek)"
echo "3. RSS财经抓取器"
echo "4. 数据质量监控"
echo "5. 启动文档网站 (本地预览)"
echo "6. 构建部署文档 (生成静态网站)"
echo "7. 一键执行每日流程 (抓取+分析+文档)"
echo "8. 退出"
echo

read -p "请选择功能 (1-8): " choice

case $choice in
    1)
        echo "🚀 启动交互式运行器..."
        python3 scripts/interactive_runner.py
        ;;
    2)
        echo "🤖 启动AI分析脚本 (DeepSeek)..."
        echo

        echo "📝 选择分析字段："
        echo "  • 1 = summary - 摘要优先（推荐，速度快，成功率85.7%）"
        echo "  • 2 = content - 正文优先（信息详细，但成功率76.5%）"
        echo "  • 3 = auto - 智能选择"
        echo
        read -p "请选择字段 [1/2/3，默认1]: " field_choice

        content_field="summary"
        if [ "$field_choice" = "2" ]; then
            content_field="content"
            echo "✅ 已选择：正文优先"
        elif [ "$field_choice" = "3" ]; then
            content_field="auto"
            echo "✅ 已选择：智能选择"
        else
            echo "✅ 已选择：摘要优先"
        fi

        echo
        echo "🚀 使用DeepSeek模型，字段模式：$content_field"
        python3 scripts/ai_analyze_deepseek.py --content-field "$content_field"
        ;;
    3)
        echo "📰 启动RSS财经抓取器..."
        echo
        
        # 抓取正文选项
        read -p "是否抓取正文内容？[Y/n]: " fetch_content
        rss_cmd="python3 scripts/rss_finance_analyzer.py"
        if [ -z "$fetch_content" ] || [ "$fetch_content" = "Y" ] || [ "$fetch_content" = "y" ]; then
            rss_cmd="$rss_cmd --fetch-content"
        fi
        
        # 智能去重选项
        read -p "是否启用智能去重？[Y/n]: " use_dedup
        if [ -z "$use_dedup" ] || [ "$use_dedup" = "Y" ] || [ "$use_dedup" = "y" ]; then
            rss_cmd="$rss_cmd --deduplicate"
        fi
        
        # 并发数选项
        read -p "并发数 (默认5，输入1-20): " workers
        if [ ! -z "$workers" ] && [ "$workers" -ge 1 ] && [ "$workers" -le 20 ] 2>/dev/null; then
            rss_cmd="$rss_cmd --max-workers $workers"
        fi
        
        echo
        echo "🚀 执行命令: $rss_cmd"
        echo
        $rss_cmd
        ;;
    4)
        echo "📊 数据质量监控..."
        echo
        read -p "分析最近几天的数据？(默认7天): " days
        if [ -z "$days" ]; then
            days=7
        fi
        
        quality_cmd="python3 scripts/monitor_data_quality.py --days $days"
        
        read -p "是否导出JSON报告？[y/N]: " export_json
        if [ "$export_json" = "Y" ] || [ "$export_json" = "y" ]; then
            read -p "输出文件名 (默认quality_report.json): " output_file
            if [ -z "$output_file" ]; then
                output_file="quality_report.json"
            fi
            quality_cmd="$quality_cmd --output $output_file"
        fi
        
        echo
        echo "🚀 执行命令: $quality_cmd"
        echo
        $quality_cmd
        ;;
    5)
        echo "🌐 启动文档网站..."
        echo "📝 正在生成导航配置..."
        python3 scripts/generate_mkdocs_nav.py
        if [ $? -eq 0 ]; then
            echo "✅ 导航配置生成成功"
            echo "🚀 启动文档服务器..."
            mkdocs serve
        else
            echo "❌ 导航配置生成失败，请检查错误信息"
            exit 1
        fi
        ;;
    6)
        echo "🔨 构建部署文档..."
        bash scripts/deploy.sh
        ;;
    7)
        echo "🚀 一键执行每日流程..."
        echo "📋 流程：数据抓取 → AI分析 → 文档构建"
        echo

        if [ -f "scripts/daily_run.py" ]; then
            python3 scripts/daily_run.py
        else
            echo "❌ scripts/daily_run.py 不存在，请先创建该脚本"
            echo ""
            echo "💡 您也可以手动分步执行："
            echo "  1. python3 scripts/rss_finance_analyzer.py --fetch-content --deduplicate"
            echo "  2. python3 scripts/ai_analyze_deepseek.py --content-field summary"
            echo "  3. bash scripts/deploy.sh"
        fi
        ;;
    8)
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