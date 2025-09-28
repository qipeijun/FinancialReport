#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地测试脚本
用于在本地启动 Docsify 服务器进行测试
"""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

def check_docsify():
    """检查是否安装了 docsify-cli"""
    try:
        result = subprocess.run(['docsify', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✅ Docsify CLI 已安装: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docsify CLI 未安装")
        return False

def install_docsify():
    """安装 docsify-cli"""
    print("🔄 正在安装 docsify-cli...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'docsify-cli', '-g'], 
                      check=True)
        print("✅ Docsify CLI 安装成功")
        return True
    except subprocess.CalledProcessError:
        print("❌ Docsify CLI 安装失败")
        return False

def generate_sidebar():
    """生成侧边栏"""
    print("🔄 生成侧边栏目录...")
    try:
        subprocess.run([sys.executable, 'generate_sidebar.py'], check=True)
        print("✅ 侧边栏生成成功")
        return True
    except subprocess.CalledProcessError:
        print("❌ 侧边栏生成失败")
        return False

def start_server():
    """启动本地服务器"""
    print("🚀 启动本地 Docsify 服务器...")
    try:
        # 启动服务器
        process = subprocess.Popen(['docsify', 'serve', '.', '--port', '3000'])
        
        # 等待服务器启动
        import time
        time.sleep(2)
        
        # 打开浏览器
        webbrowser.open('http://localhost:3000')
        
        print("✅ 服务器已启动")
        print("🌐 访问地址: http://localhost:3000")
        print("📝 按 Ctrl+C 停止服务器")
        
        # 等待用户中断
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n🛑 正在停止服务器...")
            process.terminate()
            print("✅ 服务器已停止")
        
        return True
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        return False

def main():
    """主函数"""
    print("🔧 财经分析报告系统 - 本地测试工具")
    print("=" * 50)
    
    # 检查当前目录
    if not os.path.exists('index.html'):
        print("❌ 请在项目根目录下运行此脚本")
        return
    
    # 生成侧边栏
    if not generate_sidebar():
        return
    
    # 检查 docsify
    if not check_docsify():
        if not install_docsify():
            return
    
    # 启动服务器
    start_server()

if __name__ == "__main__":
    main()
