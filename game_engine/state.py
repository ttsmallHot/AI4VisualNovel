from typing import Dict, Optional, List, Tuple

# --- 游戏状态类 ---
class GameState:
    """游戏状态管理"""
    
    def __init__(self, game_design: Dict, character_info: Optional[Dict] = None):
        self.game_design = game_design
        
        # 基础状态
        self.current_node_id = "root"
        self.scene_index = 0 # 当前节点内的场景索引
        
        # 角色状态 (仅保留基本信息，移除好感度)
        self.characters = {}
        
        if character_info:
            # 从存档加载
            self.current_node_id = character_info.get("current_node_id", "root")
            self.scene_index = character_info.get("scene_index", 0)
            # 加载其他状态...
        else:
            # 新游戏：从设计文档初始化
            print("🆕 初始化新游戏状态...")
            for char in game_design.get('characters', []):
                char_name = char.get('name')
                if char_name:
                    self.characters[char_name] = {
                        "met": False,
                        "story_flags": []
                    }
        
        # 标记和状态
        self.story_flags = []
        self.choices_made = []
    
    def set_node(self, node_id: str):
        """跳转到指定节点"""
        self.current_node_id = node_id
        self.scene_index = 0
        print(f"🔀 跳转到节点: {node_id}")

    def add_story_flag(self, flag: str):
        """添加剧情标记"""
        if flag not in self.story_flags:
            self.story_flags.append(flag)

    def to_dict(self):
        """序列化状态"""
        return {
            "current_node_id": self.current_node_id,
            "scene_index": self.scene_index,
            "characters": self.characters,
            "story_flags": self.story_flags,
            "choices_made": self.choices_made
        }

    def from_dict(self, data):
        """反序列化状态"""
        self.current_node_id = data.get("current_node_id", "root")
        self.scene_index = data.get("scene_index", 0)
        
        # 合并角色状态
        saved_chars = data.get("characters", {})
        for name, char_data in saved_chars.items():
            if name in self.characters:
                self.characters[name].update(char_data)
            else:
                self.characters[name] = char_data
                
        self.story_flags = data.get("story_flags", [])
        self.choices_made = data.get("choices_made", [])
