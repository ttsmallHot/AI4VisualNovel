import logging
from typing import Optional, List

from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class BaseAgent:
    """所有智能体的基类，提供统一的 LLM 驱动与短期记忆能力。"""

    def __init__(
        self,
        name: str,
        role: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        short_term_memory_limit: int = 10
    ):
        self.name = name
        self.role = role

        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)

        self.short_term_memory_limit = max(1, short_term_memory_limit)
        self.short_term_memory: List[str] = []

        logger.info(f"🤖 [{self.role}] {self.name} 基类初始化完成")

    def add_short_term_memory(self, content: str):
        if not content:
            return
        self.short_term_memory.append(content)
        if len(self.short_term_memory) > self.short_term_memory_limit:
            self.short_term_memory = self.short_term_memory[-self.short_term_memory_limit:]

    def get_short_term_memory(self, max_items: int = 5) -> str:
        if max_items <= 0:
            return ""
        return "\n".join(self.short_term_memory[-max_items:])

    def get_memory_context(self, max_items: int = 5) -> str:
        short_ctx = self.get_short_term_memory(max_items=max_items)
        if short_ctx:
            logger.debug(f"🧠 [{self.name}] 短期记忆命中")
            return f"【短期记忆】\n{short_ctx}"
        return ""
