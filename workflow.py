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
from typing import Dict, Any, Optional, List, Callable, Set, Tuple
import time
from pathlib import Path
import re
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.producer_agent import ProducerAgent
from agents.designer_agent import DesignerAgent, CLOSED_ENDING_COMPLETION_CONDITIONS
from agents.artist_agent import ArtistAgent
from agents.writer_agent import WriterAgent
from agents.actor_agent import ActorAgent
from agents.config import PathConfig, DesignerConfig, WriterConfig
from agents.story_graph import StoryGraph
from agents.memory import MemoryManager, default_hash_embedding
from game_engine.data import StoryParser

# 常量定义
logger = logging.getLogger(__name__)


def _is_valid_expression_name(value: Any) -> bool:
    """Reject partial/markup-tainted expression names left by draft generation."""
    return bool(re.fullmatch(r"[\w-]{2,40}", str(value).strip(), flags=re.UNICODE))


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
        self.world_memory = MemoryManager(name="writer_world", short_term_capacity=2)
        
        self.game_design = None
        
        logger.info("🎮 工作流控制器初始化")

    def _writer_embedding_with_fallback(self, text: str):
        """优先使用 Writer 对应 Provider 的 embedding，失败则回退哈希 embedding。"""
        try:
            if self.writer and self.writer.llm_client:
                embedding = self.writer.llm_client.get_embedding(text)
                if embedding:
                    return embedding
        except Exception:
            pass
        return default_hash_embedding(text)
    
    def initialize_agents(
        self,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        include_artist: bool = True,
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
            
            if include_artist:
                logger.info("   🎨 初始化美术 Agent...")
                self.artist = ArtistAgent(api_key=openai_api_key, base_url=openai_base_url)
            
            # 初始化编剧 Agent
            logger.info("   ✍️  初始化编剧 Agent...")
            self.writer = WriterAgent(api_key=openai_api_key, base_url=openai_base_url)
            self.world_memory = MemoryManager(
                name="writer_world",
                short_term_capacity=2,
                embedding_fn=self._writer_embedding_with_fallback,
            )
            
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
            raise RuntimeError("未找到游戏设计文档，请先运行设计阶段")
            
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
            raise RuntimeError("未找到游戏设计文档，请先运行设计阶段")
            
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

            # 第三步：剧情 CG（由 Writer 决定，相关 Actor 审核）
            logger.info("   🎞️ 开始渲染剧情 CG...")
            self._generate_cg_assets()
            
            # 第四步：标题画面
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

            self._validate_render_assets()
            
            logger.info("\n" + "="*60)
            logger.info("🎉 游戏制作全流程彻底完成！进入 play 模式即可游玩。")
            return True
            
        except Exception as e:
            logger.error(f"❌ 渲染阶段失败: {e}", exc_info=True)
            raise

    def _validate_render_assets(self) -> None:
        """Reject incomplete or corrupt assets before reporting render success."""
        from PIL import Image

        expected = {Path(PathConfig.IMAGES_DIR) / "title_screen.png"}
        for scene in self.game_design.get("scenes", []):
            name = re.sub(r'[^\w\s-]', '', scene["name"]).strip().replace(' ', '_')
            expected.add(Path(PathConfig.BACKGROUNDS_DIR) / f"{name}.png")
        for character in self.game_design.get("characters", []):
            character_id = character.get("id", character["name"])
            expressions = {"neutral", *self._get_character_expressions(character["name"])}
            for expression in expressions:
                expected.add(Path(PathConfig.CHARACTERS_DIR) / character_id / f"{expression}.png")
        for cg in self._load_cg_manifest():
            expected.add(Path(PathConfig.CG_DIR) / f"{cg['id']}.png")

        invalid = []
        for path in sorted(expected):
            try:
                with Image.open(path) as image:
                    image.verify()
            except (OSError, SyntaxError):
                invalid.append(str(path.relative_to(PathConfig.IMAGES_DIR)))
        if invalid:
            raise RuntimeError("资产渲染未完成，缺失或损坏: " + ", ".join(invalid))

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

    def _generate_cg_assets(self) -> Dict[str, str]:
        """Generate Writer-planned CGs and let every depicted Actor review them."""
        cgs = self._load_cg_manifest()
        if not cgs:
            logger.info("   ℹ️ Writer 没有为当前剧情安排 CG")
            return {}
        if not self.artist:
            raise RuntimeError("Artist 尚未初始化，无法生成 CG")

        characters = {
            str(character.get("id", "")).strip(): character
            for character in self.game_design.get("characters", [])
            if isinstance(character, dict) and str(character.get("id", "")).strip()
        }
        actors_by_id = {
            str(actor.character_info.get("id", "")).strip(): actor
            for actor in self.actors.values()
            if str(actor.character_info.get("id", "")).strip()
        }
        generated: Dict[str, str] = {}
        for cg in cgs:
            cg_id = str(cg.get("id", "")).strip()
            existing = Path(PathConfig.CG_DIR) / f"{cg_id}.png"
            if existing.is_file():
                logger.info(f"   ⏭️ CG 已存在，保留并跳过审核: {cg_id}")
                generated[cg_id] = str(existing)
                continue
            character_ids = [
                str(character_id).strip()
                for character_id in cg.get("characters", [])
                if str(character_id).strip() in characters
            ]
            cg_characters = [characters[character_id] for character_id in character_ids]
            reference_paths = []
            reference_by_id = {}
            for character_id in character_ids:
                neutral = Path(PathConfig.CHARACTERS_DIR) / character_id / "neutral.png"
                if neutral.exists():
                    reference_paths.append(str(neutral))
                    reference_by_id[character_id] = str(neutral)

            feedback = ""
            feedback_history: List[str] = []
            image_path = None
            for attempt in range(3):
                image_path = self.artist.generate_cg(
                    cg=cg,
                    characters=cg_characters,
                    reference_image_paths=reference_paths or None,
                    story_background=self.game_design.get("background", ""),
                    art_style=self.game_design.get("art_style", ""),
                    feedback=feedback,
                )
                if not image_path:
                    logger.warning(f"   ⚠️ CG {cg_id} 第 {attempt + 1}/3 次生成失败")
                    continue

                actor_feedback = []
                for character_id in character_ids:
                    actor = actors_by_id.get(character_id)
                    if not actor:
                        logger.warning(f"   ⚠️ CG {cg_id} 找不到 Actor: {character_id}")
                        continue
                    critique = actor.critique_cg(
                        image_path=image_path,
                        cg=cg,
                        reference_image_path=reference_by_id.get(character_id),
                        story_background=self.game_design.get("background", ""),
                        art_style=self.game_design.get("art_style", ""),
                    )
                    if critique != "PASS":
                        actor_feedback.append(f"{actor.name}: {critique}")

                if not actor_feedback:
                    generated[cg_id] = image_path
                    logger.info(f"   ✅ CG {cg_id} 已通过全部相关 Actor 审核")
                    break
                feedback_history.extend(actor_feedback)
                # Preserve earlier corrections so a later redraw does not regress
                # details that a depicted Actor already asked the Artist to fix.
                feedback = "\n".join(dict.fromkeys(feedback_history))
                logger.warning(
                    f"   🔄 CG {cg_id} 需要重绘（{attempt + 1}/3）：{feedback[:240]}"
                )

            if image_path and cg_id not in generated:
                generated[cg_id] = image_path
                logger.warning(f"   ⚠️ CG {cg_id} 达到审核上限，保留最后一版")
        return generated



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
                raise ValueError(f"故事图验证失败: {error_msg}")

            node_order = story_graph.topological_sort()
            logger.info(f"📋 故事图包含 {len(node_order)} 个节点")

            layers = self._build_topological_layers(story_graph, node_order)
            self.world_memory = MemoryManager(
                name="writer_world",
                short_term_capacity=2,
                embedding_fn=self._writer_embedding_with_fallback,
            )
            cg_manifest = self._load_cg_manifest()

            generated_count = 0
            for layer_idx, layer_nodes in enumerate(layers, 1):
                logger.info(f"\n🚦 [层 {layer_idx}/{len(layers)}] 节点: {layer_nodes}")

                nodes_to_generate: List[str] = []
                for node_id in layer_nodes:
                    node_content = self._extract_node_story(node_id)
                    if node_content:
                        logger.info(f"   ⏭️ 节点剧情已存在，跳过生成: {node_id}")
                        self._register_node_memory(
                            node_id=node_id,
                            node_content=node_content,
                        )
                        continue
                    nodes_to_generate.append(node_id)

                if not nodes_to_generate:
                    continue

                layer_outputs: Dict[str, Dict[str, Any]] = {}
                max_workers = min(4, len(nodes_to_generate))

                if max_workers == 1:
                    node_id = nodes_to_generate[0]
                    node_info = story_graph.get_node(node_id)
                    layer_outputs[node_id] = self._generate_node_script(
                        node_id=node_id,
                        node_info=node_info,
                        story_graph=story_graph,
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

                    output_payload = layer_outputs[node_id]
                    polished_script = str(output_payload.get("script", ""))
                    if not polished_script.strip():
                        raise RuntimeError(f"节点 {node_id} 生成了空剧本")
                    self._save_node_story(node_id, polished_script)
                    cg_manifest = [
                        cg for cg in cg_manifest
                        if str(cg.get("node_id", "")) != node_id
                    ]
                    cg_manifest.extend(output_payload.get("cgs", []))
                    self._save_cg_manifest(cg_manifest)
                    saved_node_content = self._extract_node_story(node_id)

                    self._register_node_memory(
                        node_id=node_id,
                        node_content=saved_node_content or polished_script,
                    )

                    generated_count += 1
                    logger.info(f"✅ 节点 {node_id} 剧情生成完成")

                missing = [node_id for node_id in layer_nodes if not self._extract_node_story(node_id)]
                if missing:
                    raise RuntimeError("剧本生成未完成，缺失节点: " + ", ".join(missing))

            logger.info(f"\n🎉 完整故事生成完成！本次新生成节点数: {generated_count}")
            
        except Exception as e:
            logger.error(f"❌ 故事生成失败: {e}", exc_info=True)
            raise

    def run_rolling_story(
        self,
        requirements: str,
        character_count: int,
        node_count: int,
        locked_characters: Optional[List[Dict[str, Any]]] = None,
        ending_mode: str = "closed",
        max_revisions: int = 2,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """Generate a linear story with one verified goal per node."""
        if not self.producer or not self.designer or not self.writer:
            raise RuntimeError("Producer、Designer、Writer 尚未初始化")

        node_count = max(1, int(node_count))
        if ending_mode not in {"closed", "open"}:
            raise ValueError("ending_mode must be 'closed' or 'open'")
        max_revisions = max(0, int(max_revisions))
        checkpoint_path = (
            os.path.join(PathConfig.DATA_DIR, "rolling_state.json")
            if PathConfig.DATA_DIR else ""
        )
        checkpoint = None
        seed_core_gdd = None
        if resume and checkpoint_path and os.path.exists(checkpoint_path):
            with open(checkpoint_path, "r", encoding="utf-8") as handle:
                candidate = json.load(handle)
            if candidate.get("schema_version") == "rolling-state/3.2":
                checkpoint = candidate
            elif candidate.get("core_gdd", {}).get("schema_version") == "core-gdd/1.1":
                seed_core_gdd = dict(candidate["core_gdd"])

        if checkpoint:
            self._validate_rolling_checkpoint_for_resume(checkpoint, node_count)
            core_gdd = dict(checkpoint["core_gdd"])
            logger.info(
                f"♻️ 恢复滚动检查点：已提交 {len(checkpoint.get('scripts', {}))} 个节点"
            )
        else:
            if seed_core_gdd:
                core_gdd = seed_core_gdd
                logger.info("♻️ 仅复用旧检查点的 Core GDD，丢弃旧节点")
            else:
                logger.info("📚 Producer 正在生成 Core GDD（不含完整剧情）...")
                core_gdd = self.producer.generate_core_gdd(
                    requirements=requirements,
                    character_count=character_count,
                    locked_characters=locked_characters,
                )
        self.game_design = core_gdd
        self._initialize_actors()

        if checkpoint:
            world_state = dict(checkpoint.get("world_state", {}))
            agenda = dict(checkpoint.get("agenda", {}))
            goals = dict(checkpoint.get("goals", {}))
            reviews = dict(checkpoint.get("reviews", {}))
            summaries = dict(checkpoint.get("summaries", {}))
            scripts = dict(checkpoint.get("scripts", {}))
            performances = dict(checkpoint.get("performances", {}))
            graph = deepcopy(checkpoint.get("story_graph", {"nodes": {}, "edges": []}))
            start_index = len(scripts)
            previous_summaries = [summaries[node_id] for node_id in scripts if node_id in summaries]
            if start_index > node_count:
                raise ValueError(
                    f"检查点已有 {start_index} 个节点，超过目标数 {node_count}"
                )
            scripts, scripts_migrated = self._recompile_checkpoint_scripts(
                core_gdd=core_gdd,
                scripts=scripts,
                performances=performances,
                goals=goals,
            )
            if scripts_migrated:
                logger.info("🧹 已从 Actor 原始表演重新编译旧节点，保留原台词与跳转")
                self._persist_rolling_story(
                    core_gdd=core_gdd,
                    graph=graph,
                    scripts=scripts,
                    goals=goals,
                    reviews=reviews,
                    performances=performances,
                    summaries=summaries,
                    world_state=world_state,
                    agenda=agenda,
                )
        else:
            world_state = dict(core_gdd.get("initial_world_state", {}))
            agenda = dict(core_gdd.get("initial_agenda", {}))
            previous_summaries = []
            goals = {}
            reviews = {}
            summaries = {}
            scripts = {}
            performances = {}
            graph = {"nodes": {}, "edges": []}
            start_index = 0

        for index in range(start_index, node_count):
            node_id = "root" if index == 0 else f"node{index}"
            previous_script = next(reversed(scripts.values())) if scripts else ""
            previous_tail = self._extract_transition_source(previous_script)
            self._persist_rolling_pre_node_snapshot(
                node_id=node_id,
                core_gdd=core_gdd,
                graph=graph,
                scripts=scripts,
                goals=goals,
                reviews=reviews,
                performances=performances,
                summaries=summaries,
                world_state=world_state,
                agenda=agenda,
            )
            retry_context = self._load_rolling_retry_context(node_id)
            retry_goal = retry_context.get("node_goal")
            if isinstance(retry_goal, dict) and retry_goal:
                node_goal = deepcopy(retry_goal)
                logger.info(f"♻️ 为 {node_id} 复用上一轮未提交的 NodeGoal")
            elif index == 0:
                node_goal = self.designer.plan_initial_goal(
                    core_gdd=core_gdd,
                    total_nodes=node_count,
                    ending_mode=ending_mode,
                )
            else:
                node_goal = self.designer.plan_next_goal(
                    core_gdd=core_gdd,
                    world_state=world_state,
                    agenda=agenda,
                    previous_summaries=previous_summaries,
                    node_index=index,
                    total_nodes=node_count,
                    ending_mode=ending_mode,
                    previous_tail=previous_tail,
                )

            node_goal = self._ensure_transition_contract(
                node_goal=node_goal,
                previous_script=previous_script,
                is_root=index == 0,
            )
            if index > 0:
                previous_node_id = "root" if index == 1 else f"node{index - 1}"
                transition = node_goal["transition_contract"]
                for edge in graph.get("edges", []):
                    if edge.get("from") == previous_node_id and edge.get("to") == node_id:
                        edge["discourse_relation"] = transition["relation_to_previous"]
                        edge["source_anchor"] = transition["source_anchor"]
                        break

            self._persist_rolling_retry_context(
                node_id=node_id,
                node_goal=node_goal,
                feedback=list(retry_context.get("feedback", [])),
                review=dict(retry_context.get("review", {})),
                draft=str(retry_context.get("draft", "")),
                turns=list(retry_context.get("turns", [])),
                revision_index=int(retry_context.get("revision_index", -1)),
                status="revise",
            )

            logger.info(f"🎬 [滚动节点 {index + 1}/{node_count}] {node_goal.get('goal', '')}")
            goals[node_id] = node_goal
            graph["nodes"][node_id] = {
                "id": node_id,
                "summary": node_goal.get("goal", ""),
                "type": "normal",
                "generation_status": "pending",
            }

            review: Dict[str, Any] = {}
            actor_turns: List[Dict[str, Any]] = []
            producer_feedback: List[str] = list(retry_context.get("feedback", []))
            for revision_index in range(max_revisions + 1):
                scene_script, actor_turns = self._generate_actor_driven_node(
                    node_id=node_id,
                    core_gdd=core_gdd,
                    node_goal=node_goal,
                    world_state=world_state,
                    agenda=agenda,
                    previous_summaries=previous_summaries,
                    previous_node_ids=set(scripts),
                    previous_script=previous_script,
                    producer_feedback=producer_feedback,
                )
                review = self.producer.review_and_reduce_node(
                    core_gdd=core_gdd,
                    node_goal=node_goal,
                    draft=scene_script,
                    world_state=world_state,
                    agenda=agenda,
                    actor_performances=actor_turns,
                    node_index=index,
                    total_nodes=node_count,
                    ending_mode=ending_mode,
                    previous_script=previous_script,
                )
                self._persist_rolling_retry_context(
                    node_id=node_id,
                    node_goal=node_goal,
                    feedback=list(review.get("feedback", [])),
                    review=review,
                    draft=scene_script,
                    turns=actor_turns,
                    revision_index=revision_index,
                    status=(
                        "passed"
                        if review.get("decision") == "PASS"
                        and review.get("goal_completed") is True
                        else "revise"
                    ),
                )
                if review.get("decision") == "PASS" and review.get("goal_completed") is True:
                    break
                if revision_index >= max_revisions:
                    feedback = "; ".join(review.get("feedback", []))
                    raise RuntimeError(
                        f"Producer 在 {max_revisions + 1} 轮审核后仍驳回 {node_id}: {feedback}"
                    )
                logger.warning(
                    f"🔧 {node_id} 需要修订（{revision_index + 1}/{max_revisions}）"
                )
                producer_feedback = list(review.get("feedback", []))

            # Commit only after the Producer's fail-closed gate passes.
            world_state = self._apply_evidence_backed_updates(
                world_state,
                review.get("state_updates", []),
            )
            agenda = deepcopy(review.get("agenda", agenda))
            summary = str(review.get("summary", "")).strip()
            if not summary:
                raise ValueError(f"Producer 通过 {node_id} 但未返回摘要")
            previous_summaries.append(summary)
            reviews[node_id] = review
            performances[node_id] = actor_turns
            self._commit_actor_performances(
                node_id=node_id,
                turns=actor_turns,
                node_script=scene_script,
                node_goal=node_goal,
            )

            if index < node_count - 1:
                next_node_id = f"node{index + 1}"
                graph["edges"].append({"from": node_id, "to": next_node_id, "choice_text": None})
                scene_script = scene_script.rstrip() + f'\n\n<jump target="{next_node_id}"/>'

            scripts[node_id] = scene_script + "\n"
            summaries[node_id] = summary
            graph["nodes"][node_id]["summary"] = summary
            graph["nodes"][node_id]["generation_status"] = "completed"
            if hasattr(self, "world_memory"):
                self._register_node_memory(node_id=node_id, node_content=scene_script)
            self._persist_rolling_story(
                core_gdd=core_gdd,
                graph=graph,
                scripts=scripts,
                goals=goals,
                reviews=reviews,
                performances=performances,
                summaries=summaries,
                world_state=world_state,
                agenda=agenda,
            )

        logger.info(f"✅ 滚动故事生成完成，共 {node_count} 个节点")
        return {
            "core_gdd": core_gdd,
            "story_graph": graph,
            "scripts": scripts,
            "goals": goals,
            "contracts": goals,
            "reviews": reviews,
            "performances": performances,
            "summaries": summaries,
            "world_state": world_state,
            "agenda": agenda,
        }

    @staticmethod
    def _rolling_retry_path() -> str:
        if not PathConfig.DATA_DIR:
            return ""
        return os.path.join(PathConfig.DATA_DIR, "rolling_retry.json")

    @staticmethod
    def _rolling_pre_node_path() -> str:
        if not PathConfig.DATA_DIR:
            return ""
        return os.path.join(PathConfig.DATA_DIR, "rolling_pre_node.json")

    def _persist_rolling_pre_node_snapshot(
        self,
        *,
        node_id: str,
        core_gdd: Dict[str, Any],
        graph: Dict[str, Any],
        scripts: Dict[str, str],
        goals: Dict[str, Dict[str, Any]],
        reviews: Dict[str, Dict[str, Any]],
        performances: Dict[str, List[Dict[str, Any]]],
        summaries: Dict[str, str],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
    ) -> None:
        """Save the exact committed state before an uncommitted node begins."""
        path = self._rolling_pre_node_path()
        if not path:
            return
        self._save_json(
            path,
            {
                "schema_version": "rolling-pre-node/1.0",
                "next_node_id": node_id,
                "core_gdd": core_gdd,
                "story_graph": graph,
                "scripts": scripts,
                "goals": goals,
                "reviews": reviews,
                "performances": performances,
                "summaries": summaries,
                "world_state": world_state,
                "agenda": agenda,
            },
        )

    def _load_rolling_retry_context(self, node_id: str) -> Dict[str, Any]:
        """Reuse only the latest failed Producer feedback for the same uncommitted node."""
        path = self._rolling_retry_path()
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                retry = json.load(handle)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"⚠️ 无法读取滚动重试上下文，将忽略: {exc}")
            return {}
        if retry.get("node_id") != node_id or retry.get("status") != "revise":
            return {}
        feedback = retry.get("feedback", [])
        if not isinstance(feedback, list) or not all(isinstance(item, str) for item in feedback):
            return {}
        logger.info(f"♻️ 为 {node_id} 恢复 {len(feedback)} 条 Producer 驳回要求")
        return retry

    def _persist_rolling_retry_context(
        self,
        *,
        node_id: str,
        node_goal: Dict[str, Any],
        feedback: List[str],
        review: Dict[str, Any],
        draft: str,
        turns: List[Dict[str, Any]],
        revision_index: int,
        status: str,
    ) -> None:
        """Persist uncommitted attempt evidence without touching Actor memory."""
        path = self._rolling_retry_path()
        if not path:
            return
        self._save_json(
            path,
            {
                "schema_version": "rolling-retry/1.0",
                "node_id": node_id,
                "status": status,
                "revision_index": revision_index,
                "node_goal": node_goal,
                "feedback": feedback,
                "review": review,
                "draft": draft,
                "turns": turns,
            },
        )

    @staticmethod
    def _validate_rolling_checkpoint_for_resume(
        checkpoint: Dict[str, Any],
        node_count: int,
    ) -> None:
        """Reject partial or misaligned committed state before making model calls."""
        expected_all = ["root", *(f"node{index}" for index in range(1, node_count))]
        scripts = checkpoint.get("scripts", {})
        if not isinstance(scripts, dict):
            raise ValueError("滚动检查点 scripts 必须是对象")
        committed_ids = list(scripts)
        expected_prefix = expected_all[:len(committed_ids)]
        if committed_ids != expected_prefix:
            raise ValueError(
                f"滚动检查点节点顺序不合法：应为 {expected_prefix}，实际为 {committed_ids}"
            )

        for field in ("goals", "reviews", "performances", "summaries"):
            value = checkpoint.get(field, {})
            if not isinstance(value, dict) or list(value) != committed_ids:
                actual = list(value) if isinstance(value, dict) else type(value).__name__
                raise ValueError(
                    f"滚动检查点 {field} 必须与已提交 scripts 完全对齐，实际为 {actual}"
                )

        for node_id in committed_ids:
            review = checkpoint["reviews"].get(node_id, {})
            if review.get("decision") != "PASS" or review.get("goal_completed") is not True:
                raise ValueError(f"滚动检查点包含未通过的已提交节点：{node_id}")
            if not checkpoint["performances"].get(node_id):
                raise ValueError(f"滚动检查点缺少 {node_id} 的 Actor 表演记录")

        for index, node_id in enumerate(committed_ids):
            goal = checkpoint["goals"].get(node_id, {})
            transition = goal.get("transition_contract", {})
            if index == 0:
                if transition.get("relation_to_previous") != "root":
                    raise ValueError("滚动检查点 root 缺少 root transition_contract")
                continue
            previous_node_id = committed_ids[index - 1]
            source = WorkflowController._extract_transition_source(
                checkpoint["scripts"][previous_node_id]
            )
            if not (
                transition.get("relation_to_previous") not in {None, "", "root"}
                and all(transition.get(key) == value for key, value in source.items())
                and str(transition.get("bridge_requirement", "")).strip()
            ):
                raise ValueError(f"滚动检查点 {node_id} 的 transition_contract 无效")
            continuity = checkpoint["reviews"][node_id].get("continuity_check", {})
            required = (
                "applicable",
                "source_anchor_acknowledged",
                "discourse_relation_realized",
                "action_continuity_preserved",
                "scene_transition_grounded",
            )
            evidence = continuity.get("evidence", [])
            if not (
                all(continuity.get(field) is True for field in required)
                and continuity.get("relation_to_previous")
                == transition.get("relation_to_previous")
                and isinstance(evidence, list)
                and evidence
                and all(
                    isinstance(quote, str)
                    and quote.strip()
                    and quote.strip() in checkpoint["scripts"][node_id]
                    for quote in evidence
                )
            ):
                raise ValueError(f"滚动检查点 {node_id} 的 continuity_check 无效")

    def _recompile_checkpoint_scripts(
        self,
        core_gdd: Dict[str, Any],
        scripts: Dict[str, str],
        performances: Dict[str, List[Dict[str, Any]]],
        goals: Dict[str, Dict[str, Any]],
    ) -> Tuple[Dict[str, str], bool]:
        """Rebuild committed scripts from Actor records after compiler upgrades."""
        rebuilt = dict(scripts)
        changed = False
        previous_script = ""
        for node_id, old_script in scripts.items():
            turns = performances.get(node_id)
            if not turns:
                continue
            new_script = self.writer.synthesize_actor_performances(
                turns=turns,
                node_goal=goals.get(node_id, {}),
                story_context=previous_script,
                core_gdd=core_gdd,
            ).strip()
            jump = re.search(r'<jump\s+target="([^"]+)"\s*/>', old_script)
            if jump:
                new_script += f'\n\n<jump target="{jump.group(1)}"/>'
            new_script += "\n"
            if new_script != old_script:
                rebuilt[node_id] = new_script
                changed = True
            previous_script = new_script
        return rebuilt, changed

    @staticmethod
    def _extract_transition_source(script: str) -> Dict[str, str]:
        """Extract the exact previous scene and final visible utterance/action anchor."""
        scenes = re.findall(r"<scene>(.*?)</scene>", script or "", flags=re.DOTALL)
        contents = re.findall(
            r'<content\s+id="([^"]+)">(.*?)</content>',
            script or "",
            flags=re.DOTALL,
        )
        speaker, anchor = contents[-1] if contents else ("", "")
        return {
            "source_scene": scenes[-1].strip() if scenes else "",
            "source_speaker": speaker.strip(),
            "source_anchor": anchor.strip(),
        }

    @classmethod
    def _ensure_transition_contract(
        cls,
        *,
        node_goal: Dict[str, Any],
        previous_script: str,
        is_root: bool,
    ) -> Dict[str, Any]:
        """Normalize model output against the exact committed tail; never trust copied anchors."""
        normalized = deepcopy(node_goal)
        existing = normalized.get("transition_contract", {})
        if not isinstance(existing, dict):
            existing = {}
        source = cls._extract_transition_source(previous_script)
        allowed = {
            "acknowledgement", "answer", "continuation", "elaboration",
            "explanation", "result", "correction", "contrast", "topic_shift",
        }
        relation = str(existing.get("relation_to_previous", "")).strip()
        if is_root:
            relation = "root"
            source = {"source_scene": "", "source_speaker": "", "source_anchor": ""}
            bridge = str(existing.get("bridge_requirement", "")).strip() or (
                "建立初始冲突，不假装回应不存在的上一节点。"
            )
        else:
            if relation not in allowed:
                relation = "continuation"
            # A committed tail that visibly ends in a direct question requires
            # an answer before the story can legitimately continue elsewhere.
            # Do not let a weaker model label it as a generic continuation and
            # hand the first turn to a third party.
            if source["source_anchor"].rstrip().endswith(("?", "？")):
                relation = "answer"
            bridge = str(existing.get("bridge_requirement", "")).strip() or (
                "首个 Actor 回合必须直接回应或继续上一节点最后的台词或动作；"
                "若要切换地点或调查目标，必须先给出可见触发与移动。"
            )
        normalized["transition_contract"] = {
            "relation_to_previous": relation,
            **source,
            "bridge_requirement": bridge,
        }
        return normalized

    def _generate_actor_driven_node(
        self,
        node_id: str,
        core_gdd: Dict[str, Any],
        node_goal: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summaries: List[str],
        previous_node_ids: Set[str],
        previous_script: str,
        producer_feedback: List[str],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Run the original Director -> Actor -> Writer node creation loop."""
        present_actors = list(getattr(self, "actors", {}).items())
        if not present_actors:
            raise RuntimeError("没有可用 Actor，无法生成节点")

        producer_feedback = self._dedupe_producer_feedback(producer_feedback)

        base_context = (
            f"【Core GDD】\n{json.dumps(core_gdd, ensure_ascii=False, indent=2)}\n\n"
            f"【已提交世界状态】\n{json.dumps(world_state, ensure_ascii=False, indent=2)}\n\n"
            f"【未解议题】\n{json.dumps(agenda, ensure_ascii=False, indent=2)}\n\n"
            f"【前文摘要】\n{json.dumps(previous_summaries, ensure_ascii=False, indent=2)}"
        )
        if previous_script:
            base_context += f"\n\n【上一节点完整剧本】\n{previous_script.strip()}"
        if producer_feedback:
            base_context += (
                "\n\n【Producer 对上一版的驳回要求】\n"
                + json.dumps(producer_feedback, ensure_ascii=False, indent=2)
            )

        turns: List[Dict[str, Any]] = []
        current_dialogue_context = ""
        required_revision_actors = self._required_revision_actors(
            producer_feedback,
            [name for name, _actor in present_actors],
        )
        performed_revision_actors: Set[str] = set()
        director_goal = deepcopy(node_goal)
        if producer_feedback:
            director_goal["mandatory_revision_evidence"] = producer_feedback
            director_goal["revision_rule"] = (
                "每条驳回要求都必须由 Actor 的可见动作或明确台词直接证明；"
                "不要用含糊推测替代确认，也不要在全部满足前 STOP。"
            )
            if required_revision_actors:
                director_goal["mandatory_revision_actors"] = required_revision_actors
                director_goal["mandatory_actor_rule"] = (
                    "名单中的每位 Actor 都必须在本版中实际产生至少一个可见回合；"
                    "全部完成前不得安排尾声落句或 STOP。"
                )
        node_goal_text = json.dumps(director_goal, ensure_ascii=False, indent=2)
        director_outline = json.dumps(
            {
                "global_goal": core_gdd.get("global_goal", {}),
                "current_node_goal": node_goal,
            },
            ensure_ascii=False,
            indent=2,
        )

        scheduled_conditions = self._compact_final_completion_conditions(
            node_goal.get("completion_conditions", []),
            core_gdd.get("global_goal", {}).get("terminal_conditions", []),
        )
        scheduled_conditions = self._ensure_police_handoff_task(
            scheduled_conditions,
            node_goal,
        )
        scheduled_conditions = self._ensure_final_character_resolution_tasks(
            scheduled_conditions,
            node_goal,
            [name for name, _actor in present_actors],
        )
        completion_count = len(scheduled_conditions)
        # A long Producer feedback list previously inflated a revision to 32
        # Actor turns, even when the Director was repeating the same exchange.
        # Keep enough room to realize each condition and each required actor,
        # but fail into the next Producer review instead of generating filler.
        turn_limit = min(
            20,
            max(12, completion_count * 2 + len(required_revision_actors)),
        )
        actor_names = [name for name, _actor in present_actors]
        transition = node_goal.get("transition_contract", {})
        completion_tasks = self._completion_actor_tasks(
            scheduled_conditions,
            actor_names,
        )
        source_scene = str(transition.get("source_scene", "")).strip()
        completion_tasks = self._specialize_terminal_prep_tasks(
            completion_tasks,
            core_gdd=core_gdd,
            source_scene=source_scene,
            protagonist=actor_names[0] if actor_names else "",
            actor_names=actor_names,
        )
        completion_tasks = self._route_completion_tasks(
            completion_tasks,
            core_gdd=core_gdd,
            source_scene=source_scene,
            protagonist=actor_names[0] if actor_names else "",
        )
        had_completion_tasks = bool(completion_tasks)
        answer_actor = self._infer_answer_actor(transition, actor_names)
        strict_retry_counts: Dict[str, int] = {}
        for _ in range(turn_limit):
            story_context = f"{base_context}\n\n【当前表演】\n{current_dialogue_context or '尚未开始'}"
            strict_actor_task = False
            strict_condition = ""
            if not turns and answer_actor:
                strict_actor_task = True
                next_speaker_name = answer_actor
                director_guidance = (
                    f"直接回答{transition.get('source_speaker', '上一位角色')}刚才对你的问题："
                    f"“{transition.get('source_anchor', '')}”。"
                    "必须先给出可见的口头回答或拒答，再继续本节点；"
                    "不要由第三者接管、转述或先把你带离现场。"
                )
            elif turns and completion_tasks:
                strict_actor_task = True
                next_speaker_name, condition = completion_tasks.pop(0)
                strict_condition = condition
                director_guidance = (
                    "这是本回合唯一任务。你的 action 或 dialogue 必须明确覆盖下列条件中的"
                    f"全部实体、地点和结果：【{condition}】。不得换成其他线索，不得新增该条件"
                    "未要求的信息，不得只提问、要求别人行动或重复已发生的内容。"
                )
                if self._is_final_beat_guidance(condition):
                    director_guidance += (
                        " 这是全剧最后一个可见回合：不得再提凶手、认罪、证据、物证、"
                        "警察或案件移交，也不得提出问题；只能用陈述句呈现事件后的安静"
                        "新平衡，并给出明确结束感。不得用‘回教室’、‘继续上课’或类似日常安排"
                        "轻描淡写地替代人物关系与情绪的真正收束。"
                    )
            else:
                next_speaker_name, director_guidance = self.writer.decide_next_speaker(
                    node_goal=node_goal_text,
                    characters=[actor.character_info for _, actor in present_actors],
                    story_context=story_context,
                    game_outline=director_outline,
                )
            if not turns and transition.get("relation_to_previous") != "root":
                strict_actor_task = True
                if answer_actor:
                    transition["bridge_requirement"] = (
                        f"{answer_actor}必须在首个 Actor 回合直接回答"
                        f"{transition.get('source_speaker', '上一位角色')}的提问；"
                        "不得由第三者接管或转述。"
                    )
                director_guidance = (
                    "这是节点首回合，必须先落实跨节点话语关系。"
                    f"上一节点最后内容是“{transition.get('source_anchor', '')}”，"
                    f"关系类型是 {transition.get('relation_to_previous', 'continuation')}；"
                    f"承接要求：{transition.get('bridge_requirement', '')}。"
                    "本轮必须用可见动作或明确台词直接承接，不能跳过正在进行的动作，"
                    "不能无理由改变地点或调查目标。\n"
                    + director_guidance
                )
            missing_revision_actors = [
                name for name in required_revision_actors
                if name not in performed_revision_actors
            ]
            if missing_revision_actors and (
                "STOP" in next_speaker_name.upper()
                or self._is_final_beat_guidance(director_guidance)
            ):
                next_speaker_name = missing_revision_actors[0]
                director_guidance = (
                    "针对 Producer 的驳回要求，用一个可见动作或一句明确台词完成本角色的"
                    "确认、决定或人物弧收束；不要只重复已有线索，也不要说尾声落句。"
                )
            if "STOP" in next_speaker_name.upper():
                if len(turns) >= max(4, len(present_actors)):
                    break
                current_dialogue_context += (
                    "[节点尚未达到最少表演轮数，请继续推进 NodeGoal]\n"
                )
                continue

            selected = next(
                (
                    (name, actor) for name, actor in present_actors
                    if name in next_speaker_name or next_speaker_name in name
                ),
                None,
            )
            if not selected:
                raise ValueError(f"Director 选择了未知 Actor: {next_speaker_name}")
            actor_name, actor = selected
            other_characters = [
                other.character_info for name, other in present_actors if name != actor_name
            ]
            actor_memory_context = actor.build_memory_context(
                query=director_guidance,
                valid_node_ids=previous_node_ids,
                long_k=3,
                previous_node_ids=previous_node_ids,
            )
            performance = actor.perform_scene(
                director_guidance=director_guidance,
                other_characters=other_characters,
                story_context=story_context,
                memory_context=actor_memory_context,
                character_expressions=self._get_expressions_str(actor_name),
                temperature=0.35 if strict_actor_task else 0.9,
            )
            turn = {
                "character": actor_name,
                "thought": str(performance.get("thought", "")).strip(),
                "action": str(performance.get("action", "")).strip(),
                "dialogue": str(performance.get("dialogue", "")).strip(),
                "image": str(performance.get("image", "")).strip(),
            }
            if not turn["action"] and not turn["dialogue"]:
                raise ValueError(f"Actor {actor_name} 返回了空表演")
            missing_condition_items = self._missing_enumerated_condition_items(
                strict_condition,
                f"{turn['action']}\n{turn['dialogue']}",
            )
            if strict_condition and missing_condition_items:
                base_strict_condition = strict_condition.split(
                    " 上一次表演漏掉了", 1
                )[0]
                retry_key = f"{actor_name}:{base_strict_condition}"
                retry_count = strict_retry_counts.get(retry_key, 0)
                strict_retry_counts[retry_key] = retry_count + 1
                if retry_count >= 1:
                    missing_condition_items = []
            if strict_condition and missing_condition_items:
                missing_text = "、".join(missing_condition_items)
                completion_tasks.insert(
                    0,
                    (
                        actor_name,
                        f"{strict_condition} 上一次表演漏掉了“{missing_text}”；"
                        "本次 action 或 dialogue 必须逐字出现这些实体并说明其结果。",
                    ),
                )
                continue
            if self._is_duplicate_actor_turn(turn, turns):
                # A late closure condition can legitimately be satisfied by the
                # immediately preceding terminal beat.  Its scheduled task has
                # already been consumed, so end here when the checklist is now
                # complete.  Continuing into the free Director would append a
                # new exchange after the ending and destroy the final cadence.
                if strict_actor_task and self._completion_tasks_finished(
                    had_completion_tasks=had_completion_tasks,
                    remaining_tasks=completion_tasks,
                    turn_count=len(turns),
                    required_revision_actors=required_revision_actors,
                    performed_revision_actors=performed_revision_actors,
                ):
                    break
                continue
            turns.append(turn)
            if actor_name in required_revision_actors:
                performed_revision_actors.add(actor_name)
            visible_parts = []
            if turn["action"]:
                visible_parts.append(f"动作：{turn['action']}")
            if turn["dialogue"]:
                visible_parts.append(f"台词：{turn['dialogue']}")
            current_dialogue_context += f"{actor_name}: {'；'.join(visible_parts)}\n"
            if self._completion_tasks_finished(
                had_completion_tasks=had_completion_tasks,
                remaining_tasks=completion_tasks,
                turn_count=len(turns),
                required_revision_actors=required_revision_actors,
                performed_revision_actors=performed_revision_actors,
            ):
                break

        if not turns:
            raise ValueError(f"{node_id} 没有产生任何 Actor 表演")

        script = self.writer.synthesize_actor_performances(
            turns=turns,
            node_goal=node_goal,
            story_context=base_context,
            core_gdd=core_gdd,
        )
        script = script.strip()
        if "<scene>" not in script or "<content" not in script:
            raise ValueError(f"Writer 未将 {node_id} Actor 表演整合成合法剧本")
        return script, turns

    @staticmethod
    def _dedupe_producer_feedback(producer_feedback: List[str]) -> List[str]:
        """Remove repeated review requirements while preserving their order."""
        result: List[str] = []
        seen: Set[str] = set()
        for item in producer_feedback or []:
            text = re.sub(r"\s+", " ", str(item)).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _infer_answer_actor(
        transition: Dict[str, Any],
        actor_names: List[str],
    ) -> str:
        """Resolve the explicitly addressed cast member for an answer edge."""
        if transition.get("relation_to_previous") != "answer":
            return ""
        anchor = str(transition.get("source_anchor", ""))
        source_speaker = str(transition.get("source_speaker", ""))
        addressed = [
            name for name in actor_names
            if name and name != source_speaker and name in anchor
        ]
        return min(addressed, key=anchor.index) if addressed else ""

    @staticmethod
    def _completion_actor_tasks(
        completion_conditions: List[str],
        actor_names: List[str],
    ) -> List[Tuple[str, str]]:
        """Schedule every completion condition as one strict, visible Actor task."""
        tasks: List[Tuple[str, str]] = []
        for condition in completion_conditions or []:
            text = str(condition).strip()
            assigned = next(
                (name for name in actor_names if name and text.startswith(name)),
                "",
            )
            if (
                assigned
                and actor_names
                and re.match(
                    rf"^{re.escape(assigned)}的(?:目击)?证(?:言|词)",
                    text,
                )
            ):
                assigned = actor_names[0]
            if not assigned and actor_names:
                assigned = actor_names[0]
            if assigned and text:
                tasks.append((assigned, text))
        return tasks

    @staticmethod
    def _compact_final_completion_conditions(
        completion_conditions: List[str],
        terminal_conditions: List[str],
    ) -> List[str]:
        """Fold duplicate final acceptance criteria into specific scene tasks.

        The Designer keeps global terminal conditions verbatim in the NodeGoal so
        the Producer can audit them.  Performing each of those again, after the
        Designer's more concrete conditions, makes actors confess and summarize
        the same evidence twice.  Merge each recognizable global criterion into
        the most relevant concrete task while preserving the closure tasks last.
        """
        conditions = [str(item).strip() for item in completion_conditions if str(item).strip()]
        terminal_set = {str(item).strip() for item in terminal_conditions if str(item).strip()}
        if not terminal_set or not terminal_set.issubset(set(conditions)):
            return conditions

        closure_set = set(CLOSED_ENDING_COMPLETION_CONDITIONS)
        concrete = [
            item for item in conditions
            if item not in terminal_set and item not in closure_set
        ]
        closure = [item for item in conditions if item in closure_set]
        concept_groups = (
            ("真凶", "凶手", "矛盾", "解释", "揭露"),
            ("密室", "鱼线", "凶器", "镇纸", "手套", "物证"),
            ("竞争", "怨恨", "要挟", "动机", "嫉妒"),
            ("遗书", "韩旭", "目击", "证言"),
            ("认罪", "反抗", "控制", "共识", "一致"),
            ("警察", "救援", "抵达", "封闭", "收束"),
        )

        for terminal in [item for item in conditions if item in terminal_set]:
            group = max(
                concept_groups,
                key=lambda markers: sum(marker in terminal for marker in markers),
            )
            candidates = [
                (sum(marker in item for marker in group), index)
                for index, item in enumerate(concrete)
            ]
            score, index = max(candidates, default=(0, -1))
            if score > 0:
                concrete[index] = (
                    f"{concrete[index]} 同一回合还必须完整满足全局验收条件：{terminal}"
                )
            else:
                concrete.append(terminal)
        return concrete + closure

    @staticmethod
    def _ensure_police_handoff_task(
        conditions: List[str],
        node_goal: Dict[str, Any],
    ) -> List[str]:
        """Turn a final-goal handoff promise into one explicit Actor task."""
        goal_text = "\n".join(
            [
                str(node_goal.get("goal", "")),
                str(node_goal.get("contributes_to_global_goal", "")),
                *[str(item) for item in node_goal.get("completion_conditions", [])],
            ]
        )
        requires_handoff = (
            "警" in goal_text
            and any(marker in goal_text for marker in ("拘留", "接管", "收取", "移交"))
        )
        if not requires_handoff or any(
            ProducerAgent._has_confirmed_police_handoff(condition)
            for condition in conditions
        ):
            return conditions

        handoff_task = (
            "两名外部警察必须推门进入当前现场，亲手给赵深戴上手铐，并将镇纸、鱼线、"
            "白手套和伪造遗书装入证物袋接管；不得只写警灯、脚步声或说‘警察来了’。"
        )
        closure_set = set(CLOSED_ENDING_COMPLETION_CONDITIONS)
        first_closure = next(
            (index for index, item in enumerate(conditions) if item in closure_set),
            len(conditions),
        )
        return [*conditions[:first_closure], handoff_task, *conditions[first_closure:]]

    @staticmethod
    def _ensure_final_character_resolution_tasks(
        conditions: List[str],
        node_goal: Dict[str, Any],
        actor_names: List[str],
    ) -> List[str]:
        """Give named witnesses their own post-confession choices before the coda."""
        goal_text = "\n".join(
            [
                str(node_goal.get("goal", "")),
                str(node_goal.get("contributes_to_global_goal", "")),
                *[str(item) for item in node_goal.get("completion_conditions", [])],
            ]
        )
        if "警" not in goal_text or not any(
            marker in goal_text for marker in ("拘留", "接管", "收取", "移交")
        ):
            return conditions

        tasks: List[str] = []
        if "叶晓" in actor_names:
            tasks.append(
                "叶晓必须在赵深认罪和警方接管后亲口确认她不再隐瞒，并明确决定配合警方作证；"
                "不得由林晨替她提问或总结。"
            )
        if "韩旭" in actor_names:
            tasks.append(
                "韩旭必须在赵深认罪和警方接管后亲口确认自己的目击证言，并明确决定向警方作证；"
                "不得只递出纸条。"
            )
        if not tasks:
            return conditions

        closure_set = set(CLOSED_ENDING_COMPLETION_CONDITIONS)
        first_closure = next(
            (index for index, item in enumerate(conditions) if item in closure_set),
            len(conditions),
        )
        tasks = [task for task in tasks if task not in conditions]
        return [*conditions[:first_closure], *tasks, *conditions[first_closure:]]

    @staticmethod
    def _missing_enumerated_condition_items(condition: str, performance: str) -> List[str]:
        """Return hard enumerated terms omitted by a scheduled Actor turn."""
        marker = "全局验收条件："
        acceptance_text = (
            "\n".join(condition.split(marker)[1:])
            if marker in condition
            else ""
        )
        missing = [
            item
            for item in ProducerAgent._enumerated_terminal_items(acceptance_text)
            # A named weapon such as “石质镇纸” is stronger evidence than the
            # generic label “凶器”; the Producer can verify that Core GDD alias.
            if item != "凶器" and item not in performance
        ]
        if (
            re.search(r"(?:警察|警方)抵达", condition)
            and not ProducerAgent._has_confirmed_police_arrival(performance)
        ):
            missing.append("警方已经进入当前现场")
        if (
            "赵深" in condition
            and any(marker in condition for marker in ("拘留", "拘捕", "手铐"))
            and any(
                marker in condition
                for marker in ("证物", "证据", "镇纸", "鱼线", "手套", "遗书")
            )
            and not ProducerAgent._has_confirmed_police_handoff(performance)
        ):
            missing.append("警方拘捕赵深并收取现场证物")
        return missing

    @staticmethod
    def _infer_goal_target_scene(
        core_gdd: Dict[str, Any],
        node_goal: Dict[str, Any],
    ) -> str:
        """Match NodeGoal place language to one declared Core GDD scene."""
        goal_text = "\n".join(
            [
                str(node_goal.get("goal", "")),
                str(node_goal.get("dramatic_question", "")),
                str(node_goal.get("contributes_to_global_goal", "")),
                *[str(item) for item in node_goal.get("completion_conditions", [])],
            ]
        )
        exact_matches: List[Tuple[int, int, str]] = []
        alias_matches: List[Tuple[int, int, int, str]] = []
        for scene in core_gdd.get("scenes", []):
            if not isinstance(scene, dict):
                continue
            name = str(scene.get("name", "")).strip()
            if not name:
                continue
            exact_count = goal_text.count(name)
            if exact_count:
                exact_matches.append((exact_count, len(name), name))
                continue
            aliases = WriterAgent._scene_aliases(name)
            hits = [alias for alias in aliases if alias and goal_text.count(alias)]
            if hits:
                weighted_hits = sum(
                    len(alias) * goal_text.count(alias) for alias in hits
                )
                alias_matches.append(
                    (weighted_hits, max(map(len, hits)), len(hits), name)
                )
        if exact_matches:
            return max(exact_matches)[2]
        return max(alias_matches)[3] if alias_matches else ""

    @classmethod
    def _route_completion_tasks(
        cls,
        tasks: List[Tuple[str, str]],
        *,
        core_gdd: Dict[str, Any],
        source_scene: str,
        protagonist: str,
    ) -> List[Tuple[str, str]]:
        """Group condition tasks by declared scene and insert grounded movement turns."""
        grouped: Dict[str, List[Tuple[str, str]]] = {}
        scene_order: List[str] = []
        unlocated: List[Tuple[str, str]] = []
        for task in tasks:
            actor_name, condition = task
            target_scene = cls._infer_condition_target_scene(core_gdd, condition)
            if not target_scene:
                unlocated.append(task)
                continue
            if target_scene not in grouped:
                grouped[target_scene] = []
                scene_order.append(target_scene)
            grouped[target_scene].append(task)

        routed: List[Tuple[str, str]] = []
        current_scene = source_scene
        for target_scene in scene_order:
            if protagonist and current_scene and target_scene != current_scene:
                routed.append(
                    (
                        protagonist,
                        f"承接上一回合后说明调查理由，并实际带众人从{current_scene}移动到"
                        f"{target_scene}；action 必须明确写出‘进入{target_scene}’，"
                        "到达后再开始该地点的调查。",
                    )
                )
            routed.extend(grouped[target_scene])
            current_scene = target_scene
        routed.extend(unlocated)
        return routed

    @staticmethod
    def _infer_condition_target_scene(
        core_gdd: Dict[str, Any],
        condition: str,
    ) -> str:
        """Infer a destination only from explicit location-bound actions."""
        text = str(condition)
        matches: List[Tuple[int, int, str]] = []
        action_verbs = (
            "前往|进入|走进|来到|抵达|赶到|返回|回到|搜查|检查|勘查|调查"
        )
        result_verbs = (
            "发现|找到|检查|搜查|确认|注意|取得|拿到|承认|坦白|对质|盘问"
        )
        for scene in core_gdd.get("scenes", []):
            if not isinstance(scene, dict):
                continue
            name = str(scene.get("name", "")).strip()
            if not name:
                continue
            for alias in WriterAgent._scene_aliases(name):
                patterns = (
                    rf"(?:{action_verbs}).{{0,12}}{re.escape(alias)}",
                    rf"(?:在|于).{{0,6}}{re.escape(alias)}.{{0,8}}(?:{result_verbs})",
                )
                if any(re.search(pattern, text) for pattern in patterns):
                    matches.append((len(alias), len(name), name))
                    break
        return max(matches)[2] if matches else ""

    @staticmethod
    def _specialize_terminal_prep_tasks(
        tasks: List[Tuple[str, str]],
        *,
        core_gdd: Dict[str, Any],
        source_scene: str,
        protagonist: str,
        actor_names: List[str],
    ) -> List[Tuple[str, str]]:
        """Turn generic penultimate-node checklist items into grounded performances."""
        culprit = ""
        for fact in core_gdd.get("immutable_facts", []):
            match = re.search(r"真凶(?:是|为)([^，。；]+)", str(fact))
            if match:
                candidate = match.group(1).strip()
                if candidate in actor_names:
                    culprit = candidate
                    break

        result: List[Tuple[str, str]] = []
        for actor_name, condition in tasks:
            if (
                culprit
                and all(item in condition for item in ("竞争", "怨恨", "要挟"))
            ):
                result.append(
                    (
                        culprit,
                        f"{culprit}必须在最终供述中亲口明确说出“竞争”“怨恨”“要挟”"
                        "三个词，并分别解释它们如何共同构成杀害陈默的完整动机链；"
                        "不得由其他角色代为总结。",
                    )
                )
                continue
            match = re.match(r"终局必需项[“\"]([^”\"]+)[”\"]", condition)
            if not match:
                result.append((actor_name, condition))
                continue
            item = match.group(1)
            if item == "手套" and protagonist and source_scene:
                result.append(
                    (
                        protagonist,
                        f"{protagonist}在{source_scene}角落搜查并发现一双明确命名为“手套”的"
                        "可见物证；只能描述这双手套本身及其与已发现现场痕迹的关联，"
                        "不得凭空拿出其他道具。",
                    )
                )
            elif item in {"竞争", "怨恨", "要挟"} and culprit:
                result.append(
                    (
                        culprit,
                        f"{culprit}在供述动机时必须亲口明确说出“{item}”一词，并解释"
                        f"“{item}”如何推动自己杀害陈默；不得由其他角色代为总结，"
                        "不得出示未在 Core GDD 或前文出现的新照片、信件或道具。",
                    )
                )
            else:
                result.append((actor_name, condition))
        return result

    @staticmethod
    def _completion_tasks_finished(
        *,
        had_completion_tasks: bool,
        remaining_tasks: List[Tuple[str, str]],
        turn_count: int,
        required_revision_actors: List[str],
        performed_revision_actors: Set[str],
    ) -> bool:
        """Stop before the free Director repeats a fully scheduled NodeGoal."""
        return (
            had_completion_tasks
            and not remaining_tasks
            and turn_count >= 4
            and all(
                name in performed_revision_actors
                for name in required_revision_actors
            )
        )

    @staticmethod
    def _is_duplicate_actor_turn(
        turn: Dict[str, Any],
        previous_turns: List[Dict[str, Any]],
    ) -> bool:
        """Drop exact Actor repetition while treating its scheduled task as consumed."""
        character = str(turn.get("character", "")).strip()
        action = str(turn.get("action", "")).strip()
        dialogue = str(turn.get("dialogue", "")).strip()
        for previous in previous_turns:
            if character != str(previous.get("character", "")).strip():
                continue
            previous_action = str(previous.get("action", "")).strip()
            previous_dialogue = str(previous.get("dialogue", "")).strip()
            if action == previous_action and dialogue == previous_dialogue:
                return True
            # Changing only the stage direction does not make an identical line
            # a new dramatic beat.
            if dialogue and dialogue == previous_dialogue:
                return True
        return False

    @staticmethod
    def _required_revision_actors(
        producer_feedback: List[str],
        actor_names: List[str],
    ) -> List[str]:
        """Return actors explicitly named by the Producer for the next performance."""
        feedback_text = "\n".join(str(item) for item in producer_feedback)
        return [name for name in actor_names if name and name in feedback_text]

    @staticmethod
    def _is_final_beat_guidance(guidance: str) -> bool:
        """Recognize a Director instruction that would create the terminal beat."""
        text = str(guidance or "")
        return any(
            marker in text
            for marker in ("尾声", "落句", "收束全剧", "最终一句", "最后一句", "终止感", "结束语")
        )

    def _commit_actor_performances(
        self,
        node_id: str,
        turns: List[Dict[str, Any]],
        node_script: str,
        node_goal: Dict[str, Any],
    ) -> None:
        """Commit Actor memory only after the Producer accepts the node."""
        present_names = []
        for turn in turns:
            actor_name = str(turn.get("character", ""))
            actor = getattr(self, "actors", {}).get(actor_name)
            if not actor:
                continue
            if actor_name not in present_names:
                present_names.append(actor_name)
            private_record = {key: value for key, value in turn.items() if value}
            actor.record_short_term_dialogue(
                node_id=node_id,
                detail=json.dumps(private_record, ensure_ascii=False),
            )
            observed_record = {
                key: value for key, value in turn.items()
                if key in {"character", "action", "dialogue"} and value
            }
            observed_text = json.dumps(observed_record, ensure_ascii=False)
            for observer_name, observer in getattr(self, "actors", {}).items():
                if observer_name != actor_name:
                    observer.record_short_term_dialogue(node_id=node_id, detail=observed_text)

        present_actors = [
            (name, self.actors[name]) for name in present_names if name in self.actors
        ]
        importance = self._generate_node_importance_scores(
            node_id=node_id,
            node_script=node_script,
            actor_names=present_names,
            game_outline=json.dumps(node_goal, ensure_ascii=False),
        )
        self._finalize_actor_node_long_term_memories(
            node_id=node_id,
            present_actors=present_actors,
            importance_map=importance,
        )

    @staticmethod
    def _apply_evidence_backed_updates(
        base_state: Dict[str, Any],
        updates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply Producer-approved dot-path updates that carry textual evidence."""
        result = deepcopy(base_state)
        for update in updates or []:
            path = str(update.get("path", "")).strip()
            evidence = str(update.get("evidence", "")).strip()
            if not path or not evidence:
                raise ValueError("State updates require both path and evidence")
            segments = path.split(".")
            if any(not segment or segment.startswith("__") for segment in segments):
                raise ValueError(f"Unsafe state update path: {path}")
            target = result
            for segment in segments[:-1]:
                existing = target.get(segment)
                if not isinstance(existing, dict):
                    target[segment] = {}
                target = target[segment]
            target[segments[-1]] = deepcopy(update.get("value"))
        return result

    def _persist_rolling_story(
        self,
        core_gdd: Dict[str, Any],
        graph: Dict[str, Any],
        scripts: Dict[str, str],
        goals: Dict[str, Dict[str, Any]],
        reviews: Dict[str, Dict[str, Any]],
        performances: Dict[str, List[Dict[str, Any]]],
        summaries: Dict[str, str],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
    ) -> None:
        """保存滚动故事检查点以及现有引擎兼容文件。"""
        game_design = dict(core_gdd)
        game_design["generation_mode"] = "rolling"
        game_design["story_outline"] = {
            "mode": "rolling",
            "initial_conflict": core_gdd.get("initial_conflict", ""),
        }
        game_design["story_graph"] = graph
        self._save_json(PathConfig.GAME_DESIGN_FILE, game_design)
        self._save_json(PathConfig.STORY_GRAPH_FILE, graph)
        self._save_json(
            os.path.join(PathConfig.DATA_DIR, "rolling_state.json"),
            {
                "schema_version": "rolling-state/3.2",
                "generation_architecture": "actor-driven-node-goals",
                "core_gdd": core_gdd,
                "story_graph": graph,
                "goals": goals,
                "reviews": reviews,
                "performances": performances,
                "summaries": summaries,
                "scripts": scripts,
                "world_state": world_state,
                "agenda": agenda,
            },
        )
        story_text = "\n\n".join(
            f"=== Node: {node_id} ===\n{script.strip()}"
            for node_id, script in scripts.items()
        )
        with open(PathConfig.STORY_FILE, "w", encoding="utf-8") as handle:
            handle.write(story_text + ("\n" if story_text else ""))

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
    ) -> Dict[str, Any]:
        """生成单个节点剧本（不落盘）。"""
        logger.info(f"\n📅 正在制作节点: {node_id}")

        node_summary = node_info.get('summary', '')
        parents = story_graph.get_parents(node_id)
        valid_node_ids = self._get_ancestors(node_id, story_graph)
        long_term_memory = self._build_long_term_memory(
            node_id=node_id,
            story_graph=story_graph,
            query_text=node_summary,
            valid_node_ids=valid_node_ids,
        )

        short_term_memory = ""
        recent_writer_nodes = self.world_memory.short_term.get_recent_history(
            recent_k=2,
            valid_node_ids=valid_node_ids,
            role_code="Writer",
        )
        if recent_writer_nodes:
            short_term_memory = "\n\n".join([t for t in recent_writer_nodes if t and t.strip()])
        elif parents:
            parent_id = parents[-1]
            parent_content = self._extract_node_story(parent_id)
            short_term_memory = parent_content if parent_content else ""

        if short_term_memory:
            full_context = f"{long_term_memory}\n\n【最近剧情】:\n{short_term_memory}"
        else:
            full_context = long_term_memory

        present_actors = list(self.actors.items())
        if not present_actors:
            return {"script": node_summary}

        available_scenes = [scene['name'] for scene in self.game_design.get('scenes', [])]
        available_characters = self.game_design.get('characters', [])

        current_dialogue_context = ""
        turn_records: List[Dict[str, str]] = []
        performance_log_path = os.path.join(PathConfig.TEXT_LOG_DIR, f"performance_{node_id}.jsonl")
        if os.path.exists(performance_log_path):
            os.remove(performance_log_path)

        turn_count = 0
        safety_limit = 50
        speaker_retry_count = 0
        max_speaker_retries = 3

        game_outline_str = json.dumps(self.game_design.get("story_outline", {}), ensure_ascii=False, indent=2)

        while turn_count < safety_limit:
            current_total_context = f"{full_context}\n\n【当前对话】:\n{current_dialogue_context}"

            present_char_info = [actor.character_info for _, actor in present_actors]
            next_speaker_name, director_guidance = self.writer.decide_next_speaker(
                node_goal=node_summary,
                characters=present_char_info,
                game_outline=game_outline_str,
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

            guidance_text = director_guidance.strip()
            memory_query = guidance_text

            previous_node_ids = set(parents[-1:]) if parents else set()

            actor_memory_context = next_actor.build_memory_context(
                query=memory_query,
                valid_node_ids=valid_node_ids,
                long_k=3,
                current_node_id=node_id,
                previous_node_ids=previous_node_ids,
            )

            performance_data = next_actor.perform_scene(
                director_guidance=guidance_text,
                other_characters=other_chars,
                story_context=current_total_context,
                memory_context=actor_memory_context,
                character_expressions=available_expressions
            )

            thought = (performance_data.get("thought") or "").strip()
            action = (performance_data.get("action") or "").strip()
            dialogue = (performance_data.get("dialogue") or "").strip()
            image = (performance_data.get("image") or "").strip()

            self._log_performance(performance_log_path, {
                "node_id": node_id,
                "turn_id": turn_count + 1,
                "character": next_char_name,
                "thought": thought,
                "action": action,
                "dialogue": dialogue,
                "image": image,
            })

            if action or dialogue:
                visible_parts = []
                if action:
                    visible_parts.append(f"动作：{action}")
                if dialogue:
                    visible_parts.append(f"台词：{dialogue}")
                current_dialogue_context += f"{next_char_name}: {'；'.join(visible_parts)}\n"
                if image:
                    self._add_expressions_to_character(next_char_name, [image])

                # 自分视角的日志形式（包含 thought）
                private_record = {"character": next_char_name}
                if action:
                    private_record["action"] = action
                if dialogue:
                    private_record["dialogue"] = dialogue
                if thought:
                    private_record["thought"] = thought
                private_memory_text = json.dumps(private_record, ensure_ascii=False)

                next_actor.record_short_term_dialogue(
                    node_id=node_id,
                    detail=private_memory_text,
                )
                turn_records.append(
                    {
                        "character": next_char_name,
                        "thought": thought,
                        "action": action,
                        "dialogue": dialogue,
                        "image": image,
                    }
                )

                # 同场广播日志形式：抹除 thought
                observed_record = {"character": next_char_name}
                if action:
                    observed_record["action"] = action
                if dialogue:
                    observed_record["dialogue"] = dialogue
                observed_text = json.dumps(observed_record, ensure_ascii=False)

                for observer_name, observer_actor in present_actors:
                    if observer_name == next_char_name:
                        continue
                    observer_actor.record_short_term_dialogue(
                        node_id=node_id,
                        detail=observed_text,
                    )
                turn_count += 1
            else:
                break

        performance_records = [
            {
                "segment_id": 1,
                "node_goal": node_summary,
                "turns": turn_records,
            }
        ]

        children = story_graph.get_children(node_id)
        choices_data = []
        if len(children) > 1:
            choices_data = [{"target": child_id, "text": choice_text} for child_id, choice_text in children]

        game_outline_str = json.dumps(self.game_design.get("story_outline", {}), ensure_ascii=False, indent=2)

        script_package = self.writer.synthesize_script_package(
            performances=performance_records,
            choices=choices_data,
            game_outline=game_outline_str,
            story_context=full_context,
            available_scenes=available_scenes,
            available_characters=available_characters,
            node_id=node_id,
            node_summary=node_summary,
        )
        polished_script = str(script_package.get("script", ""))

        if len(children) == 1:
            next_node_id, _ = children[0]
            jump_tag = f"<jump target=\"{next_node_id}\"/>"
            if jump_tag not in polished_script:
                polished_script = polished_script.rstrip() + f"\n\n{jump_tag}\n"

        actor_names = [name for name, _ in present_actors]
        actor_importance_map = self._generate_node_importance_scores(
            node_id=node_id,
            node_script=polished_script,
            game_outline=game_outline_str,
            actor_names=actor_names,
        )

        # 节点结束后再做长期记忆入库：每个角色写入该节点完整记录。
        self._finalize_actor_node_long_term_memories(
            node_id=node_id,
            present_actors=present_actors,
            importance_map=actor_importance_map,
        )

        return {
            "script": polished_script,
            "cgs": script_package.get("cgs", []),
        }

    def load_existing_game(self) -> bool:
        """加载已存在的游戏数据"""
        try:
            # 如果 producer 还没初始化，先尝试加载
            if not self.producer:
                self.producer = ProducerAgent()
                
            self.game_design = self.producer.load_game_design()
            if not self.game_design:
                return False
            
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
                    raw_data = json.load(f)
                if not isinstance(raw_data, dict):
                    return {}
                cleaned = {
                    str(name): list(dict.fromkeys(
                        str(expression).strip()
                        for expression in expressions
                        if _is_valid_expression_name(expression)
                    ))
                    for name, expressions in raw_data.items()
                    if isinstance(expressions, list)
                }
                if cleaned != raw_data:
                    logger.warning("⚠️ 已清理表情库中的残缺或非法表情名")
                    with open(expr_file, 'w', encoding='utf-8') as f:
                        json.dump(cleaned, f, ensure_ascii=False, indent=2)
                return cleaned
            except Exception as e:
                logger.warning(f"⚠️ 加载表情库失败: {e}，创建新库")
                return {}
        return {}

    def _load_cg_manifest(self) -> List[Dict[str, Any]]:
        """Load the minimal four-field Writer CG manifest."""
        path = Path(PathConfig.CG_MANIFEST_FILE)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"⚠️ 加载 CG 清单失败: {exc}")
            return []

    def _save_cg_manifest(self, cgs: List[Dict[str, Any]]) -> None:
        """Persist CG metadata without workflow-only fields."""
        clean = [
            {
                "id": str(cg.get("id", "")).strip(),
                "node_id": str(cg.get("node_id", "")).strip(),
                "characters": list(cg.get("characters", [])),
                "description": str(cg.get("description", "")).strip(),
            }
            for cg in cgs
            if isinstance(cg, dict) and str(cg.get("id", "")).strip()
        ]
        Path(PathConfig.CG_MANIFEST_FILE).write_text(
            json.dumps(clean, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        expressions = [
            str(expression).strip()
            for expression in expressions
            if _is_valid_expression_name(expression)
        ]
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

    @staticmethod
    def _clamp_importance(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    def _generate_node_importance_scores(
        self,
        node_id: str,
        node_script: str,
        actor_names: List[str],
        game_outline: str = "",
    ) -> Dict[str, float]:
        """由 Writer 在节点整合后产出 actor importance 并返回。"""
        default_actor = 0.6
        defaults = {name: default_actor for name in actor_names}

        if not self.writer or not getattr(self.writer, "llm_client", None):
            return defaults

        prompt = WriterConfig.MEMORY_IMPORTANCE_SCORE_PROMPT.format(
            node_id=node_id,
            actor_names=", ".join(actor_names),
            node_script=node_script,
            game_outline=game_outline,
        )

        try:
            response = self.writer.llm_client.chat_completion(
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            raw = (response or "").strip()
            json_text = raw
            if not (raw.startswith("{") and raw.endswith("}")):
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    json_text = match.group(0)

            parsed = json.loads(json_text)

            actor_scores_raw = parsed.get("actor_importance", {})
            actor_scores: Dict[str, float] = {}
            if isinstance(actor_scores_raw, dict):
                for name in actor_names:
                    val = actor_scores_raw.get(name, defaults[name])
                    try:
                        actor_scores[name] = self._clamp_importance(float(val))
                    except Exception:
                        actor_scores[name] = defaults[name]
            else:
                actor_scores = defaults

            return actor_scores
        except Exception:
            return defaults

    def _finalize_actor_node_long_term_memories(
        self,
        node_id: str,
        present_actors: List[Any],
        importance_map: Optional[Dict[str, float]] = None,
    ) -> None:
        """节点结束后，为每个在场角色写入该节点完整长期记忆。"""
        current_node_only = {node_id}
        importance_map = importance_map or {}
        for actor_name, actor in present_actors:
            node_records = actor.memory.short_term.get_recent_history(
                recent_k=0,
                valid_node_ids=current_node_only,
                role_code=actor_name,
            )
            if not node_records:
                continue

            memory_text = "\n".join([r for r in node_records if r and r.strip()]).strip()
            if not memory_text:
                continue

            importance = self._clamp_importance(float(importance_map.get(actor_name, 0.6)))
            actor.remember_long_term(
                node_id=node_id,
                text=memory_text,
                importance=importance,
            )

    def _register_node_memory(
        self,
        node_id: str,
        node_content: str,
    ) -> None:
        """注册 Writer 记忆：短期保留最近节点。"""
        clean_content = (node_content or "").strip()
        if not clean_content:
            return

        self.world_memory.add_short_term(
            node_id=node_id,
            detail=clean_content,
            role_code="Writer",
        )

    def _build_long_term_memory(
        self, 
        node_id: str, 
        story_graph: 'StoryGraph', 
        query_text: str = "",
        valid_node_ids: Optional[Set[str]] = None,
    ) -> str:
        """为 Writer 构建长期上下文（已移除 ChromaDB 查询，目前仅回退到最短期的完整剧情）"""
        if valid_node_ids is None:
            valid_node_ids = self._get_ancestors(node_id, story_graph)

        fallback = self.world_memory.short_term.get_recent_history(
            recent_k=2,
            valid_node_ids=valid_node_ids,
            role_code="Writer",
        )
        if fallback:
            return "【最近完整剧情】\n" + "\n\n".join(fallback)
        return "游戏开始。"
    
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
