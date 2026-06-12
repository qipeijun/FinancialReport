#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志管理模块

提供统一的日志配置和管理功能，支持：
- 多级别日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 文件和控制台双输出
- 日志轮转（按大小和时间）
- 彩色终端输出
- 结构化日志记录
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器（仅用于终端输出）"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # 添加颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        
        # 格式化消息
        result = super().format(record)
        
        # 恢复原始levelname（避免影响其他handler）
        record.levelname = levelname
        
        return result


class LoggerManager:
    """日志管理器"""
    
    def __init__(self, name: str = 'financial_report'):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # 防止重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """配置日志处理器"""
        # 创建日志目录
        log_dir = Path(__file__).resolve().parents[2] / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 控制台处理器（彩色输出）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
            fmt='%(levelname)-8s | %(asctime)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 2. 文件处理器 - 所有日志（按大小轮转）
        all_log_file = log_dir / 'all.log'
        file_handler = RotatingFileHandler(
            all_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            fmt='%(levelname)s | %(asctime)s | %(name)s | %(module)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 3. 错误日志处理器（仅记录ERROR及以上）
        error_log_file = log_dir / 'error.log'
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
        
        # 4. 按日期轮转的日志文件
        daily_log_file = log_dir / f'{datetime.now().strftime("%Y-%m-%d")}.log'
        daily_handler = TimedRotatingFileHandler(
            daily_log_file,
            when='midnight',
            interval=1,
            backupCount=30,  # 保留30天
            encoding='utf-8'
        )
        daily_handler.setLevel(logging.INFO)
        daily_handler.setFormatter(file_formatter)
        self.logger.addHandler(daily_handler)
    
    def get_logger(self) -> logging.Logger:
        """获取logger实例"""
        return self.logger
    
    @staticmethod
    def get_module_logger(module_name: str) -> logging.Logger:
        """获取模块级别的logger"""
        return logging.getLogger(f'financial_report.{module_name}')


# 便捷函数
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取logger实例
    
    Args:
        name: logger名称，None时使用默认名称
    
    Returns:
        logging.Logger: logger实例
    
    Example:
        >>> logger = get_logger('rss_analyzer')
        >>> logger.info('开始抓取RSS数据')
    """
    if name is None:
        manager = LoggerManager()
        return manager.get_logger()
    else:
        return LoggerManager.get_module_logger(name)


# 创建默认logger实例
default_logger = get_logger()


# 导出便捷函数
def debug(msg: str, *args, **kwargs):
    """记录DEBUG级别日志"""
    default_logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    """记录INFO级别日志"""
    default_logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    """记录WARNING级别日志"""
    default_logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    """记录ERROR级别日志"""
    default_logger.error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs):
    """记录CRITICAL级别日志"""
    default_logger.critical(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs):
    """记录异常信息（包含堆栈跟踪）"""
    default_logger.exception(msg, *args, **kwargs)


if __name__ == '__main__':
    # 测试日志系统
    logger = get_logger('test')
    
    logger.debug('这是DEBUG日志')
    logger.info('这是INFO日志')
    logger.warning('这是WARNING日志')
    logger.error('这是ERROR日志')
    logger.critical('这是CRITICAL日志')
    
    try:
        1 / 0
    except Exception as e:
        logger.exception('捕获到异常')
    
    print(f"\n日志文件位置: {Path(__file__).resolve().parents[2] / 'logs'}")

