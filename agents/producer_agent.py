"""
Producer Agent
~~~~~~~~~~~~~~
制作人 Agent - 负责生成游戏整体设计文档
"""

import logging
from typing import Dict, Any, Optional
from .llm_client import LLMClient

from .config import APIConfig, ProducerConfig, PathConfig
from .utils import JSONParser, FileHelper, PromptBuilder

logger = logging.getLogger(__name__)


class ProducerAgent:
    """制作人 Agent - 游戏设计文档生成器"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化制作人 Agent
        
        Args:
            api_key: API Key，如果不提供则从环境变量读取
            base_url: API Base URL，如果不提供则使用默认值
        """
        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)
        self.config = ProducerConfig
        
        logger.info("✅ 制作人 Agent 初始化成功")
    
    def generate_game_design(
        self,
        game_type: str = None,
        game_style: str = None,
        character_count: int = None,
        requirements: str = ""
    ) -> Dict[str, Any]:
        """
        生成完整的游戏设计文档
        
        Args:
            game_type: 游戏类型（如"校园恋爱"、"奇幻冒险"等）
            game_style: 游戏风格（如"轻松温馨"、"悬疑刺激"等）
            character_count: 可攻略角色数量
            requirements: 用户特别要求
            
        Returns:
            游戏设计文档字典
        """
        # 使用默认值
        game_type = game_type or self.config.DEFAULT_GAME_TYPE
        game_style = game_style or self.config.DEFAULT_GAME_STYLE
        character_count = character_count or self.config.DEFAULT_CHARACTER_COUNT
        
        logger.info(f"🎬 开始生成游戏设计文档...")
        logger.info(f"   类型: {game_type} | 风格: {game_style} | 角色数: {character_count} | 深度: {self.config.MAX_DEPTH}")
        if requirements:
            logger.info(f"   📌 用户要求: {requirements}")
        
        try:
            # 1. CoT 规划阶段
            logger.info("🧠 正在进行剧情结构规划 (CoT)...")
            cot_prompt = f"""请为一款 {game_type} 风格为 {game_style} 的 Galgame 构思一个简短的剧情大纲 (Outline)。
最大深度: {self.config.MAX_DEPTH}
角色数量: {character_count}

【用户特别要求】
{requirements if requirements else "无（请自由发挥）"}

请简要描述：
1. 故事背景与核心冲突
2. 主要角色的设定与关系
3. 故事的大致发展走向（起承转合）

不需要详细规划每一层的节点，只需要提供一个清晰的故事蓝图，作为后续生成详细树状结构的参考。"""

            cot_response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": cot_prompt}
                ],
                temperature=0.8
            )
            logger.info("✅ 规划完成")
            logger.debug(f"CoT 内容: {cot_response[:500]}...")
            
            # 保存 CoT 到日志文件
            try:
                import os
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                cot_file = os.path.join(PathConfig.LOG_DIR, f"producer_cot_{timestamp}.txt")
                with open(cot_file, 'w', encoding='utf-8') as f:
                    f.write(cot_response)
                logger.info(f"💾 CoT 规划过程已保存至: {cot_file}")
            except Exception as e:
                logger.warning(f"⚠️  保存 CoT 失败: {e}")

            # 2. JSON 生成阶段
            logger.info("📝 正在生成详细设计文档 (JSON)...")
            user_prompt = self.config.GENERATION_PROMPT.format(
                game_type=game_type,
                game_style=game_style,
                character_count=character_count,
                max_depth=self.config.MAX_DEPTH,
                requirements=requirements if requirements else "无",
                max_branches=self.config.MAX_BRANCHES
            )
            
            # 将 CoT 结果作为上下文传入
            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": cot_prompt},
                    {"role": "assistant", "content": cot_response},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )
            
            logger.debug(f"LLM 响应长度: {len(content)} 字符")
            
            game_design = JSONParser.parse_ai_response(content)
            
            # 验证必要字段（使用工具类）
            # 注意：outline 替换为 story_tree，endings 已移除
            required_fields = ["title", "background", "story_tree", "characters", "scenes"]
            if not JSONParser.validate_required_fields(game_design, required_fields):
                raise ValueError("生成的设计文档缺少必需字段")
            
            logger.info(f"✅ 游戏设计文档生成成功: 《{game_design['title']}》")
            logger.info(f"   角色数量: {len(game_design['characters'])}")
            logger.info(f"   剧情节点数: {len(game_design['story_tree'])}")
            logger.info(f"   场景数量: {len(game_design.get('scenes', []))}")
            
            # 保存到文件
            self.save_game_design(game_design)
            
            return game_design
            
        except Exception as e:
            logger.error(f"❌ 游戏设计文档生成失败: {e}")
            raise
    
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
    
    def refine_character(self, character: Dict[str, Any]) -> Dict[str, Any]:
        """
        细化单个角色的设定（可选功能）
        
        Args:
            character: 角色基础设定
            
        Returns:
            细化后的角色设定
        """
        logger.info(f"🎨 细化角色设定: {character.get('name', 'Unknown')}")
        
        try:
            prompt = f"""请细化以下角色的设定，增加更多细节：

角色名: {character['name']}
性格: {character['personality']}
外貌: {character['appearance']}
背景: {character['background']}

请补充以下内容（JSON格式）：
{{
    "hobbies": ["爱好1", "爱好2", ...],
    "likes": ["喜欢的事物1", "喜欢的事物2", ...],
    "dislikes": ["讨厌的事物1", "讨厌的事物2", ...],
    "special_traits": ["特殊特征1", "特殊特征2", ...],
    "relationship_with_protagonist": "与主角的初始关系"
}}"""
            
            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )
            
            details = JSONParser.parse_ai_response(content)
            character.update(details)
            
            logger.info(f"✅ 角色细化完成: {character['name']}")
            return character
            
        except Exception as e:
            logger.error(f"❌ 角色细化失败: {e}")
            return character  # 返回原始角色设定


# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试制作人 Agent
    try:
        producer = ProducerAgent()
        
        # 生成游戏设计文档
        game_design = producer.generate_game_design(
            game_type="校园恋爱",
            game_style="轻松温馨",
            character_count=3
        )
        
        print("\n" + "="*50)
        print("🎮 游戏设计文档生成成功！")
        print("="*50)
        print(f"\n📖 游戏标题: {game_design['title']}")
        print(f"\n📝 背景故事:\n{game_design['background']}")
        print(f"\n👥 可攻略角色:")
        for char in game_design['characters']:
            print(f"   - {char['name']}: {char['personality']}")
        print("\n✅ 完整设计已保存到 data/game_design.json")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
