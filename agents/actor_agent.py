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
                response_format={"type": "json_object"}
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
