"""
Actor Agent
~~~~~~~~~~~
演员 Agent - 负责扮演特定角色并审核剧本
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List, Set
from .base_agent import BaseAgent

from .config import ActorConfig
from .schemas import (
    ACTOR_IMAGE_CRITIQUE_SCHEMA,
    ACTOR_PERFORMANCE_SCHEMA,
)
from .memory import MemoryManager, default_hash_embedding

logger = logging.getLogger(__name__)


class ActorAgent(BaseAgent):
    """演员 Agent - 角色扮演与剧本审核"""
    
    def __init__(self, character_info: Dict[str, Any], api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化演员 Agent
        
        Args:
            character_info: 角色信息字典 (包含 name, personality, background 等)
            api_key: API Key
            base_url: API Base URL
        """
        character_name = character_info.get('name', 'Unknown')
        super().__init__(
            name=character_name,
            role="演员",
            api_key=api_key,
            base_url=base_url
        )
        self.config = ActorConfig
        self.character_info = character_info
        self.name = character_name
        # 角色独立记忆（短期对白 + 长期回忆）
        self.memory = MemoryManager(
            name=f"actor_{self.name}",
            short_term_capacity=20,
            embedding_fn=self._embedding_with_fallback,
        )
        
        logger.info(f"✅ 演员 Agent ({self.name}) 初始化成功")

    def _embedding_with_fallback(self, text: str):
        """优先调用真实 embedding，失败时回退哈希 embedding。"""
        try:
            embedding = self.llm_client.get_embedding(text)
            if embedding:
                return embedding
        except Exception:
            pass
        return default_hash_embedding(text)

    def record_short_term_dialogue(self, node_id: str, detail: str) -> None:
        """记录角色短期对白记忆。"""
        self.memory.add_short_term(
            node_id=node_id,
            detail=detail,
            role_code=self.name,
        )

    def remember_long_term(
        self,
        node_id: str,
        text: str,
        importance: float = 0.5,
    ) -> None:
        """记录角色长期回忆。"""
        self.memory.add_long_term(
            node_id=node_id,
            text=text,
            owner_id=self.name,
            importance=importance,
        )

    def build_memory_context(
        self,
        query: str,
        valid_node_ids: Optional[Set[str]],
        long_k: int = 3,
        current_node_id: Optional[str] = None,
        previous_node_ids: Optional[Set[str]] = None,
    ) -> str:
        """构建角色个人记忆上下文。"""
        def _strip_thought(text: str) -> str:
            clean = (text or "").strip()
            if not clean:
                return ""
            # 私有 thought 不喂回 Actor，上下文里只保留可见行动。
            if "【行动】" in clean:
                return clean[clean.find("【行动】") :].strip()
            clean = re.sub(r"【内心】.*?(?:\n|$)", "", clean)
            return clean.strip()

        # 双节点短期上下文：当前节点已写入内容 + 上一节点完整内容（均限定为该角色私有记录）。
        short_items: List[str] = []
        if previous_node_ids:
            short_items.extend(
                self.memory.short_term.get_recent_history(
                    recent_k=0,
                    valid_node_ids=previous_node_ids,
                    role_code=self.name,
                )
            )
        if current_node_id:
            short_items.extend(
                self.memory.short_term.get_recent_history(
                    recent_k=0,
                    valid_node_ids={current_node_id},
                    role_code=self.name,
                )
            )
        long_items = self.memory.long_term.search(
            query=query,
            valid_node_ids=valid_node_ids,
            top_k=long_k,
            owner_id=self.name,
        )

        blocks: List[str] = []
        if long_items:
            lines = [
                f"- Node {item['node_id']}: {_strip_thought(item['text'])}"
                for item in long_items
                if _strip_thought(item.get("text", ""))
            ]
            if lines:
                blocks.append(f"【{self.name}长期回忆】\n" + "\n".join(lines))
        if short_items:
            visible_short_items = [_strip_thought(text) for text in short_items]
            visible_short_items = [text for text in visible_short_items if text]
            if visible_short_items:
                lines = [f"- {text}" for text in visible_short_items]
                blocks.append(f"【{self.name}最近经历】\n" + "\n".join(lines))
        return "\n\n".join(blocks)

    def _build_system_prompt(self) -> str:
        """统一构建 System Prompt（按配置模板注入角色关键信息）"""
        return self.config.SYSTEM_PROMPT.format(
            name=self.name,
            personality=self.character_info.get("personality", ""),
            background=self.character_info.get("background", "")
        )
    
    def perform_scene(
        self,
        director_guidance: str,
        other_characters: List[Dict[str, Any]],
        story_context: str,
        memory_context: str = "",
        character_expressions: List[str] = [],
        temperature: Optional[float] = None,
    ) -> Dict[str, str]:
        """根据导演指导进行表演"""
        logger.info(f"🎭 演员 {self.name} 正在表演...")

        effective_story_context = story_context
        if memory_context:
            effective_story_context = f"{memory_context}\n\n{story_context}" if story_context else memory_context
        
        # 传入在场其他角色完整设定（JSON）
        other_chars_info = json.dumps(other_characters, ensure_ascii=False, indent=2)
        
        prompt = self.config.PERFORM_PROMPT.format(
            name=self.name,
            director_guidance=director_guidance,
            other_characters=other_chars_info,
            story_context=effective_story_context,
            character_expressions=", ".join(character_expressions)
        )
        
        system_prompt = self._build_system_prompt()
        
        try:
            performance = self.call_json_with_schema(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                schema=ACTOR_PERFORMANCE_SCHEMA,
                object_name="actor_performance",
                temperature=0.9 if temperature is None else temperature,
            )

            thought = str(performance.get("thought", "")).strip()
            action = str(performance.get("action", "")).strip()
            dialogue = str(performance.get("dialogue", "")).strip()
            image = str(performance.get("image", "")).strip()
            return {
                "thought": thought,
                "action": action,
                "dialogue": dialogue,
                "image": image,
            }
        except Exception as e:
            logger.error(f"❌ 表演失败: {e}")
            return {"thought": "", "action": "", "dialogue": "", "image": ""}

    def critique_visual(
        self, 
        image_path: str, 
        expression: str = "neutral", 
        reference_image_path: Optional[str] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None
    ) -> str:
        """
        审核角色立绘
        
        Args:
            image_path: 图片文件路径
            expression: 表情名称
            reference_image_path: 参考图片路径 (通常是 neutral 表情)
            story_background: 故事背景描述
            art_style: 美术风格描述
            
        Returns:
            审核意见 (PASS 或 修改建议)
        """
        logger.info(f"🎨 演员 {self.name} 正在审核立绘: {image_path} (表情: {expression})...")
        
        # 构建 System Prompt
        system_prompt = self._build_system_prompt()
        
        # 构建 User Prompt
        user_prompt = self.config.IMAGE_CRITIQUE_PROMPT.format(
            story_background=story_background or "A visual novel game",
            art_style=art_style or "Japanese anime style",
            expression=expression,
            appearance=self.character_info.get("appearance", "")
        )
        
        try:
            # 构造包含图片的消息
            content = [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": image_path}}
            ]
            
            # 如果有参考图，添加到消息中
            if reference_image_path and expression != "neutral":
                content.insert(1, {"type": "text", "text": "这是你的标准立绘 (Neutral 表情) 作为参考："})
                content.insert(2, {"type": "image_url", "image_url": {"url": reference_image_path}})
            
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": content + [
                        {
                            "type": "text",
                            "text": (
                                "请严格输出 JSON，不要额外解释。格式如下：\n"
                                "{\n"
                                "  \"decision\": \"PASS\" 或 \"REVISE\",\n"
                                "  \"feedback\": \"审核意见\"\n"
                                "}\n"
                                "规则：如果需要修改，decision 必须是 REVISE，feedback 必须给出具体可执行修改点。"
                            )
                        }
                    ]
                }
            ]

            critique = self.call_json_with_schema(
                messages=messages,
                schema=ACTOR_IMAGE_CRITIQUE_SCHEMA,
                object_name="actor_image_critique",
                temperature=self.config.TEMPERATURE
            )

            decision = str(critique.get("decision", "REVISE")).strip().upper()
            feedback = str(critique.get("feedback", "")).strip()
            
            # 记录审核意见
            logger.info(f"🎭 演员 {self.name} 的审核结论: {decision}")
            logger.info(f"🎭 演员 {self.name} 的审核意见:\n{feedback}")

            if decision == "PASS":
                logger.info(f"✅ 演员 {self.name} 立绘审核通过")
                return "PASS"
            else:
                logger.warning(f"⚠️ 演员 {self.name} 对立绘提出修改建议")
                return feedback or "请根据角色设定继续修改当前立绘。"
                
        except Exception as e:
            logger.error(f"❌ 演员 {self.name} 立绘审核失败: {str(e)}")
            return "图片审核失败，请重试。"

    def critique_cg(
        self,
        image_path: str,
        cg: Dict[str, Any],
        reference_image_path: Optional[str] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None,
    ) -> str:
        """Review this Actor's identity and performance inside a multi-character CG."""
        logger.info(f"🎭 演员 {self.name} 正在审核剧情 CG: {cg.get('id', '')}")
        prompt = f"""你正在审核一张包含你的 Visual Novel 剧情 CG。

【故事背景】
{story_background or '未指定'}

【美术风格】
{art_style or '日系视觉小说'}

【Writer 分镜】
{cg.get('description', '')}

【你的固定角色设定】
姓名：{self.name}
外貌：{self.character_info.get('appearance', '')}
性格：{self.character_info.get('personality', '')}

请只审核画面中与你有关的部分：身份和五官是否一致、发型服装是否一致、表情视线、姿势动作、
与其他人物的互动是否准确，以及是否符合 Writer 分镜和当前角色状态。不要因为个人不喜欢构图
而否决，也不要修改剧情。若你在画面中缺失、被画成别人、严重遮挡、外貌漂移、动作情绪错误，
必须 REVISE，并给出 Artist 可直接执行的具体修改意见；全部正确则 PASS。
"""
        content = [{"type": "text", "text": prompt}]
        if reference_image_path:
            content.extend([
                {"type": "text", "text": "这是我的标准 neutral 立绘，用于核对身份与服装："},
                {"type": "image_url", "image_url": {"url": reference_image_path}},
            ])
        content.extend([
            {"type": "text", "text": "这是待审核的剧情 CG："},
            {"type": "image_url", "image_url": {"url": image_path}},
            {
                "type": "text",
                "text": (
                    '严格输出 JSON：{"decision":"PASS 或 REVISE",'
                    '"feedback":"具体审核意见"}'
                ),
            },
        ])
        try:
            critique = self.call_json_with_schema(
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": content},
                ],
                schema=ACTOR_IMAGE_CRITIQUE_SCHEMA,
                object_name="actor_cg_critique",
                temperature=self.config.TEMPERATURE,
            )
            decision = str(critique.get("decision", "REVISE")).strip().upper()
            feedback = str(critique.get("feedback", "")).strip()
            if decision == "PASS":
                logger.info(f"✅ 演员 {self.name} CG 审核通过")
                return "PASS"
            logger.warning(f"⚠️ 演员 {self.name} 要求修改 CG: {feedback}")
            return feedback or f"请修正 {self.name} 在 CG 中的角色一致性。"
        except Exception as exc:
            logger.error(f"❌ 演员 {self.name} CG 审核失败: {exc}")
            return "CG 审核失败，请重试。"

    def generate_expression_description(
        self,
        expression_name: str,
        neutral_image_path: Optional[str] = None
    ) -> str:
        """
        生成特定表情的视觉描述
        
        Args:
            expression_name: 表情名称 (如 'shy', 'happy')
            
        Returns:
            详细的视觉描述
        """
        prompt = self.config.EXPRESSION_DESCRIPTION_PROMPT.format(
            name=self.name,
            expression=expression_name,
            character_info=json.dumps(self.character_info, ensure_ascii=False, indent=2)
        )
        
        system_prompt = self._build_system_prompt()
        
        try:
            user_content: Any = prompt
            if neutral_image_path:
                user_content = [
                    {"type": "text", "text": prompt},
                    {"type": "text", "text": "这是该角色的 neutral 参考立绘："},
                    {"type": "image_url", "image_url": {"url": neutral_image_path}}
                ]

            description = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7
            )
            return description.strip()
        except Exception as e:
            logger.error(f"❌ 生成表情描述失败 ({expression_name}): {e}")
            return f"{self.name} with {expression_name} expression"
