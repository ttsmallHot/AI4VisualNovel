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
    
    # OpenAI API (用于 GPT-4 和图像生成)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    # Google Gemini API
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_BASE_URL = os.getenv("GOOGLE_BASE_URL", "")

    # 模型名称
    MODEL = os.getenv("MODEL", "gemini-3-pro-preview")
    
    # 图像生成模型
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1.5") 


# ==================== 全局常量 ====================
# 标准表情列表
STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral").split(",")

# ==================== 策划 (Designer) Agent 配置 ====================
class DesignerConfig:
    """策划 Agent - 负责草拟游戏设计文档"""
    
    # 游戏内容配置
    TOTAL_NODES = int(os.getenv("GAME_TOTAL_NODES", "12"))
    DEFAULT_CHARACTER_COUNT = int(os.getenv("GAME_CHARACTER_COUNT", "3"))
    PLOT_SEGMENTS_PER_NODE = int(os.getenv("PLOT_SEGMENTS_PER_NODE", "3"))

    SYSTEM_PROMPT = f"""你是一位资深的 Visual Novel (视觉小说) 策划，擅长创作引人入胜的故事。
你的任务是设计一个完整的 Visual Novel 游戏框架，采用**有向无环图（DAG）结构**，允许不同分支汇合。

你需要设计：
1. 吸引人的游戏标题
2. 详细的背景故事设定
3. 完整的故事图结构（约 {TOTAL_NODES} 个节点）
4. 多个性格鲜明的角色

请确保：
- 故事采用有向图结构，玩家的选择会导向不同的剧情分支
- **支持路径汇合**：不同的选择可以最终汇合到同一剧情节点，避免内容重复
- **节点数量控制**：总节点数约为 {TOTAL_NODES} 个（误差 ±2 可接受，但不能和要求相差过大)
- **分支数量灵活**：建议每个节点有 1-3 个出边，避免过于复杂
- **全员互动**：即使在特定的分支路线中，所有主要角色都应该有机会出场和互动
"""


    GAME_DESIGN_PROMPT = """请创作一个 Visual Novel 游戏设计文档。

游戏风格：{game_style}
角色数量：{character_count} (包含主角)
剧情结构：有向无环图（DAG），支持多分支和路径汇合

【用户要求】
{requirements}
（如果用户要求为空，请自由发挥；如果有内容，请务必遵守。游戏类型由你根据构想自行决定并体现在背景中。）

【重要规则】
1. 直接输出有效的 JSON 对象，不要有任何其他文字
2. 不要使用注释（不要写 //）
3. 所有文本内容避免使用换行符，用空格代替
4. 文本中如果需要引号，使用单引号或省略
5. 确保所有字符串都正确闭合
6. **节点ID命名规范**：必须使用纯数字编号或层级编号，禁止包含角色名或中文。
   - 统一使用层级命名法: "root" -> "1" -> "1-1", "1-2" -> "1-1-1"
   - 根节点 ID 必须为 "root"

【JSON 格式示例】
{{
  "title": "游戏标题",
  "background": "背景故事介绍，200到300字",
  "art_style": "美术风格描述（例如：日系动漫、赛博朋克、蒸汽朋克、水彩画风、像素风、写实风格等风格），包括色调、氛围、画面特点",
  "story_graph": {{
    "nodes": {{
      "root": {{
        "id": "root",
        "summary": "序章剧情概要，介绍背景和人物",
        "type": "normal"
      }},
      "node1": {{
        "id": "node1",
        "summary": "前往学校的路上，遇到了神秘事件",
        "type": "normal"
      }},
      "node2": {{
        "id": "node2",
        "summary": "选择调查事件，发现线索A",
        "type": "normal"
      }},
      "node3": {{
        "id": "node3",
        "summary": "选择无视事件，前往学校",
        "type": "normal"
      }},
      "node4": {{
        "id": "node4",
        "summary": "两条路径汇合：在学校与所有角色会面",
        "type": "merge"
      }},
      "node5": {{
        "id": "node5",
        "summary": "真相大白结局（叶子节点，无出边）",
        "type": "normal"
      }},
      "node6": {{
        "id": "node6",
        "summary": "平凡日常结局（叶子节点，无出边）",
        "type": "normal"
      }}
    }},
    "edges": [
      {{"from": "root", "to": "node1", "choice_text": null}},
      {{"from": "node1", "to": "node2", "choice_text": "调查事件"}},
      {{"from": "node1", "to": "node3", "choice_text": "无视前往学校"}},
      {{"from": "node2", "to": "node4", "choice_text": null}},
      {{"from": "node3", "to": "node4", "choice_text": null}},
      {{"from": "node4", "to": "node5", "choice_text": "深入调查"}},
      {{"from": "node4", "to": "node6", "choice_text": "平静生活"}}
    ]
    
    **【choice_text 规范】**：
    - **choice_text 为 null**：表示自动前进，不显示选项（适用于单一路径的自然延续）
    - **choice_text 有值**：必须是简洁的、沉浸式的选项文本（10字以内）
    - **严禁出戏标记**：不要在选项中加入元标记，如"(技术路线)"、"【武力路线】"、"[BRANCH A]"等
    - **错误示例**：❌ "联系黑客金克丝 (技术路线)"、❌ "【理性选择】寻求帮助"
    - **正确示例**：✅ "联系黑客金克丝"、✅ "寻求帮助"、✅ "独自调查"
  }},
  "characters": [
    {{
      "id": "英文标识符",
      "name": "角色名",
      "gender": "性别",
      "is_protagonist": true,
      "personality": "性格描述",
      "appearance": "详细外貌用于AI生成图像",
      "background": "背景故事"
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
1. characters 数组要包含 {character_count} 个角色，**其中必须包含 1 位主角 (is_protagonist: true)**
   - **角色名规范：所有角色名只统一使用一种语言，不要添加任何括号来表注释**
   - 错误示例：❌ "莲 (Ren)", ❌ "艾莉丝 (Alice)"
   - 正确示例：✅ "莲", ✅ "艾莉丝"
2. scenes 数组要包含至少5-10个不同场景
3. **story_graph 必须是有效的 DAG**：
   - 每个节点必须有唯一的 ID
   - edges 中的 from/to 必须引用已存在的节点
   - 不能有环路（循环引用）
4. **choice_text 规范（重要！）**：
   - **null 值**：表示自动前进，无需玩家选择（单一路径延续）
   - **有值**：必须是简洁沉浸的选项文本（5-10字），直接描述行动
   - **严禁元标记**：不要加括号注释、路线标识、分支标记等破坏沉浸感的内容
   - 错误示例：❌ "联系金克丝 (技术路线)"、❌ "【理性】寻求帮助"
   - 正确示例：✅ "联系金克丝"、✅ "寻求帮助"、✅ "独自调查"
5. **节点ID命名规范**：使用统一的 node + 数字 格式
   - 推荐格式: "root", "node1", "node2", "node3", "node4" ...
   - 根节点 ID 必须为 "root"
   - 严禁使用角色名、中文或 n1、merge1 等不统一的命名
6. **节点类型**：
   - **normal**：普通节点（包括开始、中间、结局节点）
   - **merge**：汇合点（多条路径汇入）
   - 注：开始节点就是 root，结局节点通过无出边判断（叶子节点）
7. **建议结构**：
   - 总节点数应为{total_nodes} 个（误差 ±2 可接受，但不能和要求相差过大）
   - 提供多种结局以增加游戏可玩性
8. **路径设计与逻辑连贯性（关键！）**：
   - **汇合点必须有逻辑关联**：每条分支的线索、事件或角色决定都应该自然地收束到汇合点，可能是：(1) 两条线索交叉指向同一目标；(2) 不同角色在关键时刻集合；(3) 多个事件触发同一后果；(4) 玩家被迫在某地重逢等。
   - **汇合点大纲必须统一**：汇合节点的大纲不应该是分情况讨论的，而是应该是一个统一的事件或场景。
   - **不同分支不能毫无关联**：例如，node2 "发现美术室线索" 和 node3 "骚扰学生会" 不能在 node4 毫无理由地说"线索都指向图书馆"。这样会破坏沉浸感。
   - **错误示例**：❌ node2 发现恶作剧 + node3 发现学生会腐败 → node4 "都指向图书馆" (逻辑突兀)
   - **正确示例**：✅ node2 发现化学试剂包装上的借阅条形码 + node3 发现陆沉在隐藏的正是图书馆借阅记录 → node4 自然地都指向图书馆 (逻辑连贯)
9. **节点 summary 必须详细且明确**：
   - 每个节点的 summary 要包含足够的信息让编剧理解发生了什么、为什么发生
   - 如果涉及谜团、秘密或关键信息，summary 中必须明确交代（不能模糊其辞）
   - summary 应该能回答：谁、做了什么、为什么、结果是什么
10. **充分利用汇合机制**：避免重复生成相同内容，而是让不同的选择导向不同的发现/体验，但最终在叙事上形成整体
11. 确保所有角色在不同分支中都有合理的出场机会"""

    # 模型参数
    TEMPERATURE = 0.7
    MAX_TOKENS = 10000


