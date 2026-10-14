"""Resumable rolling-horizon story generation engine."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .state import EvolutionSnapshot, NodeCursor


class EvolutionBackend(Protocol):
    """Generation operations required by :class:`EvolutionEngine`."""

    def create_core_gdd(
        self,
        requirements: str,
        character_count: int,
        locked_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]: ...

    def create_initial_contract(self, core_gdd: Dict[str, Any]) -> Dict[str, Any]: ...

    def write_scene(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        parent_script: str,
    ) -> str: ...

    def reduce_scene(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        scene_script: str,
    ) -> Dict[str, Any]: ...

    def expand_story(
        self,
        core_gdd: Dict[str, Any],
        cursor: NodeCursor,
        scene_script: str,
        transition: Dict[str, Any],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
        max_children: int,
    ) -> Dict[str, Any]: ...


class EvolutionEngine:
    """Grow a story graph after each generated scene and persist every commit."""

    STATE_FILENAME = "evolution_state.json"

    def __init__(
        self,
        output_dir: Path | str,
        backend: EvolutionBackend,
        max_nodes: int = 12,
        max_depth: int = 6,
        max_children: int = 2,
    ):
        self.output_dir = Path(output_dir)
        self.backend = backend
        self.max_nodes = max(1, int(max_nodes))
        self.max_depth = max(0, int(max_depth))
        self.max_children = max(1, min(int(max_children), 4))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.output_dir / self.STATE_FILENAME

    def run(
        self,
        requirements: str = "",
        character_count: int = 3,
        locked_characters: Optional[List[Dict[str, Any]]] = None,
        resume: bool = True,
    ) -> EvolutionSnapshot:
        snapshot = self._load_or_initialize(
            requirements=requirements,
            character_count=character_count,
            locked_characters=locked_characters,
            resume=resume,
        )

        while snapshot.frontier:
            node_id = snapshot.frontier[0]
            if node_id in snapshot.completed:
                snapshot.frontier.pop(0)
                self._persist(snapshot)
                continue

            cursor = snapshot.cursors[node_id]
            parent_script = snapshot.scripts.get(cursor.parent_id or "", "")
            scene_script = self.backend.write_scene(
                core_gdd=snapshot.core_gdd,
                cursor=cursor,
                parent_script=parent_script,
            ).strip()
            if not scene_script:
                raise ValueError(f"Scene generator returned an empty script for {node_id}")

            transition = self.backend.reduce_scene(
                core_gdd=snapshot.core_gdd,
                cursor=cursor,
                scene_script=scene_script,
            )
            next_world_state = self.apply_updates(
                cursor.world_state,
                transition.get("updates", []),
            )
            next_agenda = deepcopy(transition.get("agenda") or cursor.agenda)

            remaining_slots = self.max_nodes - len(snapshot.story_graph["nodes"])
            can_expand = cursor.depth < self.max_depth and remaining_slots > 0
            expansion = {
                "story_complete": True,
                "completion_reason": "generation limit reached",
                "next_nodes": [],
            }
            if can_expand:
                expansion = self.backend.expand_story(
                    core_gdd=snapshot.core_gdd,
                    cursor=cursor,
                    scene_script=scene_script,
                    transition=transition,
                    world_state=next_world_state,
                    agenda=next_agenda,
                    max_children=min(self.max_children, remaining_slots),
                )

            children = []
            if not expansion.get("story_complete", False):
                raw_children = expansion.get("next_nodes", [])
                if isinstance(raw_children, list):
                    children = raw_children[: min(self.max_children, remaining_slots)]

            child_records = self._append_children(
                snapshot=snapshot,
                cursor=cursor,
                children=children,
                world_state=next_world_state,
                agenda=next_agenda,
            )
            final_script = self._append_transitions(scene_script, child_records)

            snapshot.scripts[node_id] = final_script
            snapshot.node_results[node_id] = {
                "summary": transition.get("summary", cursor.contract.get("goal", "")),
                "goal_completed": bool(transition.get("goal_completed", False)),
                "world_state": next_world_state,
                "agenda": next_agenda,
                "story_complete": bool(expansion.get("story_complete", not children)),
                "completion_reason": str(expansion.get("completion_reason", "")),
            }
            snapshot.story_graph["nodes"][node_id]["generation_status"] = "completed"
            snapshot.story_graph["nodes"][node_id]["summary"] = snapshot.node_results[node_id]["summary"]
            snapshot.completed.append(node_id)
            snapshot.frontier.pop(0)
            self._persist(snapshot)

        # Reconcile derived files when resuming a completed checkpoint after an
        # interruption between atomic file replacements.
        self._persist(snapshot)
        return snapshot

    def _load_or_initialize(
        self,
        requirements: str,
        character_count: int,
        locked_characters: Optional[List[Dict[str, Any]]],
        resume: bool,
    ) -> EvolutionSnapshot:
        if self.state_path.exists():
            if not resume:
                raise FileExistsError(
                    f"Evolution state already exists: {self.state_path}. "
                    "Use a new project name or enable resume."
                )
            with self.state_path.open("r", encoding="utf-8") as handle:
                return EvolutionSnapshot.from_dict(json.load(handle))

        core_gdd = self.backend.create_core_gdd(
            requirements=requirements,
            character_count=character_count,
            locked_characters=locked_characters,
        )
        root_contract = self.backend.create_initial_contract(core_gdd)
        snapshot = EvolutionSnapshot.create(core_gdd, root_contract)
        self._persist(snapshot)
        return snapshot

    def _append_children(
        self,
        snapshot: EvolutionSnapshot,
        cursor: NodeCursor,
        children: List[Dict[str, Any]],
        world_state: Dict[str, Any],
        agenda: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        records: List[Dict[str, str]] = []
        for child in children:
            node_id = f"node{snapshot.next_node_index}"
            snapshot.next_node_index += 1
            contract = deepcopy(child.get("contract", {}))
            choice_text = str(child.get("choice_text", "继续")).strip() or "继续"

            snapshot.story_graph["nodes"][node_id] = {
                "id": node_id,
                "summary": contract.get("goal", "Continue the story"),
                "type": "normal",
                "generation_status": "pending",
            }
            snapshot.story_graph["edges"].append(
                {"from": cursor.node_id, "to": node_id, "choice_text": choice_text}
            )
            snapshot.cursors[node_id] = NodeCursor(
                node_id=node_id,
                parent_id=cursor.node_id,
                depth=cursor.depth + 1,
                path=cursor.path + [node_id],
                contract=contract,
                world_state=deepcopy(world_state),
                agenda=deepcopy(agenda),
            )
            snapshot.frontier.append(node_id)
            records.append({"node_id": node_id, "choice_text": choice_text})
        return records

    @staticmethod
    def _append_transitions(script: str, children: List[Dict[str, str]]) -> str:
        clean_script = script.rstrip()
        if not children:
            return clean_script + "\n"
        if len(children) == 1:
            return clean_script + f'\n\n<jump target="{children[0]["node_id"]}"/>\n'
        choices = "\n".join(
            f'<choice target="{child["node_id"]}">{child["choice_text"]}</choice>'
            for child in children
        )
        return clean_script + "\n\n" + choices + "\n"

    @staticmethod
    def apply_updates(
        base_state: Dict[str, Any],
        updates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply validated dot-path assignments without mutating the parent state."""
        result = deepcopy(base_state)
        for update in updates or []:
            path = str(update.get("path", "")).strip()
            if not path:
                continue
            segments = path.split(".")
            if any(not segment or segment.startswith("__") for segment in segments):
                raise ValueError(f"Unsafe state update path: {path}")
            target = result
            for segment in segments[:-1]:
                existing = target.get(segment)
                if not isinstance(existing, dict):
                    target[segment] = {}
                target = target[segment]
            target[segments[-1]] = deepcopy(update.get("value"))
        return result

    def _persist(self, snapshot: EvolutionSnapshot) -> None:
        self._atomic_write_json(self.state_path, snapshot.to_dict())
        self._atomic_write_json(self.output_dir / "story_graph.json", snapshot.story_graph)

        game_design = deepcopy(snapshot.core_gdd)
        game_design["generation_mode"] = "evolutionary"
        game_design["story_outline"] = {
            "mode": "rolling_horizon",
            "initial_conflict": snapshot.core_gdd.get("initial_conflict", ""),
        }
        game_design["story_graph"] = deepcopy(snapshot.story_graph)
        self._atomic_write_json(self.output_dir / "game_design.json", game_design)

        ordered_nodes = [node_id for node_id in snapshot.completed if node_id in snapshot.scripts]
        story_text = "\n\n".join(
            f"=== Node: {node_id} ===\n{snapshot.scripts[node_id].strip()}"
            for node_id in ordered_nodes
        )
        self._atomic_write_text(self.output_dir / "story.txt", story_text + ("\n" if story_text else ""))

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        EvolutionEngine._atomic_write_text(path, text + "\n")

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
