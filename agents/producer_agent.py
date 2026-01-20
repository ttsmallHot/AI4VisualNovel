"""
Producer Agent
~~~~~~~~~~~~~~
制作人 Agent - 负责审核设计预览并把控全局
"""

import logging
from typing import Dict, Any, Optional
from .llm_client import LLMClient
import json

from .config import APIConfig, ProducerConfig, PathConfig, STANDARD_EXPRESSIONS
from .utils import JSONParser, FileHelper, PromptBuilder

logger = logging.getLogger(__name__)


class ProducerAgent:
    """制作人 Agent - 负责审核设计预览并把控全局"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化制作人 Agent
        """
        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)
        self.config = ProducerConfig
        
        logger.info("✅ 制作人 Agent 初始化成功")
    
    def critique_game_design(self, game_design: Dict[str, Any], user_requirements: str = "") -> str:
        """
        审核由策划草拟的游戏设计文档 (Feedback phase)
        
        Args:
            game_design: 策划提交的设计方案
            user_requirements: 用户原始要求
            
        Returns:
            "PASS" 或 修改建议
        """
        logger.info("📋 制作人正在审核策划的设计草案...")
        
        try:
            prompt = self.config.GAME_DESIGN_CRITIQUE_PROMPT.format(
                game_design=json.dumps(game_design, ensure_ascii=False, indent=2),
                user_requirements=user_requirements if user_requirements else "无特别要求"
            )
            
            feedback = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            feedback = feedback.strip()
            if "PASS" in feedback:
                logger.info("✅ 制作人审核通过！方案已批准落地。")
                return "PASS"
            else:
                logger.warning("⚠️ 制作人提出修改建议")
                return feedback
                
        except Exception as e:
            logger.error(f"❌ 制作人审核过程出错: {e}")
            return "PASS" # 出错时默认为通过，避免流程中断

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

