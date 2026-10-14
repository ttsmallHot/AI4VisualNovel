"""English localization must preserve narration and asset references."""
from pathlib import Path

import pytest

from dashboard.server import parse_story
from export_renpy import convert_to_renpy
from game_engine.data import StoryParser


@pytest.mark.parametrize("narrator", ["Narrator", "narrator", "旁白"])
def test_narration_in_dashboard_engine_and_export(tmp_path, narrator):
    story = f'=== Node: root ===\n<content id="{narrator}">The lights flicker.</content>\n'
    assert parse_story(story)[0]["lines"][0]["type"] == "narration"
    assert StoryParser.parse_story(story)["root"][0] == {
        "type": "narrator", "text": "The lights flicker."
    }
    exported = convert_to_renpy({}, story, tmp_path)
    assert '    "The lights flicker."' in exported
    assert f'{narrator}：' not in exported


def test_english_names_resolve_existing_art_in_export(tmp_path):
    images = tmp_path / "images"
    for relative in ["backgrounds/Student_Council_Office.png", "characters/xiaoqi/neutral.png"]:
        path = images / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")
    design = {
        "characters": [{"id": "xiaoqi", "name": "Lin Xiaoqi"}],
        "scenes": [{"id": "scene_council", "name": "Student Council Office"}],
    }
    story = '''=== Node: root ===
<scene>Student Council Office</scene>
<image id="Lin Xiaoqi">neutral</image>
<content id="Lin Xiaoqi">That doesn't add up.</content>
'''
    exported = convert_to_renpy(design, story, images)
    assert 'image bg_scene_council = "images/backgrounds/Student_Council_Office.png"' in exported
    assert "    scene bg_scene_council" in exported
    assert "    show xiaoqi neutral" in exported
    assert '    ch_xiaoqi "That doesn\'t add up."' in exported


def test_export_prefers_stable_scene_id_when_both_filenames_exist(tmp_path):
    backgrounds = tmp_path / "backgrounds"
    backgrounds.mkdir()
    for filename in ["office.png", "Student_Council_Office.png"]:
        (backgrounds / filename).write_bytes(b"image")
    exported = convert_to_renpy(
        {"scenes": [{"id": "office", "name": "Student Council Office"}]},
        "=== Node: root ===\n<scene>Student Council Office</scene>", tmp_path,
    )
    assert 'image bg_office = "images/backgrounds/office.png"' in exported
