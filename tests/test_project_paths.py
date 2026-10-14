import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.config import PathConfig
from project_paths import resolve_project_path, projects_root, discover_projects, TOOL_ROOT


class ProjectPathTests(unittest.TestCase):
    def test_default_games_root_is_inside_repository(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(projects_root(), TOOL_ROOT / "games")

    def test_discovery_does_not_merge_legacy_projects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "games" / "wanfeng").mkdir(parents=True)
            (root / "data" / "old_game").mkdir(parents=True)
            with patch("project_paths.LEGACY_PROJECTS_ROOT", root / "data"):
                self.assertEqual(set(discover_projects(root / "games")), {"wanfeng"})

    def test_project_name_defaults_to_standalone_projects_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            self.assertEqual(resolve_project_path("new_game", root=root), (root / "new_game").resolve())

    def test_explicit_project_path_is_used_directly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "my_game"
            self.assertEqual(resolve_project_path(str(project)), project.resolve())

    def test_path_config_separates_content_and_runtime_files(self):
        fields = (
            "PROJECTS_ROOT",
            "PROJECT_NAME",
            "PROJECT_DIR",
            "DATA_DIR",
            "IMAGES_DIR",
            "CHARACTERS_DIR",
            "BACKGROUNDS_DIR",
            "CG_DIR",
            "GAME_DESIGN_FILE",
            "STORY_GRAPH_FILE",
            "STORY_FILE",
            "CHARACTER_INFO_FILE",
            "CG_MANIFEST_FILE",
            "RUNTIME_DIR",
            "LOG_DIR",
            "TEXT_LOG_DIR",
            "IMAGE_LOG_DIR",
            "CHROMA_DIR",
            "BUILD_DIR",
        )
        original = {field: getattr(PathConfig, field) for field in fields}
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                PathConfig.PROJECTS_ROOT = temp_dir
                PathConfig.init("my_game")

                project = (Path(temp_dir) / "my_game").resolve()
                self.assertEqual(Path(PathConfig.DATA_DIR), project)
                self.assertEqual(Path(PathConfig.GAME_DESIGN_FILE), project / "game_design.json")
                self.assertEqual(Path(PathConfig.IMAGES_DIR), project / "images")
                self.assertEqual(Path(PathConfig.CG_DIR), project / "images" / "cg")
                self.assertEqual(Path(PathConfig.CG_MANIFEST_FILE), project / "cg_manifest.json")
                self.assertEqual(Path(PathConfig.LOG_DIR), project / ".ai4vn" / "logs")
                self.assertEqual(Path(PathConfig.BUILD_DIR), project / ".ai4vn" / "builds")
        finally:
            for field, value in original.items():
                setattr(PathConfig, field, value)


if __name__ == "__main__":
    unittest.main()
