#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

STATUS_TOTAL=4
STATUS_STEP=0
STATUS_STAGE="待启动"
STATUS_DETAIL="初始化中"
STATUS_INTERACTIVE=0
STATUS_SESSION_START="$(date +%s)"
STATUS_STAGE_START="$STATUS_SESSION_START"
STATUS_VISIBLE=0
STATUS_SUSPENDED=0

if [[ -t 1 && "${TERM:-}" != "dumb" && "${FINANCIAL_REPORT_PLAIN_LOGS:-0}" != "1" ]]; then
  STATUS_INTERACTIVE=1
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

render_status() {
  local now total_elapsed stage_elapsed line
  if (( STATUS_SUSPENDED == 1 )); then
    return
  fi
  now="$(date +%s)"
  total_elapsed="$(format_elapsed $((now - STATUS_SESSION_START)))"
  stage_elapsed="$(format_elapsed $((now - STATUS_STAGE_START)))"
  line="[$STATUS_STEP/$STATUS_TOTAL] $STATUS_STAGE · 总 $total_elapsed · 阶段 $stage_elapsed · $STATUS_DETAIL"

  if (( STATUS_INTERACTIVE == 1 )); then
    printf '\r\033[2K\033[1;36m%s\033[0m' "$line"
    STATUS_VISIBLE=1
  else
    printf '[阶段] [%s/%s] %s - %s\n' "$STATUS_STEP" "$STATUS_TOTAL" "$STATUS_STAGE" "$STATUS_DETAIL"
  fi
}

clear_status() {
  if (( STATUS_INTERACTIVE == 1 && STATUS_VISIBLE == 1 )); then
    printf '\r\033[2K'
    STATUS_VISIBLE=0
  fi
}

status_suspend() {
  STATUS_SUSPENDED=1
  clear_status
}

status_resume() {
  STATUS_SUSPENDED=0
  if (( STATUS_INTERACTIVE == 1 )); then
    render_status
  fi
}

print_log() {
  clear_status
  printf '%s\n' "$1"
  if (( STATUS_INTERACTIVE == 1 && STATUS_SUSPENDED == 0 )); then
    render_status
  fi
}

prompt_read() {
  local __var_name="$1"
  local __prompt="$2"
  local __reply
  status_suspend
  read -r -p "$__prompt" __reply
  printf -v "$__var_name" '%s' "$__reply"
  status_resume
}

status_start() {
  STATUS_STEP="$1"
  STATUS_STAGE="$2"
  STATUS_DETAIL="$3"
  STATUS_STAGE_START="$(date +%s)"
  render_status
}

status_update() {
  STATUS_DETAIL="$1"
  if (( STATUS_INTERACTIVE == 1 )); then
    render_status
  fi
}

status_finish() {
  local summary="${1:-$STATUS_STAGE}"
  STATUS_DETAIL="$summary"
  clear_status
  printf '[完成] %s (%s)\n' "$summary" "$(format_elapsed $(( $(date +%s) - STATUS_STAGE_START )))"
}

