from typing import Dict, Optional, List, Tuple

# --- 游戏状态类 ---
class GameState:
    """游戏状态管理"""
    
    def __init__(self, game_design: Dict, character_info: Optional[Dict] = None):
        self.game_design = game_design
        
        # 基础状态
        self.block = 1
        self.group = 1
        self.time_period = 0  # 0: 上午, 1: 下午, 2: 傍晚, 3: 深夜
        self.location = "开始"
        
        # 角色状态
        self.characters = {}
        
        # 关系等级阈值 (0-5级)
        # 0: 0-19, 1: 20-39, 2: 40-59, 3: 60-79, 4: 80-99, 5: 100
        self.level_thresholds = [0, 20, 40, 60, 80, 100]
        
        # 待播放的关系剧情队列
        self.pending_relationship_stories = [] # List[Tuple[char_name, level]]
        
        if character_info:
            # 从存档加载
            for char_name, char_data in character_info.items():
                self.characters[char_name] = {
                    "affection": char_data.get("affection", 0),
                    "level": char_data.get("level", 0), # 当前等级
                    "relationship_level": char_data.get("relationship_level", "stranger"),
                    "met": char_data.get("met", False),
                    "story_flags": char_data.get("story_flags", []),
                }
        else:
            # 新游戏：从设计文档初始化
            print("🆕 初始化新游戏状态...")
            for char in game_design.get('characters', []):
                char_name = char.get('name')
                if char_name:
                    self.characters[char_name] = {
                        "affection": 0,
                        "level": 0,
                        "relationship_level": "stranger",
                        "met": False,
                        "story_flags": []
                    }
        
        # 标记和状态
        self.story_flags = []
        self.choices_made = []
        
        # 资源
        self.money = 100
    
    @property
    def time_str(self):
        periods = ["上午", "下午", "傍晚", "深夜"]
        # 兼容 scene_N 格式，如果 time_period 很大，可能需要特殊处理
        # 但目前我们假设 StoryParser 会按顺序解析场景
        return periods[self.time_period]
    
    @property
    def is_free_time(self):
        """是否是自由活动时间"""
        return False # 暂时禁用自由活动，完全线性
    
    def advance_time(self):
        """推进时间"""
        # 简单线性推进：每次只推一个场景
        # 实际逻辑应该根据当前 Block 有多少个场景来决定
        # 这里简化为：每次调用 advance_time 就跳到下一个 Block 的第一个场景
        # (因为现在的 StoryParser 把所有场景都放在一个 Block 下，但 key 可能是 scene_1, scene_2...)
        
        # 临时方案：每次直接跳到下一个 Block
        # TODO: 需要更精细的场景索引控制
        self.block += 1
        if self.block > 7:
            self.block = 1
            self.group += 1
        return True
    
    def update_affection(self, character_name: str, value: int):
        """更新好感度并检查等级提升"""
        if character_name in self.characters:
            char = self.characters[character_name]
            old_affection = char["affection"]
            new_affection = max(0, min(100, old_affection + value))
            char["affection"] = new_affection
            
            # 检查等级提升
            current_level = char["level"]
            new_level = current_level
            
            # 计算新等级
            for i, threshold in enumerate(self.level_thresholds):
                if new_affection >= threshold:
                    new_level = i
            
            # 如果等级提升，加入待播放队列
            if new_level > current_level:
                print(f"🆙 {character_name} 等级提升: {current_level} -> {new_level}")
                # 可能一次升多级，需要把中间的剧情都加上
                for lvl in range(current_level + 1, new_level + 1):
                    self.pending_relationship_stories.append((character_name, lvl))
                
                char["level"] = new_level
    
    def add_story_flag(self, flag: str):
        """添加剧情标记"""
        if flag not in self.story_flags:
            self.story_flags.append(flag)

    def to_dict(self):
        """序列化状态"""
        return {
            "group": self.group,
            "block": self.block,
            "time_period": self.time_period,
            "characters": self.characters,
            "story_flags": self.story_flags,
            "choices_made": self.choices_made,
            "money": self.money,
            "pending_relationship_stories": self.pending_relationship_stories
        }

    def from_dict(self, data):
        """反序列化状态"""
        self.group = data.get("group", 1)
        self.block = data.get("block", 1)
        self.time_period = data.get("time_period", 0)
        
        # 合并角色状态（保留新设计中的角色，更新数值）
        saved_chars = data.get("characters", {})
        for name, char_data in saved_chars.items():
            if name in self.characters:
                self.characters[name].update(char_data)
            else:
                self.characters[name] = char_data
                
        self.story_flags = data.get("story_flags", [])
        self.choices_made = data.get("choices_made", [])
        self.money = data.get("money", 100)
        self.pending_relationship_stories = data.get("pending_relationship_stories", [])
