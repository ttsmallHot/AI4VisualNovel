"""
LLM Client
~~~~~~~~~~
统一的 LLM 客户端，支持 OpenAI 和 Google Gemini
"""

import logging
import os
from typing import List, Dict, Any, Optional, Union
from .config import APIConfig

logger = logging.getLogger(__name__)

class LLMClient:
    """统一的 LLM 客户端封装"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = APIConfig.TEXT_PROVIDER.lower()
        self.api_key = api_key
        self.base_url = base_url
        
        self.client = None
        self._initialize_client()
        
    def _initialize_client(self):
        """初始化对应的客户端"""
        if self.provider == "openai":
            from openai import OpenAI
            self.api_key = self.api_key or APIConfig.OPENAI_API_KEY
            self.base_url = self.base_url or APIConfig.OPENAI_BASE_URL
            
            if not self.api_key:
                logger.warning("⚠️ OpenAI API Key 未配置")
            else:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                
        elif self.provider == "google":
            try:
                from google import genai
                self.api_key = self.api_key or APIConfig.GOOGLE_API_KEY
                self.base_url = self.base_url or APIConfig.GOOGLE_BASE_URL
                
                if not self.api_key:
                    logger.warning("⚠️ Google API Key 未配置")
                else:
                    # google-genai Client 初始化
                    # 如果有 base_url，可能需要通过 http_options 配置 (具体取决于 SDK 版本，这里假设标准用法)
                    # 注意：google-genai SDK 的 Client 初始化参数可能不同于 google-generativeai
                    
                    client_kwargs = {"api_key": self.api_key}
                    if self.base_url:
                        # 尝试适配自定义 endpoint，google-genai 通过 http_options 的 base_url 支持
                        client_kwargs["http_options"] = {"base_url": self.base_url}
                        logger.info(f"✅ Google Client 初始化 (Endpoint: {self.base_url})")
                    
                    self.client = genai.Client(**client_kwargs)
                    
            except ImportError:
                logger.error("❌ google-genai 未安装，请运行: pip install google-genai")
                
        else:
            logger.error(f"❌ 未知的 LLM 提供商: {self.provider}")

    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7, 
        json_mode: bool = False
    ) -> str:
        """
        统一的聊天补全接口
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            temperature: 温度参数
            json_mode: 是否强制返回 JSON
            
        Returns:
            生成的文本内容
        """
        if self.provider == "openai":
            return self._chat_openai(messages, temperature, json_mode)
        elif self.provider == "google":
            return self._chat_google(messages, temperature, json_mode)
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.provider}")

    def _chat_openai(self, messages: List[Dict[str, str]], temperature: float, json_mode: bool) -> str:
        if not self.client:
            raise ValueError("OpenAI 客户端未初始化")
            
        response_format = {"type": "json_object"} if json_mode else None
        
        try:
            response = self.client.chat.completions.create(
                model=APIConfig.MODEL,
                messages=messages,
                temperature=temperature,
                response_format=response_format
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise

    def _chat_google(self, messages: List[Dict[str, str]], temperature: float, json_mode: bool) -> str:
        if not self.client:
            raise ValueError("Google 客户端未初始化")
            
        from google.genai import types
            
        # 提取系统提示词
        system_instruction = None
        contents = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content)]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=content)]))
        
        # 配置生成参数
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction
        )
        
        if json_mode:
            config.response_mime_type = "application/json"
            
        try:
            response = self.client.models.generate_content(
                model=APIConfig.MODEL,
                contents=contents,
                config=config
            )
            return response.text
            
        except Exception as e:
            logger.error(f"Google Gemini API 调用失败: {e}")
            raise