run_with_status() {
  local label="$1"
  shift
  local start_ts frame_index=0 rc=0 heartbeat_interval=6
  local frames=("·" "•")
  local details=("检查运行状态" "等待命令返回" "继续执行中")
  local fifo activity_file reader_pid pid last_activity now elapsed frame detail
  start_ts="$(date +%s)"
  fifo="$(mktemp -u "/tmp/financial-report-status.XXXXXX")"
  activity_file="$(mktemp "/tmp/financial-report-activity.XXXXXX")"
  mkfifo "$fifo"
  : > "$activity_file"

  status_suspend
  "$@" >"$fifo" 2>&1 &
  pid=$!

  (
    while IFS= read -r line; do
      touch "$activity_file"
      clear_status
      printf '%s\n' "$line"
    done <"$fifo"
  ) &
  reader_pid=$!

  while kill -0 "$pid" 2>/dev/null; do
    now="$(date +%s)"
    last_activity="$(stat -f %m "$activity_file" 2>/dev/null || printf '%s' "$start_ts")"
    if (( now - last_activity >= heartbeat_interval )); then
      elapsed="$(format_elapsed $((now - start_ts)))"
      frame="${frames[$frame_index]}"
      detail="${details[$((frame_index % ${#details[@]}))]}"
      if (( STATUS_INTERACTIVE == 1 )); then
        STATUS_SUSPENDED=0
        status_update "$detail $frame"
      else
        printf '[心跳] %s - %s (%s)\n' "$label" "$detail" "$elapsed"
      fi
    else
      STATUS_SUSPENDED=1
      clear_status
    fi
    frame_index=$(((frame_index + 1) % ${#frames[@]}))
    sleep 2
  done

  set +e
  wait "$pid"
  rc=$?
  wait "$reader_pid" 2>/dev/null
  set -e
  rm -f "$fifo" "$activity_file"
  STATUS_SUSPENDED=0

  if (( rc == 0 )); then
    status_finish "$label 完成"
  else
    status_finish "$label 失败，退出码 $rc"
  fi
  return "$rc"
}

echo "========================================"
echo "  财经报告系统 - macOS/Linux 一键启动"
echo "========================================"
echo

status_start 1 "环境准备" "检查 Python 与虚拟环境"

if ! command -v python3 &> /dev/null; then
    print_log "❌ 未检测到Python3，请先安装Python 3.10+"
    print_log "   下载地址: https://www.python.org/downloads/"
    exit 1
fi

if [ ! -d "venv" ]; then
    print_log "⚠️ 虚拟环境不存在，正在创建..."
    python3 -m venv venv
    print_log "✅ 虚拟环境创建成功"
fi

print_log "🐍 激活Python虚拟环境..."
source venv/bin/activate
status_finish "环境准备完成"

status_start 2 "依赖安装" "准备安装项目依赖"
print_log "📦 检查并安装项目依赖..."
if [ -f "requirements.txt" ]; then
    if ! run_with_status "升级 pip" python3 -m pip install --upgrade --quiet pip; then
      print_log "⚠️ pip 升级失败，将继续使用当前版本"
    fi
    run_with_status "安装项目依赖" pip install --quiet --disable-pip-version-check -r requirements.txt
    print_log "✅ 依赖安装完成"
else
    print_log "⚠️ 未找到requirements.txt，跳过依赖安装"
fi

status_finish "依赖准备完成"

print_log ""
print_log "========================================"
print_log "  启动选项"
print_log "========================================"
print_log ""
print_log "1. 交互式运行器 (推荐)"
print_log "2. AI分析脚本"
print_log "3. RSS财经抓取器"
print_log "4. 数据质量监控"
print_log "5. 启动文档网站 (本地预览)"
print_log "6. 构建部署文档 (生成静态网站)"
print_log "7. 退出"
print_log ""

status_start 3 "进入功能选择" "等待用户选择启动模式"
prompt_read choice "请选择功能 (1-7): "
status_finish "已选择菜单项 $choice"

status_start 4 "执行所选任务" "准备执行菜单项 $choice"

case $choice in
    1)
        status_update "启动交互式运行器"
        print_log "🚀 启动交互式运行器..."
        status_suspend
        python3 scripts/interactive_runner.py
        status_resume
        status_update "交互式运行器已退出"
        ;;
    2)
        status_update "准备执行 AI 分析脚本"
        print_log "🤖 启动AI分析脚本..."
        print_log ""
        print_log ""
        print_log "📝 选择分析字段："
        print_log "  • 1 = summary - 摘要优先（推荐，速度快，成功率85.7%）"
        print_log "  • 2 = content - 正文优先（信息详细，但成功率76.5%）"
        print_log "  • 3 = auto - 智能选择"
        print_log ""
        prompt_read field_choice "请选择字段 [1/2/3，默认1]: "

        content_field="summary"
        if [ "$field_choice" = "2" ]; then
            content_field="content"
            print_log "✅ 已选择：正文优先"
        elif [ "$field_choice" = "3" ]; then
            content_field="auto"
            print_log "✅ 已选择：智能选择"
        else
            print_log "✅ 已选择：摘要优先"
        fi

        print_log ""
        status_update "执行 AI 分析，字段模式: $content_field"
        print_log "🌍 选择分析市场："
        print_log "  • 1 = A 股（默认）"
        print_log "  • 2 = 美股"
        print_log ""
        prompt_read market_choice "请选择市场 [1/2，默认1]: "

        stock_market="CN"
        if [ "$market_choice" = "2" ]; then
            stock_market="US"
            print_log "✅ 已选择：美股"
        else
            print_log "✅ 已选择：A 股"
        fi

        print_log ""
        status_update "执行 AI 分析，字段模式: $content_field，市场: $stock_market"
        print_log "🚀 使用DeepSeek完整报告模式，字段模式：$content_field，市场：$stock_market"
        python3 scripts/ai_analyze_deepseek_verified.py --mode markdown-report --content-field "$content_field" --stock-market "$stock_market"
        ;;
    3)
        status_update "准备执行 RSS 财经抓取"
        print_log "📰 启动RSS财经抓取器..."
        print_log ""

        prompt_read fetch_content "是否抓取正文内容？[Y/n]: "
        rss_cmd=(python3 scripts/rss_finance_analyzer.py)
        if [ -z "$fetch_content" ] || [ "$fetch_content" = "Y" ] || [ "$fetch_content" = "y" ]; then
            rss_cmd+=(--fetch-content)
        fi

        prompt_read use_dedup "是否启用智能去重？[Y/n]: "
        if [ -z "$use_dedup" ] || [ "$use_dedup" = "Y" ] || [ "$use_dedup" = "y" ]; then
            rss_cmd+=(--deduplicate)
        fi

        prompt_read workers "并发数 (默认5，输入1-20): "
        if [ -n "$workers" ] && [ "$workers" -ge 1 ] && [ "$workers" -le 20 ] 2>/dev/null; then
            rss_cmd+=(--max-workers "$workers")
        fi

        print_log ""
        status_update "执行 RSS 财经抓取"
        print_log "🚀 执行命令: ${rss_cmd[*]}"
        print_log ""
        "${rss_cmd[@]}"
        ;;
    4)
        status_update "准备执行数据质量监控"
        print_log "📊 数据质量监控..."
        print_log ""
        prompt_read days "分析最近几天的数据？(默认7天): "
        if [ -z "$days" ]; then
            days=7
        fi

        quality_cmd=(python3 scripts/monitor_data_quality.py --days "$days")

        prompt_read export_json "是否导出JSON报告？[y/N]: "
        if [ "$export_json" = "Y" ] || [ "$export_json" = "y" ]; then
            prompt_read output_file "输出文件名 (默认quality_report.json): "
            if [ -z "$output_file" ]; then
                output_file="quality_report.json"
            fi
            quality_cmd+=(--output "$output_file")
        fi

        print_log ""
        status_update "执行数据质量监控"
        print_log "🚀 执行命令: ${quality_cmd[*]}"
        print_log ""
        "${quality_cmd[@]}"
        ;;
    5)
        status_update "生成导航并启动文档网站"
        print_log "🌐 启动文档网站..."
        print_log "📝 正在生成导航配置..."
        python3 scripts/generate_mkdocs_nav.py
        print_log "✅ 导航配置生成成功"
        print_log "🚀 启动文档服务器..."
        mkdocs serve
        ;;
    6)
        status_update "构建部署文档站点"
        print_log "🔨 构建部署文档..."
        bash scripts/deploy.sh
        ;;
    7)
        status_finish "用户选择退出"
        print_log "👋 再见！"
        exit 0
        ;;
    *)
        print_log "❌ 无效选择"
        exit 1
        ;;
esac

status_finish "菜单任务执行完成"

print_log ""
print_log "💡 提示：使用 'deactivate' 退出虚拟环境"
print_log ""