# ==================== 制作人 (Producer) Agent 配置 ====================
class ProducerConfig:
    """制作人 Agent - 负责审核游戏设计文档并把控进度"""
    
    SYSTEM_PROMPT = """你是一位资深的 Visual Novel 游戏制作人，负责把控游戏的宏观质量和项目方向。
你的任务是审核策划提交的设计方案，确保其符合用户需求，且具有商业价值和艺术逻辑。"""

    GAME_DESIGN_CRITIQUE_PROMPT = """你现在是游戏制作人，请审核以下由策划草拟的游戏设计文档。

【用户原始要求】
{user_requirements}

【核心参数指标】
- 期望节点总数：{expected_nodes}
- 期望角色数量：{expected_characters}

【游戏设计文档】
{game_design}

请从以下几个维度给出反馈：
1. **指标达成度**：节点总数是否符合要求（误差 ±2 也可以接受，但是不能差别过大）？角色数量是否符合要求？
2. **需求契合度**：方案是否完美实现了用户的所有核心要求？
3. **图完整度**：DAG结构是否合理？是否存在死节点或孤立节点？
4. **故事逻辑**：是否讲述了一个清晰完整的故事？

请给出判断：
- 如果认为指标合格且方案可以直接投入正式开发，请只回复 "PASS"。
- 如果指标不符或认为需要改进，请提供具体且专业且一针见血的详细修改建议。"""



