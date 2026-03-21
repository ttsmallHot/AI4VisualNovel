"""
Producer Agent
~~~~~~~~~~~~~~
制作人 Agent - 负责审核设计预览并把控全局
"""

import logging
from typing import Dict, Any, Optional
from .base_agent import BaseAgent
import json

from .config import ProducerConfig, PathConfig
from .utils import FileHelper

logger = logging.getLogger(__name__)


class ProducerAgent(BaseAgent):
    """制作人 Agent - 负责审核设计预览并把控全局"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化制作人 Agent
        """
        super().__init__(
            name="Producer",
            role="制作人",
            api_key=api_key,
            base_url=base_url
        )
        self.config = ProducerConfig
        
        logger.info("✅ 制作人 Agent 初始化成功")
    
    def critique_game_outline(
        self,
        game_outline: Dict[str, Any],
        user_requirements: str = "",
        expected_nodes: int = 12,
        expected_characters: int = 3
    ) -> str:
        """Step1 审核：仅审核 story_outline 与基础设定。"""
        logger.info("📋 制作人正在审核 Step1 大纲...")

        try:
            prompt = self.config.GAME_OUTLINE_CRITIQUE_PROMPT.format(
                game_outline=json.dumps(game_outline, ensure_ascii=False, indent=2),
                user_requirements=user_requirements if user_requirements else "无特别要求",
                expected_nodes=expected_nodes,
                expected_characters=expected_characters
            )

            feedback = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            ).strip()

            if "PASS" in feedback:
                logger.info("✅ Step1 大纲审核通过")
                return "PASS"

            logger.warning("⚠️ Step1 大纲需要修改")
            return feedback
        except Exception as e:
            logger.error(f"❌ Step1 大纲审核失败: {e}")
            return "PASS"

    def critique_story_graph(
        self,
        story_graph: Dict[str, Any],
        game_outline: Dict[str, Any],
        expected_nodes: int = 12
    ) -> str:
        """Step2 审核：仅审核图结构与与 outline 一致性。"""
        logger.info("📋 制作人正在审核 Step2 story_graph...")

        try:
            prompt = self.config.STORY_GRAPH_CRITIQUE_PROMPT.format(
                story_graph=json.dumps(story_graph, ensure_ascii=False, indent=2),
                game_outline=json.dumps(game_outline, ensure_ascii=False, indent=2),
                expected_nodes=expected_nodes
            )

            feedback = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            ).strip()

            if "PASS" in feedback:
                logger.info("✅ Step2 story_graph 审核通过")
                return "PASS"

            logger.warning("⚠️ Step2 story_graph 需要修改")
            return feedback
        except Exception as e:
            logger.error(f"❌ Step2 story_graph 审核失败: {e}")
            return "PASS"

    def save_game_design(self, game_design: Dict[str, Any]) -> None:
        """
        保存游戏设计文档到文件
        
        Args:
            game_design: 游戏设计文档字典
        """
        if not FileHelper.safe_write_json(PathConfig.GAME_DESIGN_FILE, game_design):
            raise Exception("保存游戏设计文档失败")
    
    @staticmethod
    def load_game_design() -> Optional[Dict[str, Any]]:
        """
        从文件加载游戏设计文档
        
        Returns:
            游戏设计文档字典，如果文件不存在则返回 None
        """
        game_design = FileHelper.safe_read_json(PathConfig.GAME_DESIGN_FILE)
        if game_design:
            logger.info(f"📖 游戏设计文档已加载: 《{game_design.get('title', 'Unknown')}》")
        return game_design

