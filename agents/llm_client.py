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
        json_mode: bool = False,
        max_retries: int = 3
    ) -> str:
        """
        统一的聊天补全接口（带重试机制）
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            temperature: 温度参数
            json_mode: 是否强制返回 JSON
            max_retries: 最大重试次数
            
        Returns:
            生成的文本内容
        """
        import time
        
        for attempt in range(max_retries):
            try:
                if self.provider == "openai":
                    return self._chat_openai(messages, temperature, json_mode)
                elif self.provider == "google":
                    return self._chat_google(messages, temperature, json_mode)
                else:
                    raise ValueError(f"不支持的 LLM 提供商: {self.provider}")
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                    logger.warning(f"⚠️ LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"   ⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ LLM 调用失败，已重试 {max_retries} 次: {e}")
                    raise

    def _chat_openai(self, messages: List[Dict[str, Any]], temperature: float, json_mode: bool) -> str:
        if not self.client:
            raise ValueError("OpenAI 客户端未初始化")
            
        # 处理消息中的本地图片路径，转换为 Base64
        import base64
        import mimetypes
        
        processed_messages = []
        for msg in messages:
            new_msg = msg.copy()
            if isinstance(msg.get("content"), list):
                new_content = []
                for item in msg["content"]:
                    if item.get("type") == "image_url":
                        url = item["image_url"]["url"]
                        if os.path.exists(url):
                            # 本地文件，转换为 Base64
                            mime_type, _ = mimetypes.guess_type(url)
                            if not mime_type: mime_type = "image/png"
                            
                            try:
                                with open(url, "rb") as image_file:
                                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    new_item = item.copy()
                                    new_item["image_url"] = {
                                        "url": f"data:{mime_type};base64,{encoded_string}"
                                    }
                                    new_content.append(new_item)
                            except Exception as e:
                                logger.error(f"❌ 读取图片失败: {e}")
                                new_content.append(item) # 保持原样，虽然可能会失败
                        else:
                            new_content.append(item)
                    else:
                        new_content.append(item)
                new_msg["content"] = new_content
            processed_messages.append(new_msg)
            
        response_format = {"type": "json_object"} if json_mode else None
        
        try:
            response = self.client.chat.completions.create(
                model=APIConfig.MODEL,
                messages=processed_messages,
                temperature=temperature,
                response_format=response_format
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise

    def _chat_google(self, messages: List[Dict[str, Any]], temperature: float, json_mode: bool) -> str:
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
                parts = []
                if isinstance(content, str):
                    parts.append(types.Part.from_text(text=content))
                elif isinstance(content, list):
                    for item in content:
                        if item.get("type") == "text":
                            parts.append(types.Part.from_text(text=item["text"]))
                        elif item.get("type") == "image_url":
                            # 处理图片
                            image_path = item["image_url"]["url"]
                            try:
                                # 如果是本地路径
                                if os.path.exists(image_path):
                                    with open(image_path, "rb") as f:
                                        image_data = f.read()
                                    parts.append(types.Part.from_bytes(data=image_data, mime_type="image/png")) # 假设是 PNG
                                else:
                                    # 暂时不支持网络 URL，或者需要下载
                                    logger.warning(f"⚠️ Google Client 暂不支持网络图片 URL: {image_path}")
                            except Exception as e:
                                logger.error(f"❌ 读取图片失败: {e}")
                
                contents.append(types.Content(role="user", parts=parts))
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
