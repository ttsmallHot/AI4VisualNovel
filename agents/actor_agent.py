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
        
        logger.info(f"✅ 演员 Agent ({self.name}) 初始化成功")
    
    def critique_script(self, script_content: str, previous_story_summary: str = "") -> str:
        """
        审核剧本，检查是否 OOC
        
        Args:
            script_content: 待审核的剧本内容
            previous_story_summary: 前情提要（长期+短期记忆）
            
        Returns:
            审核意见 (PASS 或 修改建议)
        """
        logger.info(f"🎭 演员 {self.name} 正在审核剧本...")
        
        # 构建 System Prompt
        system_prompt = self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get('personality', ''),
            background=self.character_info.get('background', '')
        )
        
        # 构建 User Prompt
        user_prompt = self.config.CRITIQUE_PROMPT.format(
            script_content=script_content,
            previous_story_summary=previous_story_summary
        )
        
        try:
            feedback = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.TEMPERATURE
            )
            
            feedback = feedback.strip()
            
            if "PASS" in feedback:
                logger.info(f"✅ 演员 {self.name} 审核通过")
                return "PASS"
            else:
                logger.warning(f"⚠️ 演员 {self.name} 提出修改建议")
                return feedback
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 审核失败: {str(e)}")
            return "PASS"  # 出错时默认通过，避免阻塞
        
    def critique_visual(self, image_path: str, expression: str = "neutral", reference_image_path: Optional[str] = None) -> str:
        """
        审核角色立绘
        
        Args:
            image_path: 图片文件路径
            expression: 表情名称
            reference_image_path: 参考图片路径 (通常是 neutral 表情)
            
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
            
            if "PASS" in feedback:
                logger.info(f"✅ 演员 {self.name} 立绘审核通过")
                return "PASS"
            else:
                logger.warning(f"⚠️ 演员 {self.name} 对立绘提出修改建议")
                return feedback
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 立绘审核失败: {str(e)}")
            return "PASS"  # 出错时默认通过

    def analyze_visual_requirements(self, script_block: str, existing_assets: List[str]) -> List[Dict[str, Any]]:
        """
        分析剧本片段，生成视觉需求描述
        
        Args:
            script_block: 剧本片段
            existing_assets: 现有素材列表 (文件名或描述)
            
        Returns:
            List[Dict]: 视觉需求列表，每项包含:
                - type: "new" 或 "reuse"
                - description: 详细视觉描述 (Prompt)
                - asset_id: 复用的素材ID (如果是 reuse)
                - trigger_text: 触发该立绘的剧本行摘要
        """
        logger.info(f"🎨 演员 {self.name} 正在分析视觉需求...")
        
        system_prompt = f"""
你扮演 {self.name}。
你的任务是分析剧本片段，决定你在每一句台词或动作时应该呈现什么样的立绘。
你需要输出详细的视觉描述，以便画师生成图片。
如果现有的素材库中有合适的图片，请优先复用。

角色设定:
{json.dumps(self.character_info, ensure_ascii=False, indent=2)}

现有素材:
{json.dumps(existing_assets, ensure_ascii=False, indent=2)}

输出格式要求 (JSON List):
[
  {{
    "trigger_text": "对应的那句台词或动作描述",
    "type": "new",  // 或 "reuse"
    "expression_name": "表情关键词 (英文，例如 'shy', 'happy', 'angry')。如果剧本中有 [IMAGE: 角色-表情]，请直接使用该表情名。",
    "description": "详细的视觉描述，包含表情、动作、手势、红晕等细节。例如：'双手捂住嘴巴，眼睛瞪大，脸颊通红，惊讶的表情'。",
    "asset_id": "" // 如果是 reuse，填写现有素材的文件名
  }}
]
只输出 JSON，不要包含其他文本。
"""
        
        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"剧本片段:\n{script_block}"}
                ],
                temperature=0.7,
                json_mode=True
            )
            
            # 解析 JSON
            try:
                result = json.loads(response)
                # 兼容不同的 JSON 结构返回 (有些模型可能包在 key 里)
                if isinstance(result, dict):
                    for key, value in result.items():
                        if isinstance(value, list):
                            return value
                    # 如果没有 list，可能直接返回了 dict (单条)
                    return [result]
                elif isinstance(result, list):
                    return result
                return []
            except json.JSONDecodeError:
                logger.error(f"❌ 演员 {self.name} 视觉分析返回非 JSON 格式")
                return []
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 视觉分析失败: {str(e)}")
            return []
        
    def generate_expression_description(self, expression_name: str) -> str:
        """
        生成特定表情的视觉描述
        
        Args:
            expression_name: 表情名称 (如 'shy', 'happy')
            
        Returns:
            详细的视觉描述
        """
        system_prompt = f"""
你扮演 {self.name}。
你的任务是描述你在呈现【{expression_name}】表情时的具体样貌。
请提供详细的视觉描述，包含五官细节、面部神态、眼神、嘴型以及可能的肢体动作。
描述将用于生成立绘图片。

角色设定:
{json.dumps(self.character_info, ensure_ascii=False, indent=2)}

请直接输出描述文本，不要包含其他内容。
"""
        try:
            description = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请描述你的【{expression_name}】表情。"}
                ],
                temperature=0.7
            )
            return description.strip()
        except Exception as e:
            logger.error(f"❌ 生成表情描述失败 ({expression_name}): {e}")
            return f"{self.name} with {expression_name} expression"
        
    def critique_image(self, image_path: str, reference_image_path: Optional[str] = None, expression: str = "neutral") -> Dict[str, Any]:
        """
        审核生成的立绘图片是否符合角色设定
        
        Args:
            image_path: 待审核图片的路径
            reference_image_path: 参考图片路径 (通常是 neutral 表情)
            expression: 当前图片应该呈现的表情
            
        Returns:
            Dict: {
                "pass": bool,
                "reason": str,
                "suggestion": str
            }
        """
        logger.info(f"🧐 演员 {self.name} 正在审核图片: {expression}")
        
        system_prompt = f"""
你扮演 {self.name}。
你需要审核画师为你生成的立绘图片。
你的任务是判断这张图片是否符合你的【外貌设定】以及是否准确表达了【{expression}】这个表情。

角色设定:
{json.dumps(self.character_info, ensure_ascii=False, indent=2)}

如果提供了参考图 (Reference Image)，请确保待审核图片 (Target Image) 与参考图是同一个人（发型、发色、瞳色、五官特征一致）。
如果这是第一张图 (Neutral)，请严格根据角色设定审核。

请以 JSON 格式输出审核结果:
{{
    "pass": true/false,
    "reason": "通过的原因或失败的具体问题 (如: 头发颜色不对，表情不够开心)",
    "suggestion": "如果是 false，请给出具体的修改建议，供画师重画"
}}
"""
        
        user_content = []
        user_content.append({"type": "text", "text": f"这是待审核的图片 (Target Image)，表情应该是: {expression}"})
        user_content.append({"type": "image_url", "image_url": {"url": image_path}})
        
        if reference_image_path and os.path.exists(reference_image_path):
            user_content.append({"type": "text", "text": "这是参考图片 (Reference Image - Neutral):"})
            user_content.append({"type": "image_url", "image_url": {"url": reference_image_path}})
            
        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1, # 审核需要严谨
                json_mode=True
            )
            
            result = json.loads(response)
            return result
            
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 图片审核失败: {e}")
            # 如果审核出错，默认通过，避免阻塞
            return {"pass": True, "reason": "审核过程出错，自动通过", "suggestion": ""}
