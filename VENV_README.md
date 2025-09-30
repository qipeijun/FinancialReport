# Python虚拟环境使用指南

## 🐍 虚拟环境已配置完成

本项目已配置Python虚拟环境，确保依赖隔离和版本一致性。

## 📁 虚拟环境结构

```
venv/                    # 虚拟环境目录
├── bin/                 # 可执行文件 (Linux/macOS)
│   ├── python          # Python解释器
│   ├── pip             # 包管理器
│   └── activate        # 激活脚本
├── lib/                 # 安装的包
└── pyvenv.cfg          # 虚拟环境配置
```

## 🚀 快速开始

### 方法1：使用便捷脚本（推荐）

**Linux/macOS:**
```bash
./activate.sh
```

**Windows:**
```cmd
activate.bat
```

### 方法2：手动激活

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows:**
```cmd
venv\Scripts\activate.bat
```

## 📦 已安装的依赖

- **AI分析**: `google-generativeai` - Gemini API客户端
- **文档生成**: `mkdocs-material` - 现代化文档站点
- **数据处理**: `pyyaml`, `requests`, `feedparser`, `pytz`
- **其他工具**: 完整的依赖树已安装

## 🔧 常用命令

激活虚拟环境后，可以使用以下命令：

```bash
# 交互式运行器（推荐新手使用）
python scripts/interactive_runner.py

# AI分析脚本
python scripts/ai_analyze.py --help

# RSS抓取脚本
python scripts/rss_finance_analyzer.py --help

# 查看已安装的包
pip list

# 安装新包
pip install package_name

# 更新requirements.txt
pip freeze > requirements.txt
```

## 🛠️ 管理依赖

### 添加新依赖
```bash
# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate.bat  # Windows

# 安装新包
pip install new_package

# 更新requirements.txt
pip freeze > requirements.txt
```

### 重新安装依赖
```bash
# 删除虚拟环境
rm -rf venv  # Linux/macOS
# 或
rmdir /s venv  # Windows

# 重新创建
python3 -m venv venv

# 激活并安装依赖
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

## ⚠️ 注意事项

1. **每次使用前都要激活虚拟环境**
2. **不要将 `venv/` 目录提交到Git**
3. **使用 `requirements.txt` 管理依赖版本**
4. **虚拟环境激活后，命令提示符会显示 `(venv)` 前缀**

## 🔄 退出虚拟环境

```bash
deactivate
```

## 🆘 故障排除

### 虚拟环境未激活
如果看到类似错误：
```
ModuleNotFoundError: No module named 'google.generativeai'
```

请确保已激活虚拟环境：
```bash
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate.bat  # Windows
```

### 权限问题
如果遇到权限错误，尝试：
```bash
chmod +x activate.sh  # Linux/macOS
```

### 重新创建虚拟环境
如果虚拟环境损坏，可以删除并重新创建：
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
