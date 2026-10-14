import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from dashboard import asset_regeneration as regeneration
from dashboard import server
from agents.artist_agent import ArtistAgent
from agents.config import ArtistConfig, PathConfig


def png(color, mode="RGBA"):
    buffer = io.BytesIO()
    Image.new(mode, (24, 32), color).save(buffer, format="PNG")
    return buffer.getvalue()


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = "images/characters/hero/gentle.png"
        self.source = self.root / self.asset
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(png((40, 80, 120, 0)))
        (self.source.parent / "neutral.png").write_bytes(png((50, 90, 130, 0)))
        (self.root / "game_design.json").write_text(json.dumps({"art_style": "anime", "characters": [{"id": "hero", "name": "角色", "appearance": "黑发"}], "scenes": []}))
        self.artist = ArtistAgent.__new__(ArtistAgent)
        self.artist.available = True
        self.artist.client = Mock()
        self.artist.config = ArtistConfig
        self.artist._call_image_api = Mock(return_value=png((180, 100, 50, 128)))
        self.artist._remove_background = Mock()

    def prepare(self, feedback="保留服装，更温柔的表情"):
        return regeneration.prepare(self.root, self.asset, feedback)

    def test_candidate_preserves_original_then_accepts_with_backup(self):
        original = self.source.read_bytes()
        record = self.prepare()
        regeneration.generate(self.root, record["id"], self.artist)
        self.assertEqual(self.source.read_bytes(), original)
        ready = regeneration.latest(self.root, self.asset)
        self.assertEqual(ready["status"], "ready")
        call = self.artist._call_image_api.call_args
        self.assertIn("保留服装", call.args[0])
        self.assertIn("黑发", call.args[0])
        self.assertEqual(len(call.kwargs["reference_image_paths"]), 2)
        self.assertTrue(all(Path(path).is_relative_to(self.root / ".ai4vn") for path in call.kwargs["reference_image_paths"]))
        accepted = regeneration.accept(self.root, record["id"])
        self.assertEqual(accepted["status"], "accepted")
        self.assertNotEqual(self.source.read_bytes(), original)
        self.assertEqual((self.root / accepted["backup"]).read_bytes(), original)
        self.assertEqual(regeneration.accept(self.root, record["id"]), accepted)

    def test_duplicate_jobs_and_unreviewed_candidates_are_rejected(self):
        record = self.prepare()
        with self.assertRaises(RuntimeError):
            self.prepare()
        with self.assertRaises(RuntimeError):
            regeneration.accept(self.root, record["id"])
        with self.assertRaises(RuntimeError):
            regeneration.discard(self.root, record["id"])
        regeneration.generate(self.root, record["id"], self.artist)
        with self.assertRaises(RuntimeError):
            self.prepare()
        regeneration.discard(self.root, record["id"])
        self.assertNotEqual(self.prepare()["id"], record["id"])

    def test_changed_original_cannot_be_overwritten(self):
        record = self.prepare()
        regeneration.generate(self.root, record["id"], self.artist)
        changed = png((10, 10, 10, 0))
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(RuntimeError, "original image was modified by another task"):
            regeneration.accept(self.root, record["id"])
        self.assertEqual(self.source.read_bytes(), changed)

    def test_invalid_response_and_failed_cutout_leave_original_intact(self):
        original = self.source.read_bytes()
        for data in (None, b"not an image", png("white", "RGB")):
            with self.subTest(data=str(data)[:40]):
                record = self.prepare()
                self.artist._call_image_api.return_value = data
                with self.assertRaises(Exception):
                    regeneration.generate(self.root, record["id"], self.artist)
                self.assertEqual(regeneration.read_record(self.root, record["id"])["status"], "failed")
                self.assertEqual(self.source.read_bytes(), original)

    def test_traversal_symlink_and_unsupported_images_are_rejected(self):
        for path in ("../game_design.json", "images/../../outside.png", "images/characters/hero/unknown.png"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                regeneration.prepare(self.root, path, "")
        with self.assertRaises(ValueError):
            regeneration.read_record(self.root, "../escape")
        with tempfile.TemporaryDirectory() as outside:
            foreign = Path(outside) / "foreign.png"
            foreign.write_bytes(png("red"))
            (self.source.parent / "external.png").symlink_to(foreign)
            with self.assertRaises(ValueError):
                regeneration.prepare(self.root, "images/characters/hero/external.png", "")

    def test_background_and_cg_use_original_and_character_references(self):
        background = self.root / "images/backgrounds/教室.png"
        background.parent.mkdir()
        background.write_bytes(png("blue"))
        record = regeneration.prepare(self.root, "images/backgrounds/教室.png", "改成黄昏")
        regeneration.generate(self.root, record["id"], self.artist)
        self.artist._remove_background.assert_not_called()
        cg = self.root / "images/cg/ending.png"
        cg.parent.mkdir()
        cg.write_bytes(png("green"))
        (self.root / "cg_manifest.json").write_text(json.dumps([{"id": "ending", "characters": ["hero"], "description": "天台告别"}]))
        record = regeneration.prepare(self.root, "images/cg/ending.png", "")
        regeneration.generate(self.root, record["id"], self.artist)
        self.assertIn("天台告别", self.artist._call_image_api.call_args.args[0])
        self.assertEqual(len(record["references"]), 2)

    def test_dashboard_uses_same_character_feedback_path_as_actor_workflow(self):
        record = self.prepare()
        with patch.object(self.artist, "generate_character_images", wraps=self.artist.generate_character_images) as generate, patch.object(self.artist, "_build_prompt", wraps=self.artist._build_prompt) as build:
            regeneration.generate(self.root, record["id"], self.artist)
        self.assertEqual(generate.call_args.kwargs["feedback"], record["feedback"])
        self.assertEqual(build.call_args.kwargs["feedback"], record["feedback"])
        self.assertEqual(generate.call_args.kwargs["expressions"], ["gentle"])
        self.assertEqual(build.call_args.kwargs["art_style"], "anime")
        self.assertIn("IMPORTANT CORRECTIONS FROM CHARACTER REVIEW", self.artist._call_image_api.call_args.args[0])
        self.assertNotIn("prompt", record)

    def test_neutral_reference_controls_framing_without_changing_default_prompt(self):
        record = self.prepare("视角和比例参照 neutral")
        regeneration.generate(self.root, record["id"], self.artist)
        call = self.artist._call_image_api.call_args
        context = call.kwargs["reference_context"]
        self.assertIn("Input 2: This is neutral.png", context)
        self.assertIn("viewing angle, body proportions", context)
        self.assertEqual(Path(call.kwargs["reference_image_paths"][1]).read_bytes(), (self.source.parent / "neutral.png").read_bytes())
        self.assertIn("take priority over the default front-facing", call.args[0])
        self.assertIn("Do not invent additional props", call.args[0])
        default_prompt = self.artist._build_prompt({"name": "hero"}, "neutral")
        self.assertNotIn("take priority", default_prompt)

    def test_original_workflow_default_output_skip_and_feedback_are_preserved(self):
        with patch.object(PathConfig, "CHARACTERS_DIR", str(self.root / "images/characters")):
            result = self.artist.generate_character_images({"id": "hero"}, expressions=["gentle"])
            self.assertEqual(result["gentle"], str(self.source))
            self.artist._call_image_api.assert_not_called()
            result = self.artist.generate_character_images({"id": "hero"}, expressions=["gentle"], feedback="更温柔")
            self.assertEqual(result["gentle"], str(self.source))
            self.assertIn("更温柔", self.artist._call_image_api.call_args.args[0])

    def test_title_and_unclassified_assets_delegate_to_artist(self):
        for filename, method in (("title_screen.png", "generate_title_image"), ("extra.png", "generate_image_variation")):
            with self.subTest(filename=filename):
                source = self.root / "images" / filename
                source.write_bytes(png("blue"))
                original = source.read_bytes()
                record = regeneration.prepare(self.root, f"images/{filename}", "更明亮")
                with patch.object(self.artist, method, wraps=getattr(self.artist, method)) as generate:
                    regeneration.generate(self.root, record["id"], self.artist)
                self.assertEqual(generate.call_args.kwargs["feedback"], "更明亮")
                self.assertIn("更明亮", self.artist._call_image_api.call_args.args[0])
                self.assertEqual(source.read_bytes(), original)

    def test_discard_survives_reload_and_cache_url_changes_after_accept(self):
        old_url = next(asset["url"] for asset in server.asset_list(self.root) if asset["path"] == self.asset)
        record = self.prepare()
        regeneration.generate(self.root, record["id"], self.artist)
        regeneration.accept(self.root, record["id"])
        new_url = next(asset["url"] for asset in server.asset_list(self.root) if asset["path"] == self.asset)
        self.assertNotEqual(old_url, new_url)
        record = self.prepare()
        regeneration.generate(self.root, record["id"], self.artist)
        regeneration.discard(self.root, record["id"])
        self.assertEqual(regeneration.latest(self.root, self.asset)["status"], "discarded")

    def test_api_response_hides_internal_prompt_and_uses_encoded_project(self):
        record = self.prepare()
        response = server.regeneration_result("中文游戏", record)["request"]
        self.assertNotIn("prompt", response)
        self.assertIn("%E4%B8%AD", response["original_url"])
        self.assertIsNone(response["candidate_url"])

    def test_crashed_job_is_recoverable(self):
        record = self.prepare()
        job = {"kind": "asset-regenerate", "command": [record["id"]], "status": "failed"}
        with patch.object(server, "project_dir", return_value=self.root), patch.dict(server.JOBS, {"failed": job}, clear=True):
            result = server.current_regeneration("demo", self.asset)
        self.assertEqual(result["request"]["status"], "failed")
        self.prepare()
