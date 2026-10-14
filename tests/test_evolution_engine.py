import json
import tempfile
import unittest
from pathlib import Path

from agents.story_graph import StoryGraph
from evolution.engine import EvolutionEngine
from game_engine.data import StoryParser


class FakeEvolutionBackend:
    def __init__(self):
        self.written_nodes = []

    def create_core_gdd(self, requirements, character_count, locked_characters=None):
        return {
            "schema_version": "evo-gdd/1.0",
            "title": "Stateful Test",
            "background": requirements or "A test world",
            "art_style": "minimal",
            "themes": ["consequence"],
            "world_rules": ["Choices persist"],
            "immutable_facts": ["The key starts hidden"],
            "initial_conflict": "Find the key",
            "ending_conditions": ["A branch resolves"],
            "characters": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "gender": "unknown",
                    "is_protagonist": True,
                    "personality": "curious",
                    "appearance": "plain",
                    "background": "tester",
                    "desire": "learn",
                    "fear": "stagnation",
                    "secret": "none",
                }
            ],
            "scenes": [{"id": "room", "name": "Room", "description": "A room"}],
            "initial_world_state": {"route": "unset", "shared": {"count": 0}},
            "initial_agenda": {
                "open_questions": ["Where is the key?"],
                "unresolved_conflicts": ["Find the key"],
                "foreshadowing": [],
                "character_arcs": {},
            },
        }

    def create_initial_contract(self, core_gdd):
        return self._contract("Choose a route")

    def write_scene(self, core_gdd, cursor, parent_script):
        self.written_nodes.append(cursor.node_id)
        return f'<scene>Room</scene>\n<content id="旁白">{cursor.node_id}</content>'

    def reduce_scene(self, core_gdd, cursor, scene_script):
        route = cursor.contract["goal"].split()[-1].lower()
        return {
            "summary": f"Completed {cursor.node_id}",
            "goal_completed": True,
            "updates": [
                {"path": "route", "value": route, "evidence": scene_script},
                {"path": "shared.count", "value": cursor.depth + 1, "evidence": scene_script},
            ],
            "agenda": cursor.agenda,
        }

    def expand_story(
        self,
        core_gdd,
        cursor,
        scene_script,
        transition,
        world_state,
        agenda,
        max_children,
    ):
        if cursor.node_id == "root":
            return {
                "story_complete": False,
                "completion_reason": "",
                "next_nodes": [
                    {"choice_text": "Left", "contract": self._contract("Take LEFT")},
                    {"choice_text": "Right", "contract": self._contract("Take RIGHT")},
                ][:max_children],
            }
        return {"story_complete": True, "completion_reason": "branch complete", "next_nodes": []}

    @staticmethod
    def _contract(goal):
        return {
            "goal": goal,
            "dramatic_question": "What changes?",
            "active_cast": ["Hero"],
            "location": "Room",
            "required_outcomes": ["A decision"],
            "forbidden_outcomes": [],
        }


class EvolutionEngineTests(unittest.TestCase):
    def test_branch_state_is_independent_and_outputs_are_compatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = FakeEvolutionBackend()
            snapshot = EvolutionEngine(temp_dir, backend, max_nodes=3).run("test", 1)

            self.assertEqual(snapshot.completed, ["root", "node1", "node2"])
            self.assertEqual(snapshot.cursors["node1"].world_state["route"], "route")
            self.assertEqual(snapshot.cursors["node2"].world_state["route"], "route")
            self.assertEqual(snapshot.node_results["node1"]["world_state"]["route"], "left")
            self.assertEqual(snapshot.node_results["node2"]["world_state"]["route"], "right")
            snapshot.cursors["node1"].world_state["shared"]["count"] = 99
            self.assertEqual(snapshot.cursors["node2"].world_state["shared"]["count"], 1)
            self.assertIn('<choice target="node1">Left</choice>', snapshot.scripts["root"])
            self.assertIn('<choice target="node2">Right</choice>', snapshot.scripts["root"])

            output_dir = Path(temp_dir)
            for filename in ("game_design.json", "story_graph.json", "story.txt", "evolution_state.json"):
                self.assertTrue((output_dir / filename).exists())
            game_design = json.loads((output_dir / "game_design.json").read_text(encoding="utf-8"))
            self.assertEqual(game_design["generation_mode"], "evolutionary")
            self.assertEqual(len(game_design["story_graph"]["nodes"]), 3)
            graph = StoryGraph(game_design)
            self.assertEqual(graph.validate(), (True, "验证通过"))
            parsed_story = StoryParser.parse_story(
                (output_dir / "story.txt").read_text(encoding="utf-8")
            )
            self.assertEqual(set(parsed_story), {"root", "node1", "node2"})
            root_choices = [
                line for line in parsed_story["root"] if line["type"] == "choice_option"
            ]
            self.assertEqual([choice["target"] for choice in root_choices], ["node1", "node2"])

    def test_resume_does_not_generate_completed_nodes_again(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_backend = FakeEvolutionBackend()
            first = EvolutionEngine(temp_dir, first_backend, max_nodes=3).run()
            self.assertEqual(len(first.completed), 3)

            resumed_backend = FakeEvolutionBackend()
            Path(temp_dir, "story.txt").write_text("stale", encoding="utf-8")
            resumed = EvolutionEngine(temp_dir, resumed_backend, max_nodes=3).run(resume=True)
            self.assertEqual(resumed.completed, first.completed)
            self.assertEqual(resumed_backend.written_nodes, [])
            self.assertIn("=== Node: root ===", Path(temp_dir, "story.txt").read_text(encoding="utf-8"))

    def test_max_node_limit_caps_expansion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = FakeEvolutionBackend()
            snapshot = EvolutionEngine(temp_dir, backend, max_nodes=2, max_children=4).run()

            self.assertEqual(len(snapshot.story_graph["nodes"]), 2)
            self.assertEqual(backend.written_nodes, ["root", "node1"])

    def test_existing_state_requires_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            EvolutionEngine(temp_dir, FakeEvolutionBackend(), max_nodes=1).run()
            with self.assertRaises(FileExistsError):
                EvolutionEngine(temp_dir, FakeEvolutionBackend(), max_nodes=1).run(resume=False)


if __name__ == "__main__":
    unittest.main()
