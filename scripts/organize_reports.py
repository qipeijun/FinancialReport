#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移旧结构到按月归档的新结构：
- 旧：根目录下 YYYY-MM-DD_model 或 YYYY-MM-DD
- 新：archive/YYYY-MM/YYYY-MM-DD_model
运行方式：python3 organize_reports.py
"""

import os
import re
import shutil
from pathlib import Path

ARCHIVE_ROOT = Path('archive')
OLD_DATE_DIR_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})(?:_(.+))?$')  # 捕获日期与可选模型后缀

SUBDIRS = ['rss_data', 'news_content', 'analysis', 'reports']


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def detect_old_date_dirs(root: Path) -> list[Path]:
    candidates = []
    for p in root.iterdir():
        if p.is_dir() and OLD_DATE_DIR_RE.match(p.name):
            candidates.append(p)
    return sorted(candidates, key=lambda x: x.name)


def migrate_one(old_dir: Path) -> tuple[Path, bool]:
    m = OLD_DATE_DIR_RE.match(old_dir.name)
    assert m
    date_str = m.group(1)
    model = m.group(2) or ''
    month_str = date_str[:7]
    target_month_dir = ARCHIVE_ROOT / month_str
    target_dir_name = f"{date_str}{'_' + model if model else ''}"
    target_dir = target_month_dir / target_dir_name

    ensure_dir(target_dir)

    moved = False
    # 移动全目录（包含子文件夹）
    for item in old_dir.iterdir():
        dest = target_dir / item.name
        if dest.exists():
            continue
        if item.is_dir() or item.is_file():
            if item.is_dir() and item.name not in SUBDIRS:
                # 允许保留未知目录
                pass
            shutil.move(str(item), str(dest))
            moved = True

    # 确保子目录存在
    for sub in SUBDIRS:
        ensure_dir(target_dir / sub)

    # 若旧目录已空，则删除
    try:
        if not any(old_dir.iterdir()):
            old_dir.rmdir()
    except Exception:
        pass

    return target_dir, moved


def main() -> None:
    root = Path('.')
    ensure_dir(ARCHIVE_ROOT)
    old_dirs = detect_old_date_dirs(root)

    if not old_dirs:
        print('No legacy date directories found. Skipped migration.')
        return

    print(f"Found {len(old_dirs)} legacy date directories. Migrating...")
    migrated_count = 0
    for d in old_dirs:
        target, moved = migrate_one(d)
        if moved:
            migrated_count += 1
    print(f"Migration completed. Moved {migrated_count} directories into archive.")


if __name__ == '__main__':
    main()
