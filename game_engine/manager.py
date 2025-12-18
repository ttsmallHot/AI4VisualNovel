import pygame
import sys
import json
from typing import Optional

from .config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, DataPaths
from .data import GameDataLoader, StoryParser
from .state import GameState
from .scenes import TitleScene, DialogueScene, Scene

# --- 游戏管理器 ---
class GameManager:
    """游戏管理器"""
    
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("AI Galgame Engine")
        self.clock = pygame.time.Clock()
        self.running = True
        
        # 加载游戏数据
        self.load_game_data()
        
        # 解析剧情
        self.parsed_story = {}
        if self.story_text:
            self.parsed_story = StoryParser.parse_story(self.story_text)
        
        # 创建游戏状态
        if self.game_design:
            # 即使 character_info 为 None，也可以初始化（视为新游戏）
            self.game_state = GameState(self.game_design, self.character_info)
        else:
            print("⚠️ 游戏设计文档缺失，无法启动")
            self.game_state = None
        
        # 开始场景
        self.current_scene = TitleScene(self)
    
    def load_game_data(self):
        """加载所有游戏数据"""
        print("📚 加载游戏数据...")
        
        self.game_design = GameDataLoader.load_game_design()
        self.character_info = GameDataLoader.load_character_info()
        self.story_text = GameDataLoader.load_story()
        
        if self.game_design:
            print(f"✅ 游戏标题: {self.game_design.get('title')}")
        if self.character_info:
            print(f"✅ 角色数量: {len(self.character_info)}")
        if self.story_text:
            print(f"✅ 剧情长度: {len(self.story_text)} 字符")

    def save_game(self):
        """保存游戏"""
        if not self.game_state:
            return
        
        try:
            data = self.game_state.to_dict()
            
            # 保存当前场景的进度
            if isinstance(self.current_scene, DialogueScene):
                data["current_scene_state"] = {
                    "index": self.current_scene.index,
                    "bg_name": self.current_scene.current_bg_name,
                    "char_name": self.current_scene.current_char_name
                }
            
            save_path = DataPaths.DATA_DIR / "savegame.json"
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 游戏已保存至: {save_path}")
        except Exception as e:
            print(f"❌ 保存失败: {e}")

    def load_game(self):
        """读取游戏"""
        if not self.game_state:
            return
            
        save_path = DataPaths.DATA_DIR / "savegame.json"
        if not save_path.exists():
            print("⚠️ 未找到存档文件")
            return
            
        try:
            with open(save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.game_state.from_dict(data)
            print("📂 游戏已读取")
            
            # 重新播放当前场景
            self.play_current_scene()
            
            # 恢复场景进度
            scene_state = data.get("current_scene_state")
            if scene_state and isinstance(self.current_scene, DialogueScene):
                self.current_scene.restore_state(
                    index=scene_state.get("index", 0),
                    bg_name=scene_state.get("bg_name"),
                    char_name=scene_state.get("char_name")
                )
                print(f"🔄 恢复进度: 行 {scene_state.get('index')}")
                
        except Exception as e:
            print(f"❌ 读取失败: {e}")
    
    def get_character_id(self, name: str) -> Optional[str]:
        """根据名字获取角色ID"""
        if not self.game_state or not self.game_state.game_design:
            return None
        
        for char in self.game_state.game_design.get('characters', []):
            if char.get('name') == name:
                return char.get('id')
        return None

    def start_story(self):
        """开始剧情"""
        # 重置状态
        self.game_state.group = 1
        self.game_state.block = 1
        self.game_state.time_period = 0 # 上午
        self.play_current_scene()
    
    def advance_story(self):
        """推进剧情到下一个时间段"""
        # 推进时间
        self.game_state.advance_time()
        self.play_current_scene()
    
    def on_scene_complete(self, scene_name: str):
        """场景播放结束回调"""
        print(f"🎬 场景结束: {scene_name}")
        
        if scene_name.startswith("[支线:"):
            # 支线结束，继续检查是否有其他支线或播放主线
            # 注意：支线不消耗时间
            self.play_current_scene()
        else:
            # 主线结束，推进时间
            self.advance_story()

    def play_current_scene(self):
        """播放当前时间段的场景"""
        state = self.game_state
        
        # 1. 优先检查是否有待播放的关系剧情
        if state.pending_relationship_stories:
            # 取出第一个待播放的剧情
            char_name, level = state.pending_relationship_stories.pop(0)
            print(f"💕 触发关系剧情: {char_name} Lv.{level}")
            
            char_id = self.get_character_id(char_name)
            if char_id:
                script_text = GameDataLoader.load_relationship_story(char_id, level)
                if script_text:
                    lines = StoryParser.parse_script(script_text)
                    scene_name = f"[支线: {char_name} Lv.{level}]"
                    self.change_scene(DialogueScene(self, lines, scene_name))
                    return
                else:
                    print(f"⚠️ 无法加载关系剧情文件，跳过")
            else:
                print(f"⚠️ 无法找到角色ID: {char_name}，跳过")
        
        # 2. 播放主线剧情
        # 检查是否超出范围
        if state.group not in self.parsed_story:
            print("🎊 剧情已全部播放完毕")
            self.change_scene(TitleScene(self))
            return
            
        group_data = self.parsed_story[state.group]
        if state.block not in group_data:
            # 如果这一块没有数据，尝试推进到下一块
            print(f"⚠️ Group {state.group} Block {state.block} 无数据，跳过")
            self.advance_story()
            return
            
        block_data = group_data[state.block]
        time_str = state.time_str # "上午", "下午", "傍晚", "深夜"
        
        # 注意：WriterConfig 中只定义了 "上午", "下午", "傍晚"
        # 如果是 "深夜"，可能没有剧情，直接跳过
        # 兼容新的 scene_N 格式
        if time_str not in block_data:
            # 尝试查找 scene_N 格式的键
            found = False
            for key in block_data.keys():
                if key.startswith("scene_"):
                    # 简单策略：按顺序播放，这里需要更复杂的逻辑来映射时间到场景
                    # 暂时只播放第一个找到的场景，或者修改 GameState 来支持 scene_index
                    scene_lines = block_data[key]
                    scene_name = f"Group {state.group} - Block {state.block} - {key}"
                    print(f"▶️  播放场景: {scene_name}")
                    self.change_scene(DialogueScene(self, scene_lines, scene_name))
                    found = True
                    break
            
            if not found:
                print(f"ℹ️  {time_str} 无剧情，跳过")
                self.advance_story()
            return
            
        scene_lines = block_data[time_str]
        scene_name = f"Group {state.group} - Block {state.block} - {time_str}"
        print(f"▶️  播放场景: {scene_name}")
        
        # 切换到对话场景
        self.change_scene(DialogueScene(self, scene_lines, scene_name))
    
    def change_scene(self, new_scene):
        """切换场景"""
        self.current_scene = new_scene
    
    def run(self):
        """主循环"""
        print("\n🎮 游戏启动！")
        
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                self.current_scene.process_input(event)
            
            self.current_scene.update()
            self.current_scene.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(FPS)
        
        pygame.quit()
        sys.exit()