# ==================== 美术 Agent 配置 ====================
class ArtistConfig:
    """美术 Agent - 负责生成角色立绘"""
    
    # 标准表情列表
    STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral").split(",")
    
    # 角色立绘提示词模板
    IMAGE_PROMPT_TEMPLATE = """A single anime character portrait in vertical orientation for a visual novel game.

Story Context: {story_background}
Art Style: {art_style}

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
    
    # 图像生成参数（角色立绘）
    IMAGE_SIZE = "1024x1792"  # 竖版，适合立绘
    IMAGE_WIDTH = 1024
    IMAGE_HEIGHT = 1792
    IMAGE_QUALITY = "standard"  # "standard" 或 "hd"
    IMAGE_STYLE = "vivid"  # "vivid" 或 "natural"
    
    # 场景背景图配置（参考 AI-GAL-main 的高质量背景 prompt）
    BACKGROUND_PROMPT_TEMPLATE = """masterpiece, wallpaper, 8k, detailed CG, {location}, {atmosphere}, {time_of_day}, (no_human)

Story Context: {story_background}
Art Style: {art_style}

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
    
    SYSTEM_PROMPT = f"""你是一位经验丰富的 Visual Novel 编剧，擅长创作细腻的对话和引人入胜的剧情。
你的任务是根据游戏设计文档和当前剧情节点的大纲，生成该节点的详细剧情脚本。

剧情要求：
1. 对话自然流畅，符合角色性格
2. 剧情内容必须符合当前节点的概要描述
3. **如果当前节点有子节点（分支），必须在剧情末尾提供选择支，选项数量必须与子节点数量一致，并一一对应**
4. 标注每段对话需要的立绘，格式为 <image id="角色名">表情</image>。
   - **优先使用【现有立绘列表】中的表情**。
   - **在同一节点内，如果角色的情绪没有明显变化，请复用同一个表情标签，不要频繁更换或创造细微差别的表情**。
   - **如果剧情需要新的表情，你可以自由创造新的表情标签（例如 <image id="角色名">despair</image>），后续会自动生成**。
   - **表情名必须是完整的英文单词，严禁使用单字母缩写。**
5. **重要：场景地点只能使用游戏设计中预定义的场景，不能自创新场景**
6. **直接输出剧本内容，不要包含任何思考过程或解释性文字**"""

    PLOT_SPLIT_PROMPT = """你是一位专业的编剧。请将以下剧情节点概要切分成 {segment_count} 个具体的"剧情片段" (Plot Points)。
{split_instruction}

【节点概要】
{node_summary}

【前情提要】
{previous_story_summary}

【可用角色详情】
{available_characters}

【可用场景列表】
{available_scenes}

请输出 JSON 格式列表：
[
  {{
    "id": 1,
    "summary": "片段1的详细描述...",
    "characters": ["角色名A", "角色名B"] (必须从【可用角色列表】中选择),
    "location": "场景名" (必须从【可用场景列表】中选择)
  }},
  ...
]

注意：每个片段的 characters 数组中的角色名必须与【可用角色列表】完全一致。"""

    PLOT_SYNTHESIS_PROMPT = """你是一位专业的 Visual Novel 编剧。你的任务是将以下由 AI 演员演绎的剧情片段（JSON 格式日志）整合成一份文学性强、代入感深的 Visual Novel 剧本。

【剧情片段演绎记录 (JSON)】
{plot_performances}

【剧情上下文 (Story Context)】
{story_context}

【后续分支选项】
{choices}

【可用角色详情】
{available_characters}

【可用场景列表】
{available_scenes}

【核心任务】
1. **剧本整合与润色**：
   - 将零散的对话日志串联成连贯的故事。
   - **优化对话节奏**：如果演员的台词过于冗长或不自然，请对其进行适当的精简和润色，使其更符合口语和角色性格。
   - **增强旁白描写**：不要仅仅罗列对话。在对话之间要视情况适当加入丰富的**环境描写、动作描写、神态描写和心理活动**，并且演员对话的内容中的心理描写和动作都要单独列成旁白，而不是放在对话里。
   - **第一人称视角**：剧本通常以主角（“我”）的视角展开。请将演员日志中的动作描述转化为“我”的观察或内心独白。
   - **优化整体逻辑**：确保整体剧情逻辑完整，连贯且合理，可以通过增加额外信息确保观众能沉浸在故事环境中并理解剧情发展。

2. **格式规范**：
   - **场景标签**：**每当开始新的剧情节点或场景发生变化时，必须在剧本开头输出场景标签。**
     **场景名称必须严格使用【可用场景列表】中的名称，不得自创。**
     格式：`<scene>场景名称</scene>`
     示例：`<scene>深海站点主控大厅</scene>`
     **场景标签必须单独占一行，后面空一行再开始剧情内容。**
   - **旁白**：用于环境、动作、心理描写。
     格式：`<content id="旁白">内容...</content>`
   - **对话**：
     <image id="角色名">表情</image>
     <content id="角色名">对话内容</content>
     **角色名必须严格使用【可用角色列表】中的名称（主角除外，主角统一使用"我"）。**
   - **主角标识**：如果角色是主角，请统一使用"我"作为名字（例如 `<content id="我">...</content>`）。

3. **分支选项与结局**：
   - 如果提供了【后续分支选项】，请在剧本的最末尾生成选项。
   - **选项文本必须精简且沉浸**：请将选项内容概括为 10 个字以内的短语（例如"去海边"、"留在教室"）。
   - **严禁使用出戏的标记**：不要在选项前加【】或其他标签提示（如【顺应局势】、【启动超忆】等），直接写选项内容即可。
   - **结局描述**：如果是叶子节点（结局），请用旁白自然地描述结局，不要使用**【BAD END】**、**【GOOD END】**等出戏的标记。
   - 格式必须为：`<choice target="node_id">选项文本</choice>`

【示例输出风格】
<scene>高中教室</scene>

<content id="旁白">午后的阳光透过窗帘的缝隙洒在课桌上，空气中弥漫着粉笔灰的味道。</content>

<image id="夏雨">bored</image>
<content id="我">……好无聊啊。</content>

<content id="旁白">我趴在桌子上，百无聊赖地转着手中的圆珠笔。就在这时，教室的门被猛地推开了。</content>

<image id="雾岛莲">excited</image>
<content id="雾岛莲">大家！快看这个！</content>

直接输出最终剧本，不要包含任何解释性文字。"""

    NEXT_SPEAKER_PROMPT = """你是指挥整场戏的导演。
【当前剧情片段目标】
{plot_summary}

【可用角色详情】
{characters}

【剧情上下文 (Story Context)】
{story_context}

**你的核心职责：**
1. 判断【剧情片段目标】是否已经达成
2. 如果目标已完成，**立即喊停**，不要拖沓

**如果剧情片段目标已基本完成，请立即喊停：**
<character>STOP</character>

**否则，如果还有关键剧情未完成，请指定下一位发言者：**
<character>角色名</character>
<advice>该角色需要推进的剧情内容,内容需要非常简短，最好只是一个动作能完成的意图，要给接下来其他人说话的空间，并且禁止规定具体台词，</advice>

**示例：**
<character>夏雨</character>
<advice>表达对提议的最终决定</advice>

只输出 XML 标签，不要其他内容。
注意你只能选择在场角色中的一位作为下一发言者，不能选择旁白或者其他角色。
注意保持整体剧情的完整性和连贯性。"""

    SUMMARY_PROMPT = """请为以下剧情生成一个简短的摘要（Summary），用于作为后续剧情的"前情提要"。

【剧情内容】
{story_content}

要求：
1. 概括主要事件和关键对话。
2. 包含任何重要的伏笔或状态变化。
3. 长度控制在 200 字以内。
4. 直接输出摘要内容。"""


