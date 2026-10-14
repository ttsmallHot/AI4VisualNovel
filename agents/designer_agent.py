"""
Designer Agent
~~~~~~~~~~~~~~
策划 Agent - 负责草拟游戏整体设计文档
"""

import logging
import re
from typing import Dict, Any, Optional
from .base_agent import BaseAgent
import json

from .config import DesignerConfig
from .schemas import (
    GAME_OUTLINE_SCHEMA,
    NODE_GOAL_SCHEMA,
    ROLLING_PLAN_SCHEMA,
    SCENE_CONTRACT_SCHEMA,
    STORY_GRAPH_SCHEMA,
)

logger = logging.getLogger(__name__)


CLOSED_ENDING_COMPLETION_CONDITIONS = [
    "主要冲突解决后，必须明确呈现至少一个直接后果，不能在揭示真相或高潮动作处立即停止。",
    "必须通过关键角色可见的行动或明确台词，完成主要人物弧或人物关系的收束。",
    "必须建立事件后的新平衡状态，并以具有明确终止感的尾声画面、行动或落句结束故事。",
    "最后一个 Actor 回合必须是发生在认罪、完整动机、直接后果与人物弧收束之后的尾声落句；"
    "尾声之后不得再出现凶手供述、辩解、嘶喊或任何新的剧情内容。",
]


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

    def plan_initial_goal(
        self,
        core_gdd: Dict[str, Any],
        total_nodes: int,
        ending_mode: str = "closed",
    ) -> Dict[str, Any]:
        """Create the first one-node goal without choosing its scene or cast."""
        return self._plan_node_goal(
            core_gdd=core_gdd,
            world_state=core_gdd.get("initial_world_state", {}),
            agenda=core_gdd.get("initial_agenda", {}),
            previous_summaries=[],
            node_index=0,
            total_nodes=total_nodes,
            ending_mode=ending_mode,
            previous_tail={},
        )

    def plan_next_goal(
        self,
        core_gdd: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summaries: list[str],
        node_index: int,
        total_nodes: int,
        ending_mode: str = "closed",
        previous_tail: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create exactly one goal from committed story state."""
        return self._plan_node_goal(
            core_gdd=core_gdd,
            world_state=world_state,
            agenda=agenda,
            previous_summaries=previous_summaries,
            node_index=node_index,
            total_nodes=total_nodes,
            ending_mode=ending_mode,
            previous_tail=previous_tail or {},
        )

    def _plan_node_goal(
        self,
        core_gdd: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summaries: list[str],
        node_index: int,
        total_nodes: int,
        ending_mode: str,
        previous_tail: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        remaining_nodes = total_nodes - node_index
        closure_rules = ""
        if ending_mode == "closed":
            closure_rules = """
闭合结局规则：倒数第二个节点必须为收束做好直接准备，不得开启新的主要悬念；
最后一个节点的目标必须覆盖尚未完成的 global_goal.terminal_conditions，
并在该节点内结束核心冲突。
"""
        prompt = f"""你是滚动叙事的 Designer。为第 {node_index + 1}/{total_nodes} 个节点生成
一个且只有一个 NodeGoal。这个目标必须在当前节点内完成，不得跨节点。

【Core GDD 与不可变全局目标】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【已提交的世界状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【已提交的未解议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【前文摘要】
{json.dumps(previous_summaries, ensure_ascii=False, indent=2)}

【上一节点尾部锚点】
{json.dumps(previous_tail or {}, ensure_ascii=False, indent=2)}

还剩 {remaining_nodes} 个节点，结局模式是 {ending_mode}。
{closure_rules}
Designer 只决定“这个节点必须造成什么变化”。不得选新地点、不得选角色、
不得写场景过程、对话或后续节点。completion_conditions 必须是本节点内可验证的
结果；contributes_to_global_goal 要明确说明它怎样推进不可变的全局目标。

transition_contract 必须把当前节点与【上一节点尾部锚点】连接起来：
- 第一节点使用 relation_to_previous=root；
- 其余节点只能选择 acknowledgement/answer/continuation/elaboration/explanation/result/
  correction/contrast/topic_shift 之一；
- source_scene/source_speaker/source_anchor 必须逐字复制上一节点尾部锚点；
- bridge_requirement 只描述首个 Actor 回合必须实现的承接关系，不得规定具体台词；
- topic_shift 也必须说明由上一节点哪个结果触发，不能无理由切换调查目标。

只输出 JSON。完整 JSON Schema：
{json.dumps(NODE_GOAL_SCHEMA, ensure_ascii=False, indent=2)}
"""
        node_goal = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            schema=NODE_GOAL_SCHEMA,
            object_name="node_goal",
            temperature=0.45,
        )
        if ending_mode == "closed" and node_index == total_nodes - 1:
            conditions = [
                re.sub(
                    r"(?:与陈默)?DNA匹配|与陈默血型匹配|白手套上的血迹经比对确认为陈默的血",
                    "与现场血迹和既有痕迹相符，最终交由警方检验",
                    str(condition),
                )
                for condition in node_goal.get("completion_conditions", [])
            ]
            conditions = [
                condition.replace(
                    "等待警方到来",
                    "由实际进入现场的警方拘捕并完成证物移交",
                )
                for condition in conditions
            ]
            for condition in core_gdd.get("global_goal", {}).get(
                "terminal_conditions", []
            ):
                if condition not in conditions:
                    conditions.append(condition)
            for condition in CLOSED_ENDING_COMPLETION_CONDITIONS:
                if condition not in conditions:
                    conditions.append(condition)
            node_goal["completion_conditions"] = conditions
            node_goal["narrative_phase"] = "resolution"
            node_goal["goal"] = (
                str(node_goal.get("goal", "")).strip()
                + " 本节点必须推进到外部警方已经实际抵达现场、接管真凶并收取证据；"
                "不得停在等待警方、警方即将到达或天亮之前。"
            ).strip()
            node_goal["contributes_to_global_goal"] = (
                str(node_goal.get("contributes_to_global_goal", "")).strip()
                + " 终局时间边界以警方实际到场并完成移交为准。"
            ).strip()
        if ending_mode == "closed" and node_index == total_nodes - 2:
            terminal_conditions = core_gdd.get("global_goal", {}).get(
                "terminal_conditions", []
            )
            committed_context = json.dumps(
                {
                    "world_state": world_state,
                    "agenda": agenda,
                    "previous_summaries": previous_summaries,
                },
                ensure_ascii=False,
            )
            conditions = list(node_goal.get("completion_conditions", []))
            for item in self._enumerated_terminal_items(terminal_conditions):
                # Motive concepts belong in the final confession. Forcing their
                # verbatim disclosure one node early can directly contradict a
                # penultimate NodeGoal that preserves the culprit's denial.
                if item in {"竞争", "怨恨", "要挟"}:
                    continue
                if item not in committed_context:
                    condition = (
                        f"终局必需项“{item}”必须在本节点中被公平发现、明确命名并形成可见证据，"
                        "不得留到最终节点突然出现。"
                    )
                    if condition not in conditions:
                        conditions.append(condition)
            node_goal["completion_conditions"] = conditions
        return node_goal

    @staticmethod
    def _enumerated_terminal_items(terminal_conditions: list[str]) -> list[str]:
        items = []
        for condition in terminal_conditions:
            spans = re.findall(
                r'(?:^|[，：（(])([^，。；：()（）]*、[^，。；：()（）]+)(?=[，。；：）)]|$)',
                condition or "",
            )
            for span in spans:
                for raw_item in span.split("、"):
                    item = re.sub(r"等.*$", "", raw_item).strip()
                    if item and item not in items:
                        items.append(item)
        return items

    def plan_initial_scene(self, core_gdd: Dict[str, Any]) -> Dict[str, Any]:
        """根据 Core GDD 只规划第一场戏。"""
        prompt = f"""你是滚动叙事策划。根据 Core GDD 规划第一场戏。

{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

这次只规划一个场景，不得规划后续章节或完整剧情。第一场应直接建立初始冲突，
active_cast 必须使用 Core GDD 中的角色 name，location 必须使用 scenes 中的 name。
required_outcomes 应是本场必须实际发生的可观察结果；forbidden_outcomes 用于阻止
过早破案、无证据定罪或违反世界规则。

只输出 JSON。完整 JSON Schema：
{json.dumps(SCENE_CONTRACT_SCHEMA, ensure_ascii=False, indent=2)}
"""
        return self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            schema=SCENE_CONTRACT_SCHEMA,
            object_name="initial_scene_contract",
            temperature=0.5,
        )

    def plan_next_scene(
        self,
        core_gdd: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        current_contract: Dict[str, Any],
        current_scene: str,
        next_node_index: int,
        total_nodes: int,
    ) -> Dict[str, Any]:
        """归纳刚发生的场景，并只规划紧接着的一场戏。"""
        prompt = f"""你是滚动叙事策划。先根据剧本证据更新状态，再规划下一场戏。

【Core GDD】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【场景前世界状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【场景前未解决议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【刚完成的场景契约】
{json.dumps(current_contract, ensure_ascii=False, indent=2)}

【刚完成的剧本】
{current_scene}

接下来是第 {next_node_index + 1}/{total_nodes} 个节点。world_state 和 agenda 必须
返回更新后的完整对象；只能写入剧本中有明确证据的变化，不能把角色秘密自动变成
所有人都知道的事实。next_scene 只能规划紧接着的一场，必须推进至少一个未解决
冲突、角色关系或案件线索，不得直接跳到完整结局。角色与场景名称必须来自 Core GDD。

只输出 JSON。完整 JSON Schema：
{json.dumps(ROLLING_PLAN_SCHEMA, ensure_ascii=False, indent=2)}
"""
        return self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            schema=ROLLING_PLAN_SCHEMA,
            object_name="rolling_scene_plan",
            temperature=0.5,
        )
    
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

        user_prompt = self.config.GAME_OUTLINE_PROMPT.format(
            character_count=character_count,
            total_nodes=self.config.TOTAL_NODES,
            requirements=requirements if requirements else "无"
        )

        if locked_characters:
            user_prompt += (
                "\n\n【用户锁定角色（必须保留）】\n"
                f"{json.dumps(locked_characters, ensure_ascii=False, indent=2)}"
                "\n\n规则："
                "\n1. 这些角色必须出现在最终 characters 数组中，且 id/name 不得修改；"
                "\n2. 若锁定角色某些字段为空，可以补全；若字段已有值，不得改写；"
                "\n3. 剩余角色位可自由生成。"
            )

        if feedback and previous_game_outline:
            logger.info("🔧 大纲优化模式：根据反馈修改...")
            user_prompt += (
                f"\n\n【原大纲】\n{json.dumps(previous_game_outline, ensure_ascii=False, indent=2)}"
                f"\n\n【制作人反馈】\n{feedback}"
                "\n\n请修改大纲并保持 JSON 格式。"
            )

        outline = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            schema=GAME_OUTLINE_SCHEMA,
            object_name="game_outline",
            temperature=self.config.TEMPERATURE
        )

        outline.pop("story_graph", None)
        logger.info(f"✅ 游戏大纲生成完成: 《{outline.get('title', 'Unknown')}》")
        return outline

    def generate_story_graph_from_outline(
        self,
        game_outline: Dict[str, Any],
        feedback: str = None
    ) -> Dict[str, Any]:
        """Step2: 根据 Step1 的分组大纲生成 story_graph。"""
        logger.info("🧭 策划正在生成 story_graph（Step2）...")

        prompt = self.config.STORY_GRAPH_FROM_OUTLINE_PROMPT.format(
            total_nodes=self.config.TOTAL_NODES,
            outline_json=json.dumps(game_outline, ensure_ascii=False, indent=2)
        )

        if feedback:
            prompt += (
                f"\n\n【制作人对 Step2 的反馈】\n{feedback}"
                "\n\n请在保持 JSON 结构与硬约束不变的前提下，修正 story_graph。"
            )

        story_graph = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            schema=STORY_GRAPH_SCHEMA,
            object_name="story_graph",
            temperature=self.config.TEMPERATURE
        )

        if len(story_graph.get("nodes", {})) != self.config.TOTAL_NODES:
            raise ValueError(
                f"story_graph 节点数不匹配，期望 {self.config.TOTAL_NODES}，实际 {len(story_graph.get('nodes', {}))}"
            )

        logger.info("✅ story_graph 生成完成")
        return story_graph
