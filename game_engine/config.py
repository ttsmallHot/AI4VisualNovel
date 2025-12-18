import os
from pathlib import Path

# --- 配置与常量 ---
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
FPS = 60

# --- 现代配色方案 ---
class Colors:
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    
    # 背景色系
    BG_MORNING = (135, 206, 250) 
    BG_AFTERNOON = (255, 160, 122)
    BG_EVENING = (25, 25, 112)
    
    # UI 色系
    UI_PANEL_BG = (30, 30, 40, 230) 
    UI_BORDER = (255, 255, 255)
    UI_TEXT = (240, 240, 240)
    UI_TEXT_HIGHLIGHT = (255, 215, 0)
    
    # 按钮色系
    BTN_NORMAL = (70, 130, 180)
    BTN_HOVER = (100, 149, 237)
    BTN_TEXT = (255, 255, 255)
    
    # 地图颜色
    MAP_GRASS = (154, 205, 50)
    MAP_ROAD = (160, 160, 160)
    MAP_LAKE = (100, 149, 237)

    # 角色代表色
    CHAR_ME = (100, 149, 237)
    CHAR_GIRL = (255, 105, 180)
    CHAR_MYSTERY = (138, 43, 226)
    CHAR_UNKNOWN = (169, 169, 169)


# --- 数据路径配置 ---
class DataPaths:
    # game_engine/config.py -> game_engine/ -> pygame_galgame/
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    
    GAME_DESIGN_FILE = DATA_DIR / "game_design.json"
    CHARACTER_INFO_FILE = DATA_DIR / "character_info.json"
    STORY_FILE = DATA_DIR / "story.txt"
    
    IMAGES_DIR = DATA_DIR / "images"
    BACKGROUNDS_DIR = IMAGES_DIR / "backgrounds"
    CHARACTERS_DIR = IMAGES_DIR / "characters"
