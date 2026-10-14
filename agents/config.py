"""
Agent Configuration
~~~~~~~~~~~~~~~~~~~
所有 Agent 的配置、API Keys、模型参数和 Prompt 模板
"""

import os
from typing import Dict, Any
from pathlib import Path

from project_paths import projects_root, resolve_project_path

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
    # Optional image-only endpoint, independent of the text model proxy.
    IMAGE_OPENAI_API_KEY = os.getenv("IMAGE_OPENAI_API_KEY") or OPENAI_API_KEY
    IMAGE_OPENAI_BASE_URL = os.getenv("IMAGE_OPENAI_BASE_URL") or OPENAI_BASE_URL
    
    # Google Gemini API
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_BASE_URL = os.getenv("GOOGLE_BASE_URL", "")

    # 模型名称
    MODEL = os.getenv("MODEL", "gemini-3-pro-preview")
    
    # 图像生成模型
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")


# ==================== 全局常量 ====================
# 标准表情列表
STANDARD_EXPRESSIONS = os.getenv("GAME_CHARACTER_EXPRESSIONS", "neutral").split(",")

# ==================== 策划 (Designer) Agent 配置 ====================
class DesignerConfig:
    """策划 Agent - 负责草拟游戏设计文档"""
    
    # 游戏内容配置
    TOTAL_NODES = int(os.getenv("GAME_TOTAL_NODES", "12"))
    DEFAULT_CHARACTER_COUNT = int(os.getenv("GAME_CHARACTER_COUNT", "3"))

    SYSTEM_PROMPT = f"""你是一位资深的 Visual Novel (视觉小说) 策划，擅长创作引人入胜的故事。
你的任务是设计一个完整的 Visual Novel 游戏文档，采用**有向无环图（DAG）结构**，允许不同分支分离并汇合，并确保所有角色在复杂的剧情网中都有精彩的表现。
"""

    # 模型参数
    TEMPERATURE = 0.7
    MAX_TOKENS = 20000

    GAME_OUTLINE_PROMPT = """请创作 Visual Novel 的 Step1 设计文档。

角色数量：{character_count}（包含主角）
目标节点总数：{total_nodes}

【用户要求】
{requirements}
（如果用户要求为空，请自由发挥；如果有内容，请务必遵守。）

【任务定义（非常重要）】
这是 Step1，只产出“规划文档”，不产出 story_graph。
你需要告诉后续 Step2：故事将如何按 group 逐段展开。

【输出格式要求（必须严格遵守）】
1. 直接输出一个合法 JSON 对象，不要有任何额外文字
2. 不要使用注释（不要写 //）
3. 所有字符串必须闭合
4. 顶层必须包含并且只允许以下字段：
   - "title"
   - "background"
   - "art_style"
   - "story_outline"
   - "characters"
   - "scenes"
5. 顶层禁止包含 "story_graph"

【story_outline 结构】
1. story_outline 必须包含 groups 数组
2. groups 的每一项必须且仅需包含两个字段：group_id、group_outline
3. group_id 使用顺序命名（group1, group2, group3...）

【group 规则】
1. group_id 必须按顺序：group1, group2, group3...
2. groups 数量建议 2~6
3. 每个 group_outline 必须写清：
   - 本组主要剧情推进（发生了什么）
   - 本组与上一组如何承接（第一组可写“开场建立”）
   - 本组结尾给下一组留下什么钩子
4. 所有 group_outline 合起来必须覆盖 {total_nodes} 节点体量，不要出现“只有两三段事件却对应大量节点”的失衡规划
5. 允许分支与汇合，但必须有清晰因果，不要突兀跳转

【角色与场景规则】
1. characters 数组必须包含 {character_count} 个角色，且必须包含 1 位主角（is_protagonist=true）
2. scenes 数组建议 5-10 个（若题材确实单场景，可 >=1，但要在背景里解释）
3. 角色名统一一种语言，不要中英混写括注（例如“莲 (Ren)”是错误）

【One-shot 示例（必须参考风格与结构，禁止照抄内容）】
{{
  "title": "雾港回声",
  "background": "海雾常年笼罩的旧港城里，主角在一次停电夜发现失踪案与港务局档案篡改案其实是同一只手操纵。随着调查深入，主角被迫在保护同伴与公开真相之间做出选择。",
  "art_style": "日系悬疑动漫风，低饱和冷色调，霓虹反光与雨幕氛围，角色面部高光对比强。",
  "story_outline": {{
    "groups": [
      {{
        "group_id": "group1",
        "group_outline": "开场建立世界与核心冲突：主角在码头仓库目击异常交易并发现首个线索。以一次失败追捕收尾，留下'内鬼可能来自港务系统'的钩子。"
      }},
      {{
        "group_id": "group2",
        "group_outline": "中段扩展分支：主角可走'追查货运单据'或'接触地下情报贩'两条线，分别获得不同证据；两线最终在一场审讯对峙中汇合，确认幕后人物身份轮廓。"
      }},
      {{
        "group_id": "group3",
        "group_outline": "终局与结局分流：主角潜入档案中心公开真相，同时要在救人和保全证据间抉择。根据前面证据完整度与关系变化进入不同结局，并为续作埋下余波。"
      }}
    ]
  }},
  "characters": [
    {{
      "id": "ChenYu",
      "name": "陈雨",
      "gender": "女",
      "is_protagonist": true,
      "personality": "冷静克制，做事高效，面对风险时倾向先保全证据。",
      "appearance": "黑色短发，深蓝风衣，随身携带旧式录音笔。",
      "background": "前调查记者，因报道被压而离职，现以自由调查员身份追查港城旧案。"
    }},
    {{
      "id": "QiaoAn",
      "name": "乔岸",
      "gender": "男",
      "is_protagonist": false,
      "personality": "外表随性，内心敏锐，擅长在灰色地带获取情报。",
      "appearance": "浅灰夹克，耳钉，常带一把折叠雨伞。",
      "background": "地下情报中介，与港务系统多方势力都有往来。"
    }}
  ],
  "scenes": [
    {{"id": "scene_dock", "name": "旧码头", "description": "潮湿生锈的货柜区，夜间照明昏暗。"}},
    {{"id": "scene_archive", "name": "档案中心", "description": "层层门禁与冷白灯构成的封闭空间。"}},
    {{"id": "scene_alley", "name": "后巷茶摊", "description": "情报交易常在这里发生。"}},
    {{"id": "scene_bridge", "name": "跨海桥", "description": "雾气与车灯交错，视野受限。"}},
    {{"id": "scene_hall", "name": "港务大厅", "description": "公开发布会与最终对峙场地。"}}
  ]
}}
"""

    STORY_GRAPH_FROM_OUTLINE_PROMPT = """请根据下面的 Step1 规划文档生成 Step2 的 story_graph。

目标节点总数：{total_nodes}

【Step1 输入（game_design_outline）】
{outline_json}

【任务定义】
你只需要输出 story_graph，不要重复输出 title/background/characters/scenes。
story_graph 必须把 story_outline.groups 的顺序与承接关系落到具体节点和边上。

【输出格式要求（必须严格遵守）】
1. 直接输出一个合法 JSON 对象，不要有任何额外文字
2. 只允许两个顶层字段："nodes" 和 "edges"
3. 输出结构必须是：
{{
  "nodes": {{
    "root": {{"id": "root", "summary": "...", "type": "normal"}},
    "node1": {{"id": "node1", "summary": "...", "type": "normal"}}
  }},
  "edges": [
    {{"from": "root", "to": "node1", "choice_text": null}}
  ]
}}

【硬性约束】
1. 必须是 DAG（有向无环图），不能有环
2. root 必须存在，且所有节点必须从 root 可达
3. 节点总数必须严格等于 {total_nodes}
4. 节点命名必须统一：root, node1, node2, node3...
5. 每个节点必须包含 id/summary/type，其中 type 仅允许 normal 或 merge
6. edges 的 from/to 必须引用已存在节点

【choice_text 规则】
1. 单一路径自然推进可用 null
2. 分支选择时必须给简洁沉浸式文本（建议 5~10 字）
3. 禁止元标记，如“(技术路线)”“【A线】”等

【分组落地规则】
1. 节点顺序应体现 groups 的推进顺序
2. 每个 group_outline 描述的关键事件都要在对应节点摘要中落地
3. 组间承接必须体现在跨组边上，不能断层
4. 汇合点必须有清晰逻辑来源，不要“硬汇合”

【One-shot 示例（必须参考结构与粒度，禁止照抄内容）】
{{
  "nodes": {{
    "root": {{
      "id": "root",
      "summary": "夜雨中的旧码头发生异常交接，主角目击到疑似伪造货运单据的交易，并在追踪时发现港务系统权限卡遗落现场。",
      "type": "normal"
    }},
    "node1": {{
      "id": "node1",
      "summary": "主角选择先追查货运单据来源，潜入档案室后拿到一份被篡改的出入记录，线索指向港务内控部门。",
      "type": "normal"
    }},
    "node2": {{
      "id": "node2",
      "summary": "主角转向接触地下情报贩，得知当晚有第二批货被临时改道，且改道指令来自高权限终端。",
      "type": "normal"
    }},
    "node3": {{
      "id": "node3",
      "summary": "两条调查线在审讯室汇合：篡改记录与改道指令都指向同一名负责人，主角确认了幕后操盘者身份轮廓。",
      "type": "merge"
    }},
    "node4": {{
      "id": "node4",
      "summary": "主角公开证据并保护证人撤离，成功触发真相结局，但代价是关键同伴暴露于追杀风险。",
      "type": "normal"
    }},
    "node5": {{
      "id": "node5",
      "summary": "主角优先救人导致证据链不完整，案件暂时被压下，进入未竟结局并留下后续追查钩子。",
      "type": "normal"
    }}
  }},
  "edges": [
    {{"from": "root", "to": "node1", "choice_text": "潜入档案室"}},
    {{"from": "root", "to": "node2", "choice_text": "联络情报贩"}},
    {{"from": "node1", "to": "node3", "choice_text": null}},
    {{"from": "node2", "to": "node3", "choice_text": null}},
    {{"from": "node3", "to": "node4", "choice_text": "公开证据"}},
    {{"from": "node3", "to": "node5", "choice_text": "先救同伴"}}
  ]
}}

"""


