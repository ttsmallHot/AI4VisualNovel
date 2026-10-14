import unittest

from agents.schemas import ACTOR_PERFORMANCE_SCHEMA
from agents.writer_agent import WriterAgent


class WriterAgentTests(unittest.TestCase):
    def test_actor_performance_separates_action_and_dialogue(self):
        self.assertEqual(
            ACTOR_PERFORMANCE_SCHEMA["required"],
            ["thought", "action", "dialogue", "image"],
        )
        self.assertFalse(ACTOR_PERFORMANCE_SCHEMA["additionalProperties"])

    def test_normalize_cg_package_keeps_minimal_manifest_and_maps_character_ids(self):
        description = (
            "傍晚的学校天台，林星夏站在画面中央，苏绘位于左侧，唐音位于右侧。"
            "三人把手叠在一起，目光坚定。镜头采用略微仰视的中近景，夕阳从右后方形成金色轮廓光，"
            "远处城市轻微虚化；保持校服、发型和手中笔记本连续，不得出现额外人物、文字、水印或错误肢体。"
        )
        package = {
            "script": '<scene>学校天台</scene>\n<cg id="root_promise"/>',
            "cgs": [{
                "id": "root_promise",
                "node_id": "root",
                "characters": ["林星夏", "SuHui"],
                "description": description,
            }],
        }
        result = WriterAgent.normalize_cg_package(
            package,
            node_id="root",
            available_characters=[
                {"id": "LinXingxia", "name": "林星夏"},
                {"id": "SuHui", "name": "苏绘"},
            ],
        )
        self.assertIn('<cg id="root_promise"/>', result["script"])
        self.assertEqual(result["cgs"][0]["characters"], ["LinXingxia", "SuHui"])
        self.assertEqual(set(result["cgs"][0]), {"id", "node_id", "characters", "description"})

    def test_cg_remains_visible_for_its_first_dialogue(self):
        script = '<cg id="ending"/>\n<image id="Hero">happy</image>\n<content id="Hero">Goodbye</content>\n'
        result = WriterAgent.normalize_cg_visibility(script)
        self.assertEqual(result, '<image id="Hero">happy</image>\n<cg id="ending"/>\n<content id="Hero">Goodbye</content>\n')
        self.assertEqual(WriterAgent.normalize_cg_visibility(result), result)

    def test_normalize_cg_package_removes_tag_without_valid_manifest(self):
        result = WriterAgent.normalize_cg_package(
            {"script": '<scene>学校天台</scene>\n<cg id="missing"/>', "cgs": []},
            node_id="root",
            available_characters=[],
        )
        self.assertNotIn("<cg", result["script"])

    def test_normalize_dialogue_narration_splits_mixed_content(self):
        script = (
            '<content id="凯伦">“我在想第四个人。”凯伦的声音低得像忏悔。'
            '“一个本该在场的船员。”</content>'
        )

        normalized = WriterAgent.normalize_dialogue_narration(script)

        self.assertEqual(
            normalized.splitlines(),
            [
                '<content id="凯伦">我在想第四个人。</content>',
                '<content id="旁白">凯伦的声音低得像忏悔。</content>',
                '<content id="凯伦">一个本该在场的船员。</content>',
            ],
        )

    def test_normalize_dialogue_narration_preserves_valid_script(self):
        script = "\n".join(
            [
                '<content id="凯伦">我在想第四个人。</content>',
                '<content id="旁白">凯伦的声音低得像忏悔。</content>',
            ]
        )
        self.assertEqual(
            WriterAgent.normalize_dialogue_narration(script).splitlines(),
            script.splitlines(),
        )

    def test_normalize_scene_script_converts_character_ids_to_names(self):
        script = "\n".join(
            [
                '<content id="lin_xiaochen">\u6211\u770b\u5230\u4e86\u94a5\u5319\u3002</content>',
                '<image id="lin_xiaochen">worried</image>',
            ]
        )
        core_gdd = {
            "characters": [{"id": "lin_xiaochen", "name": "\u6797\u6653\u6668"}],
        }

        normalized = WriterAgent.normalize_scene_script(script, core_gdd)

        self.assertEqual(
            normalized.splitlines(),
            [
                '<content id="\u6797\u6653\u6668">\u6211\u770b\u5230\u4e86\u94a5\u5319\u3002</content>',
                '<image id="\u6797\u6653\u6668">worried</image>',
            ],
        )

    def test_normalize_scene_script_wraps_plain_narration(self):
        script = "\n".join([
            "<scene>档案室</scene>",
            "林尘走到门边检查插销。",
            '<content id="林尘">这是一间密室。</content>',
        ])

        normalized = WriterAgent.normalize_scene_script(script, {"characters": []})

        self.assertEqual(
            normalized.splitlines(),
            [
                "<scene>档案室</scene>",
                '<content id="旁白">林尘走到门边检查插销。</content>',
                '<content id="林尘">这是一间密室。</content>',
            ],
        )

    def test_actor_fidelity_rejects_writer_invented_dialogue(self):
        turns = [{
            "character": "林晓晨",
            "action": "抬头看向门缝",
            "dialogue": "门外有人。",
        }]
        valid_script = "\n".join([
            '<scene>教室</scene>',
            '<content id="旁白">林晓晨抬头看向门缝</content>',
            '<content id="林晓晨">门外有人。</content>',
        ])
        invented_script = valid_script + '\n<content id="林晓晨">我知道凶手是谁。</content>'

        self.assertEqual(WriterAgent.validate_actor_fidelity(valid_script, turns), (True, ""))
        valid, error = WriterAgent.validate_actor_fidelity(invented_script, turns)
        self.assertFalse(valid)
        self.assertIn("Actor dialogue", error)

    def test_deterministic_actor_formatter_produces_valid_script(self):
        turns = [{
            "character": "林尘",
            "action": "走到门边检查插销。",
            "dialogue": "这扇门从内侧锁住了。",
            "image": "serious",
        }]
        core_gdd = {"scenes": [{"name": "档案室"}]}

        script = WriterAgent._format_actor_performances(turns, core_gdd)

        self.assertIn("<scene>档案室</scene>", script)
        self.assertIn('<content id="旁白">林尘走到门边检查插销。</content>', script)
        self.assertIn('<image id="林尘">serious</image>', script)
        self.assertEqual(WriterAgent.validate_actor_fidelity(script, turns), (True, ""))

    def test_actor_formatter_switches_scene_from_actor_actions(self):
        turns = [
            {
                "character": "林尘",
                "action": "在体育馆篮球部活动室翻查储物柜。",
                "dialogue": "这里有一捆鱼线。",
                "image": "serious",
            },
            {
                "character": "林尘",
                "action": "回到美术储藏室，把鱼线穿过门缝。",
                "dialogue": "锁舌可以从外面拉上。",
                "image": "serious",
            },
        ]
        core_gdd = {
            "scenes": [
                {"name": "教学楼三楼走廊", "description": "昏暗走廊"},
                {"name": "美术储藏室", "description": "门锁和石雕"},
                {"name": "体育馆篮球部活动室", "description": "储物柜和护具"},
            ]
        }

        script = WriterAgent._format_actor_performances(turns, core_gdd)

        self.assertTrue(script.startswith("<scene>体育馆篮球部活动室</scene>"))
        self.assertIn("<scene>美术储藏室</scene>", script)
        self.assertEqual(WriterAgent.validate_actor_fidelity(script, turns), (True, ""))

    def test_actor_fidelity_rejects_action_without_performer(self):
        turns = [{
            "character": "林晨",
            "action": "先看向叶晓，再转向赵深。",
            "dialogue": "你们谁在说谎？",
        }]
        script = "\n".join([
            "<scene>走廊</scene>",
            '<content id="旁白">先看向叶晓，再转向赵深。</content>',
            '<content id="林晨">你们谁在说谎？</content>',
        ])

        valid, error = WriterAgent.validate_actor_fidelity(script, turns)

        self.assertFalse(valid)
        self.assertIn("执行者", error)

    def test_actor_formatter_does_not_duplicate_explicit_subject(self):
        turns = [{
            "character": "林晨",
            "action": "林晨走到门边检查插销。",
            "dialogue": "门锁有问题。",
        }]

        script = WriterAgent._format_actor_performances(
            turns,
            {"scenes": [{"name": "档案室"}]},
        )

        self.assertIn('<content id="旁白">林晨走到门边检查插销。</content>', script)
        self.assertNotIn("林晨林晨", script)

    def test_scene_formatter_ignores_locations_only_mentioned_in_dialogue(self):
        turns = [{
            "character": "赵深",
            "action": "身体向后靠了靠。",
            "dialogue": "我之后一直待在体育馆篮球部活动室。",
        }]
        core_gdd = {
            "scenes": [
                {"name": "教学楼三楼走廊"},
                {"name": "体育馆篮球部活动室"},
            ]
        }

        script = WriterAgent._format_actor_performances(turns, core_gdd)

        self.assertTrue(script.startswith("<scene>教学楼三楼走廊</scene>"))
        self.assertNotIn("<scene>体育馆篮球部活动室</scene>", script)

    def test_scene_formatter_inherits_previous_final_scene_until_actor_moves(self):
        turns = [
            {
                "character": "林晨",
                "action": "拿起桌上的纱布进行检验。",
                "dialogue": "污渍还没有干。",
            },
            {
                "character": "林晨",
                "action": "返回美术储藏室，把鱼线穿过门缝。",
                "dialogue": "这样就能从外面反锁。",
            },
        ]
        core_gdd = {
            "scenes": [
                {"name": "教学楼三楼走廊"},
                {"name": "体育馆篮球部活动室"},
                {"name": "美术储藏室"},
            ]
        }

        script = WriterAgent._format_actor_performances(
            turns,
            core_gdd,
            "<scene>体育馆篮球部活动室</scene>\n<content id=\"林晨\">继续。</content>",
        )

        self.assertTrue(script.startswith("<scene>体育馆篮球部活动室</scene>"))
        self.assertIn("<scene>美术储藏室</scene>", script)

    def test_actor_fidelity_rejects_missing_scene(self):
        turns = [{"character": "林尘", "action": "", "dialogue": "测试。"}]
        valid, error = WriterAgent.validate_actor_fidelity(
            '<content id="林尘">测试。</content>',
            turns,
        )
        self.assertFalse(valid)
        self.assertIn("scene", error)


if __name__ == "__main__":
    unittest.main()
