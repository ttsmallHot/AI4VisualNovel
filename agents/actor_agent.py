"""
Actor Agent
~~~~~~~~~~~
演员 Agent - 负责扮演特定角色并审核剧本
"""

import logging
import json
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent

from .config import ActorConfig
from .schemas import ACTOR_IMAGE_CRITIQUE_SCHEMA

logger = logging.getLogger(__name__)


class ActorAgent(BaseAgent):
    """演员 Agent - 角色扮演与剧本审核"""
    
    def __init__(self, character_info: Dict[str, Any], api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化演员 Agent
        
        Args:
            character_info: 角色信息字典 (包含 name, personality, background 等)
            api_key: API Key
            base_url: API Base URL
        """
        character_name = character_info.get('name', 'Unknown')
        super().__init__(
            name=character_name,
            role="演员",
            api_key=api_key,
            base_url=base_url
        )
        self.config = ActorConfig
        self.character_info = character_info
        self.name = character_name
        
        logger.info(f"✅ 演员 Agent ({self.name}) 初始化成功")

    def _build_system_prompt(self) -> str:
        """统一构建 System Prompt（按配置模板注入角色关键信息）"""
        return self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get("personality", ""),
            background=self.character_info.get("background", "")
        )
    
    def perform_plot(
        self,
        plot_summary: str,
        other_characters: List[Dict[str, Any]],
        story_context: str,
        character_expressions: List[str] = []
    ) -> str:
        """根据剧情片段进行表演"""
        logger.info(f"🎭 演员 {self.name} 正在表演片段...")
        
        # 统一使用角色真实名称作为剧本标签
        script_label = self.name
        
        # 传入在场其他角色完整设定（JSON）
        other_chars_info = json.dumps(other_characters, ensure_ascii=False, indent=2)
        
        prompt = self.config.PERFORM_PROMPT.format(
            name=self.name,
            script_label=script_label,
            plot_summary=plot_summary,
            other_characters=other_chars_info,
            story_context=story_context,
            character_expressions=", ".join(character_expressions)
        )
        
        system_prompt = self._build_system_prompt()
        
        try:
            performance = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9 # 表演需要创造力
            )

            return performance
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
        system_prompt = self._build_system_prompt()
        
        # 构建 User Prompt
        user_prompt = self.config.IMAGE_CRITIQUE_PROMPT.format(
            story_background=story_background or "A visual novel game",
            art_style=art_style or "Japanese anime style",
            expression=expression,
            appearance=self.character_info.get("appearance", "")
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
                {
                    "role": "user",
                    "content": content + [
                        {
                            "type": "text",
                            "text": (
                                "请严格输出 JSON，不要额外解释。格式如下：\n"
                                "{\n"
                                "  \"decision\": \"PASS\" 或 \"REVISE\",\n"
                                "  \"feedback\": \"审核意见\"\n"
                                "}\n"
                                "规则：如果需要修改，decision 必须是 REVISE，feedback 必须给出具体可执行修改点。"
                            )
                        }
                    ]
                }
            ]

            critique = self.call_json_with_schema(
                messages=messages,
                schema=ACTOR_IMAGE_CRITIQUE_SCHEMA,
                object_name="actor_image_critique",
                temperature=self.config.TEMPERATURE
            )

            decision = str(critique.get("decision", "REVISE")).strip().upper()
            feedback = str(critique.get("feedback", "")).strip()
            
            # 记录审核意见
            logger.info(f"🎭 演员 {self.name} 的审核结论: {decision}")
            logger.info(f"🎭 演员 {self.name} 的审核意见:\n{feedback}")

            if decision == "PASS":
                logger.info(f"✅ 演员 {self.name} 立绘审核通过")
                return "PASS"
            else:
                logger.warning(f"⚠️ 演员 {self.name} 对立绘提出修改建议")
                return feedback or "请根据角色设定继续修改当前立绘。"
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 立绘审核失败: {str(e)}")
            return "图片审核失败，请重试。"

    def generate_expression_description(
        self,
        expression_name: str,
        neutral_image_path: Optional[str] = None
    ) -> str:
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
        
        system_prompt = self._build_system_prompt()
        
        try:
            user_content: Any = prompt
            if neutral_image_path:
                user_content = [
                    {"type": "text", "text": prompt},
                    {"type": "text", "text": "这是该角色的 neutral 参考立绘："},
                    {"type": "image_url", "image_url": {"url": neutral_image_path}}
                ]

            description = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7
            )
            return description.strip()
        except Exception as e:
            logger.error(f"❌ 生成表情描述失败 ({expression_name}): {e}")
            return f"{self.name} with {expression_name} expression"
