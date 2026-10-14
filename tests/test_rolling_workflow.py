import unittest
import json
import tempfile
from pathlib import Path

from agents.config import PathConfig
from agents.designer_agent import CLOSED_ENDING_COMPLETION_CONDITIONS
from agents.writer_agent import WriterAgent
from workflow import WorkflowController


def node_goal(index):
    return {
        "goal": f"Goal {index}",
        "dramatic_question": "What changes?",
        "contributes_to_global_goal": f"Advance investigation {index}",
        "completion_conditions": [f"Clue {index} is established"],
        "forbidden_outcomes": [],
        "narrative_phase": "resolution" if index == 4 else "escalation",
    }


class FakeProducer:
    def __init__(self):
        self.review_calls = []
        self.root_rejected_once = False

    def generate_core_gdd(self, requirements, character_count, locked_characters=None):
        return {
            "schema_version": "core-gdd/1.1",
            "title": "Murder Test",
            "background": requirements,
            "art_style": "test",
            "themes": ["truth"],
            "world_rules": [],
            "immutable_facts": [],
            "initial_conflict": "A student is dead",
            "global_goal": {
                "objective": "Solve the murder",
                "dramatic_question": "Who killed the student?",
                "terminal_conditions": ["Identify the culprit with evidence"],
                "forbidden_outcomes": ["Supernatural solution"],
            },
            "ending_conditions": ["The culprit is exposed"],
            "characters": [{"id": "hero", "name": "Hero"}],
            "scenes": [{"id": "school", "name": "School", "description": "School"}],
            "initial_world_state": {"clues": [], "completed": {}},
            "initial_agenda": {"open_questions": ["Who did it?"]},
        }

    def review_and_reduce_node(self, **kwargs):
        self.review_calls.append(kwargs)
        index = kwargs["node_index"]
        if index == 0 and not self.root_rejected_once:
            self.root_rejected_once = True
            return {
                "decision": "REVISE",
                "feedback": ["Use the Actor's corrected voice"],
                "goal_completed": False,
                "summary": "",
                "state_updates": [],
                "agenda": kwargs["agenda"],
            }
        return {
            "decision": "PASS",
            "feedback": [],
            "goal_completed": True,
            "summary": f"Summary {index}",
            "state_updates": [
                {
                    "path": f"completed.node{index}",
                    "value": True,
                    "evidence": f"Goal {index} appears in the draft",
                }
            ],
            "agenda": {"open_questions": [] if index == 4 else ["Who did it?"]},
        }


class FakeDesigner:
    def __init__(self):
        self.initial_calls = 0
        self.next_calls = []

    def plan_initial_goal(self, **kwargs):
        self.initial_calls += 1
        return node_goal(0)

    def plan_next_goal(self, **kwargs):
        index = kwargs["node_index"]
        self.next_calls.append(kwargs)
        return node_goal(index)


class FakeWriter:
    def __init__(self):
        self.synthesized = []
        self.llm_client = None

    def decide_next_speaker(self, **kwargs):
        current = kwargs["story_context"].split("【当前表演】", 1)[-1]
        if "尚未开始" not in current:
            return "STOP", ""
        guidance = "revise" if "Producer 对上一版的驳回要求" in kwargs["story_context"] else "initial"
        return "Hero", guidance

    def synthesize_actor_performances(self, **kwargs):
        turn = kwargs["turns"][0]
        self.synthesized.append(turn)
        return (
            '<scene>School</scene>\n'
            f'<content id="\u65c1\u767d">{turn["action"]}</content>\n'
            f'<content id="Hero">{turn["dialogue"]}</content>\n'
        )

    @staticmethod
    def normalize_scene_script(script, core_gdd):
        return script


class FakeActor:
    def __init__(self):
        self.perform_calls = []

    character_info = {"id": "hero", "name": "Hero"}

    def build_memory_context(self, **kwargs):
        return ""

    def perform_scene(self, **kwargs):
        self.perform_calls.append(kwargs)
        revised = "Producer 对上一版的驳回要求" in kwargs["story_context"]
        return {
            "thought": "private",
            "action": "Finds evidence",
            "dialogue": "Revised line" if revised else "Initial line",
            "image": "neutral",
        }


class RollingWorkflowTests(unittest.TestCase):
    def test_generates_five_verified_node_goals_and_commits_after_revision(self):
        workflow = WorkflowController.__new__(WorkflowController)
        workflow.producer = FakeProducer()
        workflow.designer = FakeDesigner()
        workflow.writer = FakeWriter()
        workflow.game_design = None
        actor = FakeActor()
        workflow._initialize_actors = lambda: setattr(workflow, "actors", {"Hero": actor})
        workflow._get_expressions_str = lambda _name: ["neutral"]
        committed_performances = []
        workflow._commit_actor_performances = lambda **kwargs: committed_performances.append(kwargs)
        checkpoints = []
        workflow._persist_rolling_story = lambda **kwargs: checkpoints.append(kwargs)

        result = workflow.run_rolling_story(
            requirements="campus murder",
            character_count=3,
            node_count=5,
            ending_mode="closed",
            resume=False,
        )

        self.assertEqual(list(result["scripts"]), ["root", "node1", "node2", "node3", "node4"])
        self.assertEqual(list(result["goals"]), ["root", "node1", "node2", "node3", "node4"])
        self.assertEqual(workflow.designer.initial_calls, 1)
        self.assertEqual([call["node_index"] for call in workflow.designer.next_calls], [1, 2, 3, 4])
        self.assertEqual(len(actor.perform_calls), 12)
        self.assertEqual(len(workflow.writer.synthesized), 6)
        self.assertIn("Revised line", result["scripts"]["root"])

        for goal in result["goals"].values():
            self.assertNotIn("active_cast", goal)
            self.assertNotIn("location", goal)
            self.assertIn("transition_contract", goal)

        self.assertEqual(
            result["goals"]["root"]["transition_contract"]["relation_to_previous"],
            "root",
        )
        self.assertEqual(
            result["goals"]["node1"]["transition_contract"]["source_anchor"],
            "Revised line",
        )
        self.assertIn("节点首回合", actor.perform_calls[4]["director_guidance"])
        self.assertEqual(actor.perform_calls[4]["temperature"], 0.35)
        self.assertEqual(actor.perform_calls[5]["temperature"], 0.35)
        self.assertEqual(
            workflow.designer.next_calls[0]["previous_tail"]["source_anchor"],
            "Revised line",
        )

        first_review = workflow.producer.review_calls[0]
        self.assertEqual(first_review["actor_performances"][0]["character"], "Hero")
        self.assertEqual(first_review["actor_performances"][0]["dialogue"], "Initial line")
        self.assertIn("Revised line", workflow.producer.review_calls[1]["draft"])
        self.assertEqual(workflow.producer.review_calls[1]["actor_performances"][0]["dialogue"], "Revised line")
        self.assertTrue(all(review["goal_completed"] for review in result["reviews"].values()))
        self.assertEqual(len(committed_performances), 5)
        self.assertEqual(committed_performances[0]["turns"][0]["dialogue"], "Revised line")
        self.assertEqual(
            result["world_state"]["completed"],
            {f"node{index}": True for index in range(5)},
        )
        self.assertEqual(
            result["story_graph"]["edges"],
            [
                {
                    "from": "root", "to": "node1", "choice_text": None,
                    "discourse_relation": "continuation", "source_anchor": "Revised line",
                },
                {
                    "from": "node1", "to": "node2", "choice_text": None,
                    "discourse_relation": "continuation", "source_anchor": "Initial line",
                },
                {
                    "from": "node2", "to": "node3", "choice_text": None,
                    "discourse_relation": "continuation", "source_anchor": "Initial line",
                },
                {
                    "from": "node3", "to": "node4", "choice_text": None,
                    "discourse_relation": "continuation", "source_anchor": "Initial line",
                },
            ],
        )
        self.assertEqual(len(checkpoints), 5)
        self.assertEqual(workflow.producer.review_calls[1]["draft"].count("Revised line"), 1)

    def test_state_updates_require_evidence_and_reject_unsafe_paths(self):
        with self.assertRaises(ValueError):
            WorkflowController._apply_evidence_backed_updates(
                {}, [{"path": "clues.one", "value": True, "evidence": ""}]
            )
        with self.assertRaises(ValueError):
            WorkflowController._apply_evidence_backed_updates(
                {}, [{"path": "__class__.bad", "value": True, "evidence": "line"}]
            )

    def test_checkpoint_scripts_are_recompiled_from_actor_records_and_keep_jump(self):
        workflow = WorkflowController.__new__(WorkflowController)
        workflow.writer = FakeWriter()
        scripts, changed = workflow._recompile_checkpoint_scripts(
            core_gdd={"scenes": [{"name": "School"}]},
            scripts={
                "root": (
                    '<scene>Wrong</scene>\n'
                    '<content id="Hero">Old line</content>\n\n'
                    '<jump target="node1"/>\n'
                )
            },
            performances={
                "root": [{
                    "character": "Hero",
                    "action": "Finds evidence",
                    "dialogue": "Original Actor line",
                }]
            },
            goals={"root": node_goal(0)},
        )

        self.assertTrue(changed)
        self.assertIn("Original Actor line", scripts["root"])
        self.assertNotIn("Old line", scripts["root"])
        self.assertTrue(scripts["root"].endswith('<jump target="node1"/>\n'))

    def test_resume_rejects_misaligned_or_unapproved_checkpoint(self):
        checkpoint = {
            "scripts": {"root": "root", "node2": "gap"},
            "goals": {"root": {}, "node2": {}},
            "reviews": {
                "root": {"decision": "PASS", "goal_completed": True},
                "node2": {"decision": "PASS", "goal_completed": True},
            },
            "performances": {"root": [{}], "node2": [{}]},
            "summaries": {"root": "root", "node2": "gap"},
        }
        with self.assertRaisesRegex(ValueError, "节点顺序不合法"):
            WorkflowController._validate_rolling_checkpoint_for_resume(checkpoint, 5)

        checkpoint["scripts"] = {"root": "root", "node1": "draft"}
        checkpoint["goals"] = {"root": {}, "node1": {}}
        checkpoint["reviews"] = {
            "root": {"decision": "PASS", "goal_completed": True},
            "node1": {"decision": "REVISE", "goal_completed": False},
        }
        checkpoint["performances"] = {"root": [{}], "node1": [{}]}
        checkpoint["summaries"] = {"root": "root", "node1": "draft"}
        with self.assertRaisesRegex(ValueError, "未通过的已提交节点"):
            WorkflowController._validate_rolling_checkpoint_for_resume(checkpoint, 5)

    def test_resume_rejects_committed_node_without_discourse_transition_evidence(self):
        checkpoint = {
            "scripts": {
                "root": '<scene>School</scene>\n<content id="Hero">Go.</content>',
                "node1": '<scene>School</scene>\n<content id="Hero">Unrelated.</content>',
            },
            "goals": {
                "root": {
                    **node_goal(0),
                    "transition_contract": {
                        "relation_to_previous": "root",
                        "source_scene": "",
                        "source_speaker": "",
                        "source_anchor": "",
                        "bridge_requirement": "start",
                    },
                },
                "node1": node_goal(1),
            },
            "reviews": {
                "root": {"decision": "PASS", "goal_completed": True},
                "node1": {"decision": "PASS", "goal_completed": True},
            },
            "performances": {"root": [{}], "node1": [{}]},
            "summaries": {"root": "root", "node1": "unrelated"},
        }

        with self.assertRaisesRegex(ValueError, "transition_contract 无效"):
            WorkflowController._validate_rolling_checkpoint_for_resume(checkpoint, 5)

    def test_retry_context_persists_and_restores_failed_feedback(self):
        workflow = WorkflowController.__new__(WorkflowController)
        original_data_dir = PathConfig.DATA_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            PathConfig.DATA_DIR = temp_dir
            workflow._persist_rolling_retry_context(
                node_id="node3",
                node_goal=node_goal(3),
                feedback=["必须亲自完成鞋底泥土比对"],
                review={"decision": "REVISE"},
                draft="draft",
                turns=[{"character": "Hero", "action": "asks"}],
                revision_index=4,
                status="revise",
            )
            restored = workflow._load_rolling_retry_context("node3")
            payload = json.loads(Path(temp_dir, "rolling_retry.json").read_text())
        PathConfig.DATA_DIR = original_data_dir

        self.assertEqual(restored["feedback"], ["必须亲自完成鞋底泥土比对"])
        self.assertEqual(payload["status"], "revise")
        self.assertEqual(workflow._load_rolling_retry_context("node4"), {})

    def test_retry_context_keeps_the_uncommitted_node_goal(self):
        workflow = WorkflowController.__new__(WorkflowController)
        original_data_dir = PathConfig.DATA_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            PathConfig.DATA_DIR = temp_dir
            expected_goal = node_goal(3)
            workflow._persist_rolling_retry_context(
                node_id="node3",
                node_goal=expected_goal,
                feedback=[],
                review={},
                draft="",
                turns=[],
                revision_index=-1,
                status="revise",
            )
            restored = workflow._load_rolling_retry_context("node3")
        PathConfig.DATA_DIR = original_data_dir

        self.assertEqual(restored["node_goal"], expected_goal)


class DirectorParsingTests(unittest.TestCase):
    def test_writer_replaces_first_person_action_subject(self):
        self.assertEqual(
            WriterAgent._format_attributed_action("林晨", "我转身走向门口。"),
            "林晨转身走向门口。",
        )

    def test_writer_does_not_prefix_actor_to_visible_police_action(self):
        self.assertEqual(
            WriterAgent._format_attributed_action(
                "林晨",
                "两名警察推门进入储藏室。",
            ),
            "两名警察推门进入储藏室。",
        )
        self.assertEqual(
            WriterAgent._format_attributed_action(
                "林晨",
                "听见脚步声，我走到门口。",
            ),
            "林晨听见脚步声，林晨走到门口。",
        )

    def test_exact_duplicate_actor_turn_is_removed(self):
        turn = {
            "character": "韩旭",
            "action": "攥紧衣角。",
            "dialogue": "我看见赵深从美术室出来。",
        }
        self.assertTrue(
            WorkflowController._is_duplicate_actor_turn(turn, [dict(turn)])
        )
        self.assertFalse(
            WorkflowController._is_duplicate_actor_turn(
                {**turn, "dialogue": "我还看见他手上缠着纱布。"},
                [turn],
            )
        )

    def test_same_dialogue_with_different_stage_direction_is_still_duplicate(self):
        previous = {
            "character": "林晨",
            "action": "林晨转向众人。",
            "dialogue": "赵深，你敢再说一遍吗？",
        }
        repeated = {
            **previous,
            "action": "林晨向前走了一步。",
        }

        self.assertTrue(
            WorkflowController._is_duplicate_actor_turn(repeated, [previous])
        )

    def test_completion_conditions_schedule_explicit_actors_in_order(self):
        tasks = WorkflowController._completion_actor_tasks(
            [
                "韩旭明确说出看到赵深离开的目击证言。",
                "赵深解释右手纱布。",
                "调查焦点发生变化。",
                "发现床下的试卷碎片。",
                "林晨决定搜查活动室。",
                "韩旭的目击证言被林晨确认。",
            ],
            ["林晨", "叶晓", "赵深", "韩旭"],
        )

        self.assertEqual(
            tasks,
            [
                ("韩旭", "韩旭明确说出看到赵深离开的目击证言。"),
                ("赵深", "赵深解释右手纱布。"),
                ("林晨", "调查焦点发生变化。"),
                ("林晨", "发现床下的试卷碎片。"),
                ("林晨", "林晨决定搜查活动室。"),
                ("林晨", "韩旭的目击证言被林晨确认。"),
            ],
        )

    def test_goal_target_scene_matches_declared_scene_alias(self):
        target = WorkflowController._infer_goal_target_scene(
            {
                "scenes": [
                    {"name": "教学楼三楼走廊"},
                    {"name": "男生宿舍302室"},
                    {"name": "体育馆篮球部活动室"},
                ]
            },
            {
                "goal": "前往韩旭的宿舍验证时间线。",
                "dramatic_question": "宿舍里藏着什么？",
                "contributes_to_global_goal": "找到床下试卷。",
                "completion_conditions": ["林晨在宿舍发现试卷碎片。"],
            },
        )

        self.assertEqual(target, "男生宿舍302室")

    def test_goal_target_scene_prioritizes_repeated_exact_location(self):
        target = WorkflowController._infer_goal_target_scene(
            {
                "scenes": [
                    {"name": "美术储藏室"},
                    {"name": "教师办公室"},
                ]
            },
            {
                "goal": "前往教师办公室检查电话。",
                "dramatic_question": "教师办公室发生了什么？",
                "contributes_to_global_goal": "确认通讯中断。",
                "completion_conditions": [
                    "在教师办公室找到赵深申请使用美术储藏室的记录。"
                ],
            },
        )

        self.assertEqual(target, "教师办公室")

    def test_completion_tasks_are_grouped_and_routed_by_scene(self):
        routed = WorkflowController._route_completion_tasks(
            [
                ("林晨", "林晨检查美术室门缝。"),
                ("林晨", "林晨在活动室找到鱼线包装。"),
                ("韩旭", "韩旭承认曾目击赵深从美术室方向离开。"),
            ],
            core_gdd={
                "scenes": [
                    {"name": "教学楼三楼走廊"},
                    {"name": "美术储藏室"},
                    {"name": "体育馆篮球部活动室"},
                ]
            },
            source_scene="教学楼三楼走廊",
            protagonist="林晨",
        )

        self.assertEqual(
            [condition for _actor, condition in routed],
            [
                "承接上一回合后说明调查理由，并实际带众人从教学楼三楼走廊移动到美术储藏室；"
                "action 必须明确写出‘进入美术储藏室’，到达后再开始该地点的调查。",
                "林晨检查美术室门缝。",
                "承接上一回合后说明调查理由，并实际带众人从美术储藏室移动到体育馆篮球部活动室；"
                "action 必须明确写出‘进入体育馆篮球部活动室’，到达后再开始该地点的调查。",
                "林晨在活动室找到鱼线包装。",
                "韩旭承认曾目击赵深从美术室方向离开。",
            ],
        )

    def test_terminal_prep_items_use_culprit_confession_not_invented_props(self):
        tasks = WorkflowController._specialize_terminal_prep_tasks(
            [
                ("林晨", "终局必需项“手套”必须形成可见证据。"),
                ("林晨", "终局必需项“竞争”必须形成可见证据。"),
                ("林晨", "终局必需项“怨恨”必须形成可见证据。"),
                ("林晨", "终局必需项“要挟”必须形成可见证据。"),
            ],
            core_gdd={"immutable_facts": ["真凶是赵深，无其他共犯。"]},
            source_scene="美术储藏室",
            protagonist="林晨",
            actor_names=["林晨", "叶晓", "赵深", "韩旭"],
        )

        self.assertEqual([actor for actor, _condition in tasks], ["林晨", "赵深", "赵深", "赵深"])
        self.assertIn("在美术储藏室角落搜查", tasks[0][1])
        self.assertIn("亲口明确说出“竞争”", tasks[1][1])
        self.assertNotIn("照片", tasks[0][1])

    def test_scheduled_node_stops_before_free_director_repetition(self):
        self.assertTrue(
            WorkflowController._completion_tasks_finished(
                had_completion_tasks=True,
                remaining_tasks=[],
                turn_count=5,
                required_revision_actors=["韩旭", "赵深"],
                performed_revision_actors={"韩旭", "赵深"},
            )
        )
        self.assertFalse(
            WorkflowController._completion_tasks_finished(
                had_completion_tasks=True,
                remaining_tasks=[],
                turn_count=3,
                required_revision_actors=[],
                performed_revision_actors=set(),
            )
        )

    def test_question_tail_is_normalized_to_answer_relation(self):
        normalized = WorkflowController._ensure_transition_contract(
            node_goal={
                **node_goal(1),
                "transition_contract": {
                    "relation_to_previous": "continuation",
                    "bridge_requirement": "Let a third character take over.",
                },
            },
            previous_script=(
                '<scene>走廊</scene>\n'
                '<content id="赵深">韩旭，你具体几点去的？</content>'
            ),
            is_root=False,
        )

        self.assertEqual(
            normalized["transition_contract"]["relation_to_previous"],
            "answer",
        )

    def test_answer_transition_selects_the_addressed_actor(self):
        actor = WorkflowController._infer_answer_actor(
            {
                "relation_to_previous": "answer",
                "source_speaker": "赵深",
                "source_anchor": "不过韩旭，你具体是几点去的？",
            },
            ["林晨", "叶晓", "赵深", "韩旭"],
        )

        self.assertEqual(actor, "韩旭")

    def test_answer_transition_uses_first_addressee_not_later_witness(self):
        actor = WorkflowController._infer_answer_actor(
            {
                "relation_to_previous": "answer",
                "source_speaker": "叶晓",
                "source_anchor": "赵深，你还要狡辩到什么时候？韩旭都看到你了。",
            },
            ["林晨", "叶晓", "赵深", "韩旭"],
        )

        self.assertEqual(actor, "赵深")

    def test_non_answer_transition_does_not_override_director(self):
        actor = WorkflowController._infer_answer_actor(
            {
                "relation_to_previous": "continuation",
                "source_speaker": "赵深",
                "source_anchor": "韩旭转身离开。",
            },
            ["林晨", "赵深", "韩旭"],
        )

        self.assertEqual(actor, "")

    def test_duplicate_producer_feedback_is_removed_in_order(self):
        feedback = WorkflowController._dedupe_producer_feedback(
            ["补充证言", "补充证言", " 记录   证言 ", "记录 证言"]
        )

        self.assertEqual(feedback, ["补充证言", "记录 证言"])

    def test_revision_actor_gate_extracts_explicitly_named_cast(self):
        required = WorkflowController._required_revision_actors(
            ["补充叶晓和韩旭的可见行动或台词，并由林晨最后收束。"],
            ["林晨", "叶晓", "韩旭", "赵深"],
        )

        self.assertEqual(required, ["林晨", "叶晓", "韩旭"])

    def test_revision_actor_gate_recognizes_final_beat_guidance(self):
        self.assertTrue(WorkflowController._is_final_beat_guidance("说出全剧尾声落句"))
        self.assertFalse(WorkflowController._is_final_beat_guidance("当场演示鱼线反锁"))

    def test_final_terminal_conditions_merge_into_concrete_tasks(self):
        terminal = [
            "密室手法被详细重建，凶器、手套等物证被找到。",
            "动机链（竞争、怨恨、要挟）完整呈现。",
            "外部警察抵达，故事以封闭式结局收束。",
        ]
        closure = [
            "必须建立事件后的新平衡状态，并以具有明确终止感的尾声画面、行动或落句结束故事。",
        ]
        concrete = [
            "林晨展示鱼线、镇纸和手套，完整说明密室物证。",
            "赵深供认嫉妒与要挟构成的杀人动机。",
            "警察抵达后，众人确认案件结束。",
        ]

        compacted = WorkflowController._compact_final_completion_conditions(
            concrete + terminal + closure,
            terminal,
        )

        self.assertEqual(len(compacted), len(concrete) + len(closure))
        self.assertTrue(all(any(term in task for task in compacted) for term in terminal))
        self.assertEqual(compacted[-1], closure[0])

    def test_strict_actor_task_reports_omitted_enumerated_item(self):
        missing = WorkflowController._missing_enumerated_condition_items(
            "展示镇纸。同一回合还必须完整满足全局验收条件："
            "密室手法被重建，凶器、手套等物证被找到。",
            "林晨举起石质镇纸：这就是凶器。",
        )

        self.assertEqual(missing, ["手套"])

    def test_strict_actor_task_ignores_creative_closure_alternatives(self):
        missing = WorkflowController._missing_enumerated_condition_items(
            "以具有明确终止感的尾声画面、行动或落句结束故事。",
            "雨停了。",
        )

        self.assertEqual(missing, [])

    def test_strict_actor_task_requires_actual_police_arrival(self):
        condition = (
            "众人等待救援。同一回合还必须完整满足全局验收条件："
            "外部警察抵达，故事以封闭式结局收束。"
        )

        self.assertEqual(
            WorkflowController._missing_enumerated_condition_items(
                condition,
                "天快亮了，警察也该到了。",
            ),
            ["警方已经进入当前现场"],
        )
        self.assertEqual(
            WorkflowController._missing_enumerated_condition_items(
                condition,
                "走廊传来脚步声，几名警察终于走进现场。",
            ),
            [],
        )
        self.assertEqual(
            WorkflowController._missing_enumerated_condition_items(
                "外部警察抵达，故事封闭收束。",
                "我们就在这里等警察来。",
            ),
            ["警方已经进入当前现场"],
        )

    def test_strict_actor_task_requires_police_custody_and_evidence_handoff(self):
        condition = "外部警察抵达校园，赵深被正式拘留，证据移交警方。"

        self.assertEqual(
            WorkflowController._missing_enumerated_condition_items(
                condition,
                "警车灯光驶入校园，林晨说警察来了。",
            ),
            ["警方已经进入当前现场", "警方拘捕赵深并收取现场证物"],
        )
        self.assertEqual(
            WorkflowController._missing_enumerated_condition_items(
                condition,
                "警察推门进入储藏室，给赵深戴上手铐，并将镇纸和白手套装入证物袋。",
            ),
            [],
        )

    def test_final_goal_injects_explicit_police_handoff_before_closure(self):
        closure = CLOSED_ENDING_COMPLETION_CONDITIONS[0]
        conditions = WorkflowController._ensure_police_handoff_task(
            ["赵深认罪。", closure],
            {
                "goal": "警方实际抵达现场、接管真凶并收取证据。",
                "completion_conditions": ["赵深认罪。", closure],
            },
        )

        self.assertIn("给赵深戴上手铐", conditions[1])
        self.assertIn("装入证物袋", conditions[1])
        self.assertEqual(conditions[-1], closure)

    def test_final_goal_schedules_named_witness_resolutions_before_closure(self):
        closure = CLOSED_ENDING_COMPLETION_CONDITIONS[0]
        conditions = WorkflowController._ensure_final_character_resolution_tasks(
            ["警方接管真凶并收取证据。", closure],
            {"goal": "警方接管真凶并收取证据。"},
            ["林晨", "叶晓", "赵深", "韩旭"],
        )

        self.assertIn("叶晓必须", conditions[1])
        self.assertIn("韩旭必须", conditions[2])
        self.assertEqual(conditions[-1], closure)

    def test_malformed_director_output_retries_instead_of_stopping(self):
        writer = WriterAgent.__new__(WriterAgent)
        writer.config = type("Config", (), {"NEXT_SPEAKER_PROMPT": "{node_goal}{game_outline}{characters}{story_context}"})

        class Client:
            def __init__(self):
                self.responses = ["malformed", "<character>Hero</character><advice>完成检验</advice>"]

            def chat_completion(self, **_kwargs):
                return self.responses.pop(0)

        writer.llm_client = Client()
        speaker, advice = writer.decide_next_speaker(
            node_goal="goal",
            characters=[{"name": "Hero"}],
            story_context="context",
        )

        self.assertEqual(speaker, "Hero")
        self.assertEqual(advice, "完成检验")


if __name__ == "__main__":
    unittest.main()
