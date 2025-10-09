#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块

提供统一的配置管理功能，支持：
- 单例模式，全局唯一配置实例
- 懒加载，按需读取配置
- 点号路径访问（如 'api_keys.gemini'）
- 环境变量覆盖
- 配置验证
- 缓存机制
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache


class ConfigManager:
    """配置管理器（单例模式）"""
    
    _instance: Optional['ConfigManager'] = None
    _config: Optional[Dict[str, Any]] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 只初始化一次
        if not hasattr(self, '_initialized'):
            self.project_root = Path(__file__).resolve().parents[2]
            self.config_path = self.project_root / 'config' / 'config.yml'
            self.example_config_path = self.project_root / 'config' / 'config.example.yml'
            self._initialized = True
    
    @property
    def config(self) -> Dict[str, Any]:
        """
        懒加载配置
        
        Returns:
            配置字典
        """
        if self._config is None:
            self._load_config()
        return self._config
    
    def _load_config(self):
        """加载配置文件"""
        if not self.config_path.exists():
            if self.example_config_path.exists():
                raise FileNotFoundError(
                    f'配置文件不存在: {self.config_path}\n'
                    f'请复制 {self.example_config_path} 到 {self.config_path} 并填写配置'
                )
            else:
                raise FileNotFoundError(f'配置文件不存在: {self.config_path}')
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f'配置文件格式错误: {e}')
        except Exception as e:
            raise RuntimeError(f'读取配置文件失败: {e}')
    
    def reload(self):
        """重新加载配置"""
        self._config = None
        self._load_config()
    
    def get(self, key_path: str, default: Any = None, use_env: bool = True) -> Any:
        """
        获取配置值，支持点号路径访问
        
        Args:
            key_path: 配置路径，用点号分隔，如 'api_keys.gemini'
            default: 默认值
            use_env: 是否允许环境变量覆盖
        
        Returns:
            配置值或默认值
        
        Example:
            >>> config = ConfigManager()
            >>> api_key = config.get('api_keys.gemini')
            >>> max_articles = config.get('limits.max_articles', default=100)
        """
        # 先尝试从环境变量获取（如果允许）
        if use_env:
            env_key = key_path.upper().replace('.', '_')
            env_value = os.getenv(env_key)
            if env_value is not None:
                return env_value
        
        # 从配置文件获取
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default
    
    def get_api_key(self, service: str) -> Optional[str]:
        """
        获取API密钥（支持多种配置方式）
        
        Args:
            service: 服务名称，如 'gemini', 'deepseek'
        
        Returns:
            API密钥或None
        
        Example:
            >>> config = ConfigManager()
            >>> gemini_key = config.get_api_key('gemini')
        """
        # 优先级：环境变量 > api_keys.service > service.api_key
        
        # 1. 环境变量
        env_key = f'{service.upper()}_API_KEY'
        api_key = os.getenv(env_key)
        if api_key:
            return api_key
        
        # 2. api_keys.service
        api_key = self.get(f'api_keys.{service}', use_env=False)
        if api_key:
            return api_key
        
        # 3. service.api_key
        api_key = self.get(f'{service}.api_key', use_env=False)
        if api_key:
            return api_key
        
        return None
    
    def get_db_path(self) -> Path:
        """
        获取数据库路径
        
        Returns:
            数据库文件路径
        """
        db_path = self.get('database.path', default='data/news_data.db')
        if not Path(db_path).is_absolute():
            db_path = self.project_root / db_path
        else:
            db_path = Path(db_path)
        
        # 确保目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        return db_path
    
    def get_rss_sources_config(self) -> Path:
        """
        获取RSS源配置文件路径
        
        Returns:
            RSS配置文件路径
        """
        rss_config = self.get('rss.config_file', default='scripts/config/rss.json')
        if not Path(rss_config).is_absolute():
            rss_config = self.project_root / rss_config
        else:
            rss_config = Path(rss_config)
        
        return rss_config
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        验证配置完整性
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        # 检查必需的API密钥
        gemini_key = self.get_api_key('gemini')
        deepseek_key = self.get_api_key('deepseek')
        
        if not gemini_key and not deepseek_key:
            errors.append('至少需要配置一个AI模型的API密钥（Gemini或DeepSeek）')
        
        # 检查数据库路径
        try:
            db_path = self.get_db_path()
            if not db_path.parent.exists():
                errors.append(f'数据库目录不存在: {db_path.parent}')
        except Exception as e:
            errors.append(f'数据库路径配置错误: {e}')
        
        # 检查RSS配置文件
        try:
            rss_config = self.get_rss_sources_config()
            if not rss_config.exists():
                errors.append(f'RSS配置文件不存在: {rss_config}')
        except Exception as e:
            errors.append(f'RSS配置路径错误: {e}')
        
        return (len(errors) == 0, errors)
    
    def __repr__(self) -> str:
        return f"ConfigManager(config_path='{self.config_path}')"


# 创建全局配置实例
_config_instance = ConfigManager()


# 便捷函数
def get_config() -> ConfigManager:
    """
    获取配置管理器实例
    
    Returns:
        ConfigManager: 配置管理器实例
    
    Example:
        >>> from utils.config_manager import get_config
        >>> config = get_config()
        >>> api_key = config.get('api_keys.gemini')
    """
    return _config_instance


def get(key_path: str, default: Any = None) -> Any:
    """
    快捷方式：获取配置值
    
    Args:
        key_path: 配置路径
        default: 默认值
    
    Returns:
        配置值
    """
    return _config_instance.get(key_path, default)


def get_api_key(service: str) -> Optional[str]:
    """
    快捷方式：获取API密钥
    
    Args:
        service: 服务名称
    
    Returns:
        API密钥
    """
    return _config_instance.get_api_key(service)


def get_db_path() -> Path:
    """
    快捷方式：获取数据库路径
    
    Returns:
        数据库路径
    """
    return _config_instance.get_db_path()


if __name__ == '__main__':
    # 测试配置管理器
    config = get_config()
    
    print(f"配置文件路径: {config.config_path}")
    print(f"项目根目录: {config.project_root}")
    
    # 测试获取配置
    print(f"\nGemini API Key: {config.get_api_key('gemini')}")
    print(f"DeepSeek API Key: {config.get_api_key('deepseek')}")
    print(f"数据库路径: {config.get_db_path()}")
    
    # 验证配置
    is_valid, errors = config.validate()
    print(f"\n配置验证: {'✓ 通过' if is_valid else '✗ 失败'}")
    if errors:
        print("错误列表:")
        for error in errors:
            print(f"  - {error}")

