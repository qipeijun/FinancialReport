#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Gemini 模型提供商
"""

from typing import Tuple, Dict, Any, Optional
from .base_provider import BaseProvider

try:
    import google.generativeai as genai
except ImportError:
    genai = None


class GeminiProvider(BaseProvider):
    """Google Gemini 模型提供商"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)

        if genai is None:
            raise ImportError('未安装 google-generativeai，请运行: pip install google-generativeai')

        genai.configure(api_key=self.api_key)

        # 默认模型优先级（Gemini 3.0优先）
        self.default_models = kwargs.get('models') or [
            'models/gemini-3-flash-preview',      # 🥇 Gemini 3.0 Flash (最新)
            'models/gemini-3-pro-preview',         # 🥈 Gemini 3.0 Pro
            'models/gemini-2.0-flash-exp',         # 🥉 Gemini 2.0 (备用)
            'models/gemini-1.5-pro',
            'models/gemini-1.5-flash'
        ]

    def get_available_models(self) -> list:
        """获取可用的Gemini模型列表"""
        return self.default_models

    def generate(self, prompt: str, content: str, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """
        调用Gemini生成分析报告

        Args:
            prompt: 系统提示词
            content: 用户输入内容
            **kwargs:
                - preferred_model: 指定模型名称
                - max_retries: 模型失败时的重试次数

        Returns:
            Tuple[str, Dict]: (生成的文本, 使用统计)
        """
        preferred_model = kwargs.get('preferred_model')

        # 选择模型列表
        if preferred_model:
            if not preferred_model.startswith('models/'):
                preferred_model = f'models/{preferred_model}'
            model_names = [preferred_model]
        else:
            model_names = self.default_models

        # 尝试多个模型
        last_error: Optional[Exception] = None
        for model_name in model_names:
            try:
                # 替换提示词中的模型占位符
                final_prompt = prompt.replace(
                    '[使用的具体模型名称]',
                    model_name.replace('models/', '')
                )

                model = genai.GenerativeModel(model_name)
                resp = model.generate_content([final_prompt, content])

                # 提取使用统计
                usage = {'model': model_name, 'provider': 'gemini'}
                try:
                    if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                        metadata = resp.usage_metadata
                        usage['prompt_tokens'] = getattr(metadata, 'prompt_token_count', 0)
                        usage['candidates_tokens'] = getattr(metadata, 'candidates_token_count', 0)
                        usage['total_tokens'] = getattr(metadata, 'total_token_count', 0)
                except Exception:
                    pass

                return resp.text, usage

            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f'所有Gemini模型调用失败，最后错误：{last_error}')
