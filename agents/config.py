"""
Agent Configuration
~~~~~~~~~~~~~~~~~~~
所有 Agent 的配置、API Keys、模型参数和 Prompt 模板
"""

import os
from typing import Dict, Any
from pathlib import Path

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    # 查找 .env 文件（在项目根目录）
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 已加载环境变量: {env_path}")
    else:
        print(f"⚠️  .env 文件不存在: {env_path}")
except ImportError:
    print("⚠️  python-dotenv 未安装，无法自动加载 .env 文件")
    print("   请运行: pip install python-dotenv")

# ==================== API 配置 ====================
class APIConfig:
    """API 密钥配置"""
    # 提供商配置
    TEXT_PROVIDER = os.getenv("TEXT_PROVIDER", "google")
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "google")
    MUSIC_PROVIDER = os.getenv("MUSIC_PROVIDER", "suno")
    
    # OpenAI API (用于 GPT-4 和图像生成)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    # Google Gemini API
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_BASE_URL = os.getenv("GOOGLE_BASE_URL", "")  # 可选：用于代理

    # Music API (Suno/Other)
    MUSIC_API_KEY = os.getenv("MUSIC_API_KEY", "")
    MUSIC_BASE_URL = os.getenv("MUSIC_API_BASE_URL", "https://api.openai-proxy.com/v1")
    
    # 模型名称
    MODEL = os.getenv("MODEL", "gemini-3-pro-preview")  # 统一模型名称，根据 PROVIDER 自动适配默认值
    
    # 图像生成模型
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "dall-e-3")  # 或 imagen-3.0-generate-001


# ==================== 制作人 Agent 配置 ====================
class ProducerConfig:
    """制作人 Agent - 负责生成游戏设计文档"""
    
    # 游戏内容配置
    TOTAL_GROUPS = int(os.getenv("GAME_TOTAL_GROUPS", "4"))
    BLOCKS_PER_GROUP = int(os.getenv("GAME_BLOCKS_PER_GROUP", "7"))
    DEFAULT_CHARACTER_COUNT = int(os.getenv("GAME_CHARACTER_COUNT", "3"))

    SYSTEM_PROMPT = f"""你是一位资深的 Galgame 制作人，擅长创作引人入胜的恋爱故事。
你的任务是设计一个完整的 Galgame 游戏框架，包括：
1. 吸引人的游戏标题
2. 详细的背景故事设定
3. 完整的故事大纲（{TOTAL_GROUPS}组内容，每组包含{BLOCKS_PER_GROUP}个剧情块）
4. 多个性格鲜明的可攻略角色

请确保：
- 故事有明确的起承转合
- 角色性格鲜明，有成长空间
- 每组都有关键剧情点
- 结局取决于角色好感度和玩家选择"""

    GENERATION_PROMPT = """请创作一个 Galgame 游戏设计文档。

游戏类型：{game_type}
游戏风格：{game_style}
角色数量：{character_count}
剧情结构：共 {total_groups} 组，每组 {blocks_per_group} 个剧情块

【重要规则】
1. 直接输出有效的 JSON 对象，不要有任何其他文字
2. 不要使用注释（不要写 //）
3. 所有文本内容避免使用换行符，用空格代替
4. 文本中如果需要引号，使用单引号或省略
5. 确保所有字符串都正确闭合

【JSON 格式】
{{
  "title": "游戏标题",
  "background": "背景故事200到300字",
  "music_style": "音乐风格关键词，例如：J-Pop, Piano, Emotional, Anime OST",
  "music_prompt": "音乐创作提示词，描述音乐的氛围和情感，例如：A touching piano melody playing in a sunset classroom",
  "outline": {{
    "group_1": "第一组剧情概要",
    "group_2": "第二组剧情概要",
    "group_3": "第三组剧情概要",
    "group_4": "第四组剧情概要 (请根据实际组数生成对应数量的键)"
  }},
  "characters": [
    {{
      "id": "英文标识符",
      "name": "角色名",
      "personality": "性格描述",
      "appearance": "详细外貌用于AI生成图像",
      "background": "背景故事",
      "color": [255, 182, 193],
      "required_images": ["neutral"]
    }}
  ],
  "scenes": [
    {{
      "id": "scene_001",
      "name": "我的房间",
      "description": "主角的卧室，温馨舒适的私人空间",
      "atmosphere": "温馨宁静"
    }},
    {{
      "id": "scene_002",
      "name": "学校教室",
      "description": "高中三年级的教室，充满青春气息",
      "atmosphere": "明亮活泼"
    }}
  ],
  "endings": {{
    "good_ending": "完美结局条件",
    "normal_ending": "普通结局条件",
    "bad_ending": "悲剧结局条件"
  }}
}}

【重要注意事项】：
1. characters 数组要包含 {character_count} 个角色
2. **每个角色的 "required_images" 必须且只能是 ["neutral"]，不要添加其他表情！**
3. scenes 数组要包含至少5-10个不同场景，覆盖游戏中所有剧情发生的地点
4. 每个场景要有详细的描述，方便后续AI生成背景图
5. 严格遵循上面的 JSON 格式，不要自行修改字段结构"""

    # 默认参数
    DEFAULT_GAME_TYPE = "校园恋爱"
    DEFAULT_GAME_STYLE = "轻松温馨"
    
    # 模型参数
    TEMPERATURE = 0.7  # 降低温度使输出更稳定，避免格式错误
    MAX_TOKENS = 10000  # 增加 token 限制确保内容完整


