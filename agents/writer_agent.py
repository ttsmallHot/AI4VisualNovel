"""
Writer Agent
~~~~~~~~~~~~
编剧 Agent - 负责生成每周详细剧情
使用 GPT-4 根据游戏设计和角色状态创作对话和事件
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent

from .config import WriterConfig, PathConfig
from .schemas import CG_SCRIPT_PACKAGE_SCHEMA
from .utils import FileHelper

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """编剧 Agent - 剧情生成器"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化编剧 Agent
        
        Args:
            api_key: API Key
            base_url: API Base URL
        """
        super().__init__(
            name="Writer",
            role="编剧",
            api_key=api_key,
            base_url=base_url
        )
        self.config = WriterConfig
        
        logger.info("✅ 编剧 Agent 初始化成功")

    def synthesize_script(
        self,
        performances: List[Dict[str, Any]],
        choices: List[Dict[str, Any]] = [],
        story_context: str = "",
        game_outline: str = "",
        available_scenes: List[str] = [],
        available_characters: List[Dict[str, Any]] = [],
        node_id: str = "",
        node_summary: str = "",
    ) -> str:
        """将演员表演整合成剧本"""
        return self.synthesize_script_package(
            performances=performances,
            choices=choices,
            story_context=story_context,
            game_outline=game_outline,
            available_scenes=available_scenes,
            available_characters=available_characters,
            node_id=node_id,
            node_summary=node_summary,
        )["script"]

    def synthesize_script_package(
        self,
        performances: List[Dict[str, Any]],
        choices: List[Dict[str, Any]] = [],
        story_context: str = "",
        game_outline: str = "",
        available_scenes: List[str] = [],
        available_characters: List[Dict[str, Any]] = [],
        node_id: str = "",
        node_summary: str = "",
    ) -> Dict[str, Any]:
        """整合演员表演，并由 Writer 决定是否插入关键剧情 CG。"""
        logger.info("🧩 正在整合剧本 (基于结构化数据)...")
        
        # 将结构化数据转换为 JSON 字符串供 LLM 阅读
        performances_json = json.dumps(performances, ensure_ascii=False, indent=2)
        choices_json = json.dumps(choices, ensure_ascii=False, indent=2)
        scenes_str = ", ".join(available_scenes) if available_scenes else "未指定"
        # 构建角色的详细信息
        characters_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in available_characters
        ]) if available_characters else "未指定"
        
        prompt = self.config.SCRIPT_SYNTHESIS_PROMPT.format(
            performances=performances_json,
            choices=choices_json,
            story_context=story_context,
            game_outline=game_outline,
            available_scenes=scenes_str,
            available_characters=characters_info,
            node_id=node_id,
            node_summary=node_summary,
        )

        try:
            package = self.call_json_with_schema(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                schema=CG_SCRIPT_PACKAGE_SCHEMA,
                object_name="writer_script_with_cgs",
                temperature=0.7,
            )
            return self.normalize_cg_package(
                package=package,
                node_id=node_id,
                available_characters=available_characters,
            )
        except Exception as e:
            logger.error(f"❌ 整合剧本失败: {e}")
            raise

    @classmethod
    def normalize_cg_package(
        cls,
        package: Dict[str, Any],
        node_id: str,
        available_characters: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Normalize CG metadata and remove script tags without a valid manifest item."""
        script = cls.normalize_dialogue_narration(str(package.get("script", "")))
        id_by_alias: Dict[str, str] = {}
        for character in available_characters:
            if not isinstance(character, dict):
                continue
            character_id = str(character.get("id", "")).strip()
            character_name = str(character.get("name", "")).strip()
            if character_id:
                id_by_alias[character_id] = character_id
                if character_name:
                    id_by_alias[character_name] = character_id

        normalized_cgs: List[Dict[str, Any]] = []
        seen_ids = set()
        for raw in package.get("cgs", []):
            if not isinstance(raw, dict):
                continue
            cg_id = str(raw.get("id", "")).strip()
            description = str(raw.get("description", "")).strip()
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]+", cg_id)
                or cg_id in seen_ids
                or str(raw.get("node_id", "")).strip() != node_id
                or len(description) < 80
            ):
                continue
            character_ids = []
            for value in raw.get("characters", []):
                character_id = id_by_alias.get(str(value).strip())
                if character_id and character_id not in character_ids:
                    character_ids.append(character_id)
            normalized_cgs.append({
                "id": cg_id,
                "node_id": node_id,
                "characters": character_ids,
                "description": description,
            })
            seen_ids.add(cg_id)

        valid_ids = {cg["id"] for cg in normalized_cgs}
        tag_pattern = re.compile(r'^<cg\s+id="([^"]+)"\s*/>$')
        kept_lines = []
        used_ids = set()
        for raw_line in script.splitlines():
            match = tag_pattern.fullmatch(raw_line.strip())
            if match:
                cg_id = match.group(1)
                if cg_id not in valid_ids or cg_id in used_ids:
                    continue
                used_ids.add(cg_id)
                kept_lines.append(f'<cg id="{cg_id}"/>')
            else:
                kept_lines.append(raw_line)

        normalized_cgs = [cg for cg in normalized_cgs if cg["id"] in used_ids]
        return {"script": cls.normalize_cg_visibility("\n".join(kept_lines).strip()), "cgs": normalized_cgs}

    @staticmethod
    def normalize_cg_visibility(script: str) -> str:
        """Place CGs after adjacent portrait cues so the next dialogue displays them."""
        return re.sub(
            r'(?m)^(<cg\s+id="[^"]+"\s*/>)[ \t]*\n'
            r'((?:[ \t]*<image\s+id="[^"]+">[^\n]*?</image>[ \t]*\n)+)',
            lambda match: match.group(2) + match.group(1) + "\n",
            script,
        )

    def synthesize_actor_performances(
        self,
        turns: List[Dict[str, Any]],
        node_goal: Dict[str, Any],
        story_context: str,
        core_gdd: Dict[str, Any],
    ) -> str:
        """Compile Actor-authored performances without an LLM rewrite."""
        fallback = self._format_actor_performances(turns, core_gdd, story_context)
        valid, fallback_error = self.validate_actor_fidelity(fallback, turns)
        if not valid:
            raise ValueError(f"Writer 无法保真整合 Actor 表演: {fallback_error}")
        return fallback

    @staticmethod
    def _format_actor_performances(
        turns: List[Dict[str, Any]],
        core_gdd: Dict[str, Any],
        story_context: str = "",
    ) -> str:
        """Deterministic last-resort formatter that never invents Actor output."""
        scenes = core_gdd.get("scenes", [])
        scene_names = [
            str(scene.get("name", "")).strip()
            for scene in scenes
            if isinstance(scene, dict) and str(scene.get("name", "")).strip()
        ]
        scene_name = WriterAgent._infer_scene_name(turns, scenes, story_context)
        lines = [f"<scene>{scene_name}</scene>"]
        for turn in turns:
            character = str(turn.get("character", "")).strip()
            action = str(turn.get("action", "")).strip()
            dialogue = str(turn.get("dialogue", "")).strip()
            image = str(turn.get("image", "")).strip()
            explicit_scene = WriterAgent._explicit_scene_name(
                action, scene_names, require_location_action=True
            )
            if explicit_scene and explicit_scene != scene_name:
                scene_name = explicit_scene
                lines.append(f"<scene>{scene_name}</scene>")
            if action:
                attributed_action = WriterAgent._format_attributed_action(character, action)
                lines.append(f'<content id="旁白">{attributed_action}</content>')
            if image and character:
                lines.append(f'<image id="{character}">{image}</image>')
            if dialogue and character:
                lines.append(f'<content id="{character}">{dialogue}</content>')
        return "\n".join(lines)

    @staticmethod
    def _format_attributed_action(character: str, action: str) -> str:
        """Keep the Actor action verbatim while making its performer explicit."""
        character = str(character).strip()
        action = str(action).strip()
        if not action:
            return ""
        if not character:
            raise ValueError("Actor action 缺少 character，无法确定动作主语")
        if action.startswith(character):
            return action
        # An Actor can observe an external party's visible action.  Prefixing
        # the current Actor would corrupt “两名警察推门进入” into the ungrammatical
        # “林晨两名警察推门进入”.
        if re.match(r"^(?:一名|两名|几名|数名)?(?:警察|警员|警方)", action):
            return action
        if action.startswith("我"):
            return f"{character}{action[1:]}"
        action = re.sub(
            r"我(?=[走看听拿拉推站蹲转抬低伸握递说问答回关开])",
            character,
            action,
        )
        return f"{character}{action}"

    @staticmethod
    def _scene_aliases(scene_name: str) -> List[str]:
        """Return conservative place aliases used only for deterministic tagging."""
        aliases = [scene_name]
        suffixes = (
            "储藏室", "活动室", "办公室", "宿舍", "走廊", "教室",
            "体育馆", "美术室", "医务室", "食堂", "操场", "图书馆",
            "实验室", "礼堂", "天台", "车站", "客厅", "卧室", "厨房",
        )
        aliases.extend(suffix for suffix in suffixes if suffix in scene_name)
        if "美术" in scene_name and scene_name.endswith("室"):
            aliases.append("美术室")
        return sorted(set(aliases), key=len, reverse=True)

    @staticmethod
    def _explicit_scene_name(
        text: str,
        scene_names: List[str],
        require_location_action: bool = False,
    ) -> Optional[str]:
        matches = []
        for scene_name in scene_names:
            aliases = WriterAgent._scene_aliases(scene_name)
            matched_aliases = []
            for alias in aliases:
                if alias not in text:
                    continue
                if require_location_action and alias != scene_name:
                    movement = re.search(
                        rf"(?:进入|走进|来到|回到|返回|赶到|抵达|推开|穿过|走向|在)"
                        rf".{{0,12}}{re.escape(alias)}",
                        text,
                    )
                    located = re.search(
                        rf"{re.escape(alias)}(?:内|里|中|门口|门边|前|外)",
                        text,
                    )
                    if not movement and not located:
                        continue
                matched_aliases.append(alias)
            score = max((len(alias) for alias in matched_aliases), default=0)
            if score:
                matches.append((score, len(scene_name), scene_name))
        return max(matches)[2] if matches else None

    @staticmethod
    def _infer_scene_name(
        turns: List[Dict[str, Any]],
        scenes: List[Dict[str, Any]],
        story_context: str = "",
    ) -> str:
        """Select an initial scene from Actor evidence without generating prose."""
        scene_names = [
            str(scene.get("name", "")).strip()
            for scene in scenes
            if isinstance(scene, dict) and str(scene.get("name", "")).strip()
        ]
        if turns:
            text = str(turns[0].get("action", ""))
            explicit = WriterAgent._explicit_scene_name(
                text, scene_names, require_location_action=True
            )
            if explicit:
                return explicit
        context_scenes = re.findall(r"<scene>([^<]+)</scene>", story_context or "")
        for context_scene in reversed(context_scenes):
            if context_scene in scene_names:
                return context_scene
        return scene_names[0] if scene_names else "未知场景"

    @staticmethod
    def validate_actor_fidelity(
        script: str,
        turns: List[Dict[str, Any]],
    ) -> tuple[bool, str]:
        """Require final character dialogue to exactly equal Actor output in order."""
        if not re.search(r"<scene>[^<]+</scene>", script):
            return False, "缺少合法 scene 标签"
        if not re.search(r'<content\s+id="[^"]+">.*?</content>', script):
            return False, "缺少合法 content 标签"
        source_dialogue = [
            (str(turn.get("character", "")), str(turn.get("dialogue", "")).strip())
            for turn in turns if str(turn.get("dialogue", "")).strip()
        ]
        content_pattern = re.compile(r'^<content\s+id="([^"]+)">(.*)</content>$')
        final_dialogue = []
        for line in script.splitlines():
            match = content_pattern.fullmatch(line.strip())
            if match and match.group(1) != "旁白":
                final_dialogue.append((match.group(1), match.group(2).strip()))
        if final_dialogue != source_dialogue:
            return False, "最终角色台词与 Actor dialogue 的数量、顺序或文字不一致"
        narration_pattern = re.compile(r'^<content\s+id="旁白">(.*)</content>$')
        final_actions = []
        for line in script.splitlines():
            match = narration_pattern.fullmatch(line.strip())
            if match:
                final_actions.append(match.group(1).strip())
        source_actions = [
            WriterAgent._format_attributed_action(
                str(turn.get("character", "")),
                str(turn.get("action", "")),
            )
            for turn in turns if str(turn.get("action", "")).strip()
        ]
        if final_actions != source_actions:
            return False, "最终动作旁白与 Actor action 的执行者、数量、顺序或文字不一致"
        return True, ""

    def write_scene_from_contract(
        self,
        core_gdd: Dict[str, Any],
        contract: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summary: str = "",
    ) -> str:
        """根据滚动场景契约直接生成一场原生格式剧本。"""
        character_by_name = {
            character.get("name"): character
            for character in core_gdd.get("characters", [])
            if isinstance(character, dict) and character.get("name")
        }
        active_characters = [
            character_by_name[name]
            for name in contract.get("active_cast", [])
            if name in character_by_name
        ]
        prompt = f"""请根据当前场景契约创作一场 Visual Novel 剧本，只写这一场。

【Core GDD 世界知识】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【当前场景契约】
{json.dumps(contract, ensure_ascii=False, indent=2)}

【场景开始前世界状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【未解决议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【上一场摘要】
{previous_summary or '这是第一场。'}

【本场角色】
{json.dumps(active_characters, ensure_ascii=False, indent=2)}

严格使用以下格式，每个标签单独一行：
<scene>Core GDD 中已有的场景 name</scene>
<content id="旁白">环境、动作、神态或心理描写</content>
<image id="角色 name">english_expression</image>
<content id="角色 name">角色实际说出口的纯台词</content>

角色 content 内只能包含说出口的话，不要包中文引号，不得混入“某人说道”、动作、
神态或语气描写；这些内容必须写成独立旁白。严格完成 required_outcomes，避开
forbidden_outcomes。不要生成选择、跳转、下一场计划、章节名或结局标签。
使用与用户要求一致的语言。只输出剧本。
"""
        script = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.75,
        )
        return self.normalize_scene_script(script, core_gdd)

    def write_scene_from_goal(
        self,
        core_gdd: Dict[str, Any],
        node_goal: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summaries: List[str],
    ) -> str:
        """Choose the scene and cast while realizing one complete NodeGoal."""
        prompt = f"""你是 Visual Novel Writer。把当前 NodeGoal 写成一个完整节点。

【Core GDD】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【当前 NodeGoal】
{json.dumps(node_goal, ensure_ascii=False, indent=2)}

【已提交的世界状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【已提交的未解议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【前文摘要】
{json.dumps(previous_summaries, ensure_ascii=False, indent=2)}

由你从 Core GDD.scenes 中选择地点，并从 characters 中选择必要的在场角色。
本节点内必须真正完成全部 completion_conditions，但不得超前触发 forbidden_outcomes。
不得把角色秘密自动变成公开知识。

严格使用以下格式，每个标签单独一行：
<scene>Core GDD 中已有的场景 name</scene>
<content id="旁白">环境、动作、神态或心理描写</content>
<image id="角色 name">english_expression</image>
<content id="角色 name">角色实际说出口的纯台词</content>

角色 content 内只能有说出口的话，不要包中文引号，不得混入语气、动作、
神态、心理或“某人说”。这些必须写成独立旁白。不要生成选择、跳转、下一节点计划、
章节名或结局标签。使用与用户要求一致的语言。只输出剧本。
"""
        script = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.72,
        )
        return self.normalize_scene_script(script, core_gdd)

    def revise_scene_from_feedback(
        self,
        core_gdd: Dict[str, Any],
        node_goal: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        previous_summaries: List[str],
        draft: str,
        producer_feedback: List[str],
    ) -> str:
        """Patch a rejected draft without changing its NodeGoal."""
        prompt = f"""你是 Visual Novel Writer。Producer 驳回了当前节点，请修改剧本。

【Core GDD】
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

【不可更改的 NodeGoal】
{json.dumps(node_goal, ensure_ascii=False, indent=2)}

【已提交状态】
{json.dumps(world_state, ensure_ascii=False, indent=2)}

【未解议题】
{json.dumps(agenda, ensure_ascii=False, indent=2)}

【前文摘要】
{json.dumps(previous_summaries, ensure_ascii=False, indent=2)}

【原草稿】
{draft}

【Producer 修改要求】
{json.dumps(producer_feedback, ensure_ascii=False, indent=2)}

修复所有指出的问题，但不得更换 NodeGoal，不得规划下一节点。保持原生标签格式。
角色 <content> 内只保留说出口的纯台词，其它描写改成旁白。只输出完整修订稿。
"""
        script = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.config.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.55,
        )
        return self.normalize_scene_script(script, core_gdd)

    @classmethod
    def normalize_scene_script(
        cls,
        script: str,
        core_gdd: Dict[str, Any],
    ) -> str:
        """Normalize dialogue prose and convert character IDs to display names."""
        normalized = cls.normalize_dialogue_narration(script)
        normalized = cls.wrap_plain_narration(normalized)
        id_to_name = {
            str(character.get("id", "")).strip(): str(character.get("name", "")).strip()
            for character in core_gdd.get("characters", [])
            if isinstance(character, dict)
            and str(character.get("id", "")).strip()
            and str(character.get("name", "")).strip()
        }
        tag_pattern = re.compile(r'(<(?:content|image)\s+id=")([^"]+)(">)')

        def replace_tag(match: re.Match) -> str:
            speaker = match.group(2)
            return f"{match.group(1)}{id_to_name.get(speaker, speaker)}{match.group(3)}"

        return tag_pattern.sub(replace_tag, normalized)

    @staticmethod
    def wrap_plain_narration(script: str) -> str:
        """Convert Writer prose outside native tags into playable narration tags."""
        normalized_lines = []
        for raw_line in script.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("```"):
                continue
            if line.startswith("<") or line.startswith("=== Node:"):
                normalized_lines.append(line)
            else:
                normalized_lines.append(f'<content id="旁白">{line}</content>')
        return "\n".join(normalized_lines)

    @staticmethod
    def normalize_dialogue_narration(script: str) -> str:
        """Split quoted dialogue and embedded prose inside character content tags."""
        content_pattern = re.compile(r'^<content\s+id="([^"]+)">(.+)</content>$')
        quoted_dialogue_pattern = re.compile(r'“([^”]+)”')
        normalized_lines = []

        for raw_line in script.strip().splitlines():
            line = raw_line.strip()
            content_match = content_pattern.fullmatch(line)
            if not content_match or content_match.group(1) == "旁白":
                if line:
                    normalized_lines.append(line)
                continue

            speaker, text = content_match.groups()
            quoted_parts = list(quoted_dialogue_pattern.finditer(text))
            if not quoted_parts:
                normalized_lines.append(line)
                continue

            offset = 0
            for quoted_part in quoted_parts:
                narration = text[offset:quoted_part.start()].strip()
                if narration:
                    normalized_lines.append(f'<content id="旁白">{narration}</content>')
                dialogue = quoted_part.group(1).strip()
                if dialogue:
                    normalized_lines.append(f'<content id="{speaker}">{dialogue}</content>')
                offset = quoted_part.end()
            narration = text[offset:].strip()
            if narration:
                normalized_lines.append(f'<content id="旁白">{narration}</content>')

        return "\n".join(normalized_lines) + "\n"

    def decide_next_speaker(
        self,
        node_goal: str,
        characters: List[Dict[str, Any]],
        story_context: str,
        game_outline: str = ""
    ) -> tuple[str, str]:
        """
        决定下一位发言的角色及剧情指导
        
        Returns:
            (角色名, 剧情指导) 或 ("STOP", "")
        """
        # 构建角色的详细信息
        characters_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in characters
        ])
        
        prompt = self.config.NEXT_SPEAKER_PROMPT.format(
            node_goal=node_goal,
            characters=characters_info,            game_outline=game_outline,            story_context=story_context
        )
        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个辅助剧情生成的导演助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3 # 低温度以获得更确定的结果
            )
            response = response.strip()
            
            # 解析响应
            import re
            
            # 提取 <character> 标签
            char_match = re.search(r'<character>(.+?)</character>', response, re.DOTALL)
            if not char_match:
                logger.warning("⚠️ 导演返回格式错误，重试一次")
                response = self.llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": "你是一个辅助剧情生成的导演助手。"},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response},
                        {
                            "role": "user",
                            "content": (
                                "格式错误。只输出 <character>角色名或STOP</character>；"
                                "非STOP时再输出 <advice>简短意图</advice>。"
                            ),
                        },
                    ],
                    temperature=0.1,
                ).strip()
                char_match = re.search(r'<character>(.+?)</character>', response, re.DOTALL)
                if not char_match:
                    raise ValueError("导演重试后仍未返回 <character> 标签")
            
            speaker = char_match.group(1).strip()
            
            # 检查是否是 STOP
            if speaker.upper() == "STOP":
                return "STOP", ""
            
            # 提取 <advice> 标签
            advice_match = re.search(r'<advice>(.+?)</advice>', response, re.DOTALL)
            guidance = advice_match.group(1).strip() if advice_match else ""
            
            logger.debug(f"🎬 解析结果: 角色={speaker}, 指导={guidance}")
            return speaker, guidance
            
        except Exception as e:
            logger.error(f"❌ 决定下一位发言者失败: {e}")
            raise
    
    def append_story(self, story_text: str) -> None:
        """
        将新剧情追加到story.txt
        
        Args:
            story_text: 要追加的剧情文本
        """
        if not FileHelper.safe_append_text(PathConfig.STORY_FILE, story_text):
            raise Exception("追加剧情失败")
    
    @staticmethod
    def load_story() -> str:
        """
        加载完整的story.txt
        
        Returns:
            剧情文本，文件不存在返回空字符串
        """
        try:
            with open(PathConfig.STORY_FILE, 'r', encoding='utf-8') as f:
                story = f.read()
            
            logger.info(f"📖 剧情文件已加载: {len(story)} 字符")
            return story
            
        except FileNotFoundError:
            logger.warning(f"⚠️  剧情文件不存在，将创建新文件")
            return ""
        except Exception as e:
            logger.error(f"❌ 加载剧情文件失败: {e}")
            return ""
    

    
    def parse_story_for_ui(self, story_text: str) -> List[Dict[str, Any]]:
        """
        解析剧情文本为UI可用的数据结构
        
        Args:
            story_text: 原始剧情文本
            
        Returns:
            剧情片段列表，每个片段包含对话、图像、选项等信息
        """
        logger.info("📝 解析剧情文本...")
        
        segments = []
        current_location = None
        current_time = None
        
        lines = story_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 解析场景标题 (## 地点 或 ## 地点 - 时间)
            scene_match = re.match(r'##\s*(.+)', line)
            
            if scene_match:
                content = scene_match.group(1).strip()
                if '-' in content:
                    parts = content.split('-', 1)
                    new_location = parts[0].strip()
                    new_time = parts[1].strip()
                else:
                    new_location = content
                    new_time = "Day" # 默认时间
                
                # 如果场景变化，添加场景切换标记
                if new_location != current_location:
                    segments.append({
                        "type": "scene",
                        "location": new_location,
                        "time": new_time
                    })
                
                current_time = new_time
                current_location = new_location
                continue
            
            # 解析图像标注 <image id="角色">表情</image>
            image_match = re.match(r'<image\s+id="([^"]+)">([^<]+)</image>', line)
            if image_match:
                character = image_match.group(1).strip()
                expression = image_match.group(2).strip()
                
                segments.append({
                    "type": "image",
                    "character": character,
                    "expression": expression,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析对话 (角色名: "对话内容")
            dialogue_match = re.match(r'([^:]+):\s*"?(.+?)"?$', line)
            if dialogue_match:
                speaker = dialogue_match.group(1).strip()
                text = dialogue_match.group(2).strip()
                segments.append({
                    "type": "dialogue",
                    "speaker": speaker if speaker != "NARRATOR" else None,
                    "text": text,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项 ([CHOICE])
            if line == '[CHOICE]':
                segments.append({
                    "type": "choice_start",
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项内容 (选项1: "文字" → [效果])
            choice_match = re.match(r'选项(\d+):\s*"(.+?)"\s*→\s*\[(.+?)\]', line)
            if choice_match:
                choice_num = int(choice_match.group(1))
                choice_text = choice_match.group(2).strip()
                effects_str = choice_match.group(3).strip()
                
                # 解析效果
                effects = self._parse_choice_effects(effects_str)
                
                segments.append({
                    "type": "choice_option",
                    "number": choice_num,
                    "text": choice_text,
                    "effects": effects
                })
                continue
        
        logger.info(f"✅ 解析完成: {len(segments)} 个片段")
        return segments
