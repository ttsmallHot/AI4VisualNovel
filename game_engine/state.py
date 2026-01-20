from typing import Dict, Optional, List, Tuple

# --- 游戏状态类 ---
class GameState:
    """游戏状态管理"""
    
    def __init__(self, game_design: Dict):
        self.game_design = game_design
        
        # 基础状态
        self.current_node_id = "root"
        
        # 角色状态
        self.characters = {}
        
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
    
    def add_story_flag(self, flag: str):
        """添加剧情标记"""
        if flag not in self.story_flags:
            self.story_flags.append(flag)
