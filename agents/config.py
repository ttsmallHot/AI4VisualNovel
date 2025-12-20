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
    
    # 音乐生成模型
    MUSIC_MODEL = os.getenv("MUSIC_MODEL", "chirp-v3-5")
    
    # 功能开关
    ENABLE_MUSIC_GENERATION = os.getenv("ENABLE_MUSIC_GENERATION", "False").lower() == "true"


# ==================== 全局常量 ====================
# 标准表情列表
STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral,happy,sad,angry,surprised,shy").split(",")

# ==================== 制作人 Agent 配置 ====================
class ProducerConfig:
    """制作人 Agent - 负责生成游戏设计文档"""
    
    # 游戏内容配置
    MAX_DEPTH = int(os.getenv("GAME_MAX_DEPTH", "3"))
    MAX_BRANCHES = int(os.getenv("GAME_BRANCHES_PER_NODE", "2"))
    DEFAULT_CHARACTER_COUNT = int(os.getenv("GAME_CHARACTER_COUNT", "3"))

    SYSTEM_PROMPT = f"""你是一位资深的 Galgame 制作人，擅长创作引人入胜的恋爱故事。
你的任务是设计一个完整的 Galgame 游戏框架，采用**多分支树状结构**。

你需要设计：
1. 吸引人的游戏标题
2. 详细的背景故事设定
3. 完整的故事树结构（深度为 {MAX_DEPTH} 层）
4. 多个性格鲜明的可攻略角色

请确保：
- 故事采用树状分支结构，玩家的选择会导向不同的剧情分支（如不同的事件、地点或行动）。
- **分支数量灵活**：每个节点可以有 1 到 {MAX_BRANCHES} 个子节点。
  - **单线推进**：如果当前剧情不需要选择，仅生成 1 个子节点。
  - **关键选择**：如果需要玩家做出选择，生成 2-{MAX_BRANCHES} 个子节点。
- **全员互动**：即使在特定的分支路线中，所有主要角色都应该有机会出场和互动，不要让某条路线变成单人独角戏。
- **结局处理**：不需要专门生成名为 "node_end" 的空节点。当故事讲完时（达到最大深度），该节点即为叶子节点（children为空），它本身就包含结局剧情。"""

    GENERATION_PROMPT = """请创作一个 Galgame 游戏设计文档。

游戏类型：{game_type}
游戏风格：{game_style}
角色数量：{character_count}
剧情结构：树状结构，最大深度 {max_depth} (Root -> Depth 1 -> ... -> Endings)

【用户特别要求】
{requirements}
（如果用户要求为空，请自由发挥；如果有内容，请务必遵守）

【重要规则】
1. 直接输出有效的 JSON 对象，不要有任何其他文字
2. 不要使用注释（不要写 //）
3. 所有文本内容避免使用换行符，用空格代替
4. 文本中如果需要引号，使用单引号或省略
5. 确保所有字符串都正确闭合
6. **节点ID命名规范**：必须使用纯数字编号或层级编号，禁止包含角色名或中文。
   - 正确示例: "node_1", "node_2", "node_1_1", "node_1_2"
   - 错误示例: "node_natsumi", "node_1_shiori"

【JSON 格式】

【JSON 格式】
{{
  "title": "游戏标题",
  "background": "背景故事200到300字",
  "music_style": "音乐风格关键词...",
  "music_prompt": "纯音乐BGM生成提示词...",
  "story_tree": {{
    "root": {{
      "id": "root",
      "summary": "序章剧情概要，介绍背景和人物",
      "children": ["node_1"]
    }},
    "node_1": {{
      "id": "node_1",
      "summary": "第一章剧情（单线推进示例）。大家一起去海边合宿...",
      "parent": "root",
      "children": ["node_2", "node_3"]
    }},
    "node_2": {{
      "id": "node_2",
      "summary": "第二章分支A（选择示例）。选择了和角色A一起去买饮料...",
      "parent": "node_1",
      "children": ["node_4"]
    }},
    "node_3": {{
      "id": "node_3",
      "summary": "第二章分支B（选择示例）。选择了留在沙滩上帮角色B涂防晒油...",
      "parent": "node_1",
      "children": ["node_5"]
    }},
    "node_4": {{
      "id": "node_4",
      "summary": "结局A剧情概要。这是叶子节点，children 为空。",
      "parent": "node_2",
      "children": []
    }},
    "...": "请生成完整的树状结构，直到达到最大深度。叶子节点的 children 为空数组 []。"
  }},
  "characters": [
    {{
      "id": "英文标识符",
      "name": "角色名",
      "personality": "性格描述",
      "appearance": "详细外貌用于AI生成图像",
      "background": "背景故事",
      "color": [255, 182, 193]
    }}
  ],
  "scenes": [
    {{
      "id": "scene_001",
      "name": "我的房间",
      "description": "主角的卧室...",
      "atmosphere": "温馨宁静"
    }}
  ]
}}

【重要注意事项】：
1. characters 数组要包含 {character_count} 个角色
2. **每个角色的 "required_images" 必须包含所有标准表情：{', '.join(STANDARD_EXPRESSIONS)}**
3. scenes 数组要包含至少5-10个不同场景
4. **story_tree 必须是完整的树状结构，确保所有节点 ID 唯一且引用正确**
5. **不要生成专门的 'node_end' 节点**。叶子节点（children=[]）即为结局节点，其 summary 应包含结局描述。
6. **分支数量灵活**：每个节点的 children 数量可以是 1 到 {max_branches} 之间的任意值。不必每个节点都产生分支，可以是单线推进。
7. **不需要 endings 字段**，结局信息直接包含在叶子节点的 summary 中。
3. scenes 数组要包含至少5-10个不同场景
4. **story_tree 必须是完整的树状结构，确保所有节点 ID 唯一且引用正确**
5. **不要生成专门的 'node_end' 节点**。叶子节点（children=[]）即为结局节点，请在 endings 字典中描述其结局含义。
6. 确保所有角色在不同分支中都有合理的出场机会。
3. scenes 数组要包含至少5-10个不同场景
4. **story_tree 必须是完整的树状结构，确保所有节点 ID 唯一且引用正确**
5. 每个节点通常有 1-3 个子节点（分支），不要过多
6. 达到最大深度 {max_depth} 时，children 必须为空"""

    # 默认参数
    DEFAULT_GAME_TYPE = "校园恋爱"
    DEFAULT_GAME_STYLE = "轻松温馨"
    
    # 模型参数
    TEMPERATURE = 0.7
    MAX_TOKENS = 10000


