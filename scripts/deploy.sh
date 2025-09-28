#!/bin/bash
# -*- coding: utf-8 -*-
"""
MkDocs 部署脚本
自动生成导航、构建文档并部署

使用方法：
1. 本地部署：./scripts/deploy.sh
2. 推送到 GitHub 后会自动运行此脚本

功能：
- 自动生成 MkDocs 导航配置
- 构建静态文档网站
- 准备部署到 GitHub Pages
"""

echo "🚀 开始部署 MkDocs 文档..."

# 检查是否安装了必要的依赖
# 如果 MkDocs 未安装，自动安装依赖包
if ! command -v mkdocs &> /dev/null; then
    echo "❌ MkDocs 未安装，正在安装..."
    pip install -r requirements.txt
fi

# 生成导航配置
# 扫描 docs/archive 目录，自动生成 mkdocs.yml 中的 nav 配置
# 这样新增的报告会自动出现在导航菜单中
echo "📝 生成导航配置..."
python3 scripts/generate_mkdocs_nav.py

# 构建文档
# 使用 MkDocs 将 Markdown 文件转换为静态 HTML 网站
# 输出到 site/ 目录
echo "🔨 构建文档..."
mkdocs build

# 检查构建是否成功
# 如果构建失败，脚本会退出并显示错误信息
if [ $? -eq 0 ]; then
    echo "✅ 文档构建成功！"
    echo "📁 静态文件已生成到 site/ 目录"
    echo "🌐 可以通过以下方式预览："
    echo "   - 本地预览: mkdocs serve"
    echo "   - 静态文件: 打开 site/index.html"
else
    echo "❌ 文档构建失败！"
    echo "💡 请检查："
    echo "   1. mkdocs.yml 配置是否正确"
    echo "   2. docs/ 目录下的文件是否存在"
    echo "   3. 导航配置是否有效"
    exit 1
fi

echo "🎉 部署准备完成！"
echo "💡 提示："
echo "   - 推送到 GitHub 后会自动部署到 GitHub Pages"
echo "   - 每次新增报告后，导航会自动更新"
echo "   - 无需手动修改 mkdocs.yml 文件"
