#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek 模型提供商
"""

import os
from typing import Mapping, Tuple, Dict, Any
from urllib.parse import urlparse

from .base_provider import BaseProvider

try:
    import httpx
    from openai import OpenAI
except ImportError:
    httpx = None
    OpenAI = None


PROXY_ENV_KEYS = ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy')


def get_proxy_url(env: Mapping[str, str] | None = None) -> str | None:
    """读取可用于 DeepSeek 请求的代理地址。"""
    env = env or os.environ
    for key in PROXY_ENV_KEYS:
        value = (env.get(key) or '').strip()
        if value:
            parsed = urlparse(value)
            if parsed.scheme and parsed.netloc:
                return value
            raise ValueError(f'{key} 配置不是有效的代理 URL: {value}')
    return None


def build_http_client():
    """构造 OpenAI SDK 专用 HTTP 客户端，避免解析异常的 NO_PROXY。"""
    if httpx is None:
        raise ImportError('未安装 httpx，请运行: pip install httpx')

    proxy_url = get_proxy_url()
    return httpx.Client(proxy=proxy_url, trust_env=False)


class DeepSeekProvider(BaseProvider):
    """DeepSeek 模型提供商"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)

        if OpenAI is None:
            raise ImportError('未安装 openai，请运行: pip install openai')

        self.base_url = kwargs.get('base_url', 'https://api.deepseek.com')
        self.default_model = kwargs.get('model', 'deepseek-v4-pro')

        self.http_client = build_http_client()
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=self.http_client)

    def get_available_models(self) -> list:
        """获取可用的DeepSeek模型列表"""
        return ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat']

    def generate(self, prompt: str, content: str, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """
        调用DeepSeek生成分析报告

        Args:
            prompt: 系统提示词
            content: 用户输入内容
            **kwargs:
                - model: 指定模型名称

        Returns:
            Tuple[str, Dict]: (生成的文本, 使用统计)
        """
        model_name = kwargs.get('model', self.default_model)

        # 替换提示词中的模型占位符
        final_prompt = prompt.replace('[使用的具体模型名称]', model_name)

        try:
            resp = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": final_prompt},
                    {"role": "user", "content": content},
                ],
                stream=False
            )

            # 提取使用统计
            usage = {'model': getattr(resp, 'model', model_name), 'provider': 'deepseek'}
            try:
                if hasattr(resp, 'usage') and resp.usage:
                    usage['prompt_tokens'] = getattr(resp.usage, 'prompt_tokens', 0)
                    usage['completion_tokens'] = getattr(resp.usage, 'completion_tokens', 0)
                    usage['total_tokens'] = getattr(resp.usage, 'total_tokens', 0)
            except Exception:
                pass

            text = resp.choices[0].message.content if resp and resp.choices else ''
            return text, usage

        except Exception as e:
            raise RuntimeError(f'DeepSeek模型调用失败：{e}')