# ==================== 美术 Agent 配置 ====================
class ArtistConfig:
    """美术 Agent - 负责生成角色立绘"""
    
    # 标准表情列表
    STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral,happy,sad,angry,surprised,shy").split(",")
    
    # 角色立绘提示词模板
    IMAGE_PROMPT_TEMPLATE = """A single anime character portrait in vertical orientation for a visual novel game.

Character: {appearance}
Expression: {expression}

CRITICAL REQUIREMENTS:
- ONLY ONE character, solo portrait
- VERTICAL portrait orientation (not horizontal)
- Upper body view (from waist up) or Knee-up view
- Character facing forward, looking at viewer
- Standing pose
- Transparent background (if possible) or solid color contrasting with character
- NO complex backgrounds, NO scenery, NO other characters

Art style: High quality Japanese anime/manga style, beautiful detailed eyes, detailed hair, soft lighting, clean professional composition.

This is a character sprite for a visual novel game."""
    
    # DALL-E 图像生成参数（角色立绘）
    IMAGE_SIZE = "1024x1792"  # 竖版，适合立绘
    IMAGE_WIDTH = 1024
    IMAGE_HEIGHT = 1792
    IMAGE_QUALITY = "standard"  # "standard" 或 "hd"
    IMAGE_STYLE = "vivid"  # "vivid" 或 "natural"
    
    # 场景背景图配置（参考 AI-GAL-main 的高质量背景 prompt）
    BACKGROUND_PROMPT_TEMPLATE = """masterpiece, wallpaper, 8k, detailed CG, {location}, {atmosphere}, {time_of_day}, (no_human)

Beautiful anime style background scene for visual novel. High quality Japanese anime background art, detailed scenery, atmospheric lighting, rich colors, depth and dimension.

Wide establishing shot, environment only, professional game CG quality.

AVOID: people, characters, text, watermark, low quality, cropped, blurry, bad composition"""

    BACKGROUND_SIZE = "1792x1024"  # 横版，适合背景
    BACKGROUND_WIDTH = 1792
    BACKGROUND_HEIGHT = 1024
    BACKGROUND_QUALITY = "standard"
    BACKGROUND_STYLE = "vivid"


