"""
Actor Agent
~~~~~~~~~~~
演员 Agent - 负责扮演特定角色并审核剧本
"""

import json
import logging
from typing import Dict, Any, Optional, List
from .llm_client import LLMClient

from .config import ActorConfig

logger = logging.getLogger(__name__)


class ActorAgent:
    """演员 Agent - 角色扮演与剧本审核"""
    
    def __init__(self, character_info: Dict[str, Any], api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化演员 Agent
        
        Args:
            character_info: 角色信息字典 (包含 name, personality, background 等)
            api_key: API Key
            base_url: API Base URL
        """
        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)
        self.config = ActorConfig
        self.character_info = character_info
        self.name = character_info.get('name', 'Unknown')
        self.is_protagonist = character_info.get('is_protagonist', False)
        
        logger.info(f"✅ 演员 Agent ({self.name}) 初始化成功")
    
    def perform_plot(
        self,
        plot_summary: str,
        other_characters: List[Dict[str, Any]],
        story_context: str,
        character_expressions: List[str] = []
    ) -> str:
        """根据剧情片段进行表演"""
        logger.info(f"🎭 演员 {self.name} 正在表演片段...")
        
        # 确定剧本中使用的标签名
        script_label = "我" if self.is_protagonist else self.name
        
        # 构建其他角色的详细信息
        other_chars_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in other_characters
        ])
        
        prompt = self.config.PERFORM_PROMPT.format(
            name=self.name,
            script_label=script_label,
            plot_summary=plot_summary,
            other_characters=other_chars_info,
            story_context=story_context,
            character_expressions=", ".join(character_expressions)
        )
        
        system_prompt = self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get('personality', ''),
            background=self.character_info.get('background', '')
        )
        
        try:
            return self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9 # 表演需要创造力
            )
        except Exception as e:
            logger.error(f"❌ 表演失败: {e}")
            return ""
        
    def critique_visual(
        self, 
        image_path: str, 
        expression: str = "neutral", 
        reference_image_path: Optional[str] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None
    ) -> str:
        """
        审核角色立绘
        
        Args:
            image_path: 图片文件路径
            expression: 表情名称
            reference_image_path: 参考图片路径 (通常是 neutral 表情)
            story_background: 故事背景描述
            art_style: 美术风格描述
            
        Returns:
            审核意见 (PASS 或 修改建议)
        """
        logger.info(f"🎨 演员 {self.name} 正在审核立绘: {image_path} (表情: {expression})...")
        
        # 构建 System Prompt
        system_prompt = self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get('personality', ''),
            background=self.character_info.get('background', '')
        )
        
        # 构建 User Prompt
        user_prompt = self.config.IMAGE_CRITIQUE_PROMPT.format(
            story_background=story_background or "A visual novel game",
            art_style=art_style or "Japanese anime style",
            appearance=self.character_info.get('appearance', ''),
            expression=expression
        )
        
        try:
            # 构造包含图片的消息
            content = [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": image_path}}
            ]
            
            # 如果有参考图，添加到消息中
            if reference_image_path and expression != "neutral":
                content.insert(1, {"type": "text", "text": "这是你的标准立绘 (Neutral 表情) 作为参考："})
                content.insert(2, {"type": "image_url", "image_url": {"url": reference_image_path}})
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            feedback = self.llm_client.chat_completion(
                messages=messages,
                temperature=self.config.TEMPERATURE
            )
            
            feedback = feedback.strip()
            
            # 记录审核意见
            logger.info(f"🎭 演员 {self.name} 的审核意见:\n{feedback}")
            
            if "PASS" in feedback:
                logger.info(f"✅ 演员 {self.name} 立绘审核通过")
                return "PASS"
            else:
                logger.warning(f"⚠️ 演员 {self.name} 对立绘提出修改建议")
                return feedback
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 立绘审核失败: {str(e)}")
            return "PASS"  # 出错时默认通过

    def generate_expression_description(self, expression_name: str) -> str:
        """
        生成特定表情的视觉描述
        
        Args:
            expression_name: 表情名称 (如 'shy', 'happy')
            
        Returns:
            详细的视觉描述
        """
        prompt = self.config.EXPRESSION_DESCRIPTION_PROMPT.format(
            name=self.name,
            expression=expression_name,
            character_info=json.dumps(self.character_info, ensure_ascii=False, indent=2)
        )
        
        system_prompt = self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get('personality', ''),
            background=self.character_info.get('background', '')
        )
        
        try:
            description = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return description.strip()
        except Exception as e:
            logger.error(f"❌ 生成表情描述失败 ({expression_name}): {e}")
            return f"{self.name} with {expression_name} expression"
