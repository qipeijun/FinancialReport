@echo off
REM Windows 一键启动脚本 - 财经报告系统

echo ========================================
echo   财经报告系统 - Windows 一键启动
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未检测到Python，请先安装Python 3.10+
    echo   下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查虚拟环境是否存在
if not exist "venv\Scripts\activate.bat" (
    echo ⚠️ 虚拟环境不存在，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo ✅ 虚拟环境创建成功
)

REM 激活虚拟环境
echo 🐍 激活Python虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 📦 检查并安装项目依赖...
if exist "requirements.txt" (
    python -m pip install --upgrade pip >nul 2>&1
    pip install -r requirements.txt >nul 2>&1
    echo ✅ 依赖安装完成
) else (
    echo ⚠️ 未找到requirements.txt，跳过依赖安装
)

echo.
echo ========================================
echo   启动选项
echo ========================================
echo.
echo 1. 交互式运行器 (推荐)
echo 2. AI分析脚本
echo 3. RSS财经抓取器
echo 4. 启动文档网站
echo 5. 退出
echo.

set /p choice="请选择功能 (1-5): "

if "%choice%"=="1" (
    echo 🚀 启动交互式运行器...
    python scripts\interactive_runner.py
) else if "%choice%"=="2" (
    echo 🤖 启动AI分析脚本...
    python scripts\ai_analyze.py --help
) else if "%choice%"=="3" (
    echo 📰 启动RSS财经抓取器...
    python scripts\rss_finance_analyzer.py --help
) else if "%choice%"=="4" (
    echo 🌐 启动文档网站...
    mkdocs serve
) else if "%choice%"=="5" (
    echo 👋 再见！
    pause
    exit /b 0
) else (
    echo ❌ 无效选择
    pause
    exit /b 1
)

echo.
echo 💡 提示：使用 'deactivate' 退出虚拟环境
echo.
pause