import unittest

from agents.designer_agent import (
    CLOSED_ENDING_COMPLETION_CONDITIONS,
    DesignerAgent,
)
from agents.producer_agent import ProducerAgent


def base_goal():
    return {
        "goal": "揭示真相",
        "dramatic_question": "谁是真凶？",
        "contributes_to_global_goal": "解决案件",
        "completion_conditions": ["真凶被确认"],
        "forbidden_outcomes": [],
        "narrative_phase": "confrontation",
    }


class ClosedEndingTests(unittest.TestCase):
    def test_penultimate_prep_does_not_force_final_motive_confession(self):
        designer = DesignerAgent.__new__(DesignerAgent)
        designer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        designer.call_json_with_schema = lambda **_kwargs: {
            **base_goal(),
            "completion_conditions": ["赵深的不在场证明被推翻。"],
            "transition_contract": {
                "relation_to_previous": "continuation",
                "source_scene": "美术储藏室",
                "source_speaker": "林晨",
                "source_anchor": "继续调查。",
                "bridge_requirement": "承接调查。",
            },
        }

        goal = designer._plan_node_goal(
            core_gdd={
                "global_goal": {
                    "terminal_conditions": [
                        "密室手法被重建，凶器、手套等物证被找到。",
                        "动机链（竞争、怨恨、要挟）完整呈现。",
                    ]
                }
            },
            world_state={},
            agenda={},
            previous_summaries=[],
            node_index=3,
            total_nodes=5,
            ending_mode="closed",
            previous_tail={},
        )

        conditions = "\n".join(goal["completion_conditions"])
        self.assertIn("终局必需项“手套”", conditions)
        self.assertNotIn("终局必需项“竞争”", conditions)
        self.assertNotIn("终局必需项“怨恨”", conditions)
        self.assertNotIn("终局必需项“要挟”", conditions)

    def test_final_goal_includes_all_terminal_conditions_before_closure(self):
        designer = DesignerAgent.__new__(DesignerAgent)
        designer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        designer.call_json_with_schema = lambda **_kwargs: {
            **base_goal(),
            "completion_conditions": ["赵深认罪。"],
            "transition_contract": {
                "relation_to_previous": "continuation",
                "source_scene": "美术储藏室",
                "source_speaker": "林晨",
                "source_anchor": "证据齐全。",
                "bridge_requirement": "开始最终对质。",
            },
        }
        terminal_conditions = [
            "凶器、手套均被确认。",
            "竞争、怨恨、要挟完整呈现。",
        ]

        goal = designer._plan_node_goal(
            core_gdd={"global_goal": {"terminal_conditions": terminal_conditions}},
            world_state={},
            agenda={},
            previous_summaries=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
            previous_tail={},
        )

        conditions = goal["completion_conditions"]
        self.assertLess(conditions.index(terminal_conditions[-1]), conditions.index(CLOSED_ENDING_COMPLETION_CONDITIONS[0]))
        self.assertIn("警方已经实际抵达现场", goal["goal"])

    def test_final_goal_removes_impossible_on_site_dna_claim(self):
        designer = DesignerAgent.__new__(DesignerAgent)
        designer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        designer.call_json_with_schema = lambda **_kwargs: {
            **base_goal(),
            "goal": "在警方到达前查明真相。",
            "completion_conditions": [
                "镇纸血迹与陈默DNA匹配。",
                "白手套上的血迹经比对确认为陈默的血。",
                "赵深被控制，等待警方到来。",
            ],
        }

        result = designer._plan_node_goal(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            world_state={},
            agenda={},
            previous_summaries=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
            previous_tail={},
        )

        self.assertNotIn("DNA匹配", "\n".join(result["completion_conditions"]))
        self.assertIn("交由警方检验", result["completion_conditions"][0])
        self.assertNotIn("确认为陈默的血", "\n".join(result["completion_conditions"]))
        self.assertNotIn("等待警方到来", "\n".join(result["completion_conditions"]))
        self.assertIn("完成证物移交", "\n".join(result["completion_conditions"]))
        self.assertEqual(result["narrative_phase"], "resolution")

    def test_review_feedback_drops_disproved_actor_fidelity_claim(self):
        line = "赵深，解开纱布让我们看看伤口。"
        feedback = ProducerAgent._sanitize_review_feedback(
            [
                f"Writer擅自添加了‘{line}’，Actor记录中没有。",
                "草稿中同一句追问重复两次，需要精简。",
                "continuity_check应改为true。",
            ],
            f'<content id="林晨">{line}</content>',
            [{"character": "林晨", "action": "伸手示意", "dialogue": line}],
            base_goal(),
        )

        self.assertEqual(feedback, ["草稿中同一句追问重复两次，需要精简。"])

    def test_review_feedback_drops_style_and_false_inference_conflicts(self):
        goal = base_goal()
        goal["completion_conditions"] = ["林晨推断凶手可能用鱼线从外部拉上内锁。"]
        draft = "林晨初步推断可能用鱼线拉锁，但仍需要验证。"

        feedback = ProducerAgent._sanitize_review_feedback(
            [
                "台词过于集中，缺乏逐步发现，建议穿插其他角色反应。",
                "该推断超出本节点并且过早揭露手法，应删除。",
                "草稿没有说明鱼线已经被回收。",
                "草稿没有说明鱼线已经被回收。",
            ],
            draft,
            [],
            goal,
        )

        self.assertEqual(feedback, ["草稿没有说明鱼线已经被回收。"])

    def test_review_feedback_recognizes_chinese_clock_spelling(self):
        feedback = ProducerAgent._sanitize_review_feedback(
            ["草稿未明确提及赵深声称的7:40离开时间。"],
            "赵深，你说你七点四十就离开了。",
            [],
            base_goal(),
        )

        self.assertEqual(feedback, [])

    def test_review_feedback_drops_false_missing_quoted_term(self):
        feedback = ProducerAgent._sanitize_review_feedback(
            ["草稿未明确命名'手套'，需要补充。"],
            "这里有一双手套。",
            [],
            base_goal(),
        )

        self.assertEqual(feedback, [])

    def test_review_feedback_drops_missing_claim_refuted_by_multiple_terms(self):
        feedback = ProducerAgent._sanitize_review_feedback(
            [
                "韩旭的证词需要更明确地指出赵深手上缠有纱布，并提及具体时间八点十五分。",
                "林晨应更明确提及脚印走向与时间位置吻合。",
            ],
            "八点十五分，赵深手上缠着纱布。脚印走向与时间位置吻合。",
            [],
            base_goal(),
        )

        self.assertEqual(feedback, [])

    def test_nonfinal_review_passes_when_all_feedback_is_textually_refuted(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        line = "八点十五分，我看到赵深手上缠着纱布。"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "REVISE",
            "feedback": ["证词需要更明确提及八点十五和纱布。"],
            "goal_completed": False,
            "summary": "",
            "state_updates": [],
            "agenda": {},
            "continuity_check": {},
            "terminal_condition_checks": [],
            "closure_check": {},
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=base_goal(),
            draft=f'<scene>走廊</scene>\n<content id="韩旭">{line}</content>',
            world_state={},
            agenda={"open_questions": []},
            actor_performances=[{"character": "韩旭", "dialogue": line}],
            node_index=0,
            total_nodes=5,
        )

        self.assertEqual(review["decision"], "PASS")
        self.assertTrue(review["goal_completed"])
        self.assertEqual(review["summary"], line)

    def test_ordinary_question_is_not_direct_culprit_accusation(self):
        self.assertFalse(
            ProducerAgent._has_explicit_culprit_accusation(
                "赵深，你当时为什么在美术室附近？你手上的纱布怎么回事？"
            )
        )
        self.assertTrue(
            ProducerAgent._has_explicit_culprit_accusation(
                "赵深，你就是杀害陈默的凶手。"
            )
        )

    def test_producer_deterministically_accepts_addressed_actor_answer(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        answer = "我八点十分去的水房，但我不想说看见了什么。"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "韩旭直接回应追问。",
            "state_updates": [],
            "agenda": {},
            "continuity_check": {
                "applicable": True,
                "relation_to_previous": "answer",
                "source_anchor_acknowledged": True,
                "discourse_relation_realized": False,
                "action_continuity_preserved": True,
                "scene_transition_grounded": True,
                "evidence": [answer, f"韩旭：'{answer}'"],
            },
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": False,
                "consequences_shown": False,
                "character_arcs_paid_off": False,
                "new_equilibrium_established": False,
                "finality_signal_present": False,
                "evidence": [],
                "final_beat": "",
            },
        }
        previous = (
            '<scene>走廊</scene>\n'
            '<content id="赵深">韩旭，你具体几点去的水房？</content>'
        )
        goal = base_goal()
        goal["transition_contract"] = {
            "relation_to_previous": "answer",
            "source_scene": "走廊",
            "source_speaker": "赵深",
            "source_anchor": "韩旭，你具体几点去的水房？",
            "bridge_requirement": "韩旭首回合回答。",
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=goal,
            draft=f'<scene>走廊</scene>\n<content id="韩旭">{answer}</content>',
            world_state={},
            agenda={},
            actor_performances=[{"character": "韩旭", "dialogue": answer}],
            node_index=1,
            total_nodes=5,
            previous_script=previous,
        )

        self.assertEqual(review["decision"], "PASS")
        self.assertTrue(review["continuity_check"]["discourse_relation_realized"])
        self.assertEqual(review["continuity_check"]["evidence"], [answer])

    def test_producer_uses_first_dialogue_as_continuation_evidence(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        line = "窗台水渍和门缝鱼线说明，凶手可能从外部操作反锁。"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "REVISE",
            "feedback": ["跨节点话语关系未通过：evidence。"],
            "goal_completed": False,
            "summary": "",
            "state_updates": [],
            "agenda": {},
            "continuity_check": {
                "applicable": True,
                "relation_to_previous": "continuation",
                "source_anchor_acknowledged": True,
                "discourse_relation_realized": True,
                "action_continuity_preserved": True,
                "scene_transition_grounded": True,
                "evidence": [f"林晨：{line}"],
            },
            "terminal_condition_checks": [],
            "closure_check": {},
        }
        previous = (
            '<scene>美术储藏室</scene>\n'
            '<content id="林晨">窗台上有水渍。</content>'
        )
        goal = base_goal()
        goal["transition_contract"] = {
            "relation_to_previous": "continuation",
            "source_scene": "美术储藏室",
            "source_speaker": "林晨",
            "source_anchor": "窗台上有水渍。",
            "bridge_requirement": "继续分析水渍。",
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=goal,
            draft=f'<scene>美术储藏室</scene>\n<content id="林晨">{line}</content>',
            world_state={},
            agenda={},
            actor_performances=[{"character": "林晨", "dialogue": line}],
            node_index=1,
            total_nodes=5,
            previous_script=previous,
        )

        self.assertEqual(review["decision"], "PASS")
        self.assertEqual(review["continuity_check"]["evidence"], [line])

    def test_producer_accepts_evidence_backed_discourse_bridge(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        bridge = "韩旭堵在门口，终于抬头叫住了正要离开的林晨。"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "韩旭打断离场并决定作证。",
            "state_updates": [],
            "agenda": {},
            "continuity_check": {
                "applicable": True,
                "relation_to_previous": "correction",
                "source_anchor_acknowledged": True,
                "discourse_relation_realized": True,
                "action_continuity_preserved": True,
                "scene_transition_grounded": True,
                "evidence": [bridge],
            },
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": False,
                "consequences_shown": False,
                "character_arcs_paid_off": False,
                "new_equilibrium_established": False,
                "finality_signal_present": False,
                "evidence": [],
                "final_beat": "",
            },
        }
        previous = (
            '<scene>活动室</scene>\n'
            '<content id="旁白">林晨转身走向门口。</content>\n'
            '<content id="林晨">赵深，带我去找证人。</content>'
        )
        goal = base_goal()
        goal["transition_contract"] = {
            "relation_to_previous": "correction",
            "source_scene": "活动室",
            "source_speaker": "林晨",
            "source_anchor": "赵深，带我去找证人。",
            "bridge_requirement": "由新的证言在门口明确打断离场行动。",
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=goal,
            draft=f'<scene>活动室</scene>\n<content id="旁白">{bridge}</content>',
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=1,
            total_nodes=5,
            previous_script=previous,
        )

        self.assertEqual(review["decision"], "PASS")
        self.assertTrue(review["goal_completed"])

    def test_producer_rejects_same_scene_action_rollback_between_nodes(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "继续调查。",
            "state_updates": [],
            "agenda": {},
            "continuity_check": {
                "applicable": True,
                "relation_to_previous": "continuation",
                "source_anchor_acknowledged": False,
                "discourse_relation_realized": False,
                "action_continuity_preserved": False,
                "scene_transition_grounded": True,
                "evidence": ["林晨折回储物柜。"],
            },
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": False,
                "consequences_shown": False,
                "character_arcs_paid_off": False,
                "new_equilibrium_established": False,
                "finality_signal_present": False,
                "evidence": [],
                "final_beat": "",
            },
        }
        previous = (
            '<scene>活动室</scene>\n'
            '<content id="旁白">林晨转身走向门口。</content>\n'
            '<content id="林晨">赵深，带我去找证人。</content>'
        )
        goal = base_goal()
        goal["transition_contract"] = {
            "relation_to_previous": "continuation",
            "source_scene": "活动室",
            "source_speaker": "林晨",
            "source_anchor": "赵深，带我去找证人。",
            "bridge_requirement": "先执行找证人的行动，或由可见事件明确打断。",
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=goal,
            draft=(
                '<scene>活动室</scene>\n'
                '<content id="旁白">林晨折回储物柜。</content>'
            ),
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=1,
            total_nodes=5,
            previous_script=previous,
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertIn("跨节点话语关系未通过", review["feedback"][-1])
        self.assertIn("action_continuity_preserved", review["feedback"][-1])

    def test_designer_injects_coda_conditions_into_closed_final_node(self):
        designer = DesignerAgent.__new__(DesignerAgent)
        designer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        designer.call_json_with_schema = lambda **_kwargs: base_goal()

        goal = designer._plan_node_goal(
            core_gdd={},
            world_state={},
            agenda={},
            previous_summaries=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(goal["narrative_phase"], "resolution")
        for condition in CLOSED_ENDING_COMPLETION_CONDITIONS:
            self.assertIn(condition, goal["completion_conditions"])

    def test_designer_requires_unseeded_terminal_evidence_before_final_node(self):
        designer = DesignerAgent.__new__(DesignerAgent)
        designer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        designer.call_json_with_schema = lambda **_kwargs: base_goal()

        goal = designer._plan_node_goal(
            core_gdd={
                "global_goal": {
                    "terminal_conditions": ["凶器、手套等物证被找到。"]
                }
            },
            world_state={"known": ["凶器"]},
            agenda={},
            previous_summaries=[],
            node_index=3,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertTrue(any("手套" in item for item in goal["completion_conditions"]))
        self.assertFalse(any("凶器”必须" in item for item in goal["completion_conditions"]))

    def test_producer_forces_revision_when_closed_final_node_lacks_coda(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "凶手承认。",
            "state_updates": [{
                "path": "case.solved",
                "value": True,
                "evidence": "凶手承认。",
            }],
            "agenda": {},
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": False,
                "character_arcs_paid_off": False,
                "new_equilibrium_established": False,
                "finality_signal_present": False,
                "evidence": ["凶手承认。"],
                "final_beat": "凶手承认。",
            },
        }

        review = producer.review_and_reduce_node(
            core_gdd={},
            node_goal=base_goal(),
            draft="凶手承认。",
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertFalse(review["goal_completed"])
        self.assertEqual(review["state_updates"], [])
        self.assertIn("consequences_shown", review["feedback"][-1])

    def test_producer_requires_every_terminal_condition_with_verbatim_evidence(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "真相与尾声都已完成。",
            "state_updates": [],
            "agenda": {},
            "terminal_condition_checks": [{
                "condition": "警方抵达",
                "satisfied": True,
                "evidence": ["警笛声穿过雨幕，警方抵达"],
            }],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": ["天终于亮了"],
                "final_beat": "天终于亮了",
            },
        }

        review = producer.review_and_reduce_node(
            core_gdd={
                "global_goal": {
                    "terminal_conditions": ["凶手认罪", "警方抵达"]
                }
            },
            node_goal=base_goal(),
            draft="赵深低头认罪。警笛声穿过雨幕，警方抵达。天终于亮了。",
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertFalse(review["goal_completed"])
        self.assertIn("凶手认罪", review["feedback"][0])

    def test_producer_rejects_finality_line_followed_by_culprit_monologue(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "案件结束。",
            "state_updates": [],
            "agenda": {},
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": ["天快亮了。"],
                "final_beat": "天快亮了。",
            },
        }
        draft = (
            '<content id="林晨">天快亮了。</content>\n'
            '<content id="赵深">都是他逼我的！</content>'
        )

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=base_goal(),
            draft=draft,
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertIn("final_beat", review["feedback"][-1])

    def test_enumerated_terminal_items_are_required_in_evidence(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "案件结束。",
            "state_updates": [],
            "agenda": {},
            "terminal_condition_checks": [{
                "condition": "凶器、手套等物证被找到。",
                "satisfied": True,
                "evidence": ["凶器已经找到。"],
            }],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": ["故事结束。"],
                "final_beat": "故事结束。",
            },
        }
        draft = (
            '<content id="林晨">凶器已经找到。</content>\n'
            '<content id="林晨">故事结束。</content>'
        )

        review = producer.review_and_reduce_node(
            core_gdd={
                "global_goal": {"terminal_conditions": ["凶器、手套等物证被找到。"]}
            },
            node_goal=base_goal(),
            draft=draft,
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertIn("凶器、手套", review["feedback"][0])

    def test_terminal_evidence_is_supplemented_from_exact_draft_lines(self):
        condition = "密室被重建，凶器、手套等物证被找到。"
        evidence = ProducerAgent._supplement_terminal_evidence(
            condition,
            ["鱼线穿过门缝。"],
            ["石质镇纸就是凶器。", "白手套留在纸箱里。"],
        )

        self.assertIn("石质镇纸就是凶器。", evidence)
        self.assertIn("白手套留在纸箱里。", evidence)

    def test_generic_weapon_item_accepts_core_gdd_concrete_alias(self):
        self.assertTrue(
            ProducerAgent._terminal_item_is_covered(
                "凶器",
                "镇纸底部留有血迹。",
                {"immutable_facts": ["凶器为美术室内的石质雕塑（镇纸）。"]},
            )
        )

    def test_police_arrival_requires_visible_entry_not_a_report_or_car_lights(self):
        self.assertFalse(ProducerAgent._has_confirmed_police_arrival("警察来了。"))
        self.assertFalse(
            ProducerAgent._has_confirmed_police_arrival("警车灯光驶入校园。")
        )
        self.assertTrue(
            ProducerAgent._has_confirmed_police_arrival(
                "两名警察推门进入美术储藏室。"
            )
        )

    def test_police_handoff_requires_custody_and_evidence_collection(self):
        self.assertFalse(
            ProducerAgent._has_confirmed_police_handoff(
                "两名警察推门进入美术储藏室。"
            )
        )
        self.assertTrue(
            ProducerAgent._has_confirmed_police_handoff(
                "两名警察推门进入美术储藏室，给赵深戴上手铐，并将镇纸、鱼线和白手套装入证物袋。"
            )
        )
        self.assertFalse(
            ProducerAgent._has_confirmed_police_handoff(
                "两名警察推门进入储藏室，一人走向赵深，另一人把镇纸装入证物袋。"
                "林晨说：请你们接管。"
            )
        )

    def test_final_beat_cannot_double_as_terminal_evidence(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        final_line = "我因为怨恨杀了他！"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "案件结束。",
            "state_updates": [],
            "agenda": {},
            "terminal_condition_checks": [{
                "condition": "动机被揭露。",
                "satisfied": True,
                "evidence": [final_line],
            }],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": ["警察控制了凶手。", final_line],
                "final_beat": final_line,
            },
        }
        draft = (
            '<content id="旁白">警察控制了凶手。</content>\n'
            f'<content id="赵深">{final_line}</content>'
        )

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": ["动机被揭露。"]}},
            node_goal=base_goal(),
            draft=draft,
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertIn("final_beat_order", review["feedback"][-1])

    def test_closed_final_rejects_trailing_ellipsis_as_final_beat(self):
        producer = ProducerAgent.__new__(ProducerAgent)
        producer.config = type("Config", (), {"SYSTEM_PROMPT": "test"})
        dangling = "我终于决定说出那个秘密……"
        producer.call_json_with_schema = lambda **_kwargs: {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": "案件结束。",
            "state_updates": [],
            "agenda": {},
            "terminal_condition_checks": [],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": [dangling],
                "final_beat": dangling,
            },
            "continuity_check": {
                "applicable": False,
                "relation_to_previous": "root",
                "source_anchor_acknowledged": True,
                "discourse_relation_realized": True,
                "action_continuity_preserved": True,
                "scene_transition_grounded": True,
                "evidence": [],
            },
        }

        review = producer.review_and_reduce_node(
            core_gdd={"global_goal": {"terminal_conditions": []}},
            node_goal=base_goal(),
            draft=f'<content id="叶晓">{dangling}</content>',
            world_state={},
            agenda={},
            actor_performances=[],
            node_index=4,
            total_nodes=5,
            ending_mode="closed",
        )

        self.assertEqual(review["decision"], "REVISE")
        self.assertIn("final_beat_finality", review["feedback"][-1])


if __name__ == "__main__":
    unittest.main()