# ==================== 美术 Agent 配置 ====================
class ArtistConfig:
    """美术 Agent - 负责生成角色立绘"""
    
    # 标准表情列表
    STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral,happy,sad,angry,surprised,shy").split(",")
    
    # 角色立绘提示词模板
    IMAGE_PROMPT_TEMPLATE = """A single anime character portrait in vertical orientation for a visual novel game.

Character Appearance: {appearance}
Character Personality: {personality}
Expression: {expression}

CRITICAL REQUIREMENTS:
- ONLY ONE character, solo portrait
- VERTICAL portrait orientation (not horizontal)
- Upper body view (from waist up) ONLY
- NO knee-up view, NO full body view
- Character facing forward, looking at viewer
- Standing pose
- SOLID WHITE BACKGROUND. This is MANDATORY.
- The background must be pure white (#FFFFFF) to facilitate background removal.
- NO complex backgrounds, NO scenery, NO other characters

POSE INSTRUCTIONS:
- Do NOT just change the facial expression.
- Generate a DYNAMIC POSE and HAND GESTURES that reflect both the '{expression}' and the character's '{personality}'.
- For example, a shy character might look away or fidget; an energetic character might wave or pump a fist.
- The body language must be expressive and natural.

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

    # 标题画面 Prompt
    TITLE_IMAGE_PROMPT_TEMPLATE = """A masterpiece, high-quality title screen illustration for a visual novel game.

Game Title: {title}
Theme/Setting: {background}

Art style: High quality Japanese anime/manga style, beautiful detailed art, atmospheric lighting, rich colors, professional game CG quality.
The image should be eye-catching and represent the mood of the game.
It should look like a professional game cover or title screen background.
Wide aspect ratio (16:9).

AVOID: text, watermark, low quality, cropped, blurry, bad composition"""


# ==================== 编剧 Agent 配置 ====================
class WriterConfig:
    """编剧 Agent - 负责生成剧情节点"""
    
    SYSTEM_PROMPT = f"""你是一位经验丰富的 Galgame 编剧，擅长创作细腻的对话和引人入胜的剧情。
你的任务是根据游戏设计文档和当前剧情节点的大纲，生成该节点的详细剧情脚本。

