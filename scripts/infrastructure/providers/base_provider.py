#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模型提供商抽象基类
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional


class BaseProvider(ABC):
    """AI模型提供商抽象基类"""

    def __init__(self, api_key: str, **kwargs):
        """
        初始化提供商

        Args:
            api_key: API密钥
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.config = kwargs

    @abstractmethod
    def generate(self, prompt: str, content: str, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """
        生成AI分析报告

        Args:
            prompt: 系统提示词
            content: 用户输入内容
            **kwargs: 其他生成参数

        Returns:
            Tuple[str, Dict]: (生成的文本, 使用统计信息)
        """
        pass

    @abstractmethod
    def get_available_models(self) -> list:
        """
        获取可用的模型列表

        Returns:
            list: 模型名称列表
        """
        pass

    def get_provider_name(self) -> str:
        """获取提供商名称"""
        return self.__class__.__name__.replace('Provider', '')
