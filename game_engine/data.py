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
        if DataPaths.CHARACTER_INFO_FILE.exists():
            with open(DataPaths.CHARACTER_INFO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        print(f"ℹ️  未找到角色存档文件 (新游戏): {DataPaths.CHARACTER_INFO_FILE}")
        return None
    
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
    def parse_story(story_text: str) -> Dict[str, List[Dict]]:
        """
        解析剧情文本为结构化数据 (Tree-based)
        
        返回格式:
        {
            "node_id": [lines...]
        }
        """
        nodes = {}
        current_node_id = None
        current_lines = []
        
        lines = story_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # 跳过空行和无关行
            if not line or line.startswith('这里为您生成') or line.startswith('=== End'):
                continue
            
            # 匹配节点头: === Node: node_id ===
            node_match = re.match(r'===\s*Node:\s*(.+?)\s*===', line, re.IGNORECASE)
            if node_match:
                # 保存上一个节点
                if current_node_id:
                    nodes[current_node_id] = current_lines
                
                current_node_id = node_match.group(1).strip()
                current_lines = []
                print(f"📖 解析 Node: {current_node_id}")
                continue
            
            # 解析行内容
            if current_node_id:
                parsed = StoryParser._parse_line(line)
                if parsed:
                    current_lines.append(parsed)
        
        # 保存最后一个节点
        if current_node_id:
            nodes[current_node_id] = current_lines
            
        return nodes
    
    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        """解析单行剧情"""
        # ## [场景名]
        # 兼容两种格式: "## [场景名]" 和 "## 场景名"
        scene_match = re.match(r'##\s*\[?(.+?)\]?$', line)
        if scene_match:
            return {"type": "scene", "value": scene_match.group(1).strip()}

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
        
        # [JUMP: node_id]
        jump_match = re.match(r'\[JUMP: (.+?)\]', line)
        if jump_match:
            return {"type": "jump", "target": jump_match.group(1)}

        # [CHOICE]
        if line == '[CHOICE]':
            return {"type": "choice_start"}
        
        # 选项 (格式: 1. Option Text [JUMP: node_id])
        # 兼容格式: "1. 选项文字 [JUMP: node_id]" 和 "1. 选项文字"
        # 使用更宽松的正则，允许 [JUMP] 部分可选，防止解析失败
        choice_match = re.match(r'(\d+)\.\s*(.+?)(?:\s*\[JUMP:\s*(.+?)\])?$', line)
        if choice_match:
            text = choice_match.group(2).strip()
            target = choice_match.group(3).strip() if choice_match.group(3) else None
            
            #以此防止 [JUMP 被包含在 text 中 (如果正则贪婪匹配了)
            if '[JUMP' in text:
                text = text.split('[JUMP')[0].strip()
                
            return {
                "type": "choice_option",
                "index": int(choice_match.group(1)),
                "text": text,
                "target": target
            }
        
        # 旧格式兼容: 选项N: xxx → [效果]
        old_choice_match = re.match(r'选项(\d+): (.+?) → \[(.+?)\]', line)
        if old_choice_match:
             return {
                "type": "choice_option",
                "index": int(old_choice_match.group(1)),
                "text": old_choice_match.group(2),
                "effect": old_choice_match.group(3) # Legacy effect
            }

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
        
        # SOUND_EFFECT
        if line.startswith('SOUND_EFFECT:'):
            return {"type": "sound", "value": line[13:].strip()}
        
        return None
