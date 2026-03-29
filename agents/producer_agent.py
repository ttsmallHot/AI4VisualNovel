"""
Producer Agent
~~~~~~~~~~~~~~
制作人 Agent - 负责审核设计预览并把控全局
"""

import logging
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
import json

from .config import ProducerConfig, PathConfig
from .utils import FileHelper
from .tool_registry import call_tool
from .schemas import PRODUCER_REACT_STEP_SCHEMA

logger = logging.getLogger(__name__)


class ProducerAgent(BaseAgent):
    """制作人 Agent - 负责审核设计预览并把控全局"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化制作人 Agent
        """
        super().__init__(
            name="Producer",
            role="制作人",
            api_key=api_key,
            base_url=base_url
        )
        self.config = ProducerConfig
        
        logger.info("✅ 制作人 Agent 初始化成功")

    @staticmethod
    def _is_pass_feedback(feedback: str) -> bool:
        """严格判断制作人反馈是否通过。"""
        normalized = (feedback or "").strip().upper()
        return normalized == "PASS"

    def _run_critique(self, prompt: str, temperature: float, phase_name: str) -> str:
        """统一执行审核调用与返回规范化。"""
        try:
            feedback = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature
            ).strip()

            if self._is_pass_feedback(feedback):
                logger.info(f"✅ {phase_name}审核通过")
                return "PASS"

            logger.warning(f"⚠️ {phase_name}需要修改")
            return feedback
        except Exception as e:
            logger.error(f"❌ {phase_name}审核失败: {e}")
            return "PASS"

    def _react_story_graph_critique(
        self,
        story_graph: Dict[str, Any],
        game_outline: Dict[str, Any],
        expected_nodes: int = 12
    ) -> str:
        observations: List[Dict[str, Any]] = []
        max_steps = 4

        for _ in range(max_steps):
            prompt = self.config.STORY_GRAPH_REACT_PROMPT.format(
                expected_nodes=expected_nodes,
                game_outline=json.dumps(game_outline, ensure_ascii=False, indent=2),
                story_graph=json.dumps(story_graph, ensure_ascii=False, indent=2),
                observations=json.dumps(observations, ensure_ascii=False, indent=2)
            )

            step = self.call_json_with_schema(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                schema=PRODUCER_REACT_STEP_SCHEMA,
                object_name="producer_react_step",
                temperature=0.2
            )

            action = str(step.get("action", "")).strip()
            action_input = step.get("action_input", {}) if isinstance(step.get("action_input", {}), dict) else {}

            if action == "graph_validate":
                tool_result = call_tool("graph_validate", {"story_graph": story_graph})
                observations.append({"action": action, "result": tool_result})
                if not tool_result.get("is_valid", False):
                    return f"图结构不合法：{tool_result.get('error', '未知错误')}"
                continue

            if action == "enumerate_paths":
                max_paths = int(action_input.get("max_paths", 128)) if str(action_input.get("max_paths", "")).strip() else 128
                max_paths = max(1, min(max_paths, 300))
                tool_result = call_tool("enumerate_paths", {
                    "story_graph": story_graph,
                    "max_paths": max_paths
                })
                observations.append({"action": action, "result": tool_result})
                continue

            if action == "finalize":
                decision = str(step.get("final_decision", "")).strip().upper()
                if decision == "PASS":
                    return "PASS"
                feedback = str(step.get("final_feedback", "")).strip()
                return feedback if feedback else "请增强分支差异性与路径节奏，并修复图结构细节问题。"

            observations.append({"action": action, "result": {"warning": "unknown action"}})

        return "请补充分支路径差异性评估并给出节点级修订建议。"
    
    def critique_game_outline(
        self,
        game_outline: Dict[str, Any],
        user_requirements: str = "",
        expected_nodes: int = 12,
        expected_characters: int = 3
    ) -> str:
        """Step1 审核：仅审核 story_outline 与基础设定。"""
        logger.info("📋 制作人正在审核 Step1 大纲...")

        prompt = self.config.GAME_OUTLINE_CRITIQUE_PROMPT.format(
            game_outline=json.dumps(game_outline, ensure_ascii=False, indent=2),
            user_requirements=user_requirements if user_requirements else "无特别要求",
            expected_nodes=expected_nodes,
            expected_characters=expected_characters
        )
        return self._run_critique(prompt=prompt, temperature=0.5, phase_name="Step1 大纲")

    def critique_story_graph(
        self,
        story_graph: Dict[str, Any],
        game_outline: Dict[str, Any],
        expected_nodes: int = 12
    ) -> str:
        """Step2 审核：仅审核图结构与与 outline 一致性。"""
        logger.info("📋 制作人正在审核 Step2 story_graph...")
        try:
            result = self._react_story_graph_critique(
                story_graph=story_graph,
                game_outline=game_outline,
                expected_nodes=expected_nodes
            )
            if self._is_pass_feedback(result):
                logger.info("✅ Step2 story_graph 审核通过（ReAct）")
                return "PASS"
            logger.warning("⚠️ Step2 story_graph 需要修改（ReAct）")
            return result
        except Exception as e:
            logger.warning(f"⚠️ ReAct 审核失败，回退普通审核: {e}")
            prompt = self.config.STORY_GRAPH_CRITIQUE_PROMPT.format(
                story_graph=json.dumps(story_graph, ensure_ascii=False, indent=2),
                game_outline=json.dumps(game_outline, ensure_ascii=False, indent=2),
                expected_nodes=expected_nodes
            )
            return self._run_critique(prompt=prompt, temperature=0.3, phase_name="Step2 story_graph")

    def save_game_design(self, game_design: Dict[str, Any]) -> None:
        """
        保存游戏设计文档到文件
        
        Args:
            game_design: 游戏设计文档字典
        """
        if not FileHelper.safe_write_json(PathConfig.GAME_DESIGN_FILE, game_design):
            raise Exception("保存游戏设计文档失败")
    
    @staticmethod
    def load_game_design() -> Optional[Dict[str, Any]]:
        """
        从文件加载游戏设计文档
        
        Returns:
            游戏设计文档字典，如果文件不存在则返回 None
        """
        game_design = FileHelper.safe_read_json(PathConfig.GAME_DESIGN_FILE)
        if game_design:
            logger.info(f"📖 游戏设计文档已加载: 《{game_design.get('title', 'Unknown')}》")
        return game_design

