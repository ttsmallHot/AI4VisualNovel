import pygame
import sys
from typing import Optional

from .config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS
from .data import GameDataLoader, StoryParser
from .state import GameState
from .scenes import TitleScene, DialogueScene

# --- 游戏管理器 ---
class GameManager:
    """游戏管理器"""
    
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("AI Visual Novel Engine")
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
            # 初始化新游戏状态
            self.game_state = GameState(self.game_design)
        else:
            print("⚠️ 游戏设计文档缺失，无法启动")
            self.game_state = None
        
        # 开始场景
        self.current_scene = TitleScene(self)
    
    def load_game_data(self):
        """加载所有游戏数据"""
        print("📚 加载游戏数据...")
        
        self.game_design = GameDataLoader.load_game_design()
        self.story_text = GameDataLoader.load_story()
        
        if self.game_design:
            print(f"✅ 游戏标题: {self.game_design.get('title')}")
        if self.story_text:
            print(f"✅ 剧情长度: {len(self.story_text)} 字符")

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
        self.play_current_scene()
    
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
