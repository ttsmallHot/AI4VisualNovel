import pygame
import os
from .config import Colors

# 字体配置
def get_font(size, bold=False):
    """获取合适的中文字体"""
    local_fonts = ['SourceHanSansCN-Regular.otf', 'font.ttf', 'SimHei.ttf']
    for font_file in local_fonts:
        if os.path.exists(font_file):
            try:
                return pygame.font.Font(font_file, size)
            except Exception as e:
                continue

    font_names = [
        'sourcehansanscn', 'notosanssc', 'microsoftyaheiui', 'microsoftyahei', 
        'pingfangsc', 'heiti', 'simhei', 'arialunicodems'
    ]
    for name in font_names:
        try:
            path = pygame.font.match_font(name)
            if path:
                return pygame.font.Font(path, size)
        except:
            continue
    return pygame.font.SysFont('microsoftyahei', size, bold=bold)


# --- 辅助绘图函数 ---
def draw_panel(surface, rect, alpha=230):
    """绘制通用的 UI 面板（带圆角和阴影）"""
    shadow_rect = pygame.Rect(rect[0]+4, rect[1]+4, rect[2], rect[3])
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, 100), s.get_rect(), border_radius=15)
    surface.blit(s, shadow_rect.topleft)
    
    s_main = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    bg_color = list(Colors.UI_PANEL_BG)
    bg_color[3] = alpha
    pygame.draw.rect(s_main, tuple(bg_color), s_main.get_rect(), border_radius=15)
    pygame.draw.rect(s_main, Colors.UI_BORDER, s_main.get_rect(), 2, border_radius=15)
    surface.blit(s_main, rect[:2])


# --- UI 组件 ---
class Button:
    """按钮组件"""
    def __init__(self, x, y, w, h, text, callback):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.is_hovered = False
        self.animation_offset = 0

    def update(self):
        target = -4 if self.is_hovered else 0
        self.animation_offset += (target - self.animation_offset) * 0.2

    def draw(self, surface, font):
        draw_rect = self.rect.copy()
        draw_rect.y += self.animation_offset
        
        # 阴影
        shadow_rect = draw_rect.copy()
        shadow_rect.move_ip(2, 4)
        pygame.draw.rect(surface, (0,0,0,80), shadow_rect, border_radius=12)

        color = Colors.BTN_HOVER if self.is_hovered else Colors.BTN_NORMAL
        pygame.draw.rect(surface, color, draw_rect, border_radius=12)
        pygame.draw.rect(surface, (255,255,255, 100), draw_rect, 2, border_radius=12)

        text_surf = font.render(self.text, True, Colors.BTN_TEXT)
        text_rect = text_surf.get_rect(center=draw_rect.center)
        surface.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_hovered and event.button == 1:
                self.callback()
