from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

import workflow
from agents.artist_agent import ArtistAgent
from workflow import WorkflowController


@pytest.fixture
def render_workflow(tmp_path, monkeypatch):
    images = tmp_path / "images"
    paths = SimpleNamespace(
        IMAGES_DIR=str(images), BACKGROUNDS_DIR=str(images / "backgrounds"),
        CHARACTERS_DIR=str(images / "characters"), CG_DIR=str(images / "cg"),
    )
    monkeypatch.setattr(workflow, "PathConfig", paths)
    controller = WorkflowController.__new__(WorkflowController)
    controller.game_design = {
        "characters": [{"id": "hero", "name": "Hero"}],
        "scenes": [{"name": "School"}],
    }
    controller.expressions_db = {"Hero": ["neutral", "happy"]}
    controller._load_cg_manifest = Mock(return_value=[{"id": "ending"}])
    controller.load_existing_game = Mock(return_value=True)
    controller._initialize_actors = Mock()
    controller._sync_expressions_with_design = Mock()
    controller._generate_character_assets = Mock()
    controller._generate_cg_assets = Mock()
    controller.artist = Mock()
    controller.artist.generate_title_image.return_value = None
    for name in ["title_screen.png", "backgrounds/School.png",
                 "characters/hero/neutral.png", "characters/hero/happy.png", "cg/ending.png"]:
        path = images / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2, 2)).save(path)
    return controller, images


@pytest.mark.parametrize("missing", ["title_screen.png", "cg/ending.png",
                                      "backgrounds/School.png", "characters/hero/happy.png"])
def test_render_rejects_missing_assets(render_workflow, missing):
    controller, images = render_workflow
    (images / missing).unlink()
    with pytest.raises(RuntimeError, match="资产渲染未完成") as error:
        controller.run_render_phase()
    assert missing in str(error.value)


def test_render_rejects_corrupt_image(render_workflow):
    controller, images = render_workflow
    (images / "cg/ending.png").write_bytes(b"not an image")
    with pytest.raises(RuntimeError, match="cg/ending.png"):
        controller.run_render_phase()


def test_render_accepts_complete_existing_assets(render_workflow):
    controller, _ = render_workflow
    assert controller.run_render_phase() is True


def test_resume_preserves_existing_cg_without_model_calls(render_workflow):
    controller, images = render_workflow
    controller.actors = {}
    result = WorkflowController._generate_cg_assets(controller)
    assert result == {"ending": str(images / "cg/ending.png")}
    controller.artist.generate_cg.assert_not_called()


def test_resume_preserves_existing_cover(render_workflow, monkeypatch):
    _, images = render_workflow
    monkeypatch.setattr("agents.artist_agent.PathConfig", workflow.PathConfig)
    artist = ArtistAgent.__new__(ArtistAgent)
    artist._call_image_api = Mock()
    path = images / "title_screen.png"
    before = path.read_bytes()
    assert artist.generate_title_image("Title", "Story") == str(path)
    assert path.read_bytes() == before
    artist._call_image_api.assert_not_called()


def test_parallel_failure_keeps_successful_nodes_and_blocks_descendants(monkeypatch):
    controller = WorkflowController.__new__(WorkflowController)
    ids = ["root", "left", "right", "end"]
    controller.game_design = {"story_graph": {
        "nodes": {key: {"id": key, "summary": key, "type": "normal"} for key in ids},
        "edges": [{"from": a, "to": b, "choice_text": b} for a, b in
                  [("root", "left"), ("root", "right"), ("left", "end"), ("right", "end")]],
    }}
    saved = {"root": "Existing root"}
    controller._extract_node_story = lambda node: saved.get(node, "")
    controller._save_node_story = lambda node, script: saved.update({node: script})
    controller._register_node_memory = Mock()
    controller._load_cg_manifest = Mock(return_value=[])
    controller._save_cg_manifest = Mock()
    monkeypatch.setattr(workflow, "MemoryManager", Mock())

    def generate(node, *_args, **_kwargs):
        if node == "right":
            raise RuntimeError("API unavailable")
        return {"script": f"Generated {node}", "cgs": []}

    controller._generate_node_script = Mock(side_effect=generate)
    with pytest.raises(RuntimeError, match="缺失节点: right"):
        controller._generate_full_story()
    assert saved == {"root": "Existing root", "left": "Generated left"}
    assert {call.args[0] for call in controller._generate_node_script.call_args_list} == {"left", "right"}

    controller._generate_node_script = Mock(return_value={"script": "Resumed", "cgs": []})
    controller._generate_full_story()
    assert set(saved) == set(ids)
    assert saved["left"] == "Generated left"


def test_invalid_graph_failure_is_not_swallowed():
    controller = WorkflowController.__new__(WorkflowController)
    controller.game_design = {"story_graph": {"nodes": {}, "edges": []}}
    with pytest.raises(ValueError, match="故事图验证失败"):
        controller._generate_full_story()


def test_cli_exits_nonzero_when_render_fails(monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--mode", "render", "--project", "test"])
    monkeypatch.setattr(main.PathConfig, "init", Mock())
    monkeypatch.setattr("game_engine.config.DataPaths.configure", Mock())
    monkeypatch.setattr(main, "setup_logging", Mock())
    monkeypatch.setattr(main, "render_game_flow", Mock(side_effect=RuntimeError("missing CG")))
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 1
