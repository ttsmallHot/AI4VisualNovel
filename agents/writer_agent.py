"""
Writer Agent
~~~~~~~~~~~~
编剧 Agent - 负责生成每周详细剧情
使用 GPT-4 根据游戏设计和角色状态创作对话和事件
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional
from .llm_client import LLMClient

from .config import APIConfig, WriterConfig, PathConfig, ArtistConfig
from .utils import JSONParser, FileHelper, TextProcessor

logger = logging.getLogger(__name__)


class WriterAgent:
    """编剧 Agent - 剧情生成器"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化编剧 Agent
        
        Args:
            api_key: API Key
            base_url: API Base URL
        """
        self.llm_client = LLMClient(api_key=api_key, base_url=base_url)
        self.config = WriterConfig
        
        logger.info("✅ 编剧 Agent 初始化成功")
    
    def generate_node_story(
        self,
        node_id: str,
        node_info: Dict[str, Any],
        game_design: Dict[str, Any],
        previous_story_summary: str = "",
        critique_feedback: str = "无"
    ) -> str:
        """
        生成指定剧情节点的详细剧情
        
        Args:
            node_id: 节点ID
            node_info: 节点信息 (包含 summary, children 等)
            game_design: 游戏设计文档
            previous_story_summary: 前情提要
            critique_feedback: 演员反馈意见
            
        Returns:
            本节点剧情文本
        """
        logger.info(f"✍️  开始生成节点 【{node_id}】 剧情")
        
        try:
            # 获取节点概要
            node_summary = node_info.get('summary', '剧情发展')
            parent_id = node_info.get('parent')
            
            # 获取父节点摘要 (如果需要，可以从 game_design 中查找)
            parent_summary = "无"
            if parent_id and 'story_tree' in game_design:
                parent_node = game_design['story_tree'].get(parent_id)
                if parent_node:
                    parent_summary = parent_node.get('summary', '无')

            # 获取子节点列表
            children_ids = node_info.get('children', [])
            children_nodes_str = ", ".join(children_ids) if children_ids else "无 (结局)"
            
            # 获取可用场景列表
            available_scenes = self._format_scenes(game_design.get('scenes', []))
            
            # 获取可用表情列表
            available_expressions = ", ".join(ArtistConfig.STANDARD_EXPRESSIONS)
            
            # 构建提示词
            prompt = self.config.NODE_GENERATION_PROMPT.format(
                node_id=node_id,
                game_design=self._format_game_design(game_design),
                node_summary=node_summary,
                parent_summary=parent_summary,
                children_nodes=children_nodes_str,
                available_scenes=available_scenes,
                available_expressions=available_expressions,
                previous_story_summary=previous_story_summary,
                critique_feedback=critique_feedback,
                child_1_id=children_ids[0] if len(children_ids) > 0 else "无",
                child_2_id=children_ids[1] if len(children_ids) > 1 else "无"
            )
            
            # 调用 LLM
            story_content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.TEMPERATURE
            )
            
            return story_content
            
        except Exception as e:
            logger.error(f"❌ 生成剧情失败: {str(e)}")
            raise

    # generate_relationship_story 已移除
    # update_character_states 已移除
            
        except Exception as e:
            logger.error(f"❌ 角色状态更新失败: {e}")
            # 发生错误时返回简单更新的状态
            return self._apply_choice_effects(current_states, choice_effects)
    
    def _apply_choice_effects(
        self,
        states: Dict[str, Any],
        effects: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        应用选择效果到角色状态
        
        Args:
            states: 当前状态
            effects: 效果字典
            
        Returns:
            更新后的状态
        """
        import copy
        new_states = copy.deepcopy(states)
        
        for char_name, change in effects.items():
            if char_name == "money":
                # 金钱变化（在游戏主状态中处理）
                continue
            
            if char_name in new_states:
                char_state = new_states[char_name]
                
                # 好感度变化
                if isinstance(change, (int, float)):
                    affection = char_state.get('affection', 0)
                    new_affection = max(0, min(100, affection + change))
                    char_state['affection'] = new_affection
                    
                    # 更新关系等级
                    char_state['relationship_level'] = self._get_relationship_level(new_affection)
        
        return new_states
    
    def _get_relationship_level(self, affection: int) -> str:
        """根据好感度获取关系等级"""
        for level, (min_aff, max_aff) in self.config.AFFECTION_THRESHOLDS.items():
            if min_aff <= affection < max_aff:
                return level
        return "lover" if affection >= 80 else "stranger"
    
    def _format_game_design(self, game_design: Dict[str, Any]) -> str:
        """格式化游戏设计文档为摘要文本"""
        summary = f"""
【游戏标题】{game_design.get('title', 'Unknown')}

【背景故事】
{game_design.get('background', '')}

【角色设定】
"""
        for char in game_design.get('characters', []):
            summary += f"- {char.get('name', 'Unknown')}: {char.get('personality', '')}\n"
        
        return summary
    
    def _format_scenes(self, scenes: List[Dict[str, Any]]) -> str:
        """格式化场景列表"""
        if not scenes:
            return "未定义场景，可以自由创作"
        
        scene_list = []
        for scene in scenes:
            scene_name = scene.get('name', 'Unknown')
            scene_desc = scene.get('description', '')
            scene_list.append(f"- {scene_name}: {scene_desc}")
        
        return "\n".join(scene_list)
    
    def _get_recent_story(self, story: str, max_chars: int = 2000) -> str:
        """获取最近的剧情片段"""
        if len(story) <= max_chars:
            return story
        return "...\n" + story[-max_chars:]
    
    def append_story(self, story_text: str) -> None:
        """
        将新剧情追加到story.txt
        
        Args:
            story_text: 要追加的剧情文本
        """
        if not FileHelper.safe_append_text(PathConfig.STORY_FILE, story_text):
            raise Exception("追加剧情失败")
    
    @staticmethod
    def load_story() -> str:
        """
        加载完整的story.txt
        
        Returns:
            剧情文本，文件不存在返回空字符串
        """
        try:
            with open(PathConfig.STORY_FILE, 'r', encoding='utf-8') as f:
                story = f.read()
            
            logger.info(f"📖 剧情文件已加载: {len(story)} 字符")
            return story
            
        except FileNotFoundError:
            logger.warning(f"⚠️  剧情文件不存在，将创建新文件")
            return ""
        except Exception as e:
            logger.error(f"❌ 加载剧情文件失败: {e}")
            return ""
    
    def save_character_states(self, states: Dict[str, Any]) -> None:
        """
        保存角色状态到character_info.json
        
        Args:
            states: 角色状态字典
        """
        if not FileHelper.safe_write_json(PathConfig.CHARACTER_INFO_FILE, states):
            raise Exception("保存角色状态失败")
    
    @staticmethod
    def load_character_states() -> Dict[str, Any]:
        """
        加载角色状态
        
        Returns:
            角色状态字典
        """
        states = FileHelper.safe_read_json(PathConfig.CHARACTER_INFO_FILE)
        if states:
            logger.info(f"📖 角色状态已加载: {len(states)} 个角色")
            return states
        return {}
    
    @staticmethod
    def initialize_character_states(game_design: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据游戏设计初始化角色状态
        
        Args:
            game_design: 游戏设计文档
            
        Returns:
            初始化的角色状态
        """
        logger.info("🎬 初始化角色状态")
        
        states = {}
        
        for char in game_design.get('characters', []):
            char_name = char.get('name')
            states[char_name] = {
                "affection": 0,
                "relationship_level": "stranger",
                "story_flags": [],
                "special_events": [],
                "met": False
            }
        
        logger.info(f"✅ 已初始化 {len(states)} 个角色状态")
        
        return states
    
    def parse_story_for_ui(self, story_text: str) -> List[Dict[str, Any]]:
        """
        解析剧情文本为UI可用的数据结构
        
        Args:
            story_text: 原始剧情文本
            
        Returns:
            剧情片段列表，每个片段包含对话、图像、选项等信息
        """
        logger.info("📝 解析剧情文本...")
        
        segments = []
        current_location = None
        current_time = None
        
        lines = story_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 解析场景标题 (## 地点 或 ## 地点 - 时间)
            scene_match = re.match(r'##\s*(.+)', line)
            
            if scene_match:
                content = scene_match.group(1).strip()
                if '-' in content:
                    parts = content.split('-', 1)
                    new_location = parts[0].strip()
                    new_time = parts[1].strip()
                else:
                    new_location = content
                    new_time = "Day" # 默认时间
                
                # 如果场景变化，添加场景切换标记
                if new_location != current_location:
                    segments.append({
                        "type": "scene",
                        "location": new_location,
                        "time": new_time
                    })
                
                current_time = new_time
                current_location = new_location
                continue
            
            # 解析图像标注 ([IMAGE: 角色] 或 [IMAGE: 角色-表情])
            image_match = re.match(r'\[IMAGE:\s*(.+?)\]', line)
            if image_match:
                content = image_match.group(1).strip()
                if '-' in content:
                    character, expression = content.split('-', 1)
                else:
                    character = content
                    expression = "neutral" # 默认表情
                
                character = character.strip()
                expression = expression.strip()
                
                segments.append({
                    "type": "image",
                    "character": character,
                    "expression": expression,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析对话 (角色名: "对话内容")
            dialogue_match = re.match(r'([^:]+):\s*"?(.+?)"?$', line)
            if dialogue_match:
                speaker = dialogue_match.group(1).strip()
                text = dialogue_match.group(2).strip()
                segments.append({
                    "type": "dialogue",
                    "speaker": speaker if speaker != "NARRATOR" else None,
                    "text": text,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项 ([CHOICE])
            if line == '[CHOICE]':
                segments.append({
                    "type": "choice_start",
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项内容 (选项1: "文字" → [效果])
            choice_match = re.match(r'选项(\d+):\s*"(.+?)"\s*→\s*\[(.+?)\]', line)
            if choice_match:
                choice_num = int(choice_match.group(1))
                choice_text = choice_match.group(2).strip()
                effects_str = choice_match.group(3).strip()
                
                # 解析效果
                effects = self._parse_choice_effects(effects_str)
                
                segments.append({
                    "type": "choice_option",
                    "number": choice_num,
                    "text": choice_text,
                    "effects": effects
                })
                continue
        
        logger.info(f"✅ 解析完成: {len(segments)} 个片段")
        return segments
    
    def _parse_choice_effects(self, effects_str: str) -> Dict[str, Any]:
        """
        解析选项效果字符串
        
        Args:
            effects_str: 效果字符串，如 "角色A好感度+5, 金钱-10"
            
        Returns:
            效果字典
        """
        effects = {}
        
        # 分割多个效果
        parts = effects_str.split(',')
        
        for part in parts:
            part = part.strip()
            
            if not part or part == "无影响":
                continue
            
            # 匹配 "角色名好感度+/-数字"
            affection_match = re.match(r'(.+?)好感度([+\-]\d+)', part)
            if affection_match:
                char_name = affection_match.group(1).strip()
                change = int(affection_match.group(2))
                effects[char_name] = change
                continue
            
            # 匹配 "金钱+/-数字"
            money_match = re.match(r'金钱([+\-]\d+)', part)
            if money_match:
                change = int(money_match.group(1))
                effects['money'] = change
                continue
        
        return effects
    
    def summarize_story(self, story_content: str) -> str:
        """
        生成剧情摘要
        
        Args:
            story_content: 剧情内容
            
        Returns:
            剧情摘要
        """
        logger.info("📝 生成剧情摘要...")
        
        try:
            prompt = self.config.SUMMARY_PROMPT.format(story_content=story_content)
            
            summary = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一位擅长总结故事的助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            )
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"❌ 摘要生成失败: {str(e)}")
            return story_content[-500:]  # 失败时回退到截取最后一段


# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试编剧 Agent
    try:
        writer = WriterAgent()
        
        # 测试游戏设计
        test_design = {
            "title": "测试游戏",
            "background": "一个普通的校园故事",
            "outline": {
                "week_1": "主角初次遇见女主角，开始校园生活"
            },
            "characters": [
                {
                    "name": "樱",
                    "personality": "温柔善良",
                    "id": "sakura"
                }
            ]
        }
        
        # 初始化角色状态
        char_states = writer.initialize_character_states(test_design)
        writer.save_character_states(char_states)
        
        print("\n" + "="*50)
        print("✍️  测试剧情生成")
        print("="*50)
        
        # 生成第一周剧情
        story = writer.generate_weekly_story(
            week=1,
            game_design=test_design,
            character_states=char_states
        )
        
        print(f"\n✅ 剧情生成成功！")
        print(f"   长度: {len(story)} 字符")
        print(f"\n前200字符预览:")
        print(story[:200] + "...")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
