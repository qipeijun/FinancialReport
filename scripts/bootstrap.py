#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顶层 CLI 入口的导入路径初始化。

仅供 `python3 scripts/xxx.py` 这类直接执行入口使用；包内模块不应调用它。
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_project_root(file: str) -> Path:
    """将项目根目录加入 sys.path，并返回该路径。"""
    project_root = Path(file).resolve().parents[1]
    root_text = str(project_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return project_root
