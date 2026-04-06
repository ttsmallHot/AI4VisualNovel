import pygame
import sys
import math
import os
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
        self.game_title = manager.game_state.game_design.get('title', '我的 Visual Novel') if manager.game_state else '我的 Visual Novel'

        # 加载标题背景图
        self.title_bg = None
        try:
            title_bg_path = DataPaths.DATA_DIR / "images" / "title_screen.png"
            if title_bg_path.exists():
                raw_bg = pygame.image.load(str(title_bg_path)).convert()
                
                # 自适应缩放 (Aspect Fill) - 保持比例填满屏幕
                img_w, img_h = raw_bg.get_size()
                scale_w = SCREEN_WIDTH / img_w
                scale_h = SCREEN_HEIGHT / img_h
                scale = max(scale_w, scale_h) # 取最大比例以填满屏幕
                
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                
                # 使用平滑缩放
                scaled_bg = pygame.transform.smoothscale(raw_bg, (new_w, new_h))
                
                # 居中裁剪
                x = (new_w - SCREEN_WIDTH) // 2
                y = (new_h - SCREEN_HEIGHT) // 2
                self.title_bg = scaled_bg.subsurface((x, y, SCREEN_WIDTH, SCREEN_HEIGHT))
        except Exception as e:
            print(f"无法加载标题背景: {e}")

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
        if self.title_bg:
            screen.blit(self.title_bg, (0, 0))
        else:
            screen.fill(Colors.BG_MORNING)
            
            # 云朵动画
            for i in range(5):
                x = (i * 200 + self.time_offset * 10) % (SCREEN_WIDTH + 200) - 100
                y = 100 + math.sin(self.time_offset + i) * 20
                pygame.draw.ellipse(screen, (255, 255, 255, 150), (x, y, 120, 60))

        # 标题 (始终显示)
        # 增强阴影以确保在复杂背景上可见
        title = self.font_large.render(self.game_title, True, Colors.WHITE)
        shadow = self.font_large.render(self.game_title, True, (0,0,0,180)) # 加深阴影
        
        # 绘制多次阴影以模拟描边效果
        screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH//2 + 2, 250 + 2)))
        screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH//2 - 2, 250 + 2)))
        screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH//2 + 2, 250 - 2)))
        screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH//2 - 2, 250 - 2)))
        
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
        self.show_speaker_name = True
        
        # 当前状态
        self.current_speaker = None
        self.current_emotion = "neutral"
        self.current_character_image = None
        
        # 选择支状态
        self.in_choice = False
        self.choice_options = []
        self.choice_buttons = []
        
        # 加载角色图像缓存
        self.character_images = {}
        self.current_background = None
        self.current_bg_name = None # 保存当前背景名
        self.current_char_name = None # 保存当前角色名
        self.background_images = {}
        
        self.load_line()

    def _save_screenshot(self):
        """保存当前窗口截图"""
        surface = pygame.display.get_surface()
        if surface is None:
            print("⚠️ 当前没有可用窗口，无法截图")
            return

        screenshot_dir = os.path.join("logs", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        filename = f"screenshot_{pygame.time.get_ticks()}.png"
        filepath = os.path.join(screenshot_dir, filename)
        pygame.image.save(surface, filepath)
        print(f"📸 已保存截图: {filepath}")
    
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
        
        # --- 常规剧情指令 ---
        
        # 处理背景/场景
        if line_type == "background" or line_type == "scene":
            bg_name = line.get("value", "").strip()
            self.current_bg_name = bg_name 
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
            self.current_char_name = image_value 
            
            # 如果是"无"或空，清除立绘
            if not image_value or image_value == "无":
                self.current_character_image = None
            else:
                if '-' in image_value:
                    char_name_part, emotion_part = image_value.split('-', 1)
                    char_name_part = char_name_part.strip()
                    emotion_part = emotion_part.strip()
                else:
                    char_name_part = image_value
                    emotion_part = "neutral"

                char_id = self._get_character_id(char_name_part)
                if char_id:
                    self.current_character_image = self.load_character_image(char_id, emotion_part)
                    print(f"📸 加载角色立绘: {char_name_part} ({char_id})")
                else:
                    print(f"⚠️ 未找到角色 ID: {char_name_part}")
                    self.current_character_image = None
            
            self.index += 1
            self.load_line()
            return
        
        # 处理旁白
        elif line_type == "narrator":
            self.current_speaker = None
            self.current_character_image = None 
            self.full_text = line.get("text", "") 
        
        # 处理对话
        elif line_type == "dialogue":
            speaker_id = line.get("speaker")
            
            if speaker_id == "主角":
                self.current_speaker = "我"
            else:
                self.current_speaker = self._get_character_name(speaker_id)
            
            self.full_text = line.get("text", "")
        
        # 处理跳转
        elif line_type == "jump":
            target_node = line.get("target")
            print(f"🦘 跳转到节点: {target_node}")
            self.manager.game_state.current_node_id = target_node
            self.manager.play_current_scene() 
            return

        # 处理选择支
        elif line_type == "choice_start" or line_type == "choice_option":
            if not self.in_choice:
                self.in_choice = True
                self.choice_options = []
                
                # 收集连续选项
                temp_index = self.index
                if line_type == "choice_start": temp_index += 1
                
                while temp_index < len(self.script_lines):
                    next_line = self.script_lines[temp_index]
                    if next_line and next_line.get("type") == "choice_option":
                        self.choice_options.append(next_line)
                        temp_index += 1
                    else:
                        break
                
                if self.choice_options:
                    self.create_choice_buttons()
                else:
                    self.in_choice = False
                    self.index += 1
                    self.load_line()
            return
        
        else:
            self.index += 1
            self.load_line()
            return
        
        # 重置打字机
        self.current_display_text = ""
        self.char_counter = 0
        self.finished_typing = False
    
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

    def _wrap_text_pixels(self, text, max_width):
        """基于像素宽度的精准换行"""
        lines = []
        # 按空格切分单词（针对英文），中文则需要逐字检查或混合处理
        # 简单的混合处理逻辑：
        current_line = ""
        for char in text:
            test_line = current_line + char
            # 使用 font.size() 获取像素宽度
            if self.font_text.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines

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
            target = choice.get("target")
            
            # 记录选择
            self.manager.game_state.choices_made.append({
                "scene": self.scene_name,
                "choice": choice.get("text"),
                "target": target
            })
            
            if target:
                print(f"🦘 选项跳转到: {target}")
                self.manager.game_state.current_node_id = target
                self.manager.play_current_scene()
                return
        
        # 如果没有跳转，重置选择模式并继续（理论上不应发生）
        self.in_choice = False
        self.choice_options = []
        self.choice_buttons = []
        self.load_line()

    def end_dialogue(self):
        """结束对话，返回地图或下一场景"""
        # 通知管理器场景结束
        self.manager.on_scene_complete(self.scene_name)
    
    def update(self):
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
        # 处理选择支点击
        if self.in_choice:
            for btn in self.choice_buttons:
                btn.handle_event(event)
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_n:
            self.show_speaker_name = not self.show_speaker_name
            state_text = "显示" if self.show_speaker_name else "隐藏"
            print(f"🏷️ 名称显示: {state_text}")
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
            self._save_screenshot()
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
        # time_str = f"{self.manager.game_state.time_str}"
        # time_surf = self.font_text.render(time_str, True, Colors.WHITE)
        # time_bg_rect = time_surf.get_rect(topleft=(20, 20))
        # time_bg_rect.inflate_ip(20, 10)
        # pygame.draw.rect(screen, (0, 0, 0, 150), time_bg_rect, border_radius=5)
        # screen.blit(time_surf, (30, 25))

        # 绘制角色立绘
        if self.current_character_image and isinstance(self.current_character_image, pygame.Surface):
            # 居中显示
            char_rect = self.current_character_image.get_rect()
            char_x = (SCREEN_WIDTH - char_rect.width) // 2
            char_y = SCREEN_HEIGHT - char_rect.height
            screen.blit(self.current_character_image, (char_x, char_y))
        
        # 绘制对话面板
        panel_height = 220
        panel_rect = (50, SCREEN_HEIGHT - panel_height - 30, SCREEN_WIDTH - 100, panel_height)
        draw_panel(screen, panel_rect)
        
        # 绘制说话人名字
        if self.show_speaker_name and self.current_speaker:
            name_surf = self.font_name.render(self.current_speaker, True, Colors.WHITE)
            name_w = name_surf.get_width() + 40
            name_rect = (panel_rect[0], panel_rect[1] - 40, name_w, 50)
            
            speaker_color = Colors.CHAR_ME if self.current_speaker in ["我", "Me"] else Colors.BTN_NORMAL
            pygame.draw.rect(screen, speaker_color, name_rect, border_top_left_radius=10, border_top_right_radius=10)
            
            screen.blit(name_surf, (name_rect[0] + 20, name_rect[1] + 10))
        
        # 绘制文本
        if not self.in_choice:
            text_start_y = panel_rect[1] + 30
            paragraphs = self.current_display_text.split('\n')
            
            # 对话框内部边距
            max_w = panel_rect[2] - 80
            
            for p in paragraphs:
                wrapped_lines = self._wrap_text_pixels(p, max_w)
                for w_line in wrapped_lines:
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
    

