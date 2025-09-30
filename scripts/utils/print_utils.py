#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公共打印工具模块

提供统一的颜色化打印功能，支持：
- 不同级别的消息（成功、警告、错误、信息、进度）
- 格式化的标题和步骤显示
- 自动检测终端是否支持颜色
- 统一的样式和图标
"""

import sys
from typing import Optional


class Colors:
    """ANSI颜色代码"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class PrintUtils:
    """打印工具类"""
    
    def __init__(self, enable_colors: Optional[bool] = None):
        """
        初始化打印工具
        
        Args:
            enable_colors: 是否启用颜色，None时自动检测
        """
        if enable_colors is None:
            # 自动检测终端是否支持颜色
            self.enable_colors = (
                hasattr(sys.stdout, 'isatty') and 
                sys.stdout.isatty() and 
                sys.platform != 'win32'
            ) or sys.platform == 'win32'  # Windows 10+ 支持ANSI
        else:
            self.enable_colors = enable_colors
    
    def _colorize(self, text: str, color: str) -> str:
        """添加颜色到文本"""
        if self.enable_colors:
            return f"{color}{text}{Colors.END}"
        return text
    
    def print_header(self, text: str, width: int = 60):
        """打印标题"""
        separator = '=' * width
        print(f"\n{self._colorize(separator, Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize(text.center(width), Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize(separator, Colors.BOLD + Colors.CYAN)}\n")
    
    def print_success(self, text: str):
        """打印成功信息"""
        print(f"{self._colorize('✅', Colors.GREEN)} {text}")
    
    def print_warning(self, text: str):
        """打印警告信息"""
        print(f"{self._colorize('⚠️ ', Colors.YELLOW)} {text}")
    
    def print_error(self, text: str):
        """打印错误信息"""
        print(f"{self._colorize('❌', Colors.RED)} {text}")
    
    def print_info(self, text: str):
        """打印信息"""
        print(f"{self._colorize('ℹ️ ', Colors.BLUE)} {text}")
    
    def print_progress(self, text: str):
        """打印进度信息"""
        print(f"{self._colorize('🔄', Colors.MAGENTA)} {text}")
    
    def print_step(self, step: int, total: int, text: str):
        """打印步骤信息"""
        print(f"{self._colorize(f'[{step}/{total}]', Colors.CYAN)} {text}")
    
    def print_section(self, text: str):
        """打印章节标题"""
        print(f"\n{self._colorize('─' * 50, Colors.CYAN)}")
        print(f"{self._colorize(text, Colors.BOLD + Colors.CYAN)}")
        print(f"{self._colorize('─' * 50, Colors.CYAN)}")
    
    def print_table_header(self, headers: list, widths: Optional[list] = None):
        """打印表格标题"""
        if widths is None:
            widths = [20] * len(headers)
        
        # 打印表头
        header_line = " | ".join(f"{h:^{w}}" for h, w in zip(headers, widths))
        print(f"{self._colorize(header_line, Colors.BOLD)}")
        
        # 打印分隔线
        separator = "-+-".join("-" * w for w in widths)
        print(f"{self._colorize(separator, Colors.CYAN)}")
    
    def print_table_row(self, row: list, widths: Optional[list] = None):
        """打印表格行"""
        if widths is None:
            widths = [20] * len(row)
        
        row_line = " | ".join(f"{str(cell):^{w}}" for cell, w in zip(row, widths))
        print(row_line)
    
    def print_statistics(self, stats: dict):
        """打印统计信息"""
        print(f"\n{self._colorize('📊 统计信息', Colors.BOLD + Colors.CYAN)}")
        for key, value in stats.items():
            if isinstance(value, (int, float)):
                if isinstance(value, int) and value > 1000:
                    value_str = f"{value:,}"
                else:
                    value_str = str(value)
            else:
                value_str = str(value)
            print(f"  {self._colorize(key, Colors.BLUE)}: {value_str}")
    
    def print_file_info(self, file_type: str, file_path: str):
        """打印文件信息"""
        print(f"{self._colorize('📁', Colors.GREEN)} {file_type}: {file_path}")
    
    def print_time_info(self, operation: str, duration: float):
        """打印时间信息"""
        print(f"{self._colorize('⏱️ ', Colors.YELLOW)} {operation} 耗时: {duration:.2f}秒")
    
    def print_count(self, item: str, count: int, total: Optional[int] = None):
        """打印计数信息"""
        if total is not None:
            print(f"{self._colorize('📈', Colors.CYAN)} {item}: {count:,}/{total:,}")
        else:
            print(f"{self._colorize('📈', Colors.CYAN)} {item}: {count:,}")


# 创建全局实例
printer = PrintUtils()


# 便捷函数
def print_header(text: str, width: int = 60):
    """打印标题"""
    printer.print_header(text, width)


def print_success(text: str):
    """打印成功信息"""
    printer.print_success(text)


def print_warning(text: str):
    """打印警告信息"""
    printer.print_warning(text)


def print_error(text: str):
    """打印错误信息"""
    printer.print_error(text)


def print_info(text: str):
    """打印信息"""
    printer.print_info(text)


def print_progress(text: str):
    """打印进度信息"""
    printer.print_progress(text)


def print_step(step: int, total: int, text: str):
    """打印步骤信息"""
    printer.print_step(step, total, text)


def print_section(text: str):
    """打印章节标题"""
    printer.print_section(text)


def print_table_header(headers: list, widths: Optional[list] = None):
    """打印表格标题"""
    printer.print_table_header(headers, widths)


def print_table_row(row: list, widths: Optional[list] = None):
    """打印表格行"""
    printer.print_table_row(row, widths)


def print_statistics(stats: dict):
    """打印统计信息"""
    printer.print_statistics(stats)


def print_file_info(file_type: str, file_path: str):
    """打印文件信息"""
    printer.print_file_info(file_type, file_path)


def print_time_info(operation: str, duration: float):
    """打印时间信息"""
    printer.print_time_info(operation, duration)


def print_count(item: str, count: int, total: Optional[int] = None):
    """打印计数信息"""
    printer.print_count(item, count, total)