# ==================== 制作人 (Producer) Agent 配置 ====================
class ProducerConfig:
    """制作人 Agent - 负责审核游戏设计文档并把控进度"""
    
    SYSTEM_PROMPT = """你是一位资深的 Visual Novel 游戏制作人，负责把控游戏的宏观质量和项目方向。
你的任务是审核策划提交的设计方案，确保其符合用户需求，且具有商业价值和艺术逻辑。"""

    GAME_OUTLINE_CRITIQUE_PROMPT = """你现在是游戏制作人，请审核 Step1 的游戏大纲文档（该文档不包含 story_graph）。

【用户原始要求】
{user_requirements}

【核心参数指标】
- 目标总节点数（用于评估体量覆盖）：{expected_nodes}
- 目标角色数量：{expected_characters}

【Step1 大纲文档】
{game_outline}

请从以下维度审核：
1. 需求契合度：是否满足用户主题、风格与核心冲突要求
2. 结构清晰度：story_outline.groups 是否清晰、顺序合理
3. 体量可行性：groups 的规划是否足以覆盖目标节点体量
4. 承接与钩子：各组是否写明承接关系与下一组钩子
5. 角色与场景：角色数与主角设定是否正确，场景是否足够支撑剧情

输出规则：
- 如果可通过，请只回复 "PASS"
- 否则给出可执行、具体的修改建议（不要泛泛而谈）
"""

    STORY_GRAPH_CRITIQUE_PROMPT = """你现在是游戏制作人，请审核 Step2 的 story_graph。

【目标总节点数】
{expected_nodes}

【Step1 大纲（用于对照）】
{game_outline}

【Step2 story_graph】
{story_graph}

请从以下维度审核：
1. DAG 合法性：是否无环、from/to 是否引用有效节点
2. 可达性：是否所有节点都从 root 可达
3. 节点数量：是否严格匹配目标总节点数
4. 分组对齐：是否体现 Step1 groups 的推进顺序与关键事件
5. 分支与汇合：汇合是否有逻辑来源，是否存在断层或硬汇合
6. 选择文本：choice_text 是否沉浸、简洁、无元标记

输出规则：
- 如果可通过，请只回复 "PASS"
- 否则给出可执行、具体的修改建议（指出节点/边层面的修正方向）
"""

    STORY_GRAPH_REACT_PROMPT = """你现在是 ReAct 风格的游戏制作人审核代理。
你的目标是审核 story_graph 的结构质量与叙事质量。

【目标节点数】
{expected_nodes}

【Step1 大纲（用于对照）】
{game_outline}

【Step2 story_graph】
{story_graph}

【可用工具】
1. graph_validate: 检查 DAG 结构合法性与基础统计。
2. enumerate_paths: 枚举 root 到叶子的所有路径，并返回路径摘要。

【当前观察记录】
{observations}

请只输出 JSON，字段格式如下：
{{
  "thought": "你的简短思考",
  "action": "graph_validate | enumerate_paths | finalize",
  "action_input": {{}},
  "final_decision": "PASS 或 REVISE（仅 action=finalize 时需要）",
  "final_feedback": "仅 action=finalize 且 REVISE 时填写可执行修改建议"
}}

规则：
1. 如果结构信息不足，先调用工具，不要直接 finalize。
2. finalize=PASS 仅在结构与叙事都合理时使用。
3. finalize=REVISE 时，final_feedback 必须具体到节点/边/路径问题。
"""



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

    CG_PROMPT_TEMPLATE = """Create a full-screen event CG illustration for a visual novel.

Story Context: {story_background}
Art Style: {art_style}
Canonical Characters: {characters}

Writer's Shot Description:
{description}

CRITICAL REQUIREMENTS:
- Treat the Writer's description as the authoritative storyboard for this exact story moment.
- Preserve every referenced character's identity, hairstyle, facial features, clothing, age, and proportions.
- Use the supplied character reference images only for identity and design consistency.
- Render one coherent 16:9 cinematic composition, not a sprite sheet, collage, character lineup, or title card.
- Accurately render the requested expressions, gaze, body language, interaction, environment, props, camera angle, lighting, and mood.
- Do not invent additional characters, props, actions, injuries, romance, or plot information.
- No text, dialogue, subtitles, UI, logos, signatures, or watermarks.
- Avoid duplicated characters, malformed hands, extra fingers, fused limbs, cropped faces, and inconsistent costumes.

Revision feedback:
{feedback}"""

    CG_IMAGE_SIZE = "1792x1024"

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
6. Writer 同时负责判断当前节点是否值得生成一张关键剧情 CG；CG 只用于告白、冲突爆发、
   真相揭晓、关系转折或结局等值得定格的瞬间，普通对话不要生成 CG。
