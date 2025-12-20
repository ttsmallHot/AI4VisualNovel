"""
Workflow Controller
~~~~~~~~~~~~~~~~~~~
协调各个 Agent 的执行流程，管理整个游戏生成和运行的生命周期
"""

import logging
import json
import os
from typing import Dict, Any, Optional
import time
from pathlib import Path
import re

from agents.producer_agent import ProducerAgent
from agents.artist_agent import ArtistAgent
from agents.writer_agent import WriterAgent
from agents.actor_agent import ActorAgent
from agents.music_agent import MusicAgent
from agents.config import PathConfig, ProducerConfig, APIConfig, WriterConfig
from game_engine.data import StoryParser

# 常量定义
TOTAL_WEEKS = 4  # 游戏总周数

logger = logging.getLogger(__name__)


class WorkflowController:
    """工作流控制器 - 协调所有 Agent"""
    
    def __init__(self):
        """初始化工作流控制器"""
        self.producer = None
        self.artist = None
        self.writer = None
        self.actors = {}  # 存储所有演员 Agent: {name: ActorAgent}
        
        self.game_design = None
        self.current_week = 1
        
        logger.info("🎮 工作流控制器初始化")
    
    def initialize_agents(
        self,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None
    ):
        """
        初始化基础 Agent (Producer, Artist, Writer)
        Actor Agent 将在游戏设计生成后初始化
        """
        logger.info("🚀 初始化 Agent 系统...")
        
        try:
            self.api_key = openai_api_key
            self.base_url = openai_base_url
            
            # 初始化制作人 Agent
            logger.info("   📋 初始化制作人 Agent...")
            self.producer = ProducerAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化美术 Agent
            logger.info("   🎨 初始化美术 Agent (DALL-E)...")
            self.artist = ArtistAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化编剧 Agent
            logger.info("   ✍️  初始化编剧 Agent...")
            self.writer = WriterAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化音乐 Agent
            if APIConfig.ENABLE_MUSIC_GENERATION:
                logger.info("   🎵 初始化音乐 Agent...")
                self.music_agent = MusicAgent()
            else:
                logger.info("   🎵 音乐生成已禁用，跳过初始化")
                self.music_agent = None
            
            logger.info("✅ 基础 Agent 初始化完成！")
            
        except Exception as e:
            logger.error(f"❌ Agent 初始化失败: {e}")
            raise

    def _initialize_actors(self):
        """根据游戏设计文档初始化演员 Agent"""
        if not self.game_design:
            raise ValueError("游戏设计文档未加载，无法初始化演员")
            
        logger.info("🎭 初始化演员 Agent...")
        self.actors = {}
        for char_info in self.game_design.get('characters', []):
            name = char_info.get('name')
            if name:
                actor = ActorAgent(
                    character_info=char_info,
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                self.actors[name] = actor
                logger.info(f"   ✅ 演员就位: {name}")
    
    def create_new_game(
        self,
        game_type: str = "校园恋爱",
        game_style: str = "轻松温馨",
        character_count: int = 3,
        requirements: str = ""
    ) -> Dict[str, Any]:
        """
        创建新游戏（完整流程：设计 -> 选角 -> 每日生成 -> 完结）
        """
        logger.info("="*60)
        logger.info("🎬 开始创建新游戏 (每日迭代模式)")
        logger.info("="*60)
        
        try:
            # Step 1: 检查或生成游戏设计文档
            logger.info("\n【Step 1/5】检查游戏设计文档...")
            existing_design = self.producer.load_game_design()
            if existing_design:
                logger.info(f"✅ 检测到已存在的游戏设计: 《{existing_design['title']}》")
                self.game_design = existing_design
            else:
                logger.info("   未找到游戏设计，开始生成...")
                self.game_design = self.producer.generate_game_design(
                    game_type=game_type,
                    game_style=game_style,
                    character_count=character_count,
                    requirements=requirements
                )
            
            # Step 2: 初始化演员
            logger.info("\n【Step 2/5】初始化演员阵容...")
            self._initialize_actors()
            
            # Step 3: 生成美术资源 (立绘 & 背景)
            logger.info("\n【Step 3/4】生成美术资源...")
            
            # 1. 先生成角色立绘 (带审核)
            self._generate_character_assets_with_critique()
            
            # 2. 收集所有角色的 neutral 立绘作为参考
            character_ref_images = []
            for char_info in self.game_design.get('characters', []):
                char_id = char_info.get('id', char_info.get('name'))
                neutral_path = os.path.join(PathConfig.CHARACTERS_DIR, char_id, "neutral.png")
                if os.path.exists(neutral_path):
                    character_ref_images.append(neutral_path)
            
            # 3. 生成标题画面 (传入角色参考图)
            self.artist.generate_title_image(
                title=self.game_design.get('title', 'My Galgame'),
                background_desc=self.game_design.get('background', 'A romantic story'),
                character_images=character_ref_images
            )
            
            # 4. 场景背景
            locations = [scene['name'] for scene in self.game_design.get('scenes', [])]
            self.artist.generate_all_backgrounds(locations)
            
            # Step 3.5: 生成背景音乐
            if APIConfig.ENABLE_MUSIC_GENERATION:
                logger.info("\n【Step 3.5/6】生成背景音乐...")
                self.music_agent.generate_bgm(self.game_design)
            else:
                logger.info("\n【Step 3.5/6】跳过背景音乐生成 (配置未启用)")
            
            # Step 4: 每日循环生成剧情
            logger.info(f"\n【Step 4/5】开始生成全本剧情 (Tree-based)...")
            self._generate_full_story()
            
            logger.info("\n" + "="*60)
            logger.info("🎉 游戏制作全部完成！")
            return self.game_design
            
        except Exception as e:
            logger.error(f"❌ 游戏创建失败: {e}")
            raise

    def _generate_character_assets_with_critique(self):
        """生成角色立绘（包含演员审核循环）"""
        logger.info("🎨 开始生成角色立绘 (带审核)...")
        
        if not self.game_design:
            logger.error("❌ 游戏设计未加载")
            return

        characters = self.game_design.get('characters', [])
        # 获取标准表情列表
        standard_expressions = self.artist.config.STANDARD_EXPRESSIONS
        
        for char_info in characters:
            name = char_info.get('name')
            char_id = char_info.get('id', name)
            actor = self.actors.get(name)
            
            if not actor:
                logger.warning(f"⚠️ 未找到演员 {name}，跳过审核")
                continue
                
            logger.info(f"   👤 处理角色: {name}")
            
            # 确保 neutral 最先生成，以便作为参考图
            sorted_expressions = sorted(standard_expressions, key=lambda x: 0 if x == 'neutral' else 1)
            
            # 记录 neutral 图片路径作为参考
            neutral_ref_path = None
            neutral_path_candidate = os.path.join(PathConfig.CHARACTERS_DIR, char_id, "neutral.png")
            if os.path.exists(neutral_path_candidate):
                neutral_ref_path = neutral_path_candidate

            for expression in sorted_expressions:
                filename = f"{expression}.png"
                image_path = os.path.join(PathConfig.CHARACTERS_DIR, char_id, filename)
                
                if os.path.exists(image_path):
                    logger.info(f"      ✅ [{expression}] 立绘已存在，跳过生成与审核")
                    # 如果是 neutral，确保更新引用
                    if expression == 'neutral':
                        neutral_ref_path = image_path
                    continue
                
                # 生成 + 审核循环
                max_retries = 3
                approved = False
                current_feedback = None
                
                for i in range(max_retries):
                    # 如果是重试（i>0）且文件存在，说明是上次被拒的，删除它
                    if i > 0 and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            logger.info(f"      🗑️ 删除旧的被拒图片 ({expression})")
                        except OSError:
                            pass

                    logger.info(f"      🔄 生成 [{expression}] 表情 (尝试 {i+1}/{max_retries})...")
                    
                    # ArtistAgent 会自动查找 neutral.png 作为参考（如果存在且当前不是 neutral）
                    # 将审核意见传入，用于修正本次生成
                    # 显式传入 neutral_ref_path，确保一致性
                    paths = self.artist.generate_character_images(
                        char_info, 
                        expressions=[expression],
                        feedback=current_feedback,
                        reference_image_path=neutral_ref_path if expression != 'neutral' else None
                    )
                    current_path = paths.get(expression)
                    
                    if not current_path or not os.path.exists(current_path):
                        logger.error(f"      ❌ [{expression}] 表情生成失败")
                        continue
                    
                    # 审核 (传入 neutral 参考图)
                    # 如果当前就是 neutral，则不需要参考图
                    ref_img = neutral_ref_path if expression != 'neutral' else None
                    feedback = actor.critique_visual(current_path, expression=expression, reference_image_path=ref_img)
                    
                    if feedback == "PASS":
                        logger.info(f"      ✅ [{expression}] 表情审核通过")
                        approved = True
                        # 如果新生成的 neutral 通过了审核，更新引用
                        if expression == 'neutral':
                            neutral_ref_path = current_path
                        break
                    else:
                        logger.warning(f"      ⚠️ 审核未通过: {feedback}")
                        # 如果是最后一次尝试，就不删了，保留结果
                        if i < max_retries - 1:
                            current_feedback = feedback
                
                if not approved:
                    logger.warning(f"      ⚠️ 角色 {name} 的 [{expression}] 表情在 {max_retries} 次尝试后仍未通过审核，保留最后一次结果。")

    def _generate_full_story(self):
        """生成完整的树状剧情 (DFS)"""
        # 节点摘要字典，用于构建路径上下文 {node_id: summary}
        node_summaries = {}
        # 节点内容字典，用于提取选项上下文 {node_id: full_content}
        node_contents = {}
        
        # 获取剧情树
        story_tree = self.game_design.get('story_tree', {})
        if not story_tree:
            logger.error("❌ 游戏设计文档中缺少 story_tree")
            return

        # 使用栈进行 DFS 遍历生成 (LIFO)
        # 为了保持顺序（先处理第一个子节点），我们需要反向将子节点入栈
        stack = ['root']
        visited = set()
        
        while stack:
            node_id = stack.pop() # DFS: Pop from end
            
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node_info = story_tree.get(node_id)
            if not node_info:
                logger.warning(f"⚠️ 节点 {node_id} 未在 story_tree 中定义，跳过")
                continue
                
            logger.info(f"\n📅 正在制作节点: {node_id}")
            
            # 检查是否已存在该节点的剧情
            story_path = Path(PathConfig.STORY_FILE)
            node_exists = False
            if story_path.exists():
                with open(story_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if f"=== Node: {node_id} ===" in content:
                        node_exists = True
                        logger.info(f"   ⏭️ 节点剧情已存在，跳过生成")
                        
                        # 提取摘要用于上下文
                        import re
                        pattern = f"=== Node: {node_id} ===(.*?)(=== Node|$)"
                        match = re.search(pattern, content, re.DOTALL)
                        if match:
                            node_content = match.group(1).strip()
                            node_contents[node_id] = node_content # 缓存内容
                            # 如果内存中没有摘要，则重新生成摘要
                            if node_id not in node_summaries:
                                node_summary = self.writer.summarize_story(node_content)
                                node_summaries[node_id] = node_summary
            
            if not node_exists:
                # 构建上下文
                # 1. 长期记忆：所有祖先节点的摘要
                path_context = []
                curr_parent_id = node_info.get('parent')
                immediate_parent_id = curr_parent_id # 记录直接父节点用于短期记忆

                while curr_parent_id:
                    if curr_parent_id in node_summaries:
                        path_context.insert(0, f"Node {curr_parent_id}: {node_summaries[curr_parent_id]}")
                    elif curr_parent_id == 'root' and 'root' in node_summaries:
                         path_context.insert(0, f"Node root: {node_summaries['root']}")
                    
                    # 向上追溯
                    curr_parent_node = story_tree.get(curr_parent_id)
                    curr_parent_id = curr_parent_node.get('parent') if curr_parent_node else None
                
                long_term_context = "\n".join(path_context) if path_context else "游戏开始。"

                # 2. 短期记忆：直接父节点的完整剧情
                short_term_context = ""
                if immediate_parent_id and immediate_parent_id in node_contents:
                    content = node_contents[immediate_parent_id]
                    # 如果内容太长，只取最后 2000 字符
                    if len(content) > 2000:
                        short_term_context = "..." + content[-2000:]
                    else:
                        short_term_context = content
                
                full_context = f"【长期记忆 (过往剧情梗概)】:\n{long_term_context}\n\n【短期记忆 (上一节完整剧情)】:\n{short_term_context}"
                
                # 1. 编剧生成初稿
                draft = self.writer.generate_node_story(
                    node_id=node_id,
                    node_info=node_info,
                    game_design=self.game_design,
                    previous_story_summary=full_context
                )
                
                # 2. 演员审核 (Critique Loop)
                final_script = self._critique_loop(draft, node_id, node_info, full_context)
                
                # 3. 保存定稿
                self.writer.append_story(final_script)
                
                # 4. 更新记忆
                node_contents[node_id] = final_script # 缓存新生成的内容
                daily_summary = self.writer.summarize_story(final_script)
                node_summaries[node_id] = daily_summary
                logger.info(f"📝 节点摘要: {daily_summary[:50]}...")
            
            # 将子节点加入栈 (反向加入，以便正向处理)
            children = node_info.get('children', [])
            for child_id in reversed(children):
                if child_id not in visited:
                    stack.append(child_id)

    def _critique_loop(self, draft: str, node_id: str, node_info: Dict, context: str) -> str:
        """演员审核循环"""
        current_script = draft
        max_retries = 2  # 最大修改次数
        
        for round in range(max_retries):
            feedback_list = []
            
            # 让每位演员审核
            for name, actor in self.actors.items():
                # 检查演员是否在剧本中出现
                is_present = False
                
                # 1. 检查全名
                if name in current_script:
                    is_present = True
                else:
                    # 2. 模糊匹配
                    simple_name = name.split("(")[0].strip()
                    if simple_name in current_script:
                        is_present = True
                    elif simple_name.replace(" ", "") in current_script:
                        is_present = True
                
                if is_present: # 只有出场的演员才审核
                    feedback = actor.critique_script(current_script, previous_story_summary=context)
                    if feedback != "PASS":
                        feedback_list.append(f"【{name}】: {feedback}")
            
            if not feedback_list:
                logger.info("✅ 所有演员审核通过")
                return current_script
            
            # 有反馈，需要修改
            logger.info(f"⚠️  收到 {len(feedback_list)} 条修改建议，正在重写 (Round {round+1})...")
            combined_feedback = "\n".join(feedback_list)
            
            # 让编剧重写
            current_script = self.writer.generate_node_story(
                node_id=node_id,
                node_info=node_info,
                game_design=self.game_design,
                previous_story_summary=context,
                critique_feedback=combined_feedback
            )
            
        logger.warning("⚠️  达到最大修改次数，强制通过")
        return current_script

    # _generate_ending 已移除，因为结局现在是叶子节点
    # check_ending_conditions 已移除
        if not self.game_design or not self.character_states:
            return None
        
        endings = self.game_design.get('endings', {})
        
        # 检查好感度
        max_affection = max(
            state.get('affection', 0)
            for state in self.character_states.values()
        )
        
        if max_affection >= 80:
            return "good_ending"
        elif max_affection >= 50:
            return "normal_ending"
        elif self.current_week >= TOTAL_WEEKS:
            return "bad_ending"
        
        return None

    def get_game_status(self) -> Dict[str, Any]:
        """
        获取当前游戏状态
        
        Returns:
            游戏状态字典
        """
        if not self.game_design:
            return {"initialized": False}
        
        return {
            "initialized": True,
            "title": self.game_design.get('title', 'Unknown'),
            "current_week": self.current_week,
            "total_weeks": TOTAL_WEEKS,
            "characters": [
                {
                    "name": name,
                    "affection": state.get('affection', 0),
                    "relationship": state.get('relationship_level', 'stranger')
                }
                for name, state in self.character_states.items()
            ],
            "ending": self.check_ending_conditions()
        }

# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试工作流
    try:
        workflow = WorkflowController()
        workflow.initialize_agents()
        
        print("\n" + "="*60)
        print("🎮 AI Galgame 工作流测试")
        print("="*60)
        
        # 尝试加载已有游戏
        if not workflow.load_existing_game():
            # 创建新游戏
            print("\n📝 创建新游戏...")
            workflow.create_new_game(
                game_type="校园恋爱",
                game_style="轻松温馨",
                character_count=2
            )
        
        # 显示游戏状态
        status = workflow.get_game_status()
        print("\n" + "="*60)
        print("📊 游戏状态")
        print("="*60)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
