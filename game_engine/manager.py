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
        self.game_state.current_node_id = "root" # 假设根节点ID为 root
        self.game_state.scene_index = 0
        self.play_current_scene()
    
    def advance_story(self):
        """推进剧情 (Node模式下通常由 Jump/Choice 触发，此方法作为备用)"""
        print("⚠️ advance_story 被调用，但在 Node 模式下应由脚本控制跳转")
        pass
    
    def on_scene_complete(self, scene_name: str):
        """场景播放结束回调"""
        print(f"🎬 场景结束: {scene_name}")
        # Node 模式下，如果场景结束且没有跳转，说明该节点剧情播完了
        # 如果是结局节点，则结束游戏
        print("🏁 剧情结束，返回标题画面")
        self.change_scene(TitleScene(self))

    def play_current_scene(self):
        """播放当前节点的剧情"""
        state = self.game_state
        node_id = state.current_node_id
        
        if not node_id:
            print("❌ current_node_id 为空")
            return

        if node_id not in self.parsed_story:
            print(f"⚠️ 未找到节点剧情: {node_id}")
            # 尝试查找是否有默认结局或提示
            return
            
        lines = self.parsed_story[node_id]
        scene_name = f"Node: {node_id}"
        print(f"▶️  播放节点: {node_id} ({len(lines)} 行)")
        
        # 切换到对话场景
        self.change_scene(DialogueScene(self, lines, scene_name))
    
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
