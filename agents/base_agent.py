import logging
from typing import Optional, List, Dict, Any

from .llm_client import LLMClient
from .utils import JSONParser

logger = logging.getLogger(__name__)


class BaseAgent:
    """所有智能体的基类，提供统一的 LLM 驱动与 Schema 调用能力。"""

    def __init__(
        self,
        name: str,
        role: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.name = name
        self.role = role

        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)

        logger.info(f"🤖 [{self.role}] {self.name} 基类初始化完成")

    def call_json_with_schema(
        self,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        object_name: str,
        temperature: float = 0.7,
        retry_once: bool = True
    ) -> Any:
        """统一的 JSON 生成 + Schema 校验入口。"""
        content = self.llm_client.chat_completion(
            messages=messages,
            temperature=temperature,
            json_mode=True
        )
        parsed = JSONParser.parse_ai_response(content)
        valid, error_message = JSONParser.validate_json_schema(parsed, schema)
        if valid:
            return parsed

        if not retry_once:
            raise ValueError(f"{object_name} Schema 校验失败: {error_message}")

        retry_messages = messages + [{
            "role": "user",
            "content": (
                f"你上一次输出的 {object_name} 未通过 Schema 校验，错误为：{error_message}。"
                "请严格按要求重新输出一个合法 JSON 对象，不要附加解释。"
            )
        }]

        retry_content = self.llm_client.chat_completion(
            messages=retry_messages,
            temperature=temperature,
            json_mode=True
        )
        retry_parsed = JSONParser.parse_ai_response(retry_content)
        retry_valid, retry_error = JSONParser.validate_json_schema(retry_parsed, schema)
        if not retry_valid:
            raise ValueError(f"{object_name} Schema 校验失败: {retry_error}")
        return retry_parsed