7. **直接输出任务要求的内容，不要包含任何思考过程或解释性文字**"""

    SCRIPT_SYNTHESIS_PROMPT = """你是一位专业的 Visual Novel 编剧。你的任务是将以下由 AI 演员演绎的对话记录（JSON 格式日志）整合成一份文学性强、代入感深的 Visual Novel 剧本。

【全剧剧情大纲 (Global Outline)】
{game_outline}

【角色演绎记录 (JSON)】
{performances}

说明：每条记录通常包含 turns 数组；每个 turn 仅有 `character`、`thought`、`action`、`dialogue`、`image` 五个字段。
- `thought` 是角色内心，只用于帮助你理解潜台词。
- `action` 是对外可见的非语言动作，只能转写为旁白。
- `dialogue` 是角色真正说出口的话，只能转写为角色台词。
- `image` 是当前表情标签。

【剧情上下文 (Story Context)】
{story_context}

【后续分支选项】
{choices}

【可用角色详情】
{available_characters}

【可用场景列表】
{available_scenes}

【当前节点】
节点 ID：{node_id}
节点概要：{node_summary}

【核心任务】
1. **剧本整合与润色**：
   - 将零散的对话日志串联成连贯的故事。
   - **优化对话节奏**：如果演员的台词过于冗长或不自然，请对其进行适当的精简和润色，使其更符合口语和角色性格。
   - **增强旁白描写**：不要仅仅罗列对话。在对话之间要视情况适当加入丰富的**环境描写、动作描写、神态描写和心理活动**，并且演员对话的内容中的心理描写和动作都要单独列成旁白，而不是放在对话里。
   - 对于 turns 中的 `thought`，请转写成旁白或心理描写，不要直接当作角色说出口的对白。
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
     **角色名必须严格使用【可用角色列表】中的名称（包括主角）。**
     **角色 content 内只能放角色实际说出口的话，禁止混入“某人说道”、动作、神态或语气描写，也不要在台词外包中文引号。所有这些内容必须单独写入旁白 content。**

