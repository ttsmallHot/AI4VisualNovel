"""
Designer Agent
~~~~~~~~~~~~~~
策划 Agent - 负责草拟游戏整体设计文档
"""

import logging
from typing import Dict, Any, Optional
from .base_agent import BaseAgent
import json

from .config import DesignerConfig
from .schemas import GAME_OUTLINE_SCHEMA, STORY_GRAPH_SCHEMA

logger = logging.getLogger(__name__)


class DesignerAgent(BaseAgent):
    """策划 Agent - 游戏设计文档草拟者"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化策划 Agent
        """
        super().__init__(
            name="Designer",
            role="策划",
            api_key=api_key,
            base_url=base_url
        )
        self.config = DesignerConfig
        
        logger.info("✅ 策划 Agent 初始化成功")
    
    def generate_game_outline(
        self,
        character_count: int = None,
        requirements: str = "",
        feedback: str = None,
        previous_game_outline: Dict[str, Any] = None,
        locked_characters: Optional[list[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Step1: 只生成不含 story_graph 的设计大纲。"""
        character_count = character_count or self.config.DEFAULT_CHARACTER_COUNT

        logger.info("📝 策划正在生成游戏大纲（Step1）...")

        user_prompt = self.config.GAME_OUTLINE_PROMPT.format(
            character_count=character_count,
            total_nodes=self.config.TOTAL_NODES,
            requirements=requirements if requirements else "无"
        )

        if locked_characters:
            user_prompt += (
                "\n\n【用户锁定角色（必须保留）】\n"
                f"{json.dumps(locked_characters, ensure_ascii=False, indent=2)}"
                "\n\n规则："
                "\n1. 这些角色必须出现在最终 characters 数组中，且 id/name 不得修改；"
                "\n2. 若锁定角色某些字段为空，可以补全；若字段已有值，不得改写；"
                "\n3. 剩余角色位可自由生成。"
            )

        if feedback and previous_game_outline:
            logger.info("🔧 大纲优化模式：根据反馈修改...")
            user_prompt += (
                f"\n\n【原大纲】\n{json.dumps(previous_game_outline, ensure_ascii=False, indent=2)}"
                f"\n\n【制作人反馈】\n{feedback}"
                "\n\n请修改大纲并保持 JSON 格式。"
            )

        outline = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            schema=GAME_OUTLINE_SCHEMA,
            object_name="game_outline",
            temperature=self.config.TEMPERATURE
        )

        outline.pop("story_graph", None)
        logger.info(f"✅ 游戏大纲生成完成: 《{outline.get('title', 'Unknown')}》")
        return outline

    def generate_story_graph_from_outline(
        self,
        game_outline: Dict[str, Any],
        feedback: str = None
    ) -> Dict[str, Any]:
        """Step2: 根据 Step1 的分组大纲生成 story_graph。"""
        logger.info("🧭 策划正在生成 story_graph（Step2）...")

        prompt = self.config.STORY_GRAPH_FROM_OUTLINE_PROMPT.format(
            total_nodes=self.config.TOTAL_NODES,
            outline_json=json.dumps(game_outline, ensure_ascii=False, indent=2)
        )

        if feedback:
            prompt += (
                f"\n\n【制作人对 Step2 的反馈】\n{feedback}"
                "\n\n请在保持 JSON 结构与硬约束不变的前提下，修正 story_graph。"
            )

        story_graph = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            schema=STORY_GRAPH_SCHEMA,
            object_name="story_graph",
            temperature=self.config.TEMPERATURE
        )

        if len(story_graph.get("nodes", {})) != self.config.TOTAL_NODES:
            raise ValueError(
                f"story_graph 节点数不匹配，期望 {self.config.TOTAL_NODES}，实际 {len(story_graph.get('nodes', {}))}"
            )

        logger.info("✅ story_graph 生成完成")
        return story_graph
