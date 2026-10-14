#!/usr/bin/env python3
"""Recoverably roll a rolling checkpoint back to a committed node prefix."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.config import PathConfig  # noqa: E402
from workflow import WorkflowController  # noqa: E402


def rollback(project: str, keep_nodes: int) -> Path:
    PathConfig.init(project)
    state_path = Path(PathConfig.DATA_DIR, "rolling_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    node_ids = list(state.get("scripts", {}))
    if keep_nodes < 0 or keep_nodes > len(node_ids):
        raise ValueError(f"keep_nodes 必须位于 0..{len(node_ids)}")
    kept = node_ids[:keep_nodes]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(PathConfig.DATA_DIR, "backups", f"before_rollback_{timestamp}")
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in (
        "rolling_state.json",
        "story.txt",
        "story_graph.json",
        "game_design.json",
        "rolling_retry.json",
        "rolling_pre_node.json",
    ):
        source = Path(PathConfig.DATA_DIR, name)
        if source.exists():
            shutil.copy2(source, backup_dir / name)

    trimmed = dict(state)
    for field in ("scripts", "goals", "reviews", "performances", "summaries"):
        trimmed[field] = {
            node_id: state.get(field, {})[node_id]
            for node_id in kept
            if node_id in state.get(field, {})
        }
    graph = dict(state.get("story_graph", {}))
    graph["nodes"] = {
        node_id: graph.get("nodes", {})[node_id]
        for node_id in kept
        if node_id in graph.get("nodes", {})
    }
    graph["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("from") in kept
    ]
    trimmed["story_graph"] = graph

    if "root" in kept:
        controller_for_contract = WorkflowController.__new__(WorkflowController)
        trimmed["goals"]["root"] = controller_for_contract._ensure_transition_contract(
            node_goal=trimmed["goals"]["root"],
            previous_script="",
            is_root=True,
        )
        trimmed["reviews"]["root"]["continuity_check"] = {
            "applicable": False,
            "relation_to_previous": "root",
            "source_anchor_acknowledged": True,
            "discourse_relation_realized": True,
            "action_continuity_preserved": True,
            "scene_transition_grounded": True,
            "evidence": [],
        }

    if keep_nodes == 0:
        world_state = state.get("core_gdd", {}).get("initial_world_state", {})
        agenda = state.get("core_gdd", {}).get("initial_agenda", {})
    else:
        controller_for_state = WorkflowController.__new__(WorkflowController)
        world_state = state.get("core_gdd", {}).get("initial_world_state", {})
        for node_id in kept:
            review = state["reviews"][node_id]
            if review.get("decision") != "PASS":
                raise ValueError(f"回滚边界内的节点未 PASS：{node_id}")
            world_state = controller_for_state._apply_evidence_backed_updates(
                world_state,
                review.get("state_updates", []),
            )
        agenda = state["reviews"][kept[-1]].get(
            "agenda", state.get("core_gdd", {}).get("initial_agenda", {})
        )

    controller = WorkflowController.__new__(WorkflowController)
    controller._persist_rolling_story(
        core_gdd=trimmed["core_gdd"],
        graph=trimmed["story_graph"],
        scripts=trimmed["scripts"],
        goals=trimmed["goals"],
        reviews=trimmed["reviews"],
        performances=trimmed["performances"],
        summaries=trimmed["summaries"],
        world_state=world_state,
        agenda=agenda,
    )
    # These files describe the now-discarded next node. Copies remain in backup_dir.
    for runtime_name in ("rolling_retry.json", "rolling_pre_node.json"):
        runtime_path = Path(PathConfig.DATA_DIR, runtime_name)
        if runtime_path.exists():
            runtime_path.unlink()
    return backup_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--keep-nodes", required=True, type=int)
    args = parser.parse_args()
    backup = rollback(args.project, args.keep_nodes)
    print(f"rollback complete; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
