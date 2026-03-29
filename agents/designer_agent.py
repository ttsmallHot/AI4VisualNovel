"""
Designer Agent
~~~~~~~~~~~~~~
策划 Agent - 负责草拟游戏整体设计文档
"""

import logging
from typing import Dict, Any, Optional
from .base_agent import BaseAgent
import json
from copy import deepcopy

from .config import DesignerConfig
from .utils import JSONParser

logger = logging.getLogger(__name__)


class DesignerAgent(BaseAgent):
    """策划 Agent - 游戏设计文档草拟者"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化策划 Agent
        """
        super().__init__(
            name="Designer",
            role="策划",
            api_key=api_key,
            base_url=base_url
        )
        self.config = DesignerConfig
        
        logger.info("✅ 策划 Agent 初始化成功")
    
    def generate_game_outline(
        self,
        character_count: int = None,
        requirements: str = "",
        feedback: str = None,
        previous_game_outline: Dict[str, Any] = None,
        locked_characters: Optional[list[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Step1: 只生成不含 story_graph 的设计大纲。"""
        character_count = character_count or self.config.DEFAULT_CHARACTER_COUNT

        logger.info("📝 策划正在生成游戏大纲（Step1）...")

        requirements_text = requirements if requirements else "无"

        if locked_characters:
            requirements_text += (
                "\n\n【用户锁定角色（必须保留）】\n"
                f"{json.dumps(locked_characters, ensure_ascii=False, indent=2)}"
                "\n\n规则："
                "\n1. 这些角色必须出现在最终 characters 数组中，且 id/name 不得修改；"
                "\n2. 若锁定角色某些字段为空，可以补全；若字段已有值，不得改写；"
                "\n3. 剩余角色位可自由生成。"
            )

        user_prompt = self.config.GAME_OUTLINE_PROMPT.format(
            character_count=character_count,
            total_nodes=self.config.TOTAL_NODES,
            requirements=requirements_text
        )

        if feedback and previous_game_outline:
            logger.info("🔧 大纲优化模式：根据反馈修改...")
            patch_prompt = self.config.GAME_OUTLINE_PATCH_PROMPT.format(
                previous_outline_json=json.dumps(previous_game_outline, ensure_ascii=False, indent=2),
                feedback=feedback
            )

            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": patch_prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )

            partial_update = JSONParser.parse_ai_response(content)
            if not isinstance(partial_update, dict):
                raise ValueError("增量修改输出必须为 JSON 对象")

            outline = self._deep_merge_dict(previous_game_outline, partial_update)
        else:
            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )

            outline = JSONParser.parse_ai_response(content)
        required_fields = ["title", "background", "art_style", "story_outline", "characters", "scenes"]
        if not JSONParser.validate_required_fields(outline, required_fields):
            raise ValueError("生成的游戏大纲缺少必需字段")

        groups = outline.get("story_outline", {}).get("groups", [])
        if not isinstance(groups, list) or len(groups) == 0:
            raise ValueError("story_outline.groups 不能为空")
        for group in groups:
            if not isinstance(group, dict) or "group_id" not in group or "group_outline" not in group:
                raise ValueError("每个 group 必须包含 group_id 和 group_outline")

        outline.pop("story_graph", None)
        logger.info(f"✅ 游戏大纲生成完成: 《{outline.get('title', 'Unknown')}》")
        return outline

    def _deep_merge_dict(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并字典：patch 覆盖 base，同名对象递归合并，数组整段替换。"""
        merged = deepcopy(base)
        for key, value in patch.items():
            if key == "story_graph":
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    def generate_story_graph_from_outline(
        self,
        game_outline: Dict[str, Any],
        feedback: str = None,
        previous_story_graph: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Step2: 根据 Step1 的分组大纲生成 story_graph。"""
        logger.info("🧭 策划正在生成 story_graph（Step2）...")

        if feedback and previous_story_graph:
            patch_prompt = self.config.STORY_GRAPH_PATCH_PROMPT.format(
                previous_story_graph_json=json.dumps(previous_story_graph, ensure_ascii=False, indent=2),
                feedback=feedback
            )

            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": patch_prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )

            partial_update = JSONParser.parse_ai_response(content)
            if not isinstance(partial_update, dict):
                raise ValueError("Step2 增量修改输出必须为 JSON 对象")
            story_graph = self._deep_merge_dict(previous_story_graph, partial_update)
        else:
            prompt = self.config.STORY_GRAPH_FROM_OUTLINE_PROMPT.format(
                total_nodes=self.config.TOTAL_NODES,
                outline_json=json.dumps(game_outline, ensure_ascii=False, indent=2)
            )

            if feedback:
                prompt += (
                    f"\n\n【制作人对 Step2 的反馈】\n{feedback}"
                    "\n\n请在保持 JSON 结构与硬约束不变的前提下，修正 story_graph。"
                )

            content = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.TEMPERATURE,
                json_mode=True
            )

            story_graph = JSONParser.parse_ai_response(content)
        required_fields = ["nodes", "edges"]
        if not JSONParser.validate_required_fields(story_graph, required_fields):
            raise ValueError("生成的 story_graph 缺少 nodes 或 edges")

        if "root" not in story_graph.get("nodes", {}):
            raise ValueError("story_graph.nodes 必须包含 root 节点")

        if len(story_graph.get("nodes", {})) != self.config.TOTAL_NODES:
            raise ValueError(
                f"story_graph 节点数不匹配，期望 {self.config.TOTAL_NODES}，实际 {len(story_graph.get('nodes', {}))}"
            )

        logger.info("✅ story_graph 生成完成")
        return story_graph
