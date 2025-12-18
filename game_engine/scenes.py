import pygame
import sys
import math
import textwrap
import re
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

from .config import Colors, SCREEN_WIDTH, SCREEN_HEIGHT, DataPaths
from .ui import Button, get_font, draw_panel

if TYPE_CHECKING:
    from .manager import GameManager

# --- 场景基类 ---
class Scene:
    def __init__(self, manager: 'GameManager'):
        self.manager = manager
    def process_input(self, event): pass
    def update(self): pass
    def draw(self, screen): pass


# --- 标题场景 ---
class TitleScene(Scene):
    """游戏标题场景"""
    def __init__(self, manager: 'GameManager'):
        super().__init__(manager)
        self.font_large = get_font(72, bold=True)
        self.font_small = get_font(32)
        
        self.start_btn = Button(SCREEN_WIDTH//2 - 120, 500, 240, 60, "开始旅程", self.start_game)
        self.quit_btn = Button(SCREEN_WIDTH//2 - 120, 600, 240, 60, "离开游戏", sys.exit)
        self.time_offset = 0
        
        # 显示游戏标题
        self.game_title = manager.game_state.game_design.get('title', '我的 Galgame') if manager.game_state else '我的 Galgame'

    def start_game(self):
        # 开始第一周第一天的剧情
        self.manager.start_story()

    def process_input(self, event):
        self.start_btn.handle_event(event)
        self.quit_btn.handle_event(event)

    def update(self):
        self.start_btn.update()
        self.quit_btn.update()
        self.time_offset += 0.05

    def draw(self, screen):
        screen.fill(Colors.BG_MORNING)
        
        # 云朵动画
        for i in range(5):
            x = (i * 200 + self.time_offset * 10) % (SCREEN_WIDTH + 200) - 100
            y = 100 + math.sin(self.time_offset + i) * 20
            pygame.draw.ellipse(screen, (255, 255, 255, 150), (x, y, 120, 60))

        # 标题
        title = self.font_large.render(self.game_title, True, Colors.WHITE)
        shadow = self.font_large.render(self.game_title, True, (0,0,0,50))
        screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH//2 + 4, 250 + 4)))
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH//2, 250)))
        
        self.start_btn.draw(screen, self.font_small)
        self.quit_btn.draw(screen, self.font_small)


# --- 对话场景 ---
class DialogueScene(Scene):
    """对话场景 - 支持 AI 生成的剧情"""
    
    def __init__(self, manager: 'GameManager', script_lines: List[Dict], scene_name: str = ""):
        super().__init__(manager)
        self.script_lines = script_lines
        self.scene_name = scene_name
        
        self.index = 0
        self.font_text = get_font(26)
        self.font_name = get_font(30, bold=True)
        
        self.full_text = ""
        self.current_display_text = ""
        self.char_counter = 0
        self.typing_speed = 1.5
        self.finished_typing = False
        
        # 当前状态
        self.current_speaker = None
        self.current_emotion = "neutral"
        self.current_character_image = None
        
        # 选择支状态
        self.in_choice = False
        self.choice_options = []
        self.choice_buttons = []
        
        # 系统按钮
        self.save_btn = Button(SCREEN_WIDTH - 110, 10, 100, 40, "保存", self.manager.save_game)
        self.load_btn = Button(SCREEN_WIDTH - 220, 10, 100, 40, "读取", self.manager.load_game)
        
        # 加载角色图像缓存
        self.character_images = {}
        self.current_background = None
        self.current_bg_name = None # 保存当前背景名
        self.current_char_name = None # 保存当前角色名
        self.background_images = {}
        
        self.load_line()
    
    def restore_state(self, index: int, bg_name: Optional[str], char_name: Optional[str]):
        """恢复场景状态"""
        self.index = index
        
        # 恢复背景
        if bg_name:
            self.current_bg_name = bg_name
            self.current_background = self.load_background_image(bg_name)
            
        # 恢复立绘
        if char_name:
            self.current_char_name = char_name
            char_id = self._get_character_id(char_name)
            if char_id:
                self.current_character_image = self.load_character_image(char_id, "neutral")
        
        # 重新加载当前行（刷新文本显示）
        self.load_line()

    def load_background_image(self, bg_name: str) -> Optional[pygame.Surface]:
        """加载背景图像"""
        if bg_name in self.background_images:
            return self.background_images[bg_name]
            
        # 尝试查找背景
        # 1. 直接匹配
        bg_path = DataPaths.BACKGROUNDS_DIR / f"{bg_name}.png"
        if not bg_path.exists():
            # 2. 尝试匹配 ID (假设 game_design 中有 scenes 定义)
            # 这里简单处理：尝试查找包含名称的文件
            for file in DataPaths.BACKGROUNDS_DIR.glob("*.png"):
                if bg_name in file.stem or file.stem in bg_name:
                    bg_path = file
                    break
        
        if bg_path.exists():
            try:
                image = pygame.image.load(str(bg_path))
                image = pygame.transform.scale(image, (SCREEN_WIDTH, SCREEN_HEIGHT))
                self.background_images[bg_name] = image
                return image
            except Exception as e:
                print(f"⚠️ 加载背景失败 {bg_path}: {e}")
        
        return None

    def load_character_image(self, character_id: str, emotion: str = "neutral") -> Optional[pygame.Surface]:
        """加载角色立绘"""
        cache_key = f"{character_id}_{emotion}"
        
        if cache_key in self.character_images:
            return self.character_images[cache_key]
        
        # 尝试从 data/images/characters 加载
        char_dir = DataPaths.CHARACTERS_DIR / character_id.lower()
        image_path = char_dir / f"{emotion}.png"
        
        if not image_path.exists():
            # 尝试 neutral
            image_path = char_dir / "neutral.png"
        
        if image_path.exists():
            try:
                image = pygame.image.load(str(image_path))
                # 缩放到合适大小 (例如 400x600)
                image = pygame.transform.scale(image, (400, 600))
                self.character_images[cache_key] = image
                return image
            except Exception as e:
                print(f"⚠️ 加载图像失败 {image_path}: {e}")
                return None
        
        return None
    
    def load_line(self):
        """加载当前行"""
        if self.index >= len(self.script_lines):
            self.end_dialogue()
            return
        
        line = self.script_lines[self.index]
        line_type = line.get("type")
        
        # --- 控制流指令 ---
        if line_type == "if":
            role = line.get("condition_role")
            level = line.get("condition_level")
            
            if self._check_condition(role, level):
                # 条件满足，进入 IF 块
                print(f"✅ 条件满足: {role} >= {level}")
                self.index += 1
                self.load_line()
            else:
                # 条件不满足，跳到 ELSE 或 ENDIF
                print(f"❌ 条件不满足: {role} < {level}，跳过...")
                self._skip_to_else_or_endif()
                # 跳过指令本身
                self.index += 1
                self.load_line()
            return

        elif line_type == "else":
            # 如果执行到 ELSE 指令，说明刚才执行了 IF 块，现在需要跳过 ELSE 块
            print("🔀 遇到 ELSE，跳过到 ENDIF")
            self._skip_to_endif()
            self.index += 1
            self.load_line()
            return

        elif line_type == "endif":
            # ENDIF 只是标记，直接继续
            self.index += 1
            self.load_line()
            return

        # --- 常规指令 ---
        
        # 处理背景
        if line_type == "background":
            bg_name = line.get("value", "").strip()
            self.current_bg_name = bg_name # 记录状态
            bg_image = self.load_background_image(bg_name)
            if bg_image:
                self.current_background = bg_image
                print(f"🖼️ 切换背景: {bg_name}")
            else:
                print(f"⚠️ 未找到背景: {bg_name}")
            
            self.index += 1
            self.load_line()
            return

        # 处理图像
        if line_type == "image":
            image_value = line.get("value", "").strip()
            self.current_char_name = image_value # 记录状态
            
            # 如果是"无"或空，清除立绘
            if not image_value or image_value == "无":
                self.current_character_image = None
            else:
                # 直接使用角色名加载图像（统一使用 neutral 表情）
                char_id = self._get_character_id(image_value)
                if char_id:
                    self.current_character_image = self.load_character_image(char_id, "neutral")
                    print(f"📸 加载角色立绘: {image_value} (ID: {char_id})")
                else:
                    print(f"⚠️ 未找到角色: {image_value}")
                    self.current_character_image = None
            
            self.index += 1
            self.load_line()  # 继续下一行
            return
        
        # 处理旁白
        elif line_type == "narrator":
            self.current_speaker = None
            self.full_text = line.get("text", "")
            self.current_character_image = None
        
        # 处理对话
        elif line_type == "dialogue":
            speaker_id = line.get("speaker")
            
            # 转换角色 ID 到显示名称
            if speaker_id == "主角":
                self.current_speaker = "我"
                # 主角说话时可以选择清除立绘或保持
                # self.current_character_image = None  # 取消注释可以清除
            else:
                # 查找角色名称
                char_name = self._get_character_name(speaker_id)
                self.current_speaker = char_name
                
                # 如果当前没有立绘，尝试加载该角色的立绘
                if not self.current_character_image:
                    char_id = self._get_character_id(char_name)
                    if char_id:
                        self.current_character_image = self.load_character_image(char_id, "neutral")
            
            self.full_text = line.get("text", "")
        
        # 处理选择支
        elif line_type == "choice_start":
            self.in_choice = True
            self.choice_options = []
            # 收集所有选项
            temp_index = self.index + 1
            while temp_index < len(self.script_lines):
                next_line = self.script_lines[temp_index]
                if next_line.get("type") == "choice_option":
                    self.choice_options.append(next_line)
                    temp_index += 1
                else:
                    break
            
            self.create_choice_buttons()
            return
        
        # 处理音效
        elif line_type == "sound":
            # TODO: 播放音效
            self.index += 1
            self.load_line()
            return
        
        else:
            self.index += 1
            self.load_line()
            return
        
        # 重置打字机效果
        self.current_display_text = ""
        self.char_counter = 0
        self.finished_typing = False
    
    def _check_condition(self, role_name: str, target_level: int) -> bool:
        """检查条件是否满足"""
        if not self.manager.game_state:
            return False
        
        # 查找角色
        char_data = self.manager.game_state.characters.get(role_name)
        if not char_data:
            # 尝试通过 ID 查找
            char_id = self._get_character_id(role_name)
            # 反向查找 name? 比较麻烦，假设 role_name 就是 name
            # 如果找不到，尝试遍历
            for name, data in self.manager.game_state.characters.items():
                if name == role_name: # 已经 check 过了
                    pass
            return False
            
        current_level = char_data.get("level", 0)
        return current_level >= target_level

    def _skip_to_else_or_endif(self):
        """跳过代码直到遇到 ELSE 或 ENDIF (考虑嵌套)"""
        depth = 0
        while self.index + 1 < len(self.script_lines):
            self.index += 1
            line = self.script_lines[self.index]
            l_type = line.get("type")
            
            if l_type == "if":
                depth += 1
            elif l_type == "endif":
                if depth == 0:
                    return # 找到了匹配的 ENDIF
                depth -= 1
            elif l_type == "else":
                if depth == 0:
                    return # 找到了匹配的 ELSE
        
    def _skip_to_endif(self):
        """跳过代码直到遇到 ENDIF (考虑嵌套)"""
        depth = 0
        while self.index + 1 < len(self.script_lines):
            self.index += 1
            line = self.script_lines[self.index]
            l_type = line.get("type")
            
            if l_type == "if":
                depth += 1
            elif l_type == "endif":
                if depth == 0:
                    return # 找到了匹配的 ENDIF
                depth -= 1

    def _get_character_name(self, character_id: str) -> str:
        """根据 ID 获取角色显示名称"""
        # 从 game_design 中查找
        if self.manager.game_state:
            for char in self.manager.game_state.game_design.get('characters', []):
                if char.get('id', '').upper() == character_id.upper():
                    return char.get('name', character_id)
        
        # ID 转名称映射
        id_map = {
            "PROTAGONIST": "我",
            "NARRATOR": "旁白"
        }
        return id_map.get(character_id.upper(), character_id)

    def _get_character_id(self, character_name: str) -> Optional[str]:
        """根据名称获取角色 ID"""
        if self.manager.game_state:
            for char in self.manager.game_state.game_design.get('characters', []):
                if char.get('name') == character_name:
                    return char.get('id')
        return None

    def create_choice_buttons(self):
        """创建选择支按钮"""
        self.choice_buttons = []
        count = len(self.choice_options)
        
        button_height = 60
        spacing = 20
        total_height = count * button_height + (count - 1) * spacing
        start_y = (SCREEN_HEIGHT - total_height) // 2
        
        for i, choice in enumerate(self.choice_options):
            button_y = start_y + i * (button_height + spacing)
            button_width = 600
            button_x = (SCREEN_WIDTH - button_width) // 2
            
            text = f"{i+1}. {choice.get('text')}"
            
            btn = Button(
                button_x, button_y, button_width, button_height,
                text,
                lambda idx=i: self.make_choice(idx)
            )
            self.choice_buttons.append(btn)
    
    def make_choice(self, choice_index: int):
        """做出选择"""
        if choice_index < len(self.choice_options):
            choice = self.choice_options[choice_index]
            effect = choice.get("effect", "")
            
            # 解析效果
            self._apply_choice_effect(effect)
            
            # 记录选择
            self.manager.game_state.choices_made.append({
                "scene": self.scene_name,
                "choice": choice.get("text"),
                "effect": effect
            })
        
        # 跳过选择支行，继续后续剧情
        self.index += len(self.choice_options) + 1
        self.in_choice = False
        self.choice_options = []
        self.choice_buttons = []
        
        self.load_line()
    
    def _apply_choice_effect(self, effect_text: str):
        """应用选择效果"""
        # 解析效果文本，例如: "夏语好感度+5, 心情+5"
        effects = [e.strip() for e in effect_text.split(',')]
        
        for effect in effects:
            # 好感度
            affection_match = re.search(r'(.+?)好感度([+\-]\d+)', effect)
            if affection_match:
                char_name = affection_match.group(1)
                value = int(affection_match.group(2))
                self.manager.game_state.update_affection(char_name, value)
                print(f"📊 {char_name} 好感度 {value:+d}")
            
            # 标记
            if '获得' in effect or '触发' in effect:
                flag_match = re.search(r'【(.+?)】', effect)
                if flag_match:
                    flag = flag_match.group(1)
                    self.manager.game_state.add_story_flag(flag)
                    print(f"🚩 获得标记: {flag}")
    
    def end_dialogue(self):
        """结束对话，返回地图或下一场景"""
        # 通知管理器场景结束
        self.manager.on_scene_complete(self.scene_name)
    
    def update(self):
        # 更新系统按钮
        self.save_btn.update()
        self.load_btn.update()

        # 更新选择按钮
        if self.in_choice:
            for btn in self.choice_buttons:
                btn.update()
            return
        
        # 打字机效果
        if not self.finished_typing:
            self.char_counter += self.typing_speed
            if int(self.char_counter) > len(self.full_text):
                self.current_display_text = self.full_text
                self.finished_typing = True
            else:
                self.current_display_text = self.full_text[:int(self.char_counter)]
    
    def process_input(self, event):
        # 处理系统按钮
        self.save_btn.handle_event(event)
        self.load_btn.handle_event(event)

        # 处理选择支点击
        if self.in_choice:
            for btn in self.choice_buttons:
                btn.handle_event(event)
            return
        
        # 点击或空格继续
        if event.type == pygame.MOUSEBUTTONDOWN or (event.type == pygame.KEYDOWN and event.key in [pygame.K_SPACE, pygame.K_RETURN]):
            if not self.finished_typing:
                # 快进
                self.current_display_text = self.full_text
                self.finished_typing = True
            else:
                # 下一行
                self.index += 1
                self.load_line()
    
    def draw(self, screen):
        # 绘制背景
        if self.current_background:
            screen.blit(self.current_background, (0, 0))
        else:
            screen.fill(Colors.BG_MORNING)
        
        # 绘制时间信息
        # time_str = f"Week {self.manager.game_state.week} - Day {self.manager.game_state.day} - {self.manager.game_state.time_str}"
        # 模糊时间概念，只显示时段
        time_str = f"{self.manager.game_state.time_str}"
        time_surf = self.font_text.render(time_str, True, Colors.WHITE)
        time_bg_rect = time_surf.get_rect(topleft=(20, 20))
        time_bg_rect.inflate_ip(20, 10)
        pygame.draw.rect(screen, (0, 0, 0, 150), time_bg_rect, border_radius=5)
        screen.blit(time_surf, (30, 25))

        # 绘制系统按钮
        self.save_btn.draw(screen, self.font_text)
        self.load_btn.draw(screen, self.font_text)
        
        # 绘制角色立绘
        if self.current_character_image and isinstance(self.current_character_image, pygame.Surface):
            char_x = SCREEN_WIDTH - 450  # 右侧显示
            char_y = SCREEN_HEIGHT - 600
            screen.blit(self.current_character_image, (char_x, char_y))
        elif self.current_speaker and self.current_speaker != "我":
            # 简单的角色占位符（如果没有图像）
            char_color = self._get_character_color(self.current_speaker)
            body_poly = [
                (SCREEN_WIDTH//2 - 60, 600), 
                (SCREEN_WIDTH//2 - 40, 200), 
                (SCREEN_WIDTH//2 + 40, 200), 
                (SCREEN_WIDTH//2 + 60, 600)  
            ]
            pygame.draw.polygon(screen, char_color, body_poly)
            pygame.draw.circle(screen, char_color, (SCREEN_WIDTH//2, 180), 70)
        
        # 绘制对话面板
        panel_height = 220
        panel_rect = (50, SCREEN_HEIGHT - panel_height - 30, SCREEN_WIDTH - 100, panel_height)
        draw_panel(screen, panel_rect)
        
        # 绘制说话人名字
        if self.current_speaker:
            name_w = len(self.current_speaker) * 35 + 40
            name_rect = (panel_rect[0], panel_rect[1] - 40, name_w, 50)
            
            speaker_color = Colors.CHAR_ME if self.current_speaker == "我" else Colors.BTN_NORMAL
            pygame.draw.rect(screen, speaker_color, name_rect, border_top_left_radius=10, border_top_right_radius=10)
            
            name_surf = self.font_name.render(self.current_speaker, True, Colors.WHITE)
            screen.blit(name_surf, (name_rect[0] + 20, name_rect[1] + 10))
        
        # 绘制文本
        if not self.in_choice:
            text_start_y = panel_rect[1] + 30
            lines = self.current_display_text.split('\n')
            
            for line in lines:
                wrapped = textwrap.wrap(line, width=45)
                for w_line in wrapped:
                    text_surf = self.font_text.render(w_line, True, Colors.UI_TEXT)
                    screen.blit(text_surf, (panel_rect[0] + 40, text_start_y))
                    text_start_y += 35
            
            # 继续指示器
            if self.finished_typing:
                tri_color = Colors.UI_TEXT_HIGHLIGHT
                offset = math.sin(pygame.time.get_ticks() * 0.01) * 3
                p1 = (panel_rect[0] + panel_rect[2] - 40, panel_rect[1] + panel_rect[3] - 30 + offset)
                p2 = (p1[0] + 20, p1[1])
                p3 = (p1[0] + 10, p1[1] + 10)
                pygame.draw.polygon(screen, tri_color, [p1, p2, p3])
        else:
            # 绘制选择支
            for btn in self.choice_buttons:
                btn.draw(screen, self.font_text)
    
    def _get_character_color(self, char_name: str) -> Tuple[int, int, int]:
        """获取角色代表色"""
        if self.manager.game_state:
            for char in self.manager.game_state.game_design.get('characters', []):
                if char.get('name') == char_name:
                    return tuple(char.get('color', [255, 105, 180]))
        
        return Colors.CHAR_GIRL