# ==================== 演员 Agent 配置 ====================
class ActorConfig:
    """演员 Agent - 负责扮演特定角色并审核剧本"""
    
    # 模型参数
    TEMPERATURE = 0.7
    
    SYSTEM_PROMPT = """你现在是 Visual Novel 游戏中的角色 "{name}"。

【你的设定】
性格：{personality}
背景：{background}

你需要沉浸在角色中，以第一人称思考和行动，但不要脸谱化和过分体现人物性格，只确保人物不要OOC即可。
请忘记你是一个 AI 模型，你就是这个角色。"""

    PERFORM_PROMPT = """请根据以下剧情片段的大纲，以及当前的对话记录，继续演绎你在其中的台词和动作。

【剧情片段】
{plot_summary}

【在场其他角色详情】
{other_characters}

【可用表情 (Character Expressions)】
{character_expressions}

【剧情上下文 (Story Context)】
{story_context}

请直接开始表演，不要输出任何分析、OOC检查或额外的说明文字。
请以剧本格式输出你的表演（包含对话和动作描述）：
<image id="{name}">表情</image>
<content id="{script_label}">对话内容</content>

请注意：
1. 只输出你自己的部分，不要重复之前的对话。
2. **极简对话原则**：一次只说一句话，或者做一个动作。严禁长篇大论。不要一次性把所有想法都说完，留给对方回应的空间。
3. 保持性格一致性，同时说法要自然流畅，避免过度书面化，戏剧化和脸谱化。
4. 使用 <image id="{name}">表情</image> 标记你的表情变化，**必须单独占一行**。
   - 优先复用【现有立绘列表】中的表情。
   - 如果情绪没有和当前已有立绘有很大差别，请尽量复用已有的立绘
   - **如果且现有立绘均无法代表你此刻的心情，则你需要新的立绘，请创造新的表情名来更好地表达你自己。**
   - **表情名必须是完整的英文单词（例如 'angry', 'surprised'），严禁使用单字母缩写（如 't', 'a'）或中文。**"""

    IMAGE_CRITIQUE_PROMPT = """你现在要审核为你生成的角色立绘图片。请以第一人称的角色视角来评价这张图片。

【故事背景】
{story_background}

【美术风格】
{art_style}

【你的外貌设定】
{appearance}

【当前要求的表情】
{expression}

请以角色的口吻和视角审核这张立绘：
1. **保持角色扮演**：用"我"来称呼自己，以你的性格和语气说话。
2. **审核要点**：
   - 图片本身逻辑是否有问题，是否存在多手/脚，低质量等图片情况
   - 立绘本身是否美观，符合视觉小说立绘的风格
   - 美术风格是否符合故事设定（{art_style}）
   - 外貌是否符合你的设定（发色、眼睛、服装、身材等）
   - 表情是否准确表达了 {expression} 这个情绪
   - 整体风格和气质是否符合你的人设

如果完全满意，请说：**"PASS"**（必须包含这个词）

如果不满意，请以角色的口吻指出问题，例如：
- "表情太僵硬了，我 {expression} 的时候不会这样..."

请直接开始审核，用你的性格和语气说话。"""

    EXPRESSION_DESCRIPTION_PROMPT = """你扮演 {name}。
你的任务是描述你在呈现【{expression}】表情时的具体样貌。
请提供详细的视觉描述，包含五官细节、面部神态、眼神、嘴型以及可能的肢体动作。
描述将用于生成立绘图片。

角色设定:
{character_info}

请直接输出描述文本，不要包含其他内容。"""

