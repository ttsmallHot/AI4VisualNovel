"""
LLM Client
~~~~~~~~~~
统一的 LLM 客户端，支持 OpenAI 和 Google Gemini
"""

import logging
import os
from typing import List, Dict, Any, Optional
from .config import APIConfig

logger = logging.getLogger(__name__)

# 全局的 BGE-M3 嵌入模型实例（单例，只加载一次）
_embedding_model_instance = None
FORCED_EMBEDDING_MODEL = "BAAI/bge-m3"

def get_global_embedding_model():
    global _embedding_model_instance
    if _embedding_model_instance is None:
        logger.info("⏳ 正在加载本地 BGE-M3 Embedding 模型 (第一次运行会自动下载)...")
        from sentence_transformers import SentenceTransformer
        _embedding_model_instance = SentenceTransformer(FORCED_EMBEDDING_MODEL)
        logger.info("✅ 本地 Embedding 模型加载成功！")
    return _embedding_model_instance

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

    def get_embedding(
        self,
        text: str,
    ) -> List[float]:
        """直接使用本地 SentenceTransformer 模型返回 Embedding，无需请求 API。"""
        if not text or not text.strip():
            return []

        try:
            local_model = get_global_embedding_model()
            # BGE-M3 模型返回的是 numpy.ndarray，转为 python list
            embedding = local_model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"❌ 本地 Embedding 生成失败 {FORCED_EMBEDDING_MODEL}: {e}")
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
        
        request_kwargs = {
            "model": APIConfig.MODEL,
            "messages": processed_messages,
            "temperature": temperature,
            "response_format": response_format,
        }
        reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "").strip().lower()
        if reasoning_effort:
            allowed_efforts = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
            if reasoning_effort not in allowed_efforts:
                raise ValueError(
                    "OPENAI_REASONING_EFFORT 必须是 none/minimal/low/medium/high/xhigh/max/ultra 之一"
                )
            request_kwargs["reasoning_effort"] = reasoning_effort
        if json_mode:
            json_max_tokens = os.getenv("JSON_MAX_TOKENS", "").strip()
            if json_max_tokens:
                try:
                    parsed_max_tokens = int(json_max_tokens)
                except ValueError as exc:
                    raise ValueError("JSON_MAX_TOKENS 必须是正整数") from exc
                if parsed_max_tokens <= 0:
                    raise ValueError("JSON_MAX_TOKENS 必须是正整数")
                request_kwargs["max_tokens"] = parsed_max_tokens

        # DeepSeek V4 defaults to thinking mode. This project expects the
        # structured final answer in ``message.content`` and does not consume
        # ``reasoning_content``, so use non-thinking mode unless explicitly
        # overridden. It is also substantially cheaper for the rolling VN run.
        if "api.deepseek.com" in (self.base_url or "") and APIConfig.MODEL.startswith("deepseek-v4-"):
            thinking_type = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
            if thinking_type not in {"enabled", "disabled"}:
                raise ValueError("DEEPSEEK_THINKING 必须是 enabled 或 disabled")
            request_kwargs["extra_body"] = {"thinking": {"type": thinking_type}}

        try:
            response = self.client.chat.completions.create(**request_kwargs)
            finish_reason = getattr(response.choices[0], "finish_reason", None)
            if finish_reason == "length":
                raise ValueError(
                    "LLM 结构化响应因 max_tokens 被截断；请提高 JSON_MAX_TOKENS"
                )
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("LLM 返回空正文，拒绝将空响应当作成功")
            return content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise

    def _chat_google(self, messages: List[Dict[str, Any]], temperature: float, json_mode: bool) -> str:
        if not self.client:
            raise ValueError("Google 客户端未初始化")

        try:
            types = __import__("google.genai.types", fromlist=["Part", "Content", "GenerateContentConfig"])
        except Exception as e:
            raise ImportError(f"google-genai types 导入失败: {e}")
            
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

    def _embedding_openai(self, text: str, model: str) -> List[float]:
        if not self.client:
            raise ValueError("OpenAI 客户端未初始化")

        response = self.client.embeddings.create(model=model, input=text)
        if not response.data:
            return []
        return list(response.data[0].embedding)

    def _embedding_google(self, text: str, model: str) -> List[float]:
        if not self.client:
            raise ValueError("Google 客户端未初始化")

        response = self.client.models.embed_content(
            model=model,
            contents=text,
        )

        # 兼容不同 SDK 结构
        emb_obj = getattr(response, "embedding", None)
        if emb_obj is not None and hasattr(emb_obj, "values"):
            return list(emb_obj.values)

        embs = getattr(response, "embeddings", None)
        if embs:
            first = embs[0]
            if hasattr(first, "values"):
                return list(first.values)

        raise ValueError("Google Embedding 响应格式无法解析")
