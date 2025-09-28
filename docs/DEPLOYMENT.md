# MkDocs + Material 部署指南

## 概述

本项目已配置为使用 MkDocs + Material 主题来构建和部署文档网站。通过 GitHub Actions 自动部署到 GitHub Pages。

## 系统架构

```
项目结构
├── mkdocs.yml              # MkDocs 配置文件
├── docs/                   # 文档源文件目录
│   ├── index.md           # 首页
│   ├── README.md          # 项目说明
│   ├── archive/           # 分析报告存档
│   └── prompts/           # 提示词配置
├── .github/workflows/     # GitHub Actions 工作流
│   └── deploy-mkdocs.yml  # 部署工作流
└── scripts/               # 辅助脚本
    └── generate_mkdocs_nav.py  # 自动生成导航
```

## 主要特性

### 🎨 Material 主题
- **响应式设计**：支持桌面和移动设备
- **深色/浅色模式**：自动切换主题
- **中文支持**：完整的中文界面
- **搜索功能**：全文搜索支持
- **导航增强**：标签页、章节导航等

### 📊 自动导航生成
- 自动扫描 `archive` 目录结构
- 按月份和日期组织报告
- 动态生成导航菜单
- 支持多种文件类型

### 🚀 自动化部署
- GitHub Actions 自动构建
- 推送到 main 分支自动部署
- GitHub Pages 自动发布
- 支持 PR 预览

## 本地开发

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动开发服务器

```bash
mkdocs serve
```

访问 http://127.0.0.1:8000 查看本地预览。

### 构建静态网站

```bash
mkdocs build
```

生成的静态文件在 `site/` 目录中。

## 部署配置

### 1. GitHub Pages 设置

1. 进入仓库的 Settings 页面
2. 找到 Pages 设置
3. 选择 "GitHub Actions" 作为源

### 2. 更新仓库信息

在 `mkdocs.yml` 中更新以下配置：

```yaml
site_url: https://your-username.github.io/Financial-report
repo_name: your-username/Financial-report
repo_url: https://github.com/your-username/Financial-report
```

### 3. 自动部署

推送代码到 main 分支后，GitHub Actions 会自动：

1. 安装依赖
2. 构建文档
3. 部署到 GitHub Pages

## 导航管理

### 自动生成导航

运行以下命令自动生成导航配置：

```bash
python3 scripts/generate_mkdocs_nav.py
```

### 手动编辑导航

在 `mkdocs.yml` 中的 `nav` 部分手动编辑：

```yaml
nav:
  - 首页: index.md
  - 项目介绍:
    - 项目说明: README.md
  - 分析报告:
    - 2025年09月:
      - 2025-09-28:
        - 财经分析报告: archive/2025-09/2025-09-28_qwen/reports/财经分析报告_20250928.md
```

## 自定义配置

### 主题配置

在 `mkdocs.yml` 中自定义主题：

```yaml
theme:
  name: material
  language: zh
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: blue
      accent: blue
```

### 插件配置

添加更多插件：

```yaml
plugins:
  - search:
      lang: zh
  - git-revision-date-localized:
      enable_creation_date: true
```

## 故障排除

### 常见问题

1. **构建失败**：检查 `mkdocs.yml` 语法
2. **页面404**：确认文件路径正确
3. **导航不显示**：运行导航生成脚本
4. **样式问题**：检查 Material 主题配置

### 调试命令

```bash
# 详细构建信息
mkdocs build --verbose

# 检查配置
mkdocs config

# 清理构建目录
rm -rf site/
```

## 更新日志

- **2025-09-28**：初始 MkDocs + Material 配置
- **2025-09-28**：添加自动导航生成
- **2025-09-28**：配置 GitHub Actions 部署

## 相关链接

- [MkDocs 官方文档](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Pages](https://pages.github.com/)
- [GitHub Actions](https://github.com/features/actions)