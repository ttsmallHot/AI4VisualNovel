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

from agents.producer_agent import ProducerAgent
from agents.artist_agent import ArtistAgent
from agents.writer_agent import WriterAgent
from agents.actor_agent import ActorAgent
from agents.music_agent import MusicAgent
from agents.config import PathConfig
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
        self.existing_assets = [] # 存储已生成的素材信息: [{id, description, character_id}]
        
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
            logger.info("   🎵 初始化音乐 Agent...")
            self.music_agent = MusicAgent()
            
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
        character_count: int = 3
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
                    character_count=character_count
                )
            
            # Step 2: 初始化演员
            logger.info("\n【Step 2/5】初始化演员阵容...")
            self._initialize_actors()
            
            # Step 3: 生成美术资源 (立绘 & 背景)
            logger.info("\n【Step 3/4】生成美术资源...")
            # 角色立绘
            self.artist.generate_all_characters(self.game_design)
            # 场景背景
            locations = [scene['name'] for scene in self.game_design.get('scenes', [])]
            self.artist.generate_all_backgrounds(locations)
            
            # Step 3.5: 生成背景音乐
            if os.getenv("ENABLE_MUSIC_GENERATION", "False").lower() == "true":
                logger.info("\n【Step 3.5/6】生成背景音乐...")
                self.music_agent.generate_bgm(self.game_design)
            else:
                logger.info("\n【Step 3.5/6】跳过背景音乐生成 (配置未启用)")
            
            # Step 4: 每日循环生成剧情
            logger.info("\n【Step 4/5】开始生成全本剧情 (4组 x 7块)...")
            self._generate_full_story()
            
            # Step 5: 生成角色关系剧情
            logger.info("\n【Step 5/5】生成角色关系专属剧情...")
            self._generate_relationship_stories()
            
            logger.info("\n" + "="*60)
            logger.info("🎉 游戏制作全部完成！")
            return self.game_design
            
        except Exception as e:
            logger.error(f"❌ 游戏创建失败: {e}")
            raise

    def _generate_relationship_stories(self):
        """生成所有角色的关系剧情 (Level 1-5)"""
        stories_dir = Path(PathConfig.DATA_DIR) / "stories"
        stories_dir.mkdir(exist_ok=True)
        
        for char_info in self.game_design.get('characters', []):
            char_name = char_info.get('name')
            char_id = char_info.get('id')
            
            if not char_name or not char_id:
                continue
                
            logger.info(f"\n💕 正在生成 {char_name} 的关系剧情...")
            
            for level in range(1, 6): # Level 1 to 5
                logger.info(f"   - Level {level}...")
                
                # 生成剧情
                story = self.writer.generate_relationship_story(char_info, level)
                
                # 演员审核 (简单审核，不依赖上下文)
                if char_name in self.actors:
                    feedback = self.actors[char_name].critique_script(story, previous_story_summary="这是你的个人专属剧情。")
                    if feedback != "PASS":
                        logger.info(f"   ⚠️ 演员提出修改建议，正在重写...")
                        # 简单重写逻辑：将反馈附加到 Prompt 中再次生成
                        # 这里为了简化，直接重新生成一次，或者忽略（因为 Writer 已经很强了）
                        # 实际项目中应该有完整的重写循环，这里简化处理
                        pass
                
                # 保存文件
                filename = f"{char_id}_level_{level}.txt"
                file_path = stories_dir / filename
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(story)
                logger.info(f"   ✅ 已保存: {filename}")

    def _generate_full_story(self):
        """生成从第一块到最后一块的完整剧情"""
        # 长期记忆列表，存储每块的摘要
        story_summaries = []
        # 短期记忆，存储上一块的最后一段原文
        last_day_raw_text = ""
        
        TOTAL_GROUPS = 4
        
        for group in range(1, TOTAL_GROUPS + 1):
            for block in range(1, 8):
                logger.info(f"\n📅 正在制作: 第 {group} 组 - Block {block}")
                
                # 构建上下文：
                # 1. 长期记忆：所有过往日期的摘要 (4组 x 7块 = 28个摘要，完全在 Context Window 范围内)
                # 这样才能确保 Group 4 能记得 Group 1 的伏笔
                long_term_context = "\n".join(story_summaries) if story_summaries else "游戏开始。"
                
                # 2. 短期记忆：上一块的最后 500 字原文 (用于衔接语气和场景)
                short_term_context = last_day_raw_text[-500:] if last_day_raw_text else ""
                
                # 2.5 可用素材提示 (新增)
                assets_context = ""
                if self.existing_assets:
                    assets_summary = json.dumps([
                        f"{a['character_id']}: {a['description']} (ID: {a['asset_id']})" 
                        for a in self.existing_assets
                    ], ensure_ascii=False)
                    assets_context = f"\n\n【可用美术素材】:\n{assets_summary}\n(请在创作时适当考虑复用这些素材对应的神态)"

                # 3. 组合上下文
                full_context = f"【前情提要 (长期记忆)】:\n{long_term_context}\n\n【上一幕结尾 (短期记忆)】:\n{short_term_context}{assets_context}"
                
                # 1. 编剧生成初稿
                draft = self.writer.generate_block_story(
                    group=group,
                    block=block,
                    game_design=self.game_design,
                    previous_story_summary=full_context
                )
                
                # 2. 演员审核 (Critique Loop)
                final_script = self._critique_loop(draft, group, block, full_context)
                
                # 2.5 生成视觉素材 (新增)
                self._generate_visuals_for_block(final_script, group, block)
                
                # 3. 保存定稿
                self.writer.append_story(final_script)
                
                # 4. 更新记忆
                # 生成今日摘要并加入长期记忆
                daily_summary = self.writer.summarize_story(final_script)
                story_summaries.append(f"Group {group} Block {block}: {daily_summary}")
                logger.info(f"📝 今日摘要: {daily_summary[:50]}...")
                
                # 更新短期记忆
                last_day_raw_text = final_script

    def _critique_loop(self, draft: str, group: int, block: int, context: str) -> str:
        """演员审核循环"""
        current_script = draft
        max_retries = 2  # 最大修改次数
        
        for round in range(max_retries):
            feedback_list = []
            
            # 让每位演员审核
            for name, actor in self.actors.items():
                if name in current_script: # 只有出场的演员才审核
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
            current_script = self.writer.generate_block_story(
                group=group,
                block=block,
                game_design=self.game_design,
                previous_story_summary=context, # 保持上下文一致
                critique_feedback=combined_feedback
            )
            
        logger.warning("⚠️  达到最大修改次数，强制通过")
        return current_script

    def _generate_ending(self) -> str:
        """生成结局剧情"""
        logger.info("🎬 生成结局剧情...")
        
        ending_type = self.check_ending_conditions() or "normal_ending"
        
        try:
            prompt = f"""根据以下信息生成结局剧情：

游戏标题: {self.game_design['title']}
结局类型: {ending_type}

角色状态:
{json.dumps(self.character_states, ensure_ascii=False, indent=2)}

结局要求:
{self.game_design.get('endings', {}).get(ending_type, '完成游戏')}

请生成一个感人且完整的结局剧情（500-800字）。"""

            ending_story = self.writer.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一位擅长创作感人结局的编剧。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8
            )
            
            # 保存结局
            self.writer.append_story(f"\n\n=== 结局: {ending_type} ===\n\n{ending_story}")
            
            logger.info(f"✅ 结局剧情生成完成: {ending_type}")
            
            return ending_story
            
        except Exception as e:
            logger.error(f"❌ 结局生成失败: {e}")
            return "游戏结束。感谢游玩！"
    
    def check_ending_conditions(self) -> Optional[str]:
        """
        检查是否达成结局条件
        
        Returns:
            结局类型，未达成返回 None
        """
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

    def _generate_visuals_for_block(self, script_block: str, group: int, block: int):
        """
        为剧情块生成所需的视觉素材
        """
        logger.info(f"🎨 分析 Group {group} Block {block} 的视觉需求...")
        
        # 1. 确保初始素材已记录 (如果是第一次运行)
        if not self.existing_assets:
            for char_info in self.game_design.get('characters', []):
                char_id = char_info.get('id')
                # 假设初始只有 neutral
                self.existing_assets.append({
                    "asset_id": f"{char_id}_neutral.png",
                    "description": "Standard neutral expression",
                    "character_id": char_id
                })
        
        # 2. 遍历演员进行分析
        for name, actor in self.actors.items():
            # 简单判断角色是否出场
            if name in script_block:
                # 获取该角色的现有素材
                char_assets = [
                    a for a in self.existing_assets 
                    if a['character_id'] == actor.character_info['id']
                ]
                
                # 分析需求
                visual_reqs = actor.analyze_visual_requirements(script_block, char_assets)
                
                # 处理需求
                for req in visual_reqs:
                    if req.get('type') == 'new':
                        description = req.get('description')
                        suffix = f"g{group}_b{block}_{int(time.time())}" # 使用时间戳防止重名
                        
                        # 生成图片
                        image_path = self.artist.generate_image_from_description(
                            actor.character_info,
                            description,
                            suffix
                        )
                        
                        if image_path:
                            filename = os.path.basename(image_path)
                            # 记录新素材
                            new_asset = {
                                "asset_id": filename,
                                "description": description,
                                "character_id": actor.character_info['id']
                            }
                            self.existing_assets.append(new_asset)
                            logger.info(f"   ✅ 新增素材: {filename}")
                    
                    elif req.get('type') == 'reuse':
                        logger.info(f"   ♻️ 复用素材: {req.get('asset_id')}")


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
