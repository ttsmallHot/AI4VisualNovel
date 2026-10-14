import unittest

from evolution.llm_backend import LLMEvolutionBackend
from evolution.state import NodeCursor


class StubLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class LLMEvolutionBackendTests(unittest.TestCase):
    def setUp(self):
        self.core_gdd = {
            "title": "Test",
            "background": "Test world",
            "themes": [],
            "world_rules": [],
            "immutable_facts": [],
            "characters": [
                {"id": "kaelen", "name": "Kaelen", "personality": "calm"},
            ],
            "scenes": [{"id": "bay", "name": "Cryo Bay", "description": "Cold"}],
        }
        self.cursor = NodeCursor(
            node_id="root",
            parent_id=None,
            depth=0,
            path=["root"],
            contract={
                "goal": "Wake up",
                "dramatic_question": "What happened?",
                "active_cast": ["Kaelen"],
                "location": "Cryo Bay",
                "required_outcomes": [],
                "forbidden_outcomes": [],
            },
            world_state={},
            agenda={},
        )

    def test_write_scene_splits_embedded_narration(self):
        raw_script = "\n".join(
            [
                "<scene>Cryo Bay</scene>",
                '<content id="kaelen">“Wait.” Kaelen lowered his voice. “Listen.”</content>',
                '<image id="kaelen">worried</image>',
            ]
        )
        backend = LLMEvolutionBackend.__new__(LLMEvolutionBackend)
        backend.llm = StubLLM(raw_script)

        script = backend.write_scene(self.core_gdd, self.cursor, "")

        self.assertEqual(
            script.splitlines(),
            [
                "<scene>Cryo Bay</scene>",
                '<content id="kaelen">Wait.</content>',
                '<content id="旁白">Kaelen lowered his voice.</content>',
                '<content id="kaelen">Listen.</content>',
                '<image id="Kaelen">worried</image>',
            ],
        )
        prompt = backend.llm.calls[0]["messages"][1]["content"]
        self.assertIn("spoken dialogue only", prompt)
        self.assertIn("separate 旁白", prompt)


if __name__ == "__main__":
    unittest.main()
