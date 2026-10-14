import unittest

from experiment.audit_rolling_story import audit_rolling_state
from agents.writer_agent import WriterAgent


class RollingStoryAuditTests(unittest.TestCase):
    def test_incomplete_checkpoint_fails_closed(self):
        state = {
            "schema_version": "rolling-state/3.2",
            "generation_architecture": "actor-driven-node-goals",
            "core_gdd": {"characters": [{}, {}, {}, {}]},
            "story_graph": {"nodes": {}, "edges": []},
            "scripts": {},
            "goals": {},
            "reviews": {},
            "performances": {},
            "summaries": {},
        }

        errors = audit_rolling_state(state, "")

        self.assertTrue(errors)
        self.assertTrue(any("scripts 节点" in error for error in errors))
        self.assertTrue(any("node4: closure_check" in error for error in errors))

    def test_complete_actor_faithful_checkpoint_passes(self):
        node_ids = ["root", "node1", "node2", "node3", "node4"]
        core_gdd = {
            "characters": [
                {"name": "侦探"}, {"name": "证人"}, {"name": "嫌疑人"}, {"name": "关系人"}
            ],
            "scenes": [{"name": "教室"}],
            "global_goal": {"terminal_conditions": ["警方抵达"]},
        }
        scripts = {}
        performances = {}
        goals = {}
        reviews = {}
        summaries = {}
        previous_script = ""
        for index, node_id in enumerate(node_ids):
            final = index == 4
            turns = [{
                "character": "侦探",
                "action": "站在教室里整理证据",
                "dialogue": "两名警察推门进入教室。" if final else f"线索{index}已经确认。",
                "image": "neutral",
            }]
            if final:
                turns.append({
                    "character": "侦探",
                    "action": "望向放晴的天空",
                    "dialogue": "天亮了。",
                    "image": "neutral",
                })
            goal = {
                "goal": f"完成节点{index}",
                "dramatic_question": "真相是什么？",
                "contributes_to_global_goal": "推进调查",
                "completion_conditions": [f"完成节点{index}"],
                "forbidden_outcomes": [],
                "narrative_phase": "resolution" if final else "escalation",
                "transition_contract": {
                    "relation_to_previous": "root" if index == 0 else "continuation",
                    "source_scene": "" if index == 0 else "教室",
                    "source_speaker": "" if index == 0 else "侦探",
                    "source_anchor": "" if index == 0 else f"线索{index - 1}已经确认。",
                    "bridge_requirement": (
                        "建立初始冲突" if index == 0 else "承接上一条已确认线索"
                    ),
                },
            }
            script = WriterAgent.synthesize_actor_performances(
                WriterAgent.__new__(WriterAgent),
                turns=turns,
                node_goal=goal,
                story_context=previous_script,
                core_gdd=core_gdd,
            ).strip()
            if not final:
                script += f'\n\n<jump target="{node_ids[index + 1]}"/>'
            scripts[node_id] = script + "\n"
            previous_script = scripts[node_id]
            performances[node_id] = turns
            goals[node_id] = goal
            summaries[node_id] = f"节点{index}完成"
            reviews[node_id] = {
                "decision": "PASS",
                "goal_completed": True,
                "continuity_check": {
                    "applicable": index > 0,
                    "relation_to_previous": "root" if index == 0 else "continuation",
                    "source_anchor_acknowledged": True,
                    "discourse_relation_realized": True,
                    "action_continuity_preserved": True,
                    "scene_transition_grounded": True,
                    "evidence": [] if index == 0 else [turns[0]["dialogue"]],
                },
            }

        final_quote = "两名警察推门进入教室。"
        final_beat = "天亮了。"
        reviews["node4"].update({
            "terminal_condition_checks": [{
                "condition": "警方抵达",
                "satisfied": True,
                "evidence": [final_quote],
            }],
            "closure_check": {
                "conflict_resolved": True,
                "consequences_shown": True,
                "character_arcs_paid_off": True,
                "new_equilibrium_established": True,
                "finality_signal_present": True,
                "evidence": [final_quote, final_beat],
                "final_beat": final_beat,
            },
        })
        graph = {
            "nodes": {
                node_id: {"id": node_id, "generation_status": "completed"}
                for node_id in node_ids
            },
            "edges": [
                {
                    "from": node_ids[index],
                    "to": node_ids[index + 1],
                    "choice_text": None,
                    "discourse_relation": "continuation",
                    "source_anchor": f"线索{index}已经确认。",
                }
                for index in range(4)
            ],
        }
        state = {
            "schema_version": "rolling-state/3.2",
            "generation_architecture": "actor-driven-node-goals",
            "core_gdd": core_gdd,
            "story_graph": graph,
            "scripts": scripts,
            "goals": goals,
            "reviews": reviews,
            "performances": performances,
            "summaries": summaries,
        }
        story_text = "\n\n".join(
            f"=== Node: {node_id} ===\n{scripts[node_id].strip()}" for node_id in node_ids
        )

        self.assertEqual(audit_rolling_state(state, story_text), [])


if __name__ == "__main__":
    unittest.main()