3. **分支选项与结局**：
   - 如果提供了【后续分支选项】，请在剧本的最末尾生成选项。
   - **选项文本必须精简且沉浸**：请将选项内容概括为 10 个字以内的短语（例如"去海边"、"留在教室"）。
   - **严禁使用出戏的标记**：不要在选项前加【】或其他标签提示（如【顺应局势】、【启动超忆】等），直接写选项内容即可。
   - **结局描述**：如果是叶子节点（结局），请用旁白自然地描述结局，不要使用**【BAD END】**、**【GOOD END】**等出戏的标记。
   - 格式必须为：`<choice target="node_id">选项文本</choice>`

4. **CG 决策与分镜**：
   - 由你判断当前节点是否存在值得定格的关键画面。普通交谈、过场和重复情绪不要生成 CG。
   - 每个节点最多生成一张 CG；不需要时 `cgs` 输出空数组。
   - 需要 CG 时，在剧本中最合适的叙事位置单独插入 `<cg id="CG_ID"/>`。
   - CG_ID 只能使用英文字母、数字、下划线和连字符，并且在项目内语义清晰。
   - `characters` 只能填写【可用角色详情】中的角色 ID；无人事件画面可为空数组。
   - `description` 必须是一段可直接交给 Artist 生成图片的详细中文分镜，至少包含：准确剧情瞬间、
     场景与时间、画面中每个人物的位置、表情、视线、姿势、动作与互动、镜头景别与角度、
     前中后景构图、光线、色彩、气氛、需要保持的服装/道具连续性，以及禁止出现的额外人物、
     文字、水印、错误肢体或剧情外元素。不得只写抽象主题。
   - CG 只能描绘本节点剧本中真实发生的瞬间，不得添加 Actor 没有表演过的新事件或新台词。