剧情要求：
1. 对话自然流畅，符合角色性格
2. 剧情内容必须符合当前节点的概要描述
3. **如果当前节点有子节点（分支），必须在剧情末尾提供选择支，选项数量必须与子节点数量一致，并一一对应**
4. 标注每段对话需要的立绘，格式为 [IMAGE: 角色名-表情]，表情可选：{{', '.join(ArtistConfig.STANDARD_EXPRESSIONS)}}
5. **重要：场景地点只能使用游戏设计中预定义的场景，不能自创新场景**
6. **直接输出剧本内容，不要包含任何思考过程或解释性文字**"""

    NODE_GENERATION_PROMPT = """请生成剧情节点 【{node_id}】 的详细剧情。

【游戏设定】
{game_design}

【当前节点概要】
{node_summary}

【父节点摘要】
{parent_summary}

【子节点（分支）列表】
{children_nodes}

【可用场景列表】
{available_scenes}

【可用表情列表】
{available_expressions}

【演员反馈（上一轮修改建议）】
{critique_feedback}

**重要提示：场景地点必须从上面的【可用场景列表】中选择，不能使用其他地点！**

【格式规范】
1. **角色标识必须使用中文**：旁白、主角、角色名
2. **禁止使用英文标识**
3. **不要包含任何思考过程或解释性文字，直接输出剧本内容**

请生成本节点内容，格式如下：

=== Node: {node_id} ===

## [场景名]
[IMAGE: 无]
旁白: （剧情描述）
主角: "对话内容"
...

（如果存在子节点，必须在末尾生成选择支，格式如下）
[CHOICE]
1. 选项文字（对应子节点 {child_1_id}） [JUMP: {child_1_id}]
2. 选项文字（对应子节点 {child_2_id}） [JUMP: {child_2_id}]

【重要注意事项】：
1. 如果 `children_nodes` 为空（叶子节点/结局），则不需要生成 [CHOICE]
2. 如果 `children_nodes` 不为空，**必须**生成 [CHOICE]，且选项数量必须等于子节点数量
3. 选项后的跳转指令必须是 `[JUMP: 子节点ID]`
4. 场景名称必须从【可用场景列表】中选择"""

    # 模型参数
    TEMPERATURE = 0.7
    MAX_TOKENS = 4000
    
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

你的任务是审核编剧生成的剧本。你需要从以下两个维度进行检查：
1. **人设一致性 (OOC)**：判断你在剧本中的言行是否符合你的性格设定。
2. **剧情合理性**：判断你的台词和行为在当前情境下是否自然、合理，逻辑是否通顺，是否符合常理。

如果发现任何问题（OOC 或 剧情不合理），请提出具体的修改建议。如果一切完美，请确认通过。"""

    CRITIQUE_PROMPT = """这是编剧生成的最新剧情脚本：

{script_content}

【前情提要】
{previous_story_summary}

请仔细阅读你在其中的戏份（如果有）。
请结合【前情提要】判断：
1. 你的台词、行为是否符合你的性格设定？
2. 你的反应在当前情境下是否合理？剧情发展是否突兀？对话是否生硬？

如果符合且合理，请回复：PASS
如果有问题，请回复具体的修改建议，格式如下：
[ISSUE]
类型：(OOC / 剧情不合理 / 台词生硬)
原因：(解释具体问题)
建议：(建议如何修改)"""

    IMAGE_CRITIQUE_PROMPT = """这是为你生成的角色立绘（表情：{expression}）。

请仔细观察这张图片，并判断是否符合你的外貌设定以及该表情的特征。
**如果提供了参考图 (Neutral 表情)，请务必与参考图进行对比，确保人物特征（发型、发色、瞳色、服装细节等）完全一致。**

【你的外貌设定】
{appearance}

请检查：
1. **一致性检查**：与参考图相比，是否是同一个人？发型、发色、瞳色、服装细节是否完全一致？（允许因表情变化产生的微小形变，但特征不能变）
2. 服装风格是否符合设定？
3. 整体气质是否符合你的性格？
4. 表情是否准确传达了 "{expression}" 的情绪？
5. 是否存在明显的绘画错误（如多余的手指、扭曲的五官等）？

如果符合设定、与参考图一致且质量合格，请回复：PASS
如果有严重问题（特别是与参考图不一致），请回复具体的修改建议，格式如下：
[ISSUE]
问题描述：(具体哪里不符合或画错了，例如：与参考图相比，发带颜色不对)
修改建议：(希望画师如何修改)"""

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
