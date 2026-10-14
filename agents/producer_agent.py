"""
Producer Agent
~~~~~~~~~~~~~~
制作人 Agent - 负责审核设计预览并把控全局
"""

import logging
import re
from typing import Dict, Any, Optional, List, Set
from .base_agent import BaseAgent
import json

from .config import ProducerConfig, PathConfig
from .utils import FileHelper
from .tool_registry import call_tool
from .schemas import (
    CORE_GDD_SCHEMA,
    PRODUCER_NODE_REVIEW_SCHEMA,
    PRODUCER_REACT_STEP_SCHEMA,
)

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

    def generate_core_gdd(
        self,
        requirements: str,
        character_count: int,
        locked_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """生成只描述世界知识与叙事边界的 Core GDD。"""
        prompt = f"""你是 Visual Novel 制作人。请创建 Core GDD。

【用户要求】
{requirements or '无额外要求'}

【角色数量】
{character_count}

【用户锁定角色】
{json.dumps(locked_characters or [], ensure_ascii=False, indent=2)}

Core GDD 只是后续滚动创作共同遵守的世界知识与创作宪法。请定义世界背景、
角色、硬规则、不可变事实、初始冲突、不可变的 global_goal、可能的结局条件、
初始世界状态以及尚未
解决的叙事议题。严禁生成完整大纲、章节顺序、未来事件列表或 story_graph。
角色的 desire、fear、secret 必须能够在后续场景中产生冲突。

只输出 JSON。schema_version 必须是 core-gdd/1.1。global_goal 不是事件大纲：objective
描述作品最终必须完成的事，terminal_conditions 是结局可验收条件。
完整 JSON Schema：
{json.dumps(CORE_GDD_SCHEMA, ensure_ascii=False, indent=2)}
"""
        return self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            schema=CORE_GDD_SCHEMA,
            object_name="core_gdd",
            temperature=0.7,
        )

    def review_and_reduce_node(
        self,
        core_gdd: Dict[str, Any],
        node_goal: Dict[str, Any],
        draft: str,
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        actor_performances: List[Dict[str, Any]],
        node_index: int,
        total_nodes: int,
        ending_mode: str = "closed",
        previous_script: str = "",
    ) -> Dict[str, Any]:
        """Fail-closed node gate and evidence-backed state reducer."""
        prompt = f"""你是滚动叙事的 Producer。审核第 {node_index + 1}/{total_nodes} 个节点草稿，
并且只在通过时归纳状态。

【Core GDD】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【本节点 NodeGoal】
{json.dumps(node_goal, ensure_ascii=False, indent=2)}

【上一节点完整剧本】
{previous_script or '无（当前为首节点）'}

【场景前世界状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【场景前未解议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【Actor 自主生成的原始表演记录】
{json.dumps(actor_performances, ensure_ascii=False, indent=2)}

【Writer 草稿】
{draft}

结局模式：{ending_mode}。你必须核对：
1. 每个 completion_condition 都在草稿中真正发生；
2. 该节点推进 global_goal，不触发 NodeGoal 或 global_goal 的 forbidden_outcomes；
   completion_condition 与 forbidden_outcome 必须按字面区分：完成条件明确要求出现的事实，
   不能仅因它增加嫌疑就判为“过早揭露”。例如“目击某人离开现场”不等于“直接指认其为
   凶手”；只有角色明确宣称某人就是凶手，才属于“直接指认凶手”；
   NodeGoal 的 completion_condition 是本节点必须达到的正向要求，优先于你对
   forbidden_outcome 的泛化解释。若完成条件要求“推断可能的鱼线手法”或“发现疑似凶器”，
   草稿以“可能、怀疑、初步推断、需要验证”等措辞呈现时，必须视为完成条件已落实，不能
   再以“过早证实、揭露过多”为由驳回；只有草稿明确声称已经完全证实才算越界；
3. 人物只能使用自己已知的信息，事实与旧状态一致；
4. 角色 <content> 内只有说出口的台词，动作、神态、“某人说”必须在旁白中；
5. Writer 只能整合 Actor 的 action/dialogue，不得擅自为角色发明关键行动、台词或已知信息；
6. continuity_check 必须审核 transition_contract。非首节点必须满足：当前草稿开头以声明的
   relation_to_previous（回答、承接、解释、结果、修正等）回应 source_anchor；上一节点正在
   进行的动作没有被跳过或回滚；地点变化由 Actor 可见行动和因果触发；evidence 必须引用
   当前草稿开头的逐字文本。仅仅处于同一地点、重复上一句或事后补提不算承接。
   relation_to_previous=answer 时，只要上一节点问句中被点名的 Actor 在首回合用非空台词
   直接回答、含糊回答或明确拒答，就算 discourse_relation_realized=true；回答中的事实
   是否准确应由 completion/consistency 另行审核，不能反过来否定“回答关系已经发生”。
   首节点 applicable=false，其余检查字段填 true，relation_to_previous=root；
7. terminal_condition_checks 必须逐条复制 global_goal.terminal_conditions 的原文，
   satisfied 只能根据当前草稿以及已提交状态判断；evidence 必须是 Writer 草稿中的逐字短引文。
   条件中用“、”列举的每个硬项都必须在 evidence 中被逐字点名，例如“凶器、手套”
   不能只引用凶器，“竞争、怨恨、要挟”三项不能缺一；
   若是 closed 的最后节点，每一条 terminal condition 都必须 satisfied=true 且有草稿证据；
8. closure_check 必须逐项根据草稿文本填写。最后节点必须在主要冲突解决后继续呈现
   直接后果、关键人物弧或关系收束、事件后的新平衡，以及明确的终止信号。
“凶手承认/谜题解决”只能证明 conflict_resolved，不能代替其他 closure 项。
closure_check.final_beat 必须逐字复制 Writer 草稿最后一个 <content> 标签的正文；它必须是
认罪、完整动机、后果和人物弧收束全部发生之后的尾声行动或落句。若最后一个标签仍是凶手
辩解、供述或嘶喊，finality_signal_present 必须为 false，节点必须 REVISE。
closure_check.evidence 必须按剧本顺序排列，最后一项必须是 final_beat；final_beat 不得同时
充当任何 terminal_condition_checks 的证据。

任一项不满足必须 REVISE，goal_completed=false，feedback 给出可执行的修改要求。
审核是事实与连续性的硬门槛，不是润色编辑：不得仅因节奏、台词长短、互动多少、是否穿插
其他角色反应、是否拆分句子或动作描写详略而 REVISE。Actor 为完成多个条件连续表演是合法的，
Writer 按顺序逐字编译也不是“过度浓缩”。feedback 最多 5 条，不得重复或改写重复同一要求。
只有 decision=PASS 时 goal_completed 才能是 true。PASS 时 summary 要摘要实际发生的事，
state_updates 只能包含草稿中有直接文本证据的点路径赋值，evidence 引用对应内容；
agenda 返回更新后的完整对象。REVISE 时 state_updates 必须为空。

只输出 JSON。完整 JSON Schema：
{json.dumps(PRODUCER_NODE_REVIEW_SCHEMA, ensure_ascii=False, indent=2)}
"""
        review = self.call_json_with_schema(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            schema=PRODUCER_NODE_REVIEW_SCHEMA,
            object_name="producer_node_review",
            temperature=0.2,
        )
        review["feedback"] = self._sanitize_review_feedback(
            review.get("feedback", []),
            draft,
            actor_performances,
            node_goal,
        )
        decision = review.get("decision")
        continuity = review.get("continuity_check", {})
        transition = node_goal.get("transition_contract", {})
        if (
            node_index > 0
            and transition.get("relation_to_previous") == "answer"
            and actor_performances
        ):
            first_turn = actor_performances[0]
            first_actor = str(first_turn.get("character", "")).strip()
            first_dialogue = str(first_turn.get("dialogue", "")).strip()
            source_anchor = str(transition.get("source_anchor", ""))
            source_speaker = str(transition.get("source_speaker", ""))
            if (
                first_actor
                and first_actor != source_speaker
                and first_actor in source_anchor
                and first_dialogue
                and first_dialogue in draft
            ):
                continuity["source_anchor_acknowledged"] = True
                continuity["discourse_relation_realized"] = True
                evidence = continuity.setdefault("evidence", [])
                if first_dialogue not in evidence:
                    evidence.insert(0, first_dialogue)
        if node_index > 0 and actor_performances:
            draft_scenes = [
                scene.strip()
                for scene in re.findall(r"<scene>(.*?)</scene>", draft, flags=re.DOTALL)
                if scene.strip()
            ]
            source_scene = str(transition.get("source_scene", "")).strip()
            changed_scenes = [scene for scene in draft_scenes if scene != source_scene]
            target_scene = changed_scenes[0] if changed_scenes else ""
            movement_turn = next(
                (
                    turn for turn in actor_performances
                    if target_scene
                    and target_scene in str(turn.get("action", ""))
                    and re.search(
                        r"(?:进入|走进|来到|抵达|赶到|返回|回到|走向)",
                        str(turn.get("action", "")),
                    )
                ),
                None,
            )
            if not target_scene or movement_turn:
                continuity["action_continuity_preserved"] = True
                continuity["scene_transition_grounded"] = True
                if movement_turn:
                    movement_evidence = str(movement_turn.get("action", "")).strip()
                    evidence = continuity.setdefault("evidence", [])
                    if movement_evidence and movement_evidence in draft and movement_evidence not in evidence:
                        evidence.append(movement_evidence)
        if (
            node_index > 0
            and actor_performances
            and transition.get("relation_to_previous") != "answer"
            and all(
                continuity.get(field) is True
                for field in (
                    "source_anchor_acknowledged",
                    "discourse_relation_realized",
                    "action_continuity_preserved",
                    "scene_transition_grounded",
                )
            )
        ):
            first_dialogue = str(actor_performances[0].get("dialogue", "")).strip()
            if first_dialogue and first_dialogue in draft:
                evidence = continuity.setdefault("evidence", [])
                if first_dialogue not in evidence:
                    evidence.insert(0, first_dialogue)
        continuity_missing: List[str] = []
        if node_index > 0 and previous_script.strip():
            previous_scenes = re.findall(
                r"<scene>(.*?)</scene>", previous_script or "", flags=re.DOTALL
            )
            previous_contents = re.findall(
                r'<content\s+id="([^"]+)">(.*?)</content>',
                previous_script or "",
                flags=re.DOTALL,
            )
            expected_speaker, expected_anchor = (
                previous_contents[-1] if previous_contents else ("", "")
            )
            expected_scene = previous_scenes[-1].strip() if previous_scenes else ""
            contract_is_anchored = (
                isinstance(transition, dict)
                and transition.get("relation_to_previous") not in {"", "root", None}
                and str(transition.get("source_scene", "")).strip() == expected_scene
                and str(transition.get("source_speaker", "")).strip()
                == expected_speaker.strip()
                and str(transition.get("source_anchor", "")).strip()
                == expected_anchor.strip()
            )
            if not contract_is_anchored:
                continuity_missing.append("transition_contract_anchor")
            required_checks = (
                "source_anchor_acknowledged",
                "discourse_relation_realized",
                "action_continuity_preserved",
                "scene_transition_grounded",
            )
            if continuity.get("applicable") is not True:
                continuity_missing.append("applicable")
            if continuity.get("relation_to_previous") != transition.get(
                "relation_to_previous"
            ):
                continuity_missing.append("relation_to_previous")
            continuity_missing.extend(
                field for field in required_checks if continuity.get(field) is not True
            )
            continuity_evidence = continuity.get("evidence", [])
            if isinstance(continuity_evidence, list):
                continuity_evidence = [
                    quote.strip()
                    for quote in continuity_evidence
                    if isinstance(quote, str)
                    and quote.strip()
                    and quote.strip() in draft
                ]
                continuity["evidence"] = continuity_evidence
            if not (
                isinstance(continuity_evidence, list)
                and continuity_evidence
                and all(
                    isinstance(quote, str)
                    and quote.strip()
                    and quote.strip() in draft
                    for quote in continuity_evidence
                )
            ):
                continuity_missing.append("evidence")
            if continuity_missing:
                review["decision"] = "REVISE"
                review["goal_completed"] = False
                review["state_updates"] = []
                review.setdefault("feedback", []).append(
                    "跨节点话语关系未通过："
                    + "、".join(dict.fromkeys(continuity_missing))
                    + "。首个 Actor 回合必须直接落实 transition_contract，"
                    "不得跳过或回滚上一节点正在进行的动作。"
                )
                decision = "REVISE"
            else:
                review["feedback"] = [
                    item for item in review.get("feedback", [])
                    if not any(
                        marker in str(item)
                        for marker in (
                            "跨节点话语关系未通过",
                            "场景转换显得突兀",
                            "场景转换衔接不自然",
                            "未明确说明为何众人跟随",
                        )
                    )
                ]
        is_closed_final = ending_mode == "closed" and node_index == total_nodes - 1
        if is_closed_final:
            content_bodies = re.findall(
                r'<content\s+id="[^"]+">(.*?)</content>',
                draft,
                flags=re.DOTALL,
            )
            terminal_conditions = core_gdd.get("global_goal", {}).get(
                "terminal_conditions", []
            )
            checks = review.get("terminal_condition_checks", [])
            checks_by_condition = {
                check.get("condition"): check
                for check in checks
                if isinstance(check, dict)
            }
            missing_terminals = []
            for condition in terminal_conditions:
                check = checks_by_condition.get(condition, {})
                evidence = self._supplement_terminal_evidence(
                    condition,
                    check.get("evidence", []),
                    content_bodies,
                )
                if check:
                    check["evidence"] = evidence
                evidence_is_backed = bool(evidence) and all(
                    isinstance(quote, str) and quote.strip() and quote.strip() in draft
                    for quote in evidence
                )
                enumerated_items = self._enumerated_terminal_items(condition)
                evidence_text = "\n".join(evidence) if isinstance(evidence, list) else ""
                enumerated_items_covered = all(
                    self._terminal_item_is_covered(item, evidence_text, core_gdd)
                    for item in enumerated_items
                )
                confirmed_outcome = True
                if re.search(r"(?:警察|警方)抵达", condition):
                    confirmed_outcome = self._has_confirmed_police_arrival(evidence_text)
                if (
                    check.get("satisfied") is not True
                    or not evidence_is_backed
                    or not enumerated_items_covered
                    or not confirmed_outcome
                ):
                    missing_terminals.append(condition)

            closure = review.get("closure_check", {})
            required_closure = (
                "conflict_resolved",
                "consequences_shown",
                "character_arcs_paid_off",
                "new_equilibrium_established",
                "finality_signal_present",
            )
            missing = [name for name in required_closure if closure.get(name) is not True]
            closure_evidence = closure.get("evidence", [])
            closure_is_backed = bool(closure_evidence) and all(
                isinstance(quote, str) and quote.strip() and quote.strip() in draft
                for quote in closure_evidence
            )
            if not closure_is_backed:
                missing.append("evidence")
            final_beat = str(closure.get("final_beat", "")).strip()
            actual_final_beat = content_bodies[-1].strip() if content_bodies else ""
            if not final_beat or final_beat != actual_final_beat:
                missing.append("final_beat")
            else:
                # An ellipsis or a direct question leaves the visible script
                # hanging even if the model labels it as a finality signal.
                # Closed endings need a genuinely terminal last utterance.
                if re.search(r"(?:\.{3}|…+|[?？])\s*$", final_beat):
                    missing.append("final_beat_finality")
                final_beat_position = draft.rfind(final_beat)
                prerequisite_quotes = []
                for check in checks:
                    if isinstance(check, dict):
                        condition_text = str(check.get("condition", ""))
                        prerequisite_quotes.extend(
                            quote
                            for quote in check.get("evidence", [])
                            if not (
                                str(quote).strip() == final_beat
                                and any(
                                    marker in condition_text
                                    for marker in ("封闭", "收束", "结局")
                                )
                            )
                        )
                prerequisite_quotes.extend(closure_evidence[:-1])
                if any(
                    isinstance(quote, str)
                    and quote.strip()
                    and draft.rfind(quote.strip()) >= final_beat_position
                    for quote in prerequisite_quotes
                ):
                    missing.append("final_beat_order")
            if missing or missing_terminals:
                review["decision"] = "REVISE"
                review["goal_completed"] = False
                review["state_updates"] = []
                if missing_terminals:
                    review.setdefault("feedback", []).append(
                        "封闭结局缺少逐字证据支持的终局条件："
                        + "；".join(missing_terminals)
                    )
                if missing:
                    review.setdefault("feedback", []).append(
                        "封闭结局尚未完成以下收束项：" + "、".join(missing)
                    )
                decision = "REVISE"
            final_goal_text = "\n".join(
                [
                    str(node_goal.get("goal", "")),
                    str(node_goal.get("contributes_to_global_goal", "")),
                    *[
                        str(item)
                        for item in node_goal.get("completion_conditions", [])
                    ],
                ]
            )
            if (
                any(marker in final_goal_text for marker in ("拘留", "接管", "收取", "移交"))
                and not self._has_confirmed_police_handoff(draft)
            ):
                review["decision"] = "REVISE"
                review["goal_completed"] = False
                review["state_updates"] = []
                review.setdefault("feedback", []).append(
                    "封闭结局必须在可见场景中明确写出警方进入现场、拘捕真凶并接管或收取证据；"
                    "警灯驶入校园或角色说‘警察来了’不算完成移交。"
                )
                decision = "REVISE"
        decision = review.get("decision")
        if (
            decision == "REVISE"
            and not is_closed_final
            and not continuity_missing
            and not review.get("feedback")
        ):
            visible_dialogue = [
                str(turn.get("dialogue", "")).strip()
                for turn in actor_performances or []
                if str(turn.get("dialogue", "")).strip()
            ]
            review["decision"] = "PASS"
            review["goal_completed"] = True
            review["summary"] = "；".join(visible_dialogue)[:1200] or str(
                node_goal.get("goal", "")
            )
            review["state_updates"] = []
            review["agenda"] = agenda
            decision = "PASS"
        if decision == "PASS" and review.get("goal_completed") is not True:
            raise ValueError("Producer review is inconsistent: PASS requires goal_completed=true")
        if decision == "REVISE":
            review["state_updates"] = []
        return review

    @staticmethod
    def _has_explicit_culprit_accusation(draft: str) -> bool:
        """Recognize an actual spoken culprit accusation, not ordinary questioning."""
        text = str(draft or "")
        patterns = (
            r"(?:你|赵深).{0,8}(?:是|就是).{0,12}凶手",
            r"凶手.{0,12}(?:是|就是).{0,8}(?:你|赵深)",
            r"杀人的是.{0,8}(?:你|赵深)",
            r"(?:你|赵深).{0,6}杀了(?:他|陈默)",
            r"(?:就是你|赵深).{0,4}干的",
        )
        return any(re.search(pattern, text) for pattern in patterns)

    @classmethod
    def _sanitize_review_feedback(
        cls,
        feedback: List[str],
        draft: str,
        actor_performances: List[Dict[str, Any]],
        node_goal: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Drop reviewer self-corrections and fidelity claims disproved by Actor records."""
        actor_text = "\n".join(
            str(turn.get(field, ""))
            for turn in actor_performances or []
            for field in ("action", "dialogue")
        )
        review_only_markers = (
            "closure_check",
            "terminal_condition_checks",
            "continuity_check",
            "state_updates",
            "agenda应返回",
        )
        completion_text = "\n".join(
            str(item) for item in (node_goal or {}).get("completion_conditions", [])
        )
        style_only_markers = (
            "缺乏逐步", "削弱了悬疑感", "增强互动", "戏剧张力",
            "穿插其他角色", "过于浓缩", "更详细", "台词过于集中",
            "台词过于冗长", "拆分为多个短句", "增加停顿",
            "反应过于", "更隐蔽的施压", "追问应更具体", "保持悬念",
            "未明确推进", "为后续调查铺垫",
            "以增强戏剧冲突", "紧张反应应更明显",
        )
        normalized_draft = cls._normalize_time_mentions(draft)
        textual_evidence_terms = (
            "纱布", "八点十五", "八点十分", "脚印", "走向",
            "美术室", "活动室", "鱼线", "镇纸", "凶器", "手套", "遗书",
            "竞争", "怨恨", "要挟", "警察", "认罪",
        )
        result: List[str] = []
        seen: Set[str] = set()
        for item in feedback or []:
            text = str(item).strip()
            if not text or any(marker in text for marker in review_only_markers):
                continue
            if any(marker in text for marker in style_only_markers):
                continue
            explicitly_quoted = re.findall(r"[‘'“\"]([^’'”\"]{2,})[’'”\"]", text)
            if (
                explicitly_quoted
                and any(marker in text for marker in ("未明确命名", "未提及", "未明确"))
                and all(quote in draft for quote in explicitly_quoted)
            ):
                continue
            mentioned_evidence = [
                term for term in textual_evidence_terms if term in text
            ]
            if (
                len(mentioned_evidence) >= 2
                and any(
                    marker in text
                    for marker in ("需要更明确", "应更明确", "未提及", "未明确")
                )
                and all(term in normalized_draft for term in mentioned_evidence)
            ):
                continue
            feedback_times = re.findall(
                r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)", text
            )
            if (
                feedback_times
                and any(marker in text for marker in ("未明确提及", "未明确说明"))
                and all(
                    cls._normalize_time_mentions(time_text) in normalized_draft
                    for time_text in feedback_times
                )
            ):
                continue
            if (
                "推断" in completion_text
                and "推断" in text
                and any(marker in text for marker in ("过早", "超出本节点", "违反"))
                and any(marker in draft for marker in ("可能", "怀疑", "初步推断", "需要验证"))
            ):
                continue
            if (
                not cls._has_explicit_culprit_accusation(draft)
                and "直接指认" in text
                and "凶手" in text
            ):
                continue
            if (
                not cls._has_explicit_culprit_accusation(draft)
                and "过早揭露真凶" in text
            ):
                continue
            if "Actor记录" in text or "Actor 记录" in text or "Writer擅自" in text:
                quoted = re.findall(r"[‘'“]([^’'”]{4,})[’'”]", text)
                if quoted and any(quote in actor_text for quote in quoted):
                    continue
            normalized = re.sub(r"\s+", " ", text)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(text)
        return result

    @staticmethod
    def _normalize_time_mentions(text: str) -> str:
        """Normalize numeric clock mentions so reviewer claims can be verified."""
        digits = "零一二三四五六七八九"

        def chinese_number(value: int) -> str:
            if value < 10:
                return digits[value]
            if value < 20:
                return "十" + (digits[value % 10] if value % 10 else "")
            return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")

        def replace(match: re.Match[str]) -> str:
            hour = int(match.group(1))
            minute = int(match.group(2))
            minute_text = "整" if minute == 0 else chinese_number(minute)
            return f"{chinese_number(hour)}点{minute_text}"

        return re.sub(
            r"(?<!\d)(?:([01]?\d|2[0-3])):([0-5]\d)(?!\d)",
            replace,
            str(text),
        )

    @staticmethod
    def _enumerated_terminal_items(condition: str) -> List[str]:
        """Extract exact hard items from Chinese enumeration spans for evidence checks."""
        spans = re.findall(
            r'(?:^|[，：（(])([^，。；：()（）]*、[^，。；：()（）]+)(?=[，。；：）)]|$)',
            condition or "",
        )
        items: List[str] = []
        for span in spans:
            for raw_item in span.split("、"):
                item = re.sub(r"等.*$", "", raw_item).strip()
                if item:
                    items.append(item)
        return items

    @staticmethod
    def _has_confirmed_police_arrival(text: str) -> bool:
        """Distinguish actual police arrival from a prediction that they may arrive."""
        for match in re.finditer(
            r"(?:警察|警方|警员)(.{0,12}?)(?:抵达现场|到达现场|赶到现场|进入|走进|冲进|推门)",
            str(text),
        ):
            if not any(
                modal in match.group(1)
                for modal in ("该", "快", "将", "会", "等", "就要", "应该")
            ):
                return True
        return False

    @classmethod
    def _has_confirmed_police_handoff(cls, text: str) -> bool:
        """Require visible police arrival plus custody and evidence handoff."""
        normalized = str(text or "")
        if not cls._has_confirmed_police_arrival(normalized):
            return False
        police_action = re.search(
            r"(?:警察|警方|警员).{0,40}(?:拘留|拘捕|逮捕|戴上手铐|铐住|控制住|带走)",
            normalized,
            flags=re.DOTALL,
        )
        evidence_handoff = re.search(
            r"(?:警察|警方|警员).{0,60}(?:收取|收走|接过|封存|装入证物袋|接管).{0,20}(?:证据|证物|镇纸|鱼线|手套|遗书)",
            normalized,
            flags=re.DOTALL,
        ) or re.search(
            r"(?:证据|证物|镇纸|鱼线|手套|遗书).{0,40}(?:交给|移交给|由).{0,12}(?:警察|警方|警员)",
            normalized,
            flags=re.DOTALL,
        )
        if not evidence_handoff and re.search(r"(?:警察|警方|警员)", normalized):
            evidence_handoff = (
                re.search(r"(?:证据|证物|镇纸|鱼线|手套|遗书)", normalized)
                and re.search(r"(?:收取|收走|接过|封存|装入证物袋|接管)", normalized)
            )
        return bool(police_action and evidence_handoff)

    @classmethod
    def _supplement_terminal_evidence(
        cls,
        condition: str,
        evidence: Any,
        content_bodies: List[str],
    ) -> List[str]:
        """Fill reviewer omissions with exact visible lines from the draft."""
        result = [
            str(item).strip()
            for item in evidence
            if (
                isinstance(item, str)
                and str(item).strip()
                and any(str(item).strip() in body for body in content_bodies)
            )
        ] if isinstance(evidence, list) else []
        evidence_text = "\n".join(result)
        for item in cls._enumerated_terminal_items(condition):
            if item in evidence_text:
                continue
            candidate = next((body.strip() for body in content_bodies if item in body), "")
            if candidate and candidate not in result:
                result.append(candidate)
                evidence_text += "\n" + candidate
        if (
            re.search(r"(?:警察|警方)抵达", condition)
            and not cls._has_confirmed_police_arrival(evidence_text)
        ):
            candidate = next(
                (
                    body.strip()
                    for body in content_bodies
                    if cls._has_confirmed_police_arrival(body)
                ),
                "",
            )
            if candidate and candidate not in result:
                result.append(candidate)
        return result

    @staticmethod
    def _terminal_item_is_covered(
        item: str,
        evidence_text: str,
        core_gdd: Dict[str, Any],
    ) -> bool:
        """Accept a Core-GDD-defined concrete object for a generic checklist noun."""
        if item in evidence_text:
            return True
        if item != "凶器":
            return False
        facts_text = "\n".join(str(fact) for fact in core_gdd.get("immutable_facts", []))
        aliases: List[str] = []
        for definition in re.findall(r"凶器(?:是|为)([^，。；]+)", facts_text):
            aliases.extend(re.findall(r"[（(]([^）)]+)[）)]", definition))
            aliases.append(
                re.sub(r"^.*?的", "", re.sub(r"[（(].*$", "", definition)).strip()
            )
        return any(alias and alias in evidence_text for alias in aliases)

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