【示例输出风格】
<scene>高中教室</scene>

<content id="旁白">午后的阳光透过窗帘的缝隙洒在课桌上，空气中弥漫着粉笔灰的味道。</content>

<image id="夏雨">bored</image>
<content id="夏雨">……好无聊啊。</content>

<content id="旁白">我趴在桌子上，百无聊赖地转着手中的圆珠笔。就在这时，教室的门被猛地推开了。</content>

<image id="雾岛莲">excited</image>
<content id="雾岛莲">大家！快看这个！</content>

严格输出一个 JSON 对象，不要 Markdown 和解释：
{{
  "script": "包含完整 VN 标签、并在合适位置包含可选 cg 标签的最终剧本",
  "cgs": [
    {{
      "id": "CG_ID",
      "node_id": "{node_id}",
      "characters": ["角色ID"],
      "description": "详细分镜描述"
    }}
  ]
}}
`cgs` 中每一项必须且只能包含 id、node_id、characters、description 四个字段。"""

    NEXT_SPEAKER_PROMPT = """你是指挥整场戏的导演。
  【当前节点目标】
  {node_goal}

【全剧剧情大纲 (Global Outline)】
{game_outline}

【可用角色详情】
{characters}

【剧情上下文 (Story Context)】
{story_context}

**你的核心职责：**
1. 判断【当前节点目标】是否已经达成
2. 如果目标已完成，请找合适的时机喊停，不要拖沓
3. 若当前节点目标含 mandatory_revision_evidence，必须逐项检查【剧情上下文】里是否已经
   出现可见结果。角色提出“要求、建议、准备、将要、带路、去取、让别人做”不算完成；
   必须继续选择能亲自执行任务或明确说出检验结果的角色。
