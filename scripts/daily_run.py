#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日流程一键执行脚本

按顺序执行以下步骤：
1. 清理数据库（可选，默认执行，保留最近30天数据）
2. 抓取RSS财经新闻
3. DeepSeek AI分析生成报告
4. 生成MkDocs导航配置
5. 构建MkDocs站点（可选，默认执行）

用法：
    python3 scripts/daily_run.py                           # 完整流程（清理+抓取+分析+导航+构建）
    python3 scripts/daily_run.py --skip-cleanup            # 跳过数据库清理
    python3 scripts/daily_run.py --skip-build              # 跳过 mkdocs build
    python3 scripts/daily_run.py --year-month 2026-06      # 指定分析月份
    python3 scripts/daily_run.py --date 2026-06-23         # 指定单日分析
    python3 scripts/daily_run.py --no-fetch-content        # 不抓取正文，仅用摘要
    python3 scripts/daily_run.py --skip-cleanup --skip-build  # 仅抓取+分析+导航
"""

import argparse
import calendar
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 项目根目录（本脚本位于 scripts/ 下）
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def log(msg: str, level: str = "INFO") -> None:
    """带时间戳的日志输出，不同级别使用不同前缀"""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "INFO": "   ",
        "STEP": "▶  ",
        "OK":   "✅ ",
        "ERR":  "❌ ",
        "WARN": "⚠️  ",
        "H1":   "📌 ",
    }.get(level, "   ")
    print(f"[{ts}] {prefix}{msg}")


def log_section(title: str) -> None:
    """打印步骤分隔标题"""
    print()
    print("─" * 56)
    print(f"  {title}")
    print("─" * 56)


def find_python() -> str:
    """
    查找Python解释器，优先级：
    1. 项目虚拟环境 (venv/bin/python)
    2. Windows虚拟环境 (venv/Scripts/python.exe)
    3. 当前运行的Python解释器
    """
    candidates = [
        PROJECT_ROOT / "venv" / "bin" / "python",
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    """
    在项目根目录下执行命令
    所有脚本均以 PROJECT_ROOT 为工作目录，确保 generate_mkdocs_nav.py
    等依赖相对路径的脚本能正确运行
    """
    return subprocess.run(cmd, cwd=PROJECT_ROOT)


def run_step(title: str, cmd: List[str]) -> bool:
    """
    执行一个步骤，打印耗时和结果
    返回 True 表示成功，False 表示失败
    """
    log_section(title)
    log(f"执行: {' '.join(cmd)}", "STEP")
    start = time.time()

    try:
        proc = run_cmd(cmd)
        elapsed = time.time() - start

        if proc.returncode == 0:
            log(f"完成（耗时 {elapsed:.1f}s）", "OK")
            return True
        else:
            log(f"失败，返回码 {proc.returncode}（耗时 {elapsed:.1f}s）", "ERR")
            return False
    except FileNotFoundError as e:
        elapsed = time.time() - start
        log(f"命令未找到: {e}", "ERR")
        return False
    except Exception as e:
        elapsed = time.time() - start
        log(f"执行异常: {e}", "ERR")
        return False


def parse_args() -> argparse.Namespace:
    """解析命令行参数，包含格式校验"""
    parser = argparse.ArgumentParser(
        description="一键执行每日财经分析完整流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                   完整流程
  %(prog)s --skip-cleanup                    跳过数据库清理
  %(prog)s --skip-build                      跳过 mkdocs build
  %(prog)s --year-month 2026-06              分析指定月份的新闻
  %(prog)s --date 2026-06-23                 分析指定单日
  %(prog)s --no-fetch-content                不抓取正文，仅用摘要
  %(prog)s --content-field content           使用正文进行AI分析
        """,
    )

    parser.add_argument(
        "--skip-cleanup", action="store_true",
        help="跳过数据库清理步骤",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="跳过 mkdocs build 步骤",
    )
    parser.add_argument(
        "--year-month", type=str, default=None, metavar="YYYY-MM",
        help="指定分析月份（如 2026-06），默认分析当天",
    )
    parser.add_argument(
        "--date", type=str, default=None, metavar="YYYY-MM-DD",
        help="指定分析单日（如 2026-06-23），与 --year-month 互斥",
    )
    parser.add_argument(
        "--fetch-content", action="store_true", default=True,
        help="抓取新闻正文（默认开启）",
    )
    parser.add_argument(
        "--no-fetch-content", dest="fetch_content", action="store_false",
        help="不抓取正文，仅使用摘要",
    )
    parser.add_argument(
        "--model", type=str, default="deepseek-chat",
        help="DeepSeek 模型名称（默认 deepseek-chat）",
    )
    parser.add_argument(
        "--content-field", choices=["summary", "content", "auto"],
        default="summary",
        help="AI分析使用的字段：summary（摘要）、content（正文）、auto（智能选择），默认 summary",
    )

    args = parser.parse_args()

    # --year-month 与 --date 互斥
    if args.year_month and args.date:
        parser.error("--year-month 与 --date 不能同时使用")

    # year_month 格式校验
    if args.year_month:
        parts = args.year_month.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            parser.error(f"--year-month 格式错误: '{args.year_month}'，应为 YYYY-MM")
        try:
            int(parts[0])
            int(parts[1])
        except ValueError:
            parser.error(f"--year-month 格式错误: '{args.year_month}'，应为 YYYY-MM")

    # date 格式校验
    if args.date:
        parts = args.date.split("-")
        if len(parts) != 3 or len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
            parser.error(f"--date 格式错误: '{args.date}'，应为 YYYY-MM-DD")

    return args


