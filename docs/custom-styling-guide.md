# 🎨 自定义样式指南

本指南详细说明如何自定义 MkDocs Material 主题的样式。

## 📁 文件结构

```
docs/
├── stylesheets/
│   └── extra.css          # 自定义样式文件
├── mkdocs.yml             # MkDocs 配置文件
└── custom-styling-guide.md # 本指南
```

## 🔧 配置方法

### 1. 在 mkdocs.yml 中添加自定义样式

```yaml
theme:
  name: material
  # ... 其他配置
  
# 自定义样式
extra_css:
  - stylesheets/extra.css
```

### 2. 创建自定义 CSS 文件

在 `docs/stylesheets/extra.css` 中编写自定义样式。

## 🎨 样式自定义方法

### 方法一：CSS 变量覆盖

```css
:root {
  /* 覆盖 Material 主题的 CSS 变量 */
  --md-primary-fg-color: #1976d2;
  --md-primary-fg-color--light: #42a5f5;
  --md-primary-fg-color--dark: #1565c0;
  --md-accent-fg-color: #ff4081;
}
```

### 方法二：直接样式覆盖

```css
/* 覆盖导航栏样式 */
.md-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* 覆盖内容区域样式 */
.md-content h1 {
  color: var(--md-primary-fg-color);
  border-bottom: 2px solid var(--md-primary-fg-color--light);
}
```

### 方法三：添加自定义 CSS 类

```css
/* 财经主题特殊样式 */
.financial-highlight {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
}

.financial-card {
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  margin: 1rem 0;
  transition: transform 0.3s ease;
}
```

## 🎯 常用样式定制

### 1. 颜色主题

```css
/* 浅色主题 */
[data-md-color-scheme="default"] {
  --md-primary-fg-color: #1976d2;
  --md-accent-fg-color: #ff4081;
}

/* 深色主题 */
[data-md-color-scheme="slate"] {
  --md-primary-fg-color: #42a5f5;
  --md-accent-fg-color: #ff4081;
}
```

### 2. 字体设置

```css
:root {
  --md-text-font: "Roboto", "Helvetica Neue", Arial, sans-serif;
  --md-code-font: "Roboto Mono", "Consolas", monospace;
}
```

### 3. 导航栏样式

```css
.md-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.md-header__title {
  font-weight: 600;
  font-size: 1.2rem;
}
```

### 4. 侧边栏样式

```css
.md-nav__title {
  font-weight: 600;
  color: var(--md-primary-fg-color);
}

.md-nav__item--nested > .md-nav__link {
  font-weight: 500;
}
```

### 5. 内容区域样式

```css
.md-content {
  line-height: 1.7;
}

.md-content h1 {
  color: var(--md-primary-fg-color);
  border-bottom: 2px solid var(--md-primary-fg-color--light);
  padding-bottom: 0.5rem;
}
```

### 6. 代码块样式

```css
.md-typeset pre > code {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}
```

### 7. 表格样式

```css
.md-typeset table:not([class]) {
  border: 1px solid #e9ecef;
  border-radius: 8px;
  overflow: hidden;
}

.md-typeset table:not([class]) th {
  background: var(--md-primary-fg-color--light);
  color: white;
  font-weight: 600;
}
```

### 8. 按钮样式

```css
.md-button {
  border-radius: 6px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.md-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
```

## 🎭 动画效果

### 1. 页面加载动画

```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.md-content__inner {
  animation: fadeInUp 0.6s ease-out;
}
```

### 2. 悬停效果

```css
.financial-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
}
```

## 📱 响应式设计

```css
/* 移动端适配 */
@media screen and (max-width: 76.1875em) {
  .md-nav--primary .md-nav__title {
    background: var(--md-primary-fg-color);
    color: white;
  }
}
```

## 🖨️ 打印样式

```css
@media print {
  .md-header,
  .md-nav,
  .md-footer {
    display: none;
  }
  
  .md-content {
    margin: 0;
    padding: 0;
  }
}
```

## 🚀 部署注意事项

1. **确保 CSS 文件路径正确**：`extra_css` 中的路径相对于 `docs_dir`
2. **测试构建**：使用 `mkdocs build` 测试样式是否生效
3. **版本控制**：将自定义样式文件提交到 Git
4. **浏览器兼容性**：测试不同浏览器的显示效果

## 📚 参考资源

- [MkDocs Material 官方文档](https://squidfunk.github.io/mkdocs-material/)
- [Material Design 颜色系统](https://material.io/design/color/)
- [CSS 变量参考](https://squidfunk.github.io/mkdocs-material/setup/changing-the-colors/)

## 🎨 样式示例

查看 `style-examples.md` 文件了解实际效果。
