#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

DASHBOARD_TOTAL=4
DASHBOARD_LINES=6
DASHBOARD_TITLE="Financial Report Launcher"
DASHBOARD_INTERACTIVE=0
DASHBOARD_CURRENT_STEP=0
DASHBOARD_CURRENT_STAGE="待启动"
DASHBOARD_DETAIL="初始化中"
DASHBOARD_EVENT="准备启动"
DASHBOARD_SESSION_START="$(date +%s)"
DASHBOARD_STAGE_START="$DASHBOARD_SESSION_START"

if [[ -t 1 && "${TERM:-}" != "dumb" && "${FINANCIAL_REPORT_PLAIN_LOGS:-0}" != "1" ]]; then
  DASHBOARD_INTERACTIVE=1
fi

format_elapsed() {
  local seconds="$1"
  if (( seconds < 0 )); then
    seconds=0
  fi
  local hours=$((seconds / 3600))
  local minutes=$(((seconds % 3600) / 60))
  local secs=$((seconds % 60))
  if (( hours > 0 )); then
    printf '%02d:%02d:%02d' "$hours" "$minutes" "$secs"
  else
    printf '%02d:%02d' "$minutes" "$secs"
  fi
}

progress_bar() {
  local width=20
  local filled=0
  if (( DASHBOARD_TOTAL > 0 && DASHBOARD_CURRENT_STEP > 0 )); then
    filled=$((width * DASHBOARD_CURRENT_STEP / DASHBOARD_TOTAL))
  fi
  local bar=""
  local idx=0
  while (( idx < width )); do
    if (( idx < filled )); then
      bar="${bar}="
    else
      bar="${bar}-"
    fi
    idx=$((idx + 1))
  done
  printf '%s' "$bar"
}

render_dashboard() {
  local now total_elapsed stage_elapsed
  now="$(date +%s)"
  total_elapsed="$(format_elapsed $((now - DASHBOARD_SESSION_START)))"
  stage_elapsed="$(format_elapsed $((now - DASHBOARD_STAGE_START)))"
  local stage_label="[$DASHBOARD_CURRENT_STEP/$DASHBOARD_TOTAL]"
  if (( DASHBOARD_CURRENT_STEP == 0 )); then
    stage_label="[--]"
  fi

  if (( DASHBOARD_INTERACTIVE == 1 )); then
    if [[ "${DASHBOARD_RENDERED:-0}" == "1" ]]; then
      printf '\033[%sF' "$DASHBOARD_LINES"
    fi
    printf '\033[2K\033[1;36m%s\033[0m\n' "┌─ $DASHBOARD_TITLE"
    printf '\033[2K\033[36m%s\033[0m\n' "│ 阶段  $stage_label $DASHBOARD_CURRENT_STAGE"
    printf '\033[2K\033[35m%s\033[0m\n' "│ 进度  [$(progress_bar)]  总耗时 $total_elapsed  当前阶段 $stage_elapsed"
    printf '\033[2K\033[34m%s\033[0m\n' "│ 动作  $DASHBOARD_DETAIL"
    printf '\033[2K\033[32m%s\033[0m\n' "│ 事件  $DASHBOARD_EVENT"
    printf '\033[2K\033[1;36m%s\033[0m\n' "└──────────────────────────────────────────────────────────"
    DASHBOARD_RENDERED=1
  else
    printf '[%s/%s] %s - %s\n' "$DASHBOARD_CURRENT_STEP" "$DASHBOARD_TOTAL" "$DASHBOARD_CURRENT_STAGE" "$DASHBOARD_DETAIL"
    printf '[事件] %s\n' "$DASHBOARD_EVENT"
  fi
}

dashboard_start_stage() {
  DASHBOARD_CURRENT_STEP="$1"
  DASHBOARD_CURRENT_STAGE="$2"
  DASHBOARD_DETAIL="$3"
  DASHBOARD_EVENT="$3"
  DASHBOARD_STAGE_START="$(date +%s)"
  render_dashboard
}

dashboard_update() {
  DASHBOARD_DETAIL="$1"
  DASHBOARD_EVENT="$1"
  render_dashboard
}

dashboard_finish() {
  local now elapsed
  now="$(date +%s)"
  elapsed="$(format_elapsed $((now - DASHBOARD_STAGE_START)))"
  DASHBOARD_EVENT="$1 ($elapsed)"
  render_dashboard
}

