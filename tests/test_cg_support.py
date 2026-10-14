import tempfile
import unittest
from pathlib import Path

from export_renpy import convert_to_renpy
from game_engine.data import StoryParser
from workflow import _is_valid_expression_name


class CGSupportTests(unittest.TestCase):
    def test_expression_name_validation_rejects_partial_draft_tokens(self):
        self.assertTrue(_is_valid_expression_name("neutral"))
        self.assertTrue(_is_valid_expression_name("喜悦"))
        self.assertFalse(_is_valid_expression_name("n"))
        self.assertFalse(_is_valid_expression_name("u"))
        self.assertFalse(_is_valid_expression_name("gentle</image>"))

    def test_story_parser_reads_cg_tag(self):
        story = """=== Node: root ===
<scene>天台</scene>
<cg id="root_promise"/>
<content id="旁白">晚风吹过。</content>
"""
        lines = StoryParser.parse_story(story)["root"]
        self.assertEqual(lines[1], {"type": "cg", "value": "root_promise"})

    def test_renpy_export_defines_and_displays_cg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            images_root = Path(temp_dir) / "images"
            cg_dir = images_root / "cg"
            cg_dir.mkdir(parents=True)
            (cg_dir / "root_promise.png").write_bytes(b"png")
            script = convert_to_renpy(
                {"characters": [], "scenes": [{"id": "roof", "name": "天台"}]},
                """=== Node: root ===
<scene>天台</scene>
<cg id="root_promise"/>
<content id="旁白">晚风吹过。</content>
""",
                images_root,
            )
            self.assertIn('image cg_root_promise = "images/cg/root_promise.png"', script)
            self.assertIn("scene cg_root_promise", script)


if __name__ == "__main__":
    unittest.main()