4. 不要重复已经发生的移动、质问或摆放物证。每次 advice 都应填补一个尚未出现的结果。
5. 当任务是检验、比对、演示或揭穿时，指导应让所选角色在这一轮直接完成动作并给出
   可观察结果；不要只让他要求另一角色去做。不得替 Actor 规定具体台词。
6. resolution 节点中，必须先完成认罪、完整动机、后果和人物弧，再安排唯一的尾声落句；
   尾声落句必须是最后一个 Actor 回合。一旦尾声发生，立即 STOP，不得再让凶手供述或嘶喊。

**如果当前节点目标已基本完成，请立即喊停：**
<character>STOP</character>

**否则，如果还有关键剧情未完成，请指定下一位发言者：**
<character>角色名</character>
<advice>该角色本轮亲自完成的一个动作或明确表达的结果。内容必须简短，给其他人留出回应空间，禁止规定具体台词。</advice>

**示例：**
<character>夏雨</character>
<advice>表达对提议的最终决定</advice>

只输出 XML 标签，不要其他内容。
注意你只能选择在场角色中的一位作为下一发言者，不能选择旁白或者其他角色。
注意保持整体剧情的丰富度，完整性和连贯性。"""

    MEMORY_IMPORTANCE_SCORE_PROMPT = """请基于以下节点剧本，给出长期记忆重要性分数。
输出严格 JSON，格式如下：
{{
  "actor_importance": {{"角色名": 0.0-1.0}}
}}
规则：
1. 分数越高表示越值得该角色长期记忆优先召回。
2. 重点考虑：主线推进、关键事实、关系变化、高后果事件。
3. 未出现在节点中的角色不必输出。

【全剧剧情大纲 (Global Outline)】
{game_outline}

【节点ID】{node_id}
【在场角色】{actor_names}
【节点剧本】
{node_script}
"""


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

    PERFORM_PROMPT = """请根据以下导演指导意见，以及当前的对话记录，继续演绎你在其中的台词和动作。

【导演指导】
{director_guidance}

【在场其他角色详情】
{other_characters}

【可用表情 (Character Expressions)】
{character_expressions}

【剧情上下文 (Story Context)】
{story_context}

【本回合唯一任务（再次确认，优先级高于上文中已经发生的表演）】
{director_guidance}

不得复述【剧情上下文】里已经发生的 action 或 dialogue。必须针对上面的本回合任务，
生成一个新的、可见且可核验的动作或台词。

请直接开始表演，不要输出任何分析、OOC检查或额外的说明文字。
请严格输出一个 JSON 对象，且只能包含以下四个字段：
{{
  "thought": "...",
  "action": "...",
  "dialogue": "...",
  "image": "..."
}}