run_with_dashboard() {
  local label="$1"
  shift
  local start_ts frame_index=0
  local frames=("[=   ]" "[==  ]" "[=== ]" "[ ===]" "[  ==]" "[   =]")
  start_ts="$(date +%s)"

  "$@" &
  local pid=$!
  local rc=0

  while kill -0 "$pid" 2>/dev/null; do
    local now elapsed frame
    now="$(date +%s)"
    elapsed="$(format_elapsed $((now - start_ts)))"
    frame="${frames[$frame_index]}"
    dashboard_update "$label 进行中 $frame 已耗时 $elapsed"
    frame_index=$(((frame_index + 1) % ${#frames[@]}))
    sleep 2
  done

  set +e
  wait "$pid"
  rc=$?
  set -e

  if (( rc == 0 )); then
    dashboard_finish "$label 完成"
  else
    dashboard_finish "$label 失败，退出码 $rc"
  fi
  return "$rc"
}

echo "========================================"
echo "  财经报告系统 - macOS/Linux 一键启动"
echo "========================================"
echo

dashboard_start_stage 1 "环境检查" "检查 Python 运行环境"

if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python 3.10+"
    echo "   下载地址: https://www.python.org/downloads/"
    exit 1
fi

dashboard_finish "Python 环境检查完成"

dashboard_start_stage 2 "虚拟环境与依赖" "准备 Python 虚拟环境"

if [ ! -d "venv" ]; then
    echo "⚠️ 虚拟环境不存在，正在创建..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
    dashboard_update "已创建虚拟环境"
fi

echo "🐍 激活Python虚拟环境..."
source venv/bin/activate
dashboard_update "虚拟环境已激活"

echo "📦 检查并安装项目依赖..."
if [ -f "requirements.txt" ]; then
    if ! run_with_dashboard "升级 pip" python3 -m pip install --upgrade --quiet pip; then
      echo "⚠️ pip 升级失败，将继续使用当前版本"
    fi
    run_with_dashboard "安装 requirements.txt 依赖" pip install --quiet --disable-pip-version-check -r requirements.txt
    echo "✅ 依赖安装完成"
else
    echo "⚠️ 未找到requirements.txt，跳过依赖安装"
fi

dashboard_finish "依赖准备完成"

echo
echo "========================================"
echo "  启动选项"
echo "========================================"
echo
echo "1. 交互式运行器 (推荐)"
echo "2. AI分析脚本"
echo "3. RSS财经抓取器"
echo "4. 数据质量监控"
echo "5. 启动文档网站 (本地预览)"
echo "6. 构建部署文档 (生成静态网站)"
echo "7. 退出"
echo

dashboard_start_stage 3 "进入功能选择" "等待用户选择启动模式"
read -r -p "请选择功能 (1-7): " choice
dashboard_finish "已选择菜单项 $choice"

dashboard_start_stage 4 "执行所选任务" "准备执行菜单项 $choice"

case $choice in
    1)
        dashboard_update "启动交互式运行器"
        echo "🚀 启动交互式运行器..."
        python3 scripts/interactive_runner.py
        ;;
    2)
        dashboard_update "准备执行 AI 分析脚本"
        echo "🤖 启动AI分析脚本..."
        echo
        echo
        echo "📝 选择分析字段："
        echo "  • 1 = summary - 摘要优先（推荐，速度快，成功率85.7%）"
        echo "  • 2 = content - 正文优先（信息详细，但成功率76.5%）"
        echo "  • 3 = auto - 智能选择"
        echo
        read -r -p "请选择字段 [1/2/3，默认1]: " field_choice

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
        dashboard_update "执行 AI 分析，字段模式: $content_field"
        echo "🚀 使用DeepSeek完整报告模式，字段模式：$content_field"
        python3 scripts/ai_analyze_deepseek_verified.py --mode markdown-report --content-field "$content_field"
        ;;
    3)
        dashboard_update "准备执行 RSS 财经抓取"
        echo "📰 启动RSS财经抓取器..."
        echo

        read -r -p "是否抓取正文内容？[Y/n]: " fetch_content
        rss_cmd=(python3 scripts/rss_finance_analyzer.py)
        if [ -z "$fetch_content" ] || [ "$fetch_content" = "Y" ] || [ "$fetch_content" = "y" ]; then
            rss_cmd+=(--fetch-content)
        fi

        read -r -p "是否启用智能去重？[Y/n]: " use_dedup
        if [ -z "$use_dedup" ] || [ "$use_dedup" = "Y" ] || [ "$use_dedup" = "y" ]; then
            rss_cmd+=(--deduplicate)
        fi

        read -r -p "并发数 (默认5，输入1-20): " workers
        if [ -n "$workers" ] && [ "$workers" -ge 1 ] && [ "$workers" -le 20 ] 2>/dev/null; then
            rss_cmd+=(--max-workers "$workers")
        fi

        echo
        dashboard_update "执行 RSS 财经抓取"
        echo "🚀 执行命令: ${rss_cmd[*]}"
        echo
        "${rss_cmd[@]}"
        ;;
    4)
        dashboard_update "准备执行数据质量监控"
        echo "📊 数据质量监控..."
        echo
        read -r -p "分析最近几天的数据？(默认7天): " days
        if [ -z "$days" ]; then
            days=7
        fi

        quality_cmd=(python3 scripts/monitor_data_quality.py --days "$days")

        read -r -p "是否导出JSON报告？[y/N]: " export_json
        if [ "$export_json" = "Y" ] || [ "$export_json" = "y" ]; then
            read -r -p "输出文件名 (默认quality_report.json): " output_file
            if [ -z "$output_file" ]; then
                output_file="quality_report.json"
            fi
            quality_cmd+=(--output "$output_file")
        fi

        echo
        dashboard_update "执行数据质量监控"
        echo "🚀 执行命令: ${quality_cmd[*]}"
        echo
        "${quality_cmd[@]}"
        ;;
    5)
        dashboard_update "生成导航并启动文档网站"
        echo "🌐 启动文档网站..."
        echo "📝 正在生成导航配置..."
        python3 scripts/generate_mkdocs_nav.py
        echo "✅ 导航配置生成成功"
        echo "🚀 启动文档服务器..."
        mkdocs serve
        ;;
    6)
        dashboard_update "构建部署文档站点"
        echo "🔨 构建部署文档..."
        bash scripts/deploy.sh
        ;;
    7)
        dashboard_finish "用户选择退出"
        echo "👋 再见！"
        exit 0
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

dashboard_finish "菜单任务执行完成"

echo
echo "💡 提示：使用 'deactivate' 退出虚拟环境"
echo