# ==================== 文件路径配置 ====================
class PathConfig:
    """文件路径配置"""
    
    # 项目根目录
    import sys
    if getattr(sys, 'frozen', False):
        PROJECT_ROOT = sys._MEIPASS
    else:
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 数据目录
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    IMAGES_DIR = os.path.join(DATA_DIR, "images")
    CHARACTERS_DIR = os.path.join(IMAGES_DIR, "characters")
    BACKGROUNDS_DIR = os.path.join(IMAGES_DIR, "backgrounds")  # 背景图目录
    
    # 游戏数据文件
    GAME_DESIGN_FILE = os.path.join(DATA_DIR, "game_design.json")
    STORY_FILE = os.path.join(DATA_DIR, "story.txt")
    CHARACTER_INFO_FILE = os.path.join(DATA_DIR, "character_info.json")
    
    # 日志目录
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    TEXT_LOG_DIR = os.path.join(LOG_DIR, "text_log")   # 存放 performance_node.jsonl
    IMAGE_LOG_DIR = os.path.join(LOG_DIR, "image_log") # 存放审核不合格图片
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        dirs = [
            cls.DATA_DIR,
            cls.IMAGES_DIR,
            cls.CHARACTERS_DIR,
            cls.BACKGROUNDS_DIR,  # 添加背景目录
            cls.LOG_DIR,
            cls.TEXT_LOG_DIR,
            cls.IMAGE_LOG_DIR
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)


# 初始化时创建必要目录
PathConfig.ensure_directories()
