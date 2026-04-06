"""
Workflow Controller
~~~~~~~~~~~~~~~~~~~
协调各个 Agent 的执行流程，管理整个游戏生成和运行的生命周期
"""

import logging
import json
import os
import shutil
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
import time
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.producer_agent import ProducerAgent
from agents.designer_agent import DesignerAgent
from agents.artist_agent import ArtistAgent
from agents.writer_agent import WriterAgent
from agents.actor_agent import ActorAgent
from agents.config import PathConfig, APIConfig, WriterConfig, DesignerConfig
from agents.story_graph import StoryGraph
from game_engine.data import StoryParser

# 常量定义
logger = logging.getLogger(__name__)


class WorkflowController:
    """工作流控制器 - 协调所有 Agent"""
    
    def __init__(self):
        """初始化工作流控制器"""
        # 确保日志和数据目录存在
        PathConfig.ensure_directories()
        
        self.producer = None
        self.designer = None
        self.artist = None
        self.writer = None
        self.api_key = None
        self.base_url = None
        self.actors = {}  # 存储所有演员 Agent: {name: ActorAgent}
        self.expressions_db = self._load_expressions()  # 表情库管理
        self._story_file_lock = threading.Lock()
        self._expressions_lock = threading.Lock()
        self._performance_log_lock = threading.Lock()
        
        self.game_design = None
        
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
            logger.info("   📋 初始化制作人 Agent (Reviewer)...")
            self.producer = ProducerAgent(api_key=openai_api_key, base_url=openai_base_url)

            # 初始化策划 Agent
            logger.info("   🎨 初始化策划 Agent (Designer)...")
            self.designer = DesignerAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化美术 Agent
            logger.info("   🎨 初始化美术 Agent...")
            self.artist = ArtistAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化编剧 Agent
            logger.info("   ✍️  初始化编剧 Agent...")
            self.writer = WriterAgent(api_key=openai_api_key, base_url=openai_base_url)
            
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
                # 初始化该角色的表情库
                self._initialize_character_expressions(name)
                
                actor = ActorAgent(
                    character_info=char_info,
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                self.actors[name] = actor
                is_protagonist = char_info.get('is_protagonist', False)
                role_label = " (主角)" if is_protagonist else ""
                logger.info(f"   ✅ 演员就位: {name}{role_label}")

    @staticmethod
    def _save_json(path: str, data: Dict[str, Any]) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_json_with_log(self, path: str, data: Dict[str, Any], message: str) -> None:
        self._save_json(path, data)
        logger.info(message)

    def _generate_outline_with_oc(
        self,
        character_count: int,
        requirements: str,
        locked_characters: List[Dict[str, Any]],
        previous_game_outline: Optional[Dict[str, Any]] = None,
        feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        outline = self.designer.generate_game_outline(
            character_count=character_count,
            requirements=requirements,
            feedback=feedback,
            previous_game_outline=previous_game_outline,
            locked_characters=locked_characters
        )

        if locked_characters:
            outline = self._apply_oc_characters_to_outline(outline, locked_characters, character_count)

        return outline

    def _review_and_revise(
        self,
        item: Dict[str, Any],
        phase_name: str,
        revise_action: str,
        max_iterations: int,
        critique_fn: Callable[[Dict[str, Any]], str],
        revise_fn: Callable[[Dict[str, Any], str], Dict[str, Any]],
        save_fn: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """通用审核-修订循环：Producer 审核，不通过则 Designer 修订。"""
        iteration = 0
        while iteration < max_iterations:
            logger.info(f"   📋 制作人正在审核{phase_name} (第 {iteration + 1} 轮)...")
            feedback = critique_fn(item)

            if feedback == "PASS":
                logger.info(f"   ✅ {phase_name}审核通过")
                return item

            logger.info(f"   ⚠️ {phase_name}反馈: {feedback[:100]}...")
            logger.info(f"   🔧 策划正在根据{phase_name}反馈{revise_action}...")
            item = revise_fn(item, feedback)

            if save_fn:
                save_fn(item)

            iteration += 1

        logger.warning(f"   ⚠️ {phase_name}达到最大审核次数，制作人强制批准当前结果继续。")
        return item
    
    def run_design_phase(
        self,
        character_count: int = 3,
        requirements: str = "",
        oc_characters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        阶段 1：设计阶段 (生成游戏大纲、角色设定和背景)
        """
        logger.info("="*60)
        logger.info("🎬 [阶段 1] 开始设计生成")
        logger.info("="*60)
        
        try:
            raw_oc_characters = oc_characters or []
            if raw_oc_characters:
                self._prepare_oc_images(raw_oc_characters)

            normalized_oc = self._normalize_oc_characters(raw_oc_characters)
            effective_character_count = max(character_count, len(normalized_oc))

            if normalized_oc:
                logger.info(f"🧩 检测到用户 OC 角色: {len(normalized_oc)} 个（design 阶段将锁定这些角色）")

            existing_design = self.producer.load_game_design()
            if existing_design:
                logger.info(f"✅ 检测到已存在的游戏设计: 《{existing_design['title']}》")
                self.game_design = existing_design
                return self.game_design
            
            logger.info("   未找到游戏设计，策划开始草拟方案...")
            max_iterations = 3

            # -------------------------
            # Step1: 生成并审核大纲（无 story_graph）
            # -------------------------
            game_outline = self._generate_outline_with_oc(
                character_count=effective_character_count,
                requirements=requirements,
                locked_characters=normalized_oc
            )
            self._save_json_with_log(
                PathConfig.GAME_DESIGN_FILE,
                game_outline,
                f"   💾 Step1 已保存（无 story_graph）: {PathConfig.GAME_DESIGN_FILE}"
            )
            game_outline = self._review_and_revise(
                item=game_outline,
                phase_name="Step1 大纲",
                revise_action="修改大纲",
                max_iterations=max_iterations,
                critique_fn=lambda current_outline: self.producer.critique_game_outline(
                    game_outline=current_outline,
                    user_requirements=requirements,
                    expected_nodes=self.designer.config.TOTAL_NODES,
                    expected_characters=effective_character_count
                ),
                revise_fn=lambda current_outline, feedback: self._generate_outline_with_oc(
                        character_count=effective_character_count,
                        requirements=requirements,
                        locked_characters=normalized_oc,
                        previous_game_outline=current_outline,
                        feedback=feedback,
                    ),
                save_fn=lambda updated_outline: self._save_json_with_log(
                    PathConfig.GAME_DESIGN_FILE,
                    updated_outline,
                    f"   💾 Step1 更新已保存: {PathConfig.GAME_DESIGN_FILE}"
                )
            )

            # -------------------------
            # Step2: 基于通过大纲生成并审核 story_graph
            # -------------------------
            story_graph = self.designer.generate_story_graph_from_outline(game_outline)
            self._save_json_with_log(
                PathConfig.STORY_GRAPH_FILE,
                story_graph,
                f"   💾 Step2 已保存 story_graph: {PathConfig.STORY_GRAPH_FILE}"
            )
            story_graph = self._review_and_revise(
                item=story_graph,
                phase_name="Step2 story_graph",
                revise_action="修正 story_graph",
                max_iterations=max_iterations,
                critique_fn=lambda current_graph: self.producer.critique_story_graph(
                    story_graph=current_graph,
                    game_outline=game_outline,
                    expected_nodes=self.designer.config.TOTAL_NODES
                ),
                revise_fn=lambda _current_graph, feedback: self.designer.generate_story_graph_from_outline(
                    game_outline,
                    feedback=feedback
                ),
                save_fn=lambda updated_graph: self._save_json_with_log(
                    PathConfig.STORY_GRAPH_FILE,
                    updated_graph,
                    f"   💾 Step2 更新已保存: {PathConfig.STORY_GRAPH_FILE}"
                )
            )

            # 合并成完整 game_design
            self.game_design = game_outline
            self.game_design["story_graph"] = story_graph
                
            self.producer.save_game_design(self.game_design)
            logger.info("🎉 阶段 1：游戏设计阶段完成！你可以检查 data/game_design.json 文件进行修改。")
            return self.game_design
            
        except Exception as e:
            logger.error(f"❌ 设计阶段失败: {e}", exc_info=True)
            raise

    def _prepare_oc_images(self, oc_characters: List[Dict[str, Any]]) -> None:
        """将 input.yaml 中声明的 OC neutral 图片复制到标准角色目录。"""
        for item in oc_characters:
            if not isinstance(item, dict):
                continue

            char_id = str(item.get("id", "")).strip()
            char_name = str(item.get("name", "")).strip() or char_id
            if not char_id:
                continue

            target_dir = Path(PathConfig.CHARACTERS_DIR) / char_id
            os.makedirs(target_dir, exist_ok=True)

            neutral_src = str(item.get("neutral_image_path", "")).strip()
            if neutral_src:
                self._copy_oc_image(neutral_src, target_dir / "neutral.png", char_name, "neutral")

    @staticmethod
    def _resolve_oc_source_path(source_path: str) -> Path:
        """解析 OC 源图片路径（支持相对项目根目录）。"""
        source = Path(source_path)
        if source.is_absolute():
            return source
        return Path(PathConfig.PROJECT_ROOT) / source

    def _copy_oc_image(self, source_path: str, target_path: Path, char_name: str, label: str) -> None:
        """复制 OC 图片到目标路径。"""
        source = self._resolve_oc_source_path(source_path)
        if not source.exists() or not source.is_file():
            logger.warning(f"⚠️ OC 图片不存在，跳过: {source_path} ({char_name}/{label})")
            return

        try:
            shutil.copy2(source, target_path)
            logger.info(f"🖼️ 已导入 OC 图片: {char_name}/{label} -> {target_path}")
        except Exception as e:
            logger.warning(f"⚠️ 导入 OC 图片失败: {source_path} ({char_name}/{label})，原因: {e}")

    @staticmethod
    def _normalize_oc_characters(oc_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """标准化并去重 OC 角色（字段与 game_design.characters 保持一致）。"""
        normalized: List[Dict[str, Any]] = []
        seen_ids = set()

        for idx, item in enumerate(oc_characters, 1):
            if not isinstance(item, dict):
                continue

            char_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()

            if not char_id or not name:
                logger.warning(f"⚠️ OC 第 {idx} 项缺少 id 或 name，已跳过")
                continue

            if char_id in seen_ids:
                logger.warning(f"⚠️ OC 出现重复 id={char_id}，后续项已跳过")
                continue

            seen_ids.add(char_id)
            normalized.append({
                "id": char_id,
                "name": name,
                "gender": item.get("gender", ""),
                "is_protagonist": bool(item.get("is_protagonist", False)),
                "personality": item.get("personality", ""),
                "appearance": item.get("appearance", ""),
                "background": item.get("background", "")
            })

        return normalized

    @staticmethod
    def _apply_oc_characters_to_outline(
        outline: Dict[str, Any],
        oc_characters: List[Dict[str, Any]],
        target_character_count: int
    ) -> Dict[str, Any]:
        """将 OC 角色注入到大纲角色池中：OC 优先，缺失字段再由生成结果补齐。"""
        generated_chars = outline.get("characters", []) if isinstance(outline.get("characters", []), list) else []

        generated_by_id = {
            str(char.get("id", "")).strip(): char
            for char in generated_chars if isinstance(char, dict) and str(char.get("id", "")).strip()
        }
        generated_by_name = {
            str(char.get("name", "")).strip(): char
            for char in generated_chars if isinstance(char, dict) and str(char.get("name", "")).strip()
        }

        merged: List[Dict[str, Any]] = []
        locked_ids = set()

        for oc in oc_characters:
            oc_copy = dict(oc)
            oc_id = str(oc_copy.get("id", "")).strip()
            oc_name = str(oc_copy.get("name", "")).strip()
            locked_ids.add(oc_id)

            candidate = generated_by_id.get(oc_id) or generated_by_name.get(oc_name)
            if candidate:
                for field in ["gender", "personality", "appearance", "background"]:
                    if not str(oc_copy.get(field, "")).strip() and str(candidate.get(field, "")).strip():
                        oc_copy[field] = candidate.get(field, "")

            merged.append(oc_copy)

        for char in generated_chars:
            if not isinstance(char, dict):
                continue
            char_id = str(char.get("id", "")).strip()
            if not char_id or char_id in locked_ids:
                continue
            merged.append(char)
            if len(merged) >= target_character_count:
                break

        if merged and not any(bool(c.get("is_protagonist", False)) for c in merged):
            merged[0]["is_protagonist"] = True

        outline["characters"] = merged
        return outline

    def run_script_phase(self) -> bool:
        """
        阶段 2：剧本生成阶段 (演员扮演、剧本切分)
        """
        logger.info("="*60)
        logger.info("🎬 [阶段 2] 开始剧本生成")
        logger.info("="*60)
        
        if not self.load_existing_game():
            logger.error("❌ 未找到游戏设计文档，请先运行设计阶段 (python main.py --mode design)！")
            return False
            
        try:
            logger.info("\n【初始化】加载演员...")
            self._sync_expressions_with_design()
            self._initialize_actors()
            
            logger.info(f"\n【生成剧本】正在按照 DAG 图生成全节点剧情...")
            self._generate_full_story()
            
            logger.info("\n【分析图片需求】扫描剧本提取所需的角色表情记录...")
            self._scan_story_for_expressions()
            
            logger.info("🎉 阶段 2：剧本生成阶段完成！所有的剧本片段已就绪。")
            return True
            
        except Exception as e:
            logger.error(f"❌ 剧本生成阶段失败: {e}", exc_info=True)
            raise

    def run_render_phase(self) -> bool:
        """
        阶段 3：多模态资产渲染阶段 (背景、立绘、审核)
        """
        logger.info("="*60)
        logger.info("🎬 [阶段 3] 开始资产渲染")
        logger.info("="*60)
        
        if not self.load_existing_game():
            logger.error("❌ 未找到游戏设计文档，请先运行设计阶段！")
            return False
            
        try:
            # 演员立绘审核需要 Actor 对象
            self._initialize_actors()
            
            # 确保表情库同步
            self._sync_expressions_with_design()
            
            # 第一步：场景渲染
            logger.info("   🎨 开始渲染场景背景...")
            locations = [scene['name'] for scene in self.game_design.get('scenes', [])]
            self.artist.generate_all_backgrounds(
                locations,
                story_background=self.game_design.get('background'),
                art_style=self.game_design.get('art_style')
            )
            
            # 第二步：角色立绘渲染
            logger.info("   👥 开始渲染全人物表情立绘...")
            self._generate_character_assets()
            
            # 第三步：标题画面
            logger.info("\n【生成封面】")
            character_ref_images = []
            for char_info in self.game_design.get('characters', []):
                char_id = char_info.get('id', char_info.get('name'))
                char_dir = os.path.join(PathConfig.CHARACTERS_DIR, char_id)
                if os.path.exists(char_dir):
                    neutral_path = os.path.join(char_dir, "neutral.png")
                    if os.path.exists(neutral_path):
                        character_ref_images.append(neutral_path)
                    else:
                        try:
                            files = [f for f in os.listdir(char_dir) if f.endswith('.png')]
                            if files:
                                character_ref_images.append(os.path.join(char_dir, files[0]))
                        except OSError:
                            pass

            self.artist.generate_title_image(
                title=self.game_design.get('title', 'My Visual Novel'),
                background_desc=self.game_design.get('background', 'A romantic story'),
                character_images=character_ref_images
            )
            
            logger.info("\n" + "="*60)
            logger.info("🎉 游戏制作全流程彻底完成！进入 play 模式即可游玩。")
            return True
            
        except Exception as e:
            logger.error(f"❌ 渲染阶段失败: {e}", exc_info=True)
            raise

    def _generate_expression_with_critique(
        self, 
        actor: ActorAgent, 
        expression: str, 
        reference_image_path: Optional[str] = None,
        additional_feedback: str = ""
    ) -> Optional[str]:
        """
        生成单个表情立绘并进行审核循环
        
        Args:
            actor: 演员 Agent
            expression: 表情名称
            reference_image_path: 参考图路径 (通常是 neutral 表情)
            additional_feedback: 额外的描述信息 (如演员对表情的描述)
            
        Returns:
            生成成功则返回图片路径，否则返回 None
        """
        max_retries = 3
        current_try = 0
        feedback = additional_feedback
        previous_attempt_path = None  # 保存上一次生成的图片路径
        
        while current_try < max_retries:
            logger.info(f"      🖼️  生成表情 [{expression}] (尝试 {current_try + 1}/{max_retries})...")
            
            # 准备参考图列表：
            # 1. 始终包含最基础的参考图 (通常是 neutral) 作为正面锚点
            # 2. 如果之前有重试失败的图，也一并传入作为上下文参考 (帮助 AI 理解哪里需要改)
            ref_paths = []
            if reference_image_path:
                ref_paths.append(reference_image_path)
            if previous_attempt_path:
                ref_paths.append(previous_attempt_path)
            
            # 生成图片
            generated_paths = self.artist.generate_character_images(
                character=actor.character_info,
                expressions=[expression],
                feedback=feedback,
                reference_image_paths=ref_paths if ref_paths else None,
                story_background=self.game_design.get('background'),
                art_style=self.game_design.get('art_style')
            )
            
            image_path = generated_paths.get(expression)
            if not image_path:
                logger.warning(f"      ❌ 图片生成失败")
                return None
                
            # 审核图片
            critique_result = actor.critique_visual(
                image_path=image_path, 
                expression=expression,
                reference_image_path=reference_image_path,  # 审核时仍用neutral作为参考
                story_background=self.game_design.get('background'),
                art_style=self.game_design.get('art_style')
            )
            
            if critique_result == "PASS":
                logger.info(f"      ✅ 审核通过: {expression}")
                return image_path
            else:
                logger.warning(f"      ⚠️  审核未通过: {critique_result[:100]}...")
                
                # 存档不合格图片及元数据到 image_log 文件夹 (供论文分析使用)
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_name = f"FAILED_{timestamp}_{actor.name}_{expression}"
                    
                    # 1. 存档图片
                    fail_path = os.path.join(PathConfig.IMAGE_LOG_DIR, f"{base_name}.png")
                    shutil.copy2(image_path, fail_path)
                    
                    # 2. 存档元数据 (角色信息、反馈等)
                    meta_path = os.path.join(PathConfig.IMAGE_LOG_DIR, f"{base_name}.json")
                    meta_data = {
                        "timestamp": timestamp,
                        "character": actor.character_info,
                        "expression": expression,
                        "prompt_feedback": feedback,     # 本轮生成时使用的反馈
                        "critique_result": critique_result, # 审核员给出的拒绝理由
                        "try_count": current_try + 1
                    }
                    with open(meta_path, 'w', encoding='utf-8') as f:
                        json.dump(meta_data, f, ensure_ascii=False, indent=4)
                        
                    logger.info(f"      📤 已将不合格样本存档至: {PathConfig.IMAGE_LOG_DIR}")
                    previous_attempt_path = fail_path # 作为下一轮的反面参考
                except Exception as e:
                    logger.warning(f"      ⚠️  存档失败: {e}")
                    previous_attempt_path = image_path
                
                current_try += 1
                
                # 合并审核意见到下一轮反馈
                if additional_feedback:
                    feedback = f"{additional_feedback}\n\nPrevious critique: {critique_result}"
                else:
                    feedback = critique_result
                
                # 达到最大重试次数，保留最后一次生成的图片
                if current_try >= max_retries:
                    logger.warning(f"      ⚠️  达到最大重试次数，保留最后一次生成的图片用于游戏")
                    return image_path
        
        return None
        
        return None



    def _generate_character_assets(self):
        """
        生成所有角色立绘资源（带审核循环）
        策略：
        1. 先生成所有角色的 neutral（主角优先作为风格参考，其他角色以主角为参考）
        2. 再生成所有其他表情（使用各自的 neutral 作为参考）
        """
        logger.info("🎨 生成角色立绘资源...")
        
        # 第一步：生成所有角色的 neutral 表情
        logger.info("   📋 第一阶段：生成所有角色的 neutral 表情")
        
        style_reference_image = None
        
        # 优先生成主角 neutral 作为全局风格基准
        for char_name, actor in self.actors.items():
            if actor.character_info.get('is_protagonist', False):
                logger.info(f"      🌟 生成主角 {char_name} 的 neutral...")
                
                char_id = actor.character_info.get('id', actor.name)
                char_dir = os.path.join(PathConfig.CHARACTERS_DIR, char_id)
                neutral_path = os.path.join(char_dir, "neutral.png")
                
                if os.path.exists(neutral_path):
                    logger.info(f"         ✅ 已存在，将作为全局风格参考")
                    style_reference_image = neutral_path
                else:
                    logger.info(f"         🎨 生成中...")
                    neutral_path = self._generate_expression_with_critique(
                        actor=actor,
                        expression="neutral",
                        reference_image_path=None,
                        additional_feedback=""
                    )
                    if neutral_path:
                        style_reference_image = neutral_path
                        logger.info(f"         ✅ 生成完成，将作为全局风格参考")
                    else:
                        logger.error(f"         ❌ 生成失败（API 调用失败）")
                
                break
        
        if not style_reference_image:
            logger.warning("      ⚠️  主角 neutral 不存在，其他角色将独立生成")
        
        # 生成其他角色的 neutral
        for char_name, actor in self.actors.items():
            if actor.character_info.get('is_protagonist', False):
                continue  # 主角已处理
            
            logger.info(f"      👤 生成角色 {char_name} 的 neutral...")
            
            char_id = actor.character_info.get('id', actor.name)
            char_dir = os.path.join(PathConfig.CHARACTERS_DIR, char_id)
            neutral_path = os.path.join(char_dir, "neutral.png")
            
            if os.path.exists(neutral_path):
                logger.info(f"         ✅ 已存在")
            else:
                logger.info(f"         🎨 生成中...")
                neutral_path = self._generate_expression_with_critique(
                    actor=actor,
                    expression="neutral",
                    # 传主角 neutral 统一画风，但通过反馈约束避免复制主角脸
                    reference_image_path=style_reference_image,
                    additional_feedback=(
                        "Match the art style of the protagonist reference image, "
                        "but keep this character's own facial structure, hairstyle, and identity. "
                        "Do not copy the protagonist's face."
                    ) if style_reference_image else ""
                )
                
                if neutral_path:
                    logger.info(f"         ✅ 生成完成")
                else:
                    logger.error(f"         ❌ 生成失败（API 调用失败）")
        
        # 第二步：生成所有其他表情
        logger.info("   📋 第二阶段：生成所有其他表情")
        
        for char_name, actor in self.actors.items():
            char_id = actor.character_info.get('id', actor.name)
            char_dir = os.path.join(PathConfig.CHARACTERS_DIR, char_id)
            
            # 获取该角色所有注册的表情
            expressions = self._get_character_expressions(char_name)
            
            # 获取 neutral 作为参考
            neutral_path = os.path.join(char_dir, "neutral.png")
            ref_path = neutral_path if os.path.exists(neutral_path) else None
            
            # 过滤出非 neutral 的表情
            other_expressions = [e for e in expressions if e != "neutral"]
            
            if not other_expressions:
                continue
            
            logger.info(f"      👤 生成角色 {char_name} 的其他表情: {other_expressions}")
            
            for expr in other_expressions:
                # 检查文件是否存在
                img_path = os.path.join(char_dir, f"{expr}.png")
                if os.path.exists(img_path):
                    logger.info(f"         ✓ {expr} 已存在")
                    continue
                
                logger.info(f"         🎨 生成 {expr}...")
                
                # 让 Actor 描述这个表情
                description = actor.generate_expression_description(expr)
                additional_feedback = f"Expression description: {description}"
                
                # 使用审核循环生成
                result_path = self._generate_expression_with_critique(
                    actor=actor,
                    expression=expr,
                    reference_image_path=ref_path,
                    additional_feedback=additional_feedback
                )
                
                if result_path:
                    logger.info(f"         ✅ {expr} 生成完成")
                else:
                    logger.error(f"         ❌ {expr} 生成失败")

    def _scan_story_for_expressions(self):
        """
        扫描 story.txt 文件，提取所有角色表情标签并更新表情库
        确保剧本中实际使用的所有表情都被记录
        """
        logger.info("📖 扫描剧本文件，检测表情使用情况...")
        
        story_path = PathConfig.STORY_FILE
        if not os.path.exists(story_path):
            logger.warning("   ⚠️ story.txt 文件不存在，跳过扫描")
            return
        
        try:
            with open(story_path, 'r', encoding='utf-8') as f:
                story_content = f.read()
            
            # 提取所有 <image id="角色名">表情</image> 标签
            # 正则匹配：支持中文角色名
            import re
            pattern = r'<image\s+id="([^"]+)">([^<]+)</image>'
            matches = re.findall(pattern, story_content)
            
            if not matches:
                logger.info("   ℹ️ 剧本中没有找到角色表情标签")
                return
            
            # 统计每个角色使用的表情
            character_expressions_in_story = {}
            for char_name, expression in matches:
                char_name = char_name.strip()
                expression = expression.strip()
                
                if char_name not in character_expressions_in_story:
                    character_expressions_in_story[char_name] = set()
                character_expressions_in_story[char_name].add(expression)
            
            # 更新表情库
            updated_count = 0
            for char_name, expressions in character_expressions_in_story.items():
                # 检查该角色是否存在于演员列表中
                if char_name not in self.actors:
                    logger.warning(f"   ⚠️ 剧本中出现未知角色: {char_name}，跳过")
                    continue
                
                # 添加新表情
                added = self._add_expressions_to_character(char_name, list(expressions))
                if added:
                    logger.info(f"   ✨ 角色 {char_name} 新增表情: {added}")
                    updated_count += len(added)
            
            if updated_count > 0:
                logger.info(f"   ✅ 表情库已更新，新增 {updated_count} 个表情")
            else:
                logger.info("   ✅ 表情库已是最新，无需更新")
                
        except Exception as e:
            logger.error(f"   ❌ 扫描剧本失败: {e}")

    def _generate_full_story(self):
        """生成完整的故事（支持树和DAG结构）"""
        try:
            story_graph = StoryGraph(self.game_design)

            is_valid, error_msg = story_graph.validate()
            if not is_valid:
                logger.error(f"❌ 故事图验证失败: {error_msg}")
                return

            node_order = story_graph.topological_sort()
            logger.info(f"📋 故事图包含 {len(node_order)} 个节点")

            layers = self._build_topological_layers(story_graph, node_order)
            node_summaries: Dict[str, str] = {}

            generated_count = 0
            for layer_idx, layer_nodes in enumerate(layers, 1):
                logger.info(f"\n🚦 [层 {layer_idx}/{len(layers)}] 节点: {layer_nodes}")

                nodes_to_generate: List[str] = []
                for node_id in layer_nodes:
                    node_content = self._extract_node_story(node_id)
                    if node_content:
                        logger.info(f"   ⏭️ 节点剧情已存在，跳过生成: {node_id}")
                        if node_id not in node_summaries:
                            node_summaries[node_id] = self.writer.summarize_story(node_content)
                        continue
                    nodes_to_generate.append(node_id)

                if not nodes_to_generate:
                    continue

                layer_inputs = dict(node_summaries)
                layer_outputs: Dict[str, str] = {}
                max_workers = min(4, len(nodes_to_generate))

                if max_workers == 1:
                    node_id = nodes_to_generate[0]
                    node_info = story_graph.get_node(node_id)
                    layer_outputs[node_id] = self._generate_node_script(
                        node_id=node_id,
                        node_info=node_info,
                        story_graph=story_graph,
                        node_summaries=layer_inputs
                    )
                else:
                    logger.info(f"   ⚡ 同层并行生成: {len(nodes_to_generate)} 个节点 (workers={max_workers})")
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {
                            executor.submit(
                                self._generate_node_script,
                                node_id,
                                story_graph.get_node(node_id),
                                story_graph,
                                layer_inputs
                            ): node_id
                            for node_id in nodes_to_generate
                        }
                        for future in as_completed(futures):
                            node_id = futures[future]
                            try:
                                layer_outputs[node_id] = future.result()
                            except Exception as ex:
                                logger.error(f"❌ 节点 {node_id} 并行生成失败: {ex}", exc_info=True)

                for node_id in nodes_to_generate:
                    if node_id not in layer_outputs:
                        continue

                    polished_script = layer_outputs[node_id]
                    self._save_node_story(node_id, polished_script)
                    saved_node_content = self._extract_node_story(node_id)
                    if saved_node_content:
                        node_summaries[node_id] = self.writer.summarize_story(saved_node_content)
                    else:
                        logger.warning(f"⚠️ 节点 {node_id} 保存后未能从 story.txt 截取到内容，回退使用内存文本")
                        node_summaries[node_id] = self.writer.summarize_story(polished_script)

                    generated_count += 1
                    logger.info(f"✅ 节点 {node_id} 剧情生成完成")

            logger.info(f"\n🎉 完整故事生成完成！本次新生成节点数: {generated_count}")
            
        except Exception as e:
            logger.error(f"❌ 故事生成失败: {e}", exc_info=True)

    def _build_topological_layers(self, story_graph: 'StoryGraph', node_order: List[str]) -> List[List[str]]:
        """将 DAG 按拓扑层切分：同层可并行，层间保持依赖顺序。"""
        order_index = {node_id: idx for idx, node_id in enumerate(node_order)}
        indegree = {node_id: len(story_graph.get_parents(node_id)) for node_id in node_order}
        current_layer = sorted([node_id for node_id, degree in indegree.items() if degree == 0], key=order_index.get)

        layers: List[List[str]] = []
        while current_layer:
            layers.append(current_layer)
            next_layer: List[str] = []

            for node_id in current_layer:
                for child_id, _ in story_graph.get_children(node_id):
                    if child_id not in indegree:
                        continue
                    indegree[child_id] -= 1
                    if indegree[child_id] == 0:
                        next_layer.append(child_id)

            current_layer = sorted(next_layer, key=order_index.get)

        return layers

    def _generate_node_script(
        self,
        node_id: str,
        node_info: Dict[str, Any],
        story_graph: 'StoryGraph',
        node_summaries: Dict[str, str]
    ) -> str:
        """生成单个节点剧本（不落盘）。"""
        logger.info(f"\n📅 正在制作节点: {node_id}")

        parents = story_graph.get_parents(node_id)
        long_term_memory = self._build_long_term_memory(node_id, story_graph, node_summaries)

        short_term_memory = ""
        if parents:
            if len(parents) > 1:
                parent_summaries = [
                    f"【路径{i + 1}】{node_summaries.get(parent_id, '(无摘要)')}"
                    for i, parent_id in enumerate(parents)
                    if parent_id in node_summaries
                ]
                short_term_memory = "多条剧情路径在此汇合，请基于公共记忆继续故事：\n" + "\n".join(parent_summaries)
            else:
                parent_contents = []
                for parent_id in parents:
                    parent_content = self._extract_node_story(parent_id)
                    if parent_content:
                        parent_contents.append(parent_content)
                short_term_memory = "\n\n".join(parent_contents)

        if short_term_memory:
            full_context = f"{long_term_memory}\n\n【最近剧情】:\n{short_term_memory}"
        else:
            full_context = long_term_memory

        plot_summary = node_info.get('summary', '')
        present_actors = list(self.actors.items())
        if not present_actors:
            return plot_summary

        available_scenes = [scene['name'] for scene in self.game_design.get('scenes', [])]
        available_characters = self.game_design.get('characters', [])

        plots = self.writer.split_node_into_plots(
            node_summary=plot_summary,
            long_term_memory=long_term_memory,
            available_scenes=available_scenes,
            available_characters=available_characters,
            segment_count=DesignerConfig.PLOT_SEGMENTS_PER_NODE
        )

        if not plots:
            logger.warning(f"⚠️ 节点 {node_id} 剧情切分失败，使用原始概要")
            plots = [{"id": 1, "summary": plot_summary}]

        logger.info(f"✅ 节点 {node_id} 已切分为 {len(plots)} 个片段")

        all_plot_contexts = []
        performance_log_path = os.path.join(PathConfig.TEXT_LOG_DIR, f"performance_{node_id}.jsonl")
        if os.path.exists(performance_log_path):
            os.remove(performance_log_path)

        for plot_idx, plot_info in enumerate(plots, 1):
            plot_id = plot_info.get('id', plot_idx)
            current_plot_summary = plot_info.get('summary', plot_summary)

            plot_current_context = ""
            turn_count = 0
            safety_limit = 50
            speaker_retry_count = 0
            max_speaker_retries = 3

            previous_plots_context = "\n\n".join(all_plot_contexts) if all_plot_contexts else ""
            plot_full_context = full_context
            if previous_plots_context:
                plot_full_context += f"\n\n【前面的片段】:\n{previous_plots_context}"

            while turn_count < safety_limit:
                current_total_context = f"{plot_full_context}\n\n【当前片段对话】:\n{plot_current_context}"

                present_char_info = [actor.character_info for _, actor in present_actors]
                next_speaker_name, plot_guidance = self.writer.decide_next_speaker(
                    plot_summary=current_plot_summary,
                    characters=present_char_info,
                    story_context=current_total_context
                )

                if "STOP" in next_speaker_name:
                    break

                next_actor = None
                next_char_name = ""
                for name, agent in present_actors:
                    if name in next_speaker_name or next_speaker_name in name:
                        next_actor = agent
                        next_char_name = name
                        break

                if not next_actor:
                    speaker_retry_count += 1
                    if speaker_retry_count < max_speaker_retries:
                        continue
                    break

                speaker_retry_count = 0
                other_chars = [
                    actor.character_info for char_name, actor in present_actors
                    if char_name != next_char_name
                ]
                available_expressions = self._get_expressions_str(next_char_name)

                enhanced_plot_summary = current_plot_summary
                if plot_guidance:
                    enhanced_plot_summary += f"\n【导演指导】{plot_guidance}"

                performance = next_actor.perform_plot(
                    plot_summary=enhanced_plot_summary,
                    other_characters=other_chars,
                    story_context=current_total_context,
                    character_expressions=available_expressions
                )

                self._log_performance(performance_log_path, {
                    "node_id": node_id,
                    "plot_id": plot_id,
                    "character": next_char_name,
                    "content": performance
                })

                if performance.strip():
                    plot_current_context += f"{performance}\n"
                    self._update_character_expressions(next_char_name, performance)
                    turn_count += 1
                else:
                    break

            all_plot_contexts.append(plot_current_context)

        current_context = "\n\n".join(all_plot_contexts)
        children = story_graph.get_children(node_id)
        choices_data = []
        if len(children) > 1:
            choices_data = [{"target": child_id, "text": choice_text} for child_id, choice_text in children]

        polished_script = self.writer.synthesize_script(
            plot_performances=[{"content": current_context}],
            choices=choices_data,
            story_context=full_context,
            available_scenes=available_scenes,
            available_characters=available_characters
        )

        if len(children) == 1:
            next_node_id, _ = children[0]
            jump_tag = f"<jump target=\"{next_node_id}\"/>"
            if jump_tag not in polished_script:
                polished_script = polished_script.rstrip() + f"\n\n{jump_tag}\n"

        return polished_script

    def load_existing_game(self) -> bool:
        """加载已存在的游戏数据"""
        try:
            # 如果 producer 还没初始化，先尝试加载
            if not self.producer:
                self.producer = ProducerAgent()
                
            self.game_design = self.producer.load_game_design()
            if not self.game_design:
                return False
                
            # 初始化演员
            self._initialize_actors()
            
            return True
        except Exception as e:
            logger.error(f"❌ 加载游戏失败: {e}")
            return False

    def _load_expressions(self) -> Dict[str, List[str]]:
        """加载现有的表情库"""
        expr_file = os.path.join(PathConfig.DATA_DIR, "character_expressions.json")
        if os.path.exists(expr_file):
            try:
                with open(expr_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ 加载表情库失败: {e}，创建新库")
                return {}
        return {}

    def _save_expressions(self):
        """保存表情库到文件"""
        expr_file = os.path.join(PathConfig.DATA_DIR, "character_expressions.json")
        try:
            with self._expressions_lock:
                with open(expr_file, 'w', encoding='utf-8') as f:
                    json.dump(self.expressions_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存表情库失败: {e}")

    def _get_character_expressions(self, character_name: str) -> List[str]:
        """获取角色的现有表情库"""
        return self.expressions_db.get(character_name, [])
    
    def _add_expressions_to_character(self, character_name: str, expressions: List[str]) -> List[str]:
        """
        添加表情到角色表情库
        
        Args:
            character_name: 角色名
            expressions: 要添加的表情列表
            
        Returns:
            新增的表情列表
        """
        with self._expressions_lock:
            current_expressions = set(self._get_character_expressions(character_name))
            new_expressions = [expr for expr in expressions if expr not in current_expressions]

            if new_expressions:
                if character_name not in self.expressions_db:
                    self.expressions_db[character_name] = []

                self.expressions_db[character_name].extend(new_expressions)
                self.expressions_db[character_name] = list(set(self.expressions_db[character_name]))  # 去重

            if not new_expressions:
                return []

        self._save_expressions()
        return new_expressions

    def _update_character_expressions(self, character_name: str, text: str) -> List[str]:
        """从文本中提取表情标签，更新该角色的表情库"""
        # 提取所有 <image id="name">expression</image> 标签
        pattern = rf'<image\s+id="{re.escape(character_name)}">([^<]+)</image>'
        extracted_expressions = list(set(re.findall(pattern, text)))
        
        if not extracted_expressions:
            return []
        
        added = self._add_expressions_to_character(character_name, extracted_expressions)
        if added:
            logger.info(f"✨ 角色 {character_name} 新增表情: {added}")
        return added

    def _initialize_character_expressions(self, character_name: str):
        """初始化角色的表情库"""
        if character_name not in self.expressions_db:
            from agents.config import STANDARD_EXPRESSIONS
            initial_expressions = STANDARD_EXPRESSIONS.copy()
            self.expressions_db[character_name] = initial_expressions
            self._save_expressions()
            logger.info(f"✅ 初始化角色 {character_name} 的表情库: {initial_expressions}")

    def _get_expressions_str(self, character_name: str) -> str:
        """获取角色表情库的字符串表示"""
        expressions = self._get_character_expressions(character_name)
        if not expressions:
            return "neutral, happy, sad, angry, surprised, shy"
        return ", ".join(expressions)

    def _sync_expressions_with_design(self):
        """确保表情库与当前游戏设计同步"""
        if not self.game_design:
            return
            
        current_character_names = set(c.get('name') for c in self.game_design.get('characters', []) if c.get('name'))
        existing_character_names = set(self.expressions_db.keys())
        
        # 找出需要删除的角色
        to_remove = existing_character_names - current_character_names
        
        if to_remove:
            logger.info(f"🧹 同步表情库：删除旧角色 {list(to_remove)}")
            for name in to_remove:
                del self.expressions_db[name]
            self._save_expressions()

    def _build_long_term_memory(
        self, 
        node_id: str, 
        story_graph: 'StoryGraph', 
        node_summaries: Dict[str, str]
    ) -> str:
        """
        构建长期上下文（祖先节点的摘要）
        
        对于汇合点：只使用公共祖先，避免互斥路径的混淆
        
        Args:
            node_id: 当前节点ID
            story_graph: 故事图对象
            node_summaries: 节点摘要缓存
            
        Returns:
            上下文文本
        """
        parents = story_graph.get_parents(node_id)
        
        # 如果是汇合点（多个父节点）
        if len(parents) > 1:
            # 找到所有父节点的公共祖先
            ancestor_sets = []
            for parent in parents:
                ancestors = self._get_ancestors(parent, story_graph)
                ancestor_sets.append(ancestors)
            
            # 取交集 - 只使用所有路径都经过的节点
            if ancestor_sets:
                common_ancestors = set.intersection(*ancestor_sets)
            else:
                common_ancestors = set()
            
            # 构建上下文（按ID排序）
            context_parts = []
            for ancestor_id in sorted(common_ancestors):
                if ancestor_id in node_summaries:
                    context_parts.append(f"Node {ancestor_id}: {node_summaries[ancestor_id]}")
            
            if context_parts:
                return "\n".join(context_parts)
            else:
                return "故事开始（多条路径在此汇合）。"
        
        # 普通节点：使用所有祖先
        else:
            ancestors = set()
            queue = parents.copy()
            
            while queue:
                parent = queue.pop(0)
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.extend(story_graph.get_parents(parent))
            
            # 构建上下文
            context_parts = []
            for ancestor_id in sorted(ancestors):
                if ancestor_id in node_summaries:
                    context_parts.append(f"Node {ancestor_id}: {node_summaries[ancestor_id]}")
            
            return "\n".join(context_parts) if context_parts else "游戏开始。"
    
    def _get_ancestors(self, node_id: str, story_graph: 'StoryGraph') -> set:
        """获取节点的所有祖先（BFS）"""
        ancestors = set()
        queue = [node_id]
        
        while queue:
            current = queue.pop(0)
            if current not in ancestors:
                ancestors.add(current)
                queue.extend(story_graph.get_parents(current))
        
        return ancestors

    def _extract_node_story(self, node_id: str) -> str:
        """从 story.txt 中按 node_id 截取该节点剧情正文。"""
        story_path = Path(PathConfig.STORY_FILE)
        if not story_path.exists():
            return ""

        try:
            with open(story_path, 'r', encoding='utf-8') as f:
                content = f.read()

            pattern = rf"=== Node: {re.escape(node_id)} ===(.*?)(=== Node|$)"
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                return ""

            return match.group(1).strip()
        except Exception as e:
            logger.warning(f"⚠️ 截取节点 {node_id} 剧情失败: {e}")
            return ""
    
    def _save_node_story(self, node_id: str, content: str):
        """
        保存节点剧情到文件
        
        Args:
            node_id: 节点ID
            content: 剧情内容
        """
        story_path = Path(PathConfig.STORY_FILE)
        with self._story_file_lock:
            with open(story_path, 'a', encoding='utf-8') as f:
                f.write(f"\n=== Node: {node_id} ===\n")
                f.write(content)
                f.write("\n")
    
    def _append_choices_to_story(self, node_id: str, children: List[tuple]):
        """
        在剧情文件中添加选项
        
        Args:
            node_id: 当前节点ID
            children: [(child_id, choice_text), ...]
        """
        story_path = Path(PathConfig.STORY_FILE)
        with open(story_path, 'a', encoding='utf-8') as f:
            f.write("\n[CHOICES]\n")
            for idx, (child_id, choice_text) in enumerate(children, 1):
                if choice_text:
                    f.write(f'<choice target="{child_id}">{choice_text}</choice>\n')
                else:
                    # 没有明确选项文本，生成默认选项（通常不应该出现在多选场景）
                    default_text = f"选项{idx}"
                    logger.warning(f"⚠️ 节点 {node_id} 的子节点 {child_id} 缺少 choice_text，使用默认值: {default_text}")
                    f.write(f'<choice target="{child_id}">{default_text}</choice>\n')
            f.write("\n")
    

    def _log_performance(self, log_path: str, data: dict):
        """
        记录表演过程到 JSONL 文件
        
        Args:
            log_path: 日志文件路径
            data: 要记录的数据字典
        """
        try:
            import json
            from datetime import datetime
            
            # 添加简洁时间戳（HH:MM:SS格式）
            data['timestamp'] = datetime.now().strftime("%H:%M:%S")
            
            # 追加到 jsonl 文件
            with self._performance_log_lock:
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(data, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f"⚠️ 记录表演日志失败: {e}")
    
    def _character_mentioned_in(self, char_name: str, text: str) -> bool:
        """判断角色是否在文本中被提及"""
        return char_name in text or char_name.lower() in text.lower()