def compute_month_range(year_month: str) -> tuple:
    """根据 YYYY-MM 格式计算该月的起止日期 (start, end)"""
    year_str, month_str = year_month.split("-")
    year = int(year_str)
    month = int(month_str)
    start = f"{year}-{month:02d}-01"
    end_day = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{end_day:02d}"
    return start, end


def main() -> int:
    args = parse_args()
    python = find_python()
    today = datetime.now().strftime("%Y-%m-%d")

    # 各步骤执行结果，用于最终摘要
    results: Dict[str, str] = {}

    # 启动横幅
    print()
    print("=" * 56)
    print(f"  每日财经分析一键流程")
    print(f"  日期: {today}")
    print(f"  项目: {PROJECT_ROOT}")
    print("=" * 56)

    # ================================================================
    # 步骤1：清理数据库（可选）
    # ================================================================
    if args.skip_cleanup:
        log("跳过数据库清理（--skip-cleanup）", "WARN")
        results["清理数据库"] = "跳过"
    else:
        cleanup_script = PROJECT_ROOT / "scripts" / "cleanup_db.py"
        success = run_step(
            "步骤 1/5: 清理数据库（保留最近30天）",
            [python, str(cleanup_script), "--days", "30"],
        )
        results["清理数据库"] = "成功" if success else "失败"
        if not success:
            log("数据库清理失败，继续执行后续步骤", "WARN")

    # ================================================================
    # 步骤2：抓取RSS财经新闻
    # ================================================================
    rss_script = PROJECT_ROOT / "scripts" / "rss_finance_analyzer.py"
    rss_cmd = [python, str(rss_script)]
    if args.fetch_content:
        rss_cmd.append("--fetch-content")

    success = run_step("步骤 2/5: 抓取RSS财经新闻", rss_cmd)
    results["抓取RSS新闻"] = "成功" if success else "失败"
    if not success:
        log("RSS抓取失败，继续后续步骤（可能已有历史数据可用）", "WARN")

    # ================================================================
    # 步骤3：DeepSeek AI分析生成报告
    # ================================================================
    ai_script = PROJECT_ROOT / "scripts" / "ai_analyze_deepseek.py"
    ai_cmd = [
        python, str(ai_script),
        "--content-field", args.content_field,
        "--model", args.model,
    ]

    # 构建日期参数和日志描述
    if args.date:
        ai_cmd += ["--date", args.date]
        date_desc = args.date
    elif args.year_month:
        start, end = compute_month_range(args.year_month)
        ai_cmd += ["--start", start, "--end", end]
        date_desc = f"{start} ~ {end}"
    else:
        # 不传日期参数，ai_analyze_deepseek.py 默认分析当天
        date_desc = f"{today}（当天）"

    success = run_step(
        f"步骤 3/5: DeepSeek AI 分析（{date_desc}）",
        ai_cmd,
    )
    results["AI分析"] = "成功" if success else "失败"
    if not success:
        log("AI分析失败，继续执行后续步骤", "WARN")

    # ================================================================
    # 步骤4：生成MkDocs导航配置
    # ================================================================
    nav_script = PROJECT_ROOT / "scripts" / "generate_mkdocs_nav.py"
    success = run_step(
        "步骤 4/5: 生成MkDocs导航配置",
        [python, str(nav_script)],
    )
    results["生成导航"] = "成功" if success else "失败"

    # ================================================================
    # 步骤5：构建MkDocs站点（可选）
    # ================================================================
    if args.skip_build:
        log("跳过 mkdocs build（--skip-build）", "WARN")
        results["构建站点"] = "跳过"
    else:
        success = run_step(
            "步骤 5/5: 构建MkDocs站点",
            ["mkdocs", "build"],
        )
        results["构建站点"] = "成功" if success else "失败"

    # ================================================================
    # 执行摘要
    # ================================================================
    print()
    print("=" * 56)
    print("  执行摘要")
    print("=" * 56)
    for step_name, status in results.items():
        if status == "成功":
            icon = "✅"
        elif status == "跳过":
            icon = "⏭️ "
        else:
            icon = "❌"
        print(f"  {icon}  {step_name}: {status}")
    print("=" * 56)

    # 判断整体结果
    failed_steps = [k for k, v in results.items() if v == "失败"]
    if failed_steps:
        log(f"以下步骤执行失败: {', '.join(failed_steps)}", "WARN")
        return 1
    else:
        log("全部步骤执行完成", "OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