# ==================== 编剧 Agent 配置 ====================
class WriterConfig:
    """编剧 Agent - 负责生成每日剧情"""
    
    SYSTEM_PROMPT = f"""你是一位经验丰富的 Galgame 编剧，擅长创作细腻的对话和引人入胜的剧情。
你的任务是根据游戏设计文档、角色状态和前文剧情，生成某一天的详细剧情。

剧情要求：
1. 对话自然流畅，符合角色性格
2. 每个剧情块包含若干个场景，推进主线或角色关系
3. 提供2-3个有意义的选项，选项会影响角色好感度和后续剧情
4. 标注每段对话需要的立绘，格式为 [IMAGE: 角色名-表情]，表情可选：{{', '.join(ArtistConfig.STANDARD_EXPRESSIONS)}}
5. **重要：场景地点只能使用游戏设计中预定义的场景，不能自创新场景**
6. **重要：不再包含支线任务或自由活动，所有剧情均为线性推进**
7. **直接输出剧本内容，不要包含任何思考过程或解释性文字**"""

    # 关系等级配置
    MAX_RELATIONSHIP_LEVEL = int(os.getenv("GAME_MAX_RELATIONSHIP_LEVEL", "5"))
    RELATIONSHIP_LEVEL_NAMES = {
        1: "初识",
        2: "朋友",
        3: "好感",
        4: "暧昧",
        5: "恋人"
    }

    RELATIONSHIP_STORY_PROMPT = """请为角色【{character_name}】生成一段【关系等级 {level} ({level_name})】的专属剧情。

【角色设定】
{character_info}

【当前关系状态】
等级: {level} ({level_name})
说明: 这是玩家与该角色关系提升到 {level} 级时触发的特殊事件。

【剧情要求】
1. 剧情应体现两人关系的进展，符合当前等级的氛围。
2. 这是一个独立的剧情块，不依赖特定的主线时间点。
3. 包含完整的起承转合。
4. **不要包含任何好感度提升选项**（这是奖励剧情）。
5. 场景可以从可用场景中选择，也可以是该角色的特殊场景。

【格式规范】
=== Character: {character_id} - Level {level} ===

## [场景名]
[IMAGE: {character_name}]
{character_name}: "对话内容"
...
"""

    DAILY_GENERATION_PROMPT = """请生成第 {group} 组 - Block {block} 的详细剧情。

【游戏设定】
{game_design}

【本组大纲】
{group_outline}

【可用场景列表】
{available_scenes}

【前一剧情块摘要】
{previous_story_summary}

【演员反馈（上一轮修改建议）】
{critique_feedback}

**重要提示：场景地点必须从上面的【可用场景列表】中选择，不能使用其他地点！**

【差分剧情说明】
- 你可以根据角色关系等级设计不同的对话分支。
- 使用 `[IF: 角色名 >= 等级] ... [ELSE] ... [ENDIF]` 语法。
- 例如：
  [IF: 小日向夏海 >= 3]
  小日向夏海: "那个...我们要不要一起走？" (脸红)
  [ELSE]
  小日向夏海: "拜拜！明天见！"
  [ENDIF]

【格式规范】
1. **角色标识必须使用中文**：旁白、主角、角色名（如：小日向夏海）
2. **禁止使用英文标识**：NARRATOR ❌、PROTAGONIST ❌
3. **不要包含任何思考过程或解释性文字，直接输出剧本内容**
4. **必须生成完整一个剧情块的剧情**

请生成本剧情块内容，格式如下：

=== Group {group} - Block {block} ===

## [场景名]
[IMAGE: 无]
旁白: （剧情描述）
主角: "对话内容"
...

[CHOICE]
选项1: "选项文字" → [小日向夏海好感度+5]
选项2: "选项文字" → [九条雪乃好感度+5]

## [场景名]
[IMAGE: 小日向夏海]
小日向夏海: "对话内容"
...

【重要注意事项】：
1. 角色对话标识必须用中文
2. 场景名称必须从【可用场景列表】中选择
3. 不要输出 "Script Generation - My Thought Process" 等无关内容"""

    # 模型参数
    TEMPERATURE = 0.7
    MAX_TOKENS = 4000
    
    # 好感度阈值（用于判断角色关系等级）
    AFFECTION_THRESHOLDS = {
        "stranger": (0, 20),      # 陌生
        "acquaintance": (20, 40), # 认识
        "friend": (40, 60),       # 朋友
        "close_friend": (60, 80), # 好友
        "lover": (80, 100)        # 恋人
    }

    SUMMARY_PROMPT = """请将以下剧情概括为一段简短的摘要（200字以内）。
重点保留：关键事件、角色关系变化、重要伏笔。
忽略：日常寒暄、无关紧要的细节。

剧情内容：
{story_content}"""


# ==================== 演员 Agent 配置 ====================
class ActorConfig:
    """演员 Agent - 负责扮演角色并审核剧本"""
    
    SYSTEM_PROMPT = """你现在是游戏中的角色：{name}。
你的性格特征是：{personality}。
你的背景故事是：{background}。

你的任务是审核编剧生成的剧本，判断你在剧本中的言行是否符合你的人设（OOC - Out Of Character）。
如果发现 OOC，请提出具体的修改建议。如果符合人设，请确认通过。"""

    CRITIQUE_PROMPT = """这是编剧生成的最新剧情脚本：

{script_content}

【前情提要】
{previous_story_summary}

请仔细阅读你在其中的戏份（如果有）。
请结合【前情提要】判断你的台词、行为和心理活动是否符合你的性格设定以及之前的剧情发展。

如果符合，请回复：PASS
如果不符合，请回复具体的修改建议，格式如下：
[OOC]
原因：(解释为什么不符合人设或前后矛盾)
建议：(建议如何修改台词或行为)"""

    TEMPERATURE = 0.5  # 较低温度以保持性格一致性
    MAX_TOKENS = 1000

# ==================== 文件路径配置 ====================
class PathConfig:
    """文件路径配置"""
    
    # 项目根目录
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 数据目录
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    IMAGES_DIR = os.path.join(DATA_DIR, "images")
    CHARACTERS_DIR = os.path.join(IMAGES_DIR, "characters")
    BACKGROUNDS_DIR = os.path.join(IMAGES_DIR, "backgrounds")  # 背景图目录
    AUDIO_DIR = os.path.join(DATA_DIR, "audio")
    BGM_DIR = os.path.join(AUDIO_DIR, "bgm")
    
    # 游戏数据文件
    GAME_DESIGN_FILE = os.path.join(DATA_DIR, "game_design.json")
    STORY_FILE = os.path.join(DATA_DIR, "story.txt")
    CHARACTER_INFO_FILE = os.path.join(DATA_DIR, "character_info.json")
    
    # 日志目录
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        dirs = [
            cls.DATA_DIR,
            cls.IMAGES_DIR,
            cls.CHARACTERS_DIR,
            cls.BACKGROUNDS_DIR,  # 添加背景目录
            cls.AUDIO_DIR,
            cls.BGM_DIR,
            cls.LOG_DIR
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)


# 初始化时创建必要目录
PathConfig.ensure_directories()
