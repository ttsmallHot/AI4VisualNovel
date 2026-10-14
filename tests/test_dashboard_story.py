import tempfile
import unittest
import json
import threading
import base64
import io
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from unittest.mock import patch
from PIL import Image

import dashboard.server as server
from main import load_input_config
from dashboard.server import asset_list, parse_story, replace_story_node, save_story_node


STORY = """=== Node: root ===
<scene>天台</scene>
<content id="旁白">开始。</content>
<cg id="root_promise"/>

=== Node: node1 ===
<scene>旧美术室</scene>
<content id="林星夏">继续。</content>
"""


class DashboardStoryTests(unittest.TestCase):
    def test_partial_outputs_are_not_reported_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "game_design.json").write_text('{"title":"Novel"}')
            (root / "story_graph.json").write_text('{"nodes":{"root":{},"node1":{}}}')
            (root / "story.txt").write_text('=== Node: root ===\n<content id="旁白">Start</content>')
            (root / "cg_manifest.json").write_text('[{"id":"ending"}]')
            (root / "images").mkdir()
            (root / "images" / "title_screen.png").write_bytes(b"image")
            progress = server.generation_progress(root)
            self.assertFalse(progress["script_complete"])
            self.assertEqual(progress["missing_nodes"], ["node1"])
            self.assertFalse(progress["assets_complete"])
            self.assertEqual(progress["missing_assets"], ["images/cg/ending.png"])
            (root / "story.txt").write_text(STORY)
            (root / "images" / "cg").mkdir()
            (root / "images" / "cg" / "ending.png").write_bytes(b"image")
            progress = server.generation_progress(root)
            self.assertTrue(progress["script_complete"])
            self.assertTrue(progress["assets_complete"])

    def test_library_excludes_other_games_and_empty_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("empty", "web_game", "novel", "draft"):
                (root / name).mkdir()
            (root / "web_game" / "project.json").write_text('{"title":"Web game"}')
            (root / "web_game" / "index.html").write_text("<html></html>")
            (root / "novel" / "game_design.json").write_text('{"title":"Novel"}')
            (root / "draft" / ".ai4vn").mkdir()
            (root / "draft" / ".ai4vn" / "design_input.json").write_text("{}")
            with patch.object(server, "PROJECTS_ROOT", root), patch.object(server, "INCLUDE_LEGACY", False):
                self.assertEqual({p["name"] for p in server.list_projects()}, {"novel", "draft"})
            self.assertTrue((root / "web_game" / "index.html").exists())

    def test_projects_endpoint_creates_draft_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            with patch.object(server, "PROJECTS_ROOT", root), patch.object(server, "INCLUDE_LEGACY", False):
                thread.start()
                try:
                    request = Request(
                        f"http://127.0.0.1:{httpd.server_port}/api/projects",
                        data=json.dumps({"name": "new_game", "title": "新游戏", "story_requirements": "校园悬疑"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(request) as response:
                        self.assertEqual(response.status, 201)
                        self.assertEqual(json.load(response)["project"], "new_game")
                    game = root / "new_game"
                    self.assertEqual(server.design_inputs(game)["story_requirements"], "校园悬疑")
                    self.assertFalse((game / "game_design.json").exists())
                    self.assertEqual(server.list_projects()[0]["title"], "新游戏")
                    before = (game / "requirements.txt").read_bytes()
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request)
                    self.assertEqual(raised.exception.code, 409)
                    self.assertEqual((game / "requirements.txt").read_bytes(), before)
                    server.create_game({"title": "中文游戏"})
                    uploaded = root / "中文游戏" / ".ai4vn/oc/character_1/portrait.png"
                    uploaded.parent.mkdir(parents=True)
                    Image.new("RGBA", (2, 2)).save(uploaded)
                    media_url = f"http://127.0.0.1:{httpd.server_port}/media/{quote('中文游戏')}/.ai4vn/oc/character_1/portrait.png"
                    with urlopen(media_url) as response:
                        self.assertEqual(response.read(), uploaded.read_bytes())
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(f"http://127.0.0.1:{httpd.server_port}/media/{quote('中文游戏')}/.ai4vn/design_input.json")
                    self.assertEqual(denied.exception.code, 400)
                finally:
                    httpd.shutdown()
                    thread.join()
                    httpd.server_close()

    def test_create_game_validates_paths_and_rolls_back_incomplete_drafts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "games"
            with patch.object(server, "PROJECTS_ROOT", root):
                for payload in ([], {"title": " "}, {"title": "a" * 81},
                                {"title": "测试", "name": "../escape"},
                                {"title": "测试", "name": "/tmp/escape"},
                                {"title": "测试", "story_requirements": []}):
                    with self.subTest(payload=payload), self.assertRaises(ValueError):
                        server.create_game(payload)
                self.assertFalse(root.exists())
                with patch.object(server, "save_design_inputs", side_effect=OSError("write failed")):
                    with self.assertRaises(OSError):
                        server.create_game({"title": "未完成"})
                self.assertEqual(list(root.iterdir()), [])
                result = server.create_game({"title": "夏日：来信", "story_requirements": "广播站的故事"})
                self.assertEqual(result["project"], "夏日_来信")
                self.assertTrue((root / result["project"] / ".ai4vn/design_input.json").is_file())

    def test_create_game_does_not_overwrite_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "games"
            root.mkdir()
            original = Path(temp_dir) / "original"
            original.mkdir()
            (original / "keep.txt").write_text("keep")
            (root / "existing").symlink_to(original, target_is_directory=True)
            with patch.object(server, "PROJECTS_ROOT", root), self.assertRaises(FileExistsError):
                server.create_game({"title": "existing"})
            self.assertEqual((original / "keep.txt").read_text(), "keep")

    def test_create_game_uploads_oc_and_preserves_image_through_design_pipeline(self):
        from workflow import WorkflowController
        from agents.config import PathConfig

        picture = io.BytesIO()
        Image.new("RGBA", (20, 30), (120, 40, 80, 180)).save(picture, format="PNG")
        encoded = "data:image/png;base64," + base64.b64encode(picture.getvalue()).decode()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(server, "PROJECTS_ROOT", root):
                result = server.create_game({"title": "OC故事", "character_count": 2, "scenes": ["天台"], "characters": [{"id": "my_oc", "name": "星夏", "is_protagonist": True, "neutral_image_data": encoded}]})
            game = root / result["project"]
            saved = server.design_inputs(game)
            character = saved["characters"][0]
            self.assertEqual(character["id"], "my_oc")
            self.assertNotIn("neutral_image_data", character)
            image_path = game / character["neutral_image_path"]
            with Image.open(image_path) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (20, 30))
            server.save_design_inputs(game, saved)
            config = load_input_config(str(game / ".ai4vn/design_input.json"))
            self.assertEqual(config["oc"]["characters"][0]["neutral_image_path"], character["neutral_image_path"])
            workflow = WorkflowController.__new__(WorkflowController)
            with patch.object(PathConfig, "PROJECT_ROOT", str(game)), patch.object(PathConfig, "CHARACTERS_DIR", str(game / "images/characters")):
                workflow._prepare_oc_images(config["oc"]["characters"])
            self.assertEqual((game / "images/characters/my_oc/neutral.png").read_bytes(), image_path.read_bytes())

    def test_create_game_rejects_invalid_oc_without_leaving_a_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(server, "PROJECTS_ROOT", root):
                for fields in ({"neutral_image_data": "data:image/png;base64,garbage"},
                               {"neutral_image_path": "../../outside.png"},
                               {"id": "../escape"}):
                    with self.subTest(fields=fields), self.assertRaises(ValueError):
                        server.create_game({"title": "invalid", "characters": [{"name": "OC", **fields}]})
                    self.assertEqual(list(root.iterdir()), [])

    def test_design_inputs_save_scenes_and_locked_characters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "requirements.txt").write_text("原有构想\n", encoding="utf-8")
            options = {"story_requirements": "校园悬疑", "scenes": ["旧美术室：藏有线索", "天台"], "character_count": 3, "characters": [{"name": "林星夏", "personality": "冷静", "is_protagonist": True}]}
            flags = server.save_design_inputs(root, options)
            self.assertEqual(flags[-2:], ["--character-count", "3"])
            self.assertIn("旧美术室：藏有线索", (root / "requirements.txt").read_text(encoding="utf-8"))
            saved = load_input_config(str(root / ".ai4vn" / "design_input.json"))
            self.assertEqual(saved["oc"]["characters"][0]["name"], "林星夏")
            self.assertEqual(saved["oc"]["characters"][0]["id"], "character_1")
            self.assertEqual(server.design_inputs(root)["scenes"], options["scenes"])

    def test_design_inputs_reject_invalid_data_without_overwriting_requirements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "requirements.txt").write_text("保留原文\n", encoding="utf-8")
            for options in (
                {"character_count": 0},
                {"character_count": 1, "characters": [{"name": "甲"}, {"name": "乙"}]},
                {"characters": [{"name": "甲"}, {"name": "甲"}]},
                {"scenes": [" "]},
            ):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    server.save_design_inputs(root, options)
            self.assertEqual((root / "requirements.txt").read_text(encoding="utf-8"), "保留原文\n")

    def test_run_design_endpoint_uses_saved_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo").mkdir()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            with patch.object(server, "PROJECTS_ROOT", root), patch.object(server, "INCLUDE_LEGACY", False), patch.object(server, "new_job", return_value="test-job") as new_job:
                thread.start()
                try:
                    payload = json.dumps({"project": "demo", "mode": "design", "design_input": {"story_requirements": "悬疑", "scenes": ["天台"], "character_count": 2, "characters": [{"name": "星夏"}]}}).encode("utf-8")
                    request = Request(f"http://127.0.0.1:{httpd.server_port}/api/run", data=payload, headers={"Content-Type": "application/json"})
                    with urlopen(request) as response:
                        self.assertEqual(response.status, 202)
                    command = new_job.call_args.args[2]
                    self.assertEqual(command[command.index("--character-count") + 1], "2")
                    self.assertTrue((root / "demo" / ".ai4vn" / "design_input.json").is_file())
                finally:
                    httpd.shutdown()
                    thread.join()
                    httpd.server_close()

    def test_project_library_uses_each_games_background_as_cover(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first"
            second = root / "second"
            (first / "images" / "backgrounds").mkdir(parents=True)
            (first / "images" / "cg").mkdir(parents=True)
            second.mkdir()
            (second / "game_design.json").write_text("{}")
            (first / "images" / "backgrounds" / "天台.png").write_bytes(b"image")
            (first / "images" / "cg" / "event.png").write_bytes(b"image")
            (first / "game_design.json").write_text(
                json.dumps({"title": "第一部", "background": "校园故事"}), encoding="utf-8"
            )
            with patch.object(server, "PROJECTS_ROOT", root), patch.object(server, "INCLUDE_LEGACY", False):
                projects = {project["name"]: project for project in server.list_projects()}

            self.assertEqual(projects["first"]["title"], "第一部")
            self.assertEqual(projects["first"]["description"], "校园故事")
            self.assertEqual(projects["first"]["cover"], "/media/first/images/backgrounds/%E5%A4%A9%E5%8F%B0.png")
            self.assertIsNone(projects["second"]["cover"])

    def test_parse_story_includes_editable_raw_content(self):
        nodes = parse_story(STORY)
        self.assertEqual(nodes[0]["id"], "root")
        self.assertIn("<scene>天台</scene>", nodes[0]["raw"])
        self.assertEqual(nodes[1]["lines"][1]["speaker"], "林星夏")
        self.assertEqual(nodes[0]["lines"][2], {"type": "cg", "id": "root_promise"})

    def test_asset_list_classifies_cg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cg_dir = root / "images" / "cg"
            cg_dir.mkdir(parents=True)
            (cg_dir / "root_promise.png").write_bytes(b"png")
            assets = asset_list(root, "demo")
            self.assertEqual(assets[0]["category"], "cg")
            self.assertEqual(assets[0]["kind"], "cg")

    def test_replace_story_node_preserves_other_nodes(self):
        updated = replace_story_node(STORY, "root", '<scene>教室</scene>\n<content id="旁白">修改。</content>')
        nodes = parse_story(updated)
        self.assertIn("修改。", nodes[0]["raw"])
        self.assertEqual(nodes[1]["raw"], parse_story(STORY)[1]["raw"])

    def test_rejects_nested_node_marker(self):
        with self.assertRaises(ValueError):
            replace_story_node(STORY, "root", "=== Node: injected ===")

    def test_save_detects_stale_editor_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "story.txt"
            path.write_text(STORY, encoding="utf-8")
            original = parse_story(STORY)[0]["raw"]
            save_story_node(path, "root", "<scene>教室</scene>", original)
            with self.assertRaises(RuntimeError):
                save_story_node(path, "root", "<scene>公园</scene>", original)


if __name__ == "__main__":
    unittest.main()
