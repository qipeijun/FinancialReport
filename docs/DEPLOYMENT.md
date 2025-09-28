# 🚀 部署说明

## 📋 部署概览

本项目使用 GitHub Pages + Docsify 进行自动部署，每次推送代码到 master 分支时，系统会自动：

1. 🧭 迁移旧结构到按月归档（archive/YYYY-MM/YYYY-MM-DD_模型）
2. 🔄 自动生成侧边栏目录（基于 archive 扫描）
3. 🌐 部署到 GitHub Pages
4. 📱 提供响应式访问界面

## 🛠️ 部署配置

### GitHub Actions 工作流

部署配置位于 `.github/workflows/run-script.yml`，包含以下步骤：

1. **检出代码** - 获取最新代码
2. **配置 Pages** - 设置 GitHub Pages 环境
3. **构建网站** - 自动生成侧边栏并复制文件
4. **上传产物** - 准备部署文件
5. **部署上线** - 发布到 GitHub Pages

### 自动目录生成

系统会自动扫描 `archive/YYYY-MM/YYYY-MM-DD_模型/` 目录，并生成包含以下内容的侧边栏：

- 📅 **分析报告** - 按日期和AI模型分类
- 🔍 **分析详情** - 热点分析和潜力分析
- 📰 **新闻内容** - 按来源分类的新闻文件
- 📡 **RSS数据源** - 原始RSS数据文件
- 🛠️ **工具配置** - 提示词文件

## 🌐 访问地址

部署完成后，可通过以下地址访问：

- **GitHub Pages**: `https://your-username.github.io/Financial-report/`
- **本地测试**: `http://localhost:3000` (使用 `python3 test_local.py`)

## 📁 文件结构

部署后的网站结构（简化）：

```
_site/
├── index.html
├── README.md
├── _sidebar.md
├── _coverpage.md
├── _404.md
└── archive/
    └── 2025-09/
        ├── 2025-09-28_gemini/
        │   ├── analysis/
        │   ├── reports/
        │   ├── news_content/
        │   └── rss_data/
        └── 2025-09-28_qwen/
            ├── analysis/
            ├── reports/
            ├── news_content/
            └── rss_data/
```

## 🔧 本地测试

### 方法一：使用测试脚本

```bash
# 运行本地测试脚本
python3 test_local.py
```

脚本会自动：
- 生成侧边栏目录
- 检查并安装 docsify-cli
- 启动本地服务器
- 打开浏览器

### 方法二：手动启动

```bash
# 1. 生成侧边栏
python3 generate_sidebar.py

# 2. 安装 docsify-cli (如果未安装)
npm install -g docsify-cli

# 3. 启动服务器
docsify serve . --port 3000
```

## 📝 自定义配置

### 修改侧边栏

编辑 `generate_sidebar.py` 文件来自定义侧边栏生成逻辑：

- 修改显示的文件数量
- 调整目录结构
- 添加自定义链接

### 修改主题

编辑 `index.html` 文件中的 Docsify 配置：

```javascript
window.$docsify = {
    name: '📊 财经分析报告系统',
    themeColor: '#42b983',  // 修改主题色
    // 其他配置...
}
```

### 添加插件

在 `index.html` 中添加更多 Docsify 插件：

```html
<!-- 添加新插件 -->
<script src="//cdn.jsdelivr.net/npm/docsify/lib/plugins/plugin-name.min.js"></script>
```

## 🚨 故障排除

### 常见问题

1. **部署失败**
   - 检查 GitHub Actions 日志
   - 确认文件路径正确
   - 验证 Python 脚本语法

2. **侧边栏不显示**
   - 确认 `_sidebar.md` 文件存在
   - 检查文件编码为 UTF-8
   - 验证 Markdown 语法

3. **文件无法访问**
   - 检查文件权限
   - 确认文件路径正确
   - 验证文件名不包含特殊字符

### 调试步骤

1. **查看构建日志**
   ```bash
   # 在 GitHub Actions 中查看详细日志
   ```

2. **本地测试**
   ```bash
   # 使用本地测试脚本
   python3 test_local.py
   ```

3. **检查文件**
   ```bash
   # 检查生成的文件
   ls -la _site/
   cat _sidebar.md
   ```

## 📈 性能优化

### 文件大小优化

- 压缩大型文本文件
- 使用 CDN 加速静态资源
- 启用 Gzip 压缩

### 加载速度优化

- 按需加载分析文件
- 使用分页显示大量内容
- 优化图片和媒体文件

## 🔄 更新流程

### 添加新报告

1. 运行分析脚本生成新报告
2. 提交代码到 GitHub
3. 系统自动部署更新

### 修改配置

1. 编辑相关配置文件
2. 测试本地效果
3. 提交并推送更改

## 📞 技术支持

如遇到部署问题，请：

1. 查看 GitHub Actions 日志
2. 检查本地测试结果
3. 提交 Issue 描述问题

---

*最后更新：2025-01-15*
