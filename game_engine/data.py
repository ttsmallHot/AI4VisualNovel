import json
import re
from typing import Dict, List, Optional
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
    def load_story() -> Optional[str]:
        """加载剧情脚本"""
        if not DataPaths.STORY_FILE.exists():
            print(f"❌ 未找到剧情文件: {DataPaths.STORY_FILE}")
            return None
        
        with open(DataPaths.STORY_FILE, 'r', encoding='utf-8') as f:
            return f.read()


# --- 剧情脚本解析器 ---
class StoryParser:
    """解析 AI 生成的剧情脚本"""
    
    @staticmethod
    def parse_story(story_text: str) -> Dict[str, List[Dict]]:
        """
        解析剧情文本为结构化数据 (DAG-based)
        
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
        # <scene>场景名</scene>
        scene_tag_match = re.match(r'<scene>(.+?)</scene>', line)
        if scene_tag_match:
            return {"type": "scene", "value": scene_tag_match.group(1).strip()}

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

        # <image id="角色名">表情</image>
        image_match = re.match(r'<image\s+id="([^"]+)">([^<]+)</image>', line)
        if image_match:
            char_name = image_match.group(1)
            expression = image_match.group(2).strip()
            return {"type": "image", "value": f"{char_name}-{expression}"}
        
        # <content id="xxx">内容</content> (统一格式，包括旁白和对话)
        content_match = re.match(r'<content\s+id="([^"]+)">([^<]+)</content>', line)
        if content_match:
            speaker = content_match.group(1).strip()
            text = content_match.group(2).strip()
            
            # 旁白特殊处理
            if speaker == "旁白":
                return {"type": "narrator", "text": text}
            else:
                return {"type": "dialogue", "speaker": speaker, "text": text, "emotion": "neutral"}
        
        # [JUMP: node_id]
        jump_match = re.match(r'\[JUMP: (.+?)\]', line)
        if jump_match:
            return {"type": "jump", "target": jump_match.group(1)}

        # [CHOICE]
        if line == '[CHOICE]':
            return {"type": "choice_start"}
        
        # <choice target="node_id">选项文本</choice>
        xml_choice_match = re.match(r'<choice\s+target="([^"]+)">(.+?)</choice>', line)
        if xml_choice_match:
            return {
                "type": "choice_option",
                "index": None,
                "text": xml_choice_match.group(2).strip(),
                "target": xml_choice_match.group(1).strip()
            }
        
        # Unknown line type
        return None