请注意：
1. 只输出你自己的部分，不要重复之前的对话。
2. **极简表演原则**：一次最多做一个动作并说一句话。严禁长篇大论，留给对方回应的空间。
3. thought 是角色内心想法（仅自己可见，不会传播给其他角色）。
4. action 只能填写对外可见的非语言动作，不得包含任何台词；没有动作时填空字符串。
5. dialogue 只能填写角色实际说出口的话，不得包含引号、说话人归属、动作、神态或语气描写；没有说话时填空字符串。
6. 保持性格一致性，同时说法要自然流畅，避免过度书面化、戏剧化和脸谱化。
7. image 为表情标签，优先复用【可用表情】中的表情（如无合适可新建英文标签）。
8. 不要输出除 thought/action/dialogue/image 之外的任何字段、解释文字或代码块。
9. action 不得突然使用 Core GDD、已提交前文和本回合任务都未声明的新物品；尤其不得凭空
   掏出手铐、照片、录音、信件或检测报告。需要控制角色时，只能使用在场人物当下可完成的动作。"""

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
   - 图片本身逻辑是否有问题，是否存在低质量等图片情况
   - 立绘本身是否美观，符合视觉小说立绘的风格
   - 美术风格是否完全符合故事设定（{art_style}）
   - 外貌是否完全符合你的设定（发色、眼睛、服装、身材等）
   - 表情是否准确表达了 {expression} 这个情绪
   - 整体行为风格和气质是否符合你的人设

如果完全满意，请说：**"PASS"**（必须包含这个词）

如果不满意，请以角色的口吻指出问题，例如：
- "表情太僵硬了，我 {expression} 的时候不会这样..."

不要过分夸张图片的问题，请直接开始审核，用你的性格和语气说话。"""

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
    
    PROJECT_NAME = None
    PROJECT_DIR = None
    PROJECTS_ROOT = str(projects_root())

    # 数据目录
    DATA_DIR = None
    IMAGES_DIR = None
    CHARACTERS_DIR = None
    BACKGROUNDS_DIR = None
    CG_DIR = None
    
    # 游戏数据文件
    GAME_DESIGN_FILE = None
    STORY_GRAPH_FILE = None
    STORY_FILE = None
    CHARACTER_INFO_FILE = None
    CG_MANIFEST_FILE = None
    
    # 日志目录
    LOG_DIR = None
    TEXT_LOG_DIR = None
    IMAGE_LOG_DIR = None
    RUNTIME_DIR = None
    CHROMA_DIR = None
    BUILD_DIR = None
    
    @classmethod
    def init(cls, project: str):
        """Initialize a standalone project path or a legacy data/<name> project."""
        project_dir = resolve_project_path(project, root=cls.PROJECTS_ROOT)

        cls.PROJECT_NAME = project_dir.name
        cls.PROJECT_DIR = str(project_dir)
        # DATA_DIR is retained as a compatibility alias used throughout the workflow.
        cls.DATA_DIR = cls.PROJECT_DIR
        cls.IMAGES_DIR = os.path.join(cls.DATA_DIR, "images")
        cls.CHARACTERS_DIR = os.path.join(cls.IMAGES_DIR, "characters")
        cls.BACKGROUNDS_DIR = os.path.join(cls.IMAGES_DIR, "backgrounds")
        cls.CG_DIR = os.path.join(cls.IMAGES_DIR, "cg")

        cls.GAME_DESIGN_FILE = os.path.join(cls.DATA_DIR, "game_design.json")
        cls.STORY_GRAPH_FILE = os.path.join(cls.DATA_DIR, "story_graph.json")
        cls.STORY_FILE = os.path.join(cls.DATA_DIR, "story.txt")
        cls.CHARACTER_INFO_FILE = os.path.join(cls.DATA_DIR, "character_info.json")
        cls.CG_MANIFEST_FILE = os.path.join(cls.DATA_DIR, "cg_manifest.json")

        cls.RUNTIME_DIR = os.path.join(cls.DATA_DIR, ".ai4vn")
        cls.LOG_DIR = os.path.join(cls.RUNTIME_DIR, "logs")
        cls.TEXT_LOG_DIR = os.path.join(cls.LOG_DIR, "text_log")
        cls.IMAGE_LOG_DIR = os.path.join(cls.LOG_DIR, "image_log")
        cls.CHROMA_DIR = os.path.join(cls.RUNTIME_DIR, "chroma")
        cls.BUILD_DIR = os.path.join(cls.RUNTIME_DIR, "builds")

        cls.ensure_directories()

    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        dirs = [
            cls.DATA_DIR,
            cls.IMAGES_DIR,
            cls.CHARACTERS_DIR,
            cls.BACKGROUNDS_DIR,  # 添加背景目录
            cls.CG_DIR,
            cls.LOG_DIR,
            cls.TEXT_LOG_DIR,
            cls.IMAGE_LOG_DIR
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
