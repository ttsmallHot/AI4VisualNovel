import json
import re
from typing import Dict, List, Optional, Any
from .config import DataPaths

# --- 游戏数据加载器 ---
class GameDataLoader:
    """加载 AI 生成的游戏数据"""
    
    @staticmethod
    def load_game_design() -> Optional[Dict]:
        """加载游戏设计文档"""
        if not DataPaths.GAME_DESIGN_FILE.exists():
            print(f"❌ 未找到游戏设计文件: {DataPaths.GAME_DESIGN_FILE}")
            return None
        
        with open(DataPaths.GAME_DESIGN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def load_character_info() -> Optional[Dict]:
        """加载角色信息"""
        if not DataPaths.CHARACTER_INFO_FILE.exists():
            print(f"❌ 未找到角色信息文件: {DataPaths.CHARACTER_INFO_FILE}")
            return None
        
        with open(DataPaths.CHARACTER_INFO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def load_story() -> Optional[str]:
        """加载剧情脚本"""
        if not DataPaths.STORY_FILE.exists():
            print(f"❌ 未找到剧情文件: {DataPaths.STORY_FILE}")
            return None
        
        with open(DataPaths.STORY_FILE, 'r', encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def load_relationship_story(char_id: str, level: int) -> Optional[str]:
        """加载角色关系剧情"""
        file_path = DataPaths.DATA_DIR / "stories" / f"{char_id}_level_{level}.txt"
        if not file_path.exists():
            print(f"⚠️ 未找到关系剧情文件: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()


# --- 剧情脚本解析器 ---
class StoryParser:
    """解析 AI 生成的剧情脚本"""
    
    @staticmethod
    def parse_script(script_text: str) -> List[Dict]:
        """解析简单的剧情脚本（不包含 Group/Block 结构）"""
        lines = []
        for line in script_text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('这里为您生成') or line.startswith('=== End'):
                continue
            
            parsed = StoryParser._parse_line(line)
            if parsed:
                lines.append(parsed)
        return lines

    @staticmethod
    def parse_story(story_text: str) -> Dict[int, Dict[int, Dict[str, List[Dict]]]]:
        """
        解析剧情文本为结构化数据
        
        返回格式:
        {
            1: { # Group 1
                1: { # Block 1
                    "上午": [lines...],
                    "下午": [lines...],
                    "傍晚": [lines...]
                }
            }
        }
        """
        groups = {}
        current_group = 0
        current_block = 0
        current_time = ""
        current_lines = []
        
        lines = story_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # 跳过空行和标题行
            if not line or line.startswith('这里为您生成') or line.startswith('=== End'):
                continue
            
            # 检测 Group/Block 标题: === Group 1 - Block 1 ===
            # 兼容旧格式: === Week 1 - Day 1 ===
            group_block_match = re.match(r'=== (?:Group|Week) (\d+) - (?:Block|Day) (\d+) ===', line)
            if group_block_match:
                current_group = int(group_block_match.group(1))
                current_block = int(group_block_match.group(2))
                
                if current_group not in groups:
                    groups[current_group] = {}
                if current_block not in groups[current_group]:
                    groups[current_group][current_block] = {}
                
                print(f"📖 解析 Group {current_group} - Block {current_block}")
                continue
            
            # 检测场景标题: ## 场景名
            scene_match = re.match(r'## (.+)', line)
            if scene_match:
                # 保存上一个场景
                if current_time and current_lines:
                    groups[current_group][current_block][current_time] = current_lines
                    print(f"   保存场景: {current_time} ({len(current_lines)} 行)")
                
                content = scene_match.group(1).strip()
                # 纯场景名模式，不再解析时间
                current_time = f"scene_{len(groups[current_group][current_block]) + 1}"
                location = content
                
                current_lines = []
                # 自动添加背景指令
                current_lines.append({"type": "background", "value": location})
                print(f"   开始解析场景: {current_time} - {location}")
                continue
            
            # 解析具体内容
            if current_group and current_block and current_time:
                parsed_line = StoryParser._parse_line(line)
                if parsed_line:
                    current_lines.append(parsed_line)
        
        # 保存最后一个场景
        if current_group and current_block and current_time and current_lines:
            groups[current_group][current_block][current_time] = current_lines
        
        return groups
    
    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        """解析单行剧情"""
        # [IF: Role >= Level]
        if_match = re.match(r'\[IF: (.+?) >= (\d+)\]', line)
        if if_match:
            return {
                "type": "if",
                "condition_role": if_match.group(1),
                "condition_level": int(if_match.group(2))
            }
            
        # [ELSE]
        if line == '[ELSE]':
            return {"type": "else"}
            
        # [ENDIF]
        if line == '[ENDIF]':
            return {"type": "endif"}

        # [IMAGE: xxx]
        image_match = re.match(r'\[IMAGE: (.+?)\]', line)
        if image_match:
            return {"type": "image", "value": image_match.group(1)}
        
        # 旁白: xxx (中文) 或 NARRATOR: xxx (英文，兼容)
        if line.startswith('旁白:') or line.startswith('NARRATOR:'):
            prefix_len = 3 if line.startswith('旁白:') else 9
            return {"type": "narrator", "text": line[prefix_len:].strip()}
        
        # 主角: xxx (中文) 或 PROTAGONIST: xxx (英文，兼容)
        if line.startswith('主角:') or line.startswith('PROTAGONIST:'):
            prefix_len = 3 if line.startswith('主角:') else 12
            text = line[prefix_len:].strip()
            return {"type": "dialogue", "speaker": "主角", "text": text, "emotion": "neutral"}
        
        # 其他角色对话 - 支持中文和英文
        # 中文格式: 小日向夏海: "对话"
        # 英文格式: CHARACTER_A: "对话" (兼容)
        dialogue_match = re.match(r'([^:：]+)[：:]\s*(.+)', line)
        if dialogue_match:
            speaker = dialogue_match.group(1).strip()
            text = dialogue_match.group(2).strip()
            # 过滤掉一些特殊情况（如选项文字中的冒号）
            if speaker and not speaker.startswith('选项') and len(speaker) < 20:
                return {"type": "dialogue", "speaker": speaker, "text": text, "emotion": "neutral"}
        
        # [CHOICE]
        if line == '[CHOICE]':
            return {"type": "choice_start"}
        
        # 选项 (格式: 选项N: xxx → [效果])
        choice_match = re.match(r'选项(\d+): (.+?) → \[(.+?)\]', line)
        if choice_match:
            return {
                "type": "choice_option",
                "index": int(choice_match.group(1)),
                "text": choice_match.group(2),
                "effect": choice_match.group(3)
            }
        
        # SOUND_EFFECT
        if line.startswith('SOUND_EFFECT:'):
            return {"type": "sound", "value": line[13:].strip()}
        
        return None
