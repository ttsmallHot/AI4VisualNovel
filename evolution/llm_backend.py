"""LLM implementation of the rolling-horizon evolution backend."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agents.llm_client import LLMClient
from agents.utils import JSONParser

from .contracts import (
    CORE_GDD_SCHEMA,
    EXPANSION_SCHEMA,
    NODE_CONTRACT_SCHEMA,
    STATE_TRANSITION_SCHEMA,
)
from .state import NodeCursor


class LLMEvolutionBackend:
    """Generate only the current scene and the next rolling-horizon goals."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.llm = LLMClient(api_key=api_key, base_url=base_url)

    def create_core_gdd(
        self,
        requirements: str,
        character_count: int,
        locked_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        prompt = f"""Create the immutable Core GDD for an evolutionary visual novel.

User requirements:
{requirements or 'No additional requirements.'}

Target character count: {character_count}
Locked user characters:
{json.dumps(locked_characters or [], ensure_ascii=False, indent=2)}

The Core GDD is a creative constitution, not a complete plot. Define the world,
characters, themes, rules, initial conflict, possible ending conditions, initial
world state, and unresolved narrative agenda. Do not create story_outline,
chapters, a story graph, or a sequence of future events. Later agents must be
able to discover the plot from character actions and evolving state.

Return JSON only. schema_version must be "evo-gdd/1.0".
"""
        return self._call_json(prompt, CORE_GDD_SCHEMA, "core_gdd", temperature=0.7)

    def create_initial_contract(self, core_gdd: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""Create only the first playable scene contract from this Core GDD.

Core GDD:
{json.dumps(core_gdd, ensure_ascii=False, indent=2)}

The scene should stage the initial conflict. It must not outline later scenes.
Use exact character names and one existing scene name. required_outcomes should
describe observable changes for this scene; forbidden_outcomes should prevent
premature reveals.

Return JSON only.
"""
        return self._call_json(prompt, NODE_CONTRACT_SCHEMA, "initial_contract", temperature=0.5)

    def write_scene(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        parent_script: str,
    ) -> str:
        character_by_name = {
            character.get("name"): character
            for character in core_gdd.get("characters", [])
            if isinstance(character, dict)
        }
        active_characters = [
            character_by_name[name]
            for name in cursor.contract.get("active_cast", [])
            if name in character_by_name
        ]
        core_view = {
            "title": core_gdd.get("title"),
            "background": core_gdd.get("background"),
            "themes": core_gdd.get("themes", []),
            "world_rules": core_gdd.get("world_rules", []),
            "immutable_facts": core_gdd.get("immutable_facts", []),
            "characters": active_characters,
        }
        prompt = f"""Write the current Visual Novel scene. Generate this scene only.

Core constraints:
{json.dumps(core_view, ensure_ascii=False, indent=2)}

Current node contract:
{json.dumps(cursor.contract, ensure_ascii=False, indent=2)}

Path-specific world state before the scene:
{json.dumps(cursor.world_state, ensure_ascii=False, indent=2)}

Open narrative agenda:
{json.dumps(cursor.agenda, ensure_ascii=False, indent=2)}

Immediate parent scene, if any:
{parent_script[-4000:] if parent_script else 'This is the opening scene.'}

Use only these line formats:
<scene>existing scene name</scene>
<content id="旁白">narration</content>
<image id="exact character name">english_expression</image>
<content id="character id">spoken dialogue only</content>

A character content tag may contain only words actually spoken aloud. Put every
action, gesture, tone description, and speaker attribution in a separate 旁白
content tag. Do not wrap spoken dialogue in quotation marks.

Wrong:
<content id="kaelen">“Wait.” Kaelen lowered his voice. “Listen.”</content>

Correct:
<content id="kaelen">Wait.</content>
<content id="旁白">Kaelen lowered his voice.</content>
<content id="kaelen">Listen.</content>

Use the same natural language as the current story context. Do not add choices,
jumps, future scene plans, chapter headings, explanations, or an ending label.
End after the current scene has made meaningful progress toward its required
outcomes.
"""
        scene_script = self.llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are an experienced visual novel scene writer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
        )
        return self.normalize_scene_script(scene_script, core_gdd)

    @staticmethod
    def normalize_scene_script(
        scene_script: str,
        core_gdd: Dict[str, Any],
    ) -> str:
        """Split quoted dialogue from embedded narration in generated tags."""
        character_names = {
            str(character.get("id")): str(character.get("name"))
            for character in core_gdd.get("characters", [])
            if character.get("id") and character.get("name")
        }
        content_pattern = re.compile(r'^<content\s+id="([^"]+)">(.+)</content>$')
        image_pattern = re.compile(r'^<image\s+id="([^"]+)">([^<]+)</image>$')
        quoted_dialogue_pattern = re.compile(r'“([^”]+)”')
        lines = []

        for raw_line in scene_script.strip().splitlines():
            line = raw_line.strip()
            content_match = content_pattern.fullmatch(line)
            if content_match and content_match.group(1) != "旁白":
                speaker_id, text = content_match.groups()
                quoted_parts = list(quoted_dialogue_pattern.finditer(text))
                if quoted_parts:
                    offset = 0
                    for quoted_part in quoted_parts:
                        narration = text[offset:quoted_part.start()].strip()
                        if narration:
                            lines.append(f'<content id="旁白">{narration}</content>')
                        dialogue = quoted_part.group(1).strip()
                        if dialogue:
                            lines.append(f'<content id="{speaker_id}">{dialogue}</content>')
                        offset = quoted_part.end()
                    narration = text[offset:].strip()
                    if narration:
                        lines.append(f'<content id="旁白">{narration}</content>')
                    continue

            image_match = image_pattern.fullmatch(line)
            if image_match:
                character_reference, expression = image_match.groups()
                character_name = character_names.get(character_reference, character_reference)
                lines.append(f'<image id="{character_name}">{expression.strip()}</image>')
                continue

            if line:
                lines.append(line)
        return "\n".join(lines) + "\n"

    def reduce_scene(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        scene_script: str,
    ) -> Dict[str, Any]:
        prompt = f"""Reduce this generated scene into a committed narrative transition.

Immutable facts:
{json.dumps(core_gdd.get('immutable_facts', []), ensure_ascii=False)}

Contract:
{json.dumps(cursor.contract, ensure_ascii=False, indent=2)}

State before scene:
{json.dumps(cursor.world_state, ensure_ascii=False, indent=2)}

Agenda before scene:
{json.dumps(cursor.agenda, ensure_ascii=False, indent=2)}

Scene:
{scene_script}

Return only facts supported by explicit scene evidence. Each update uses a safe
dot path such as facts.key_is_fake, locations.hero, knowledge.Hero.secret_name,
or relationships.Hero_Lin.trust. Do not infer unspoken thoughts as shared
knowledge. Return the full updated agenda, removing resolved items and adding
new unresolved questions only when the scene establishes them.

Return JSON only.
"""
        return self._call_json(prompt, STATE_TRANSITION_SCHEMA, "state_transition", temperature=0.2)

    def expand_story(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        scene_script: str,
        transition: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        max_children: int,
    ) -> Dict[str, Any]:
        prompt = f"""Decide whether the story should end or expand the frontier by one step.

Core GDD ending conditions:
{json.dumps(core_gdd.get('ending_conditions', []), ensure_ascii=False, indent=2)}

Current path: {cursor.path}
Current scene summary: {transition.get('summary', '')}
Committed world state:
{json.dumps(world_state, ensure_ascii=False, indent=2)}

Current narrative agenda:
{json.dumps(agenda, ensure_ascii=False, indent=2)}

You may create at most {max_children} next nodes. Plan only the immediate next
scene for each choice. Do not outline later chapters. Choices must produce
meaningfully different intentions or consequences, not paraphrases. Use exact
character names and existing scene names. Mark story_complete only when an
ending condition is actually satisfied and the important agenda is resolved.

Return JSON only.
"""
        return self._call_json(prompt, EXPANSION_SCHEMA, "story_expansion", temperature=0.7)

    def _call_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        object_name: str,
        temperature: float,
    ) -> Dict[str, Any]:
        schema_prompt = (
            f"{prompt.rstrip()}\n\n"
            "The response MUST validate against this complete JSON Schema:\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        content = self.llm.chat_completion(
            messages=[
                {"role": "system", "content": "Return one valid JSON object and no commentary."},
                {"role": "user", "content": schema_prompt},
            ],
            temperature=temperature,
            json_mode=True,
        )
        parsed = JSONParser.parse_ai_response(content)
        valid, error = JSONParser.validate_json_schema(parsed, schema)
        if not valid:
            repair = self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": "Repair JSON to satisfy the requested schema."},
                    {"role": "user", "content": schema_prompt},
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"{object_name} failed schema validation: {error}. Return corrected JSON only.",
                    },
                ],
                temperature=0.1,
                json_mode=True,
            )
            parsed = JSONParser.parse_ai_response(repair)
            valid, error = JSONParser.validate_json_schema(parsed, schema)
        if not valid:
            raise ValueError(f"{object_name} schema validation failed: {error}")
        if not isinstance(parsed, dict):
            raise ValueError(f"{object_name} must be a JSON object")
        return parsed
