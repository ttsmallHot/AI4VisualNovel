"""Serializable state for incremental story-graph expansion."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NodeCursor:
    """A pending story node together with its path-specific state."""

    node_id: str
    parent_id: Optional[str]
    depth: int
    path: List[str]
    contract: Dict[str, Any]
    world_state: Dict[str, Any]
    agenda: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeCursor":
        return cls(
            node_id=str(data["node_id"]),
            parent_id=data.get("parent_id"),
            depth=int(data.get("depth", 0)),
            path=list(data.get("path", [])),
            contract=deepcopy(data.get("contract", {})),
            world_state=deepcopy(data.get("world_state", {})),
            agenda=deepcopy(data.get("agenda", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionSnapshot:
    """Complete resumable state of one evolutionary generation run."""

    core_gdd: Dict[str, Any]
    story_graph: Dict[str, Any]
    cursors: Dict[str, NodeCursor]
    frontier: List[str]
    completed: List[str] = field(default_factory=list)
    scripts: Dict[str, str] = field(default_factory=dict)
    node_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    next_node_index: int = 1
    schema_version: str = "evo-state/1.0"

    @classmethod
    def create(
        cls,
        core_gdd: Dict[str, Any],
        root_contract: Dict[str, Any],
    ) -> "EvolutionSnapshot":
        root_cursor = NodeCursor(
            node_id="root",
            parent_id=None,
            depth=0,
            path=["root"],
            contract=deepcopy(root_contract),
            world_state=deepcopy(core_gdd.get("initial_world_state", {})),
            agenda=deepcopy(core_gdd.get("initial_agenda", {})),
        )
        return cls(
            core_gdd=deepcopy(core_gdd),
            story_graph={
                "nodes": {
                    "root": {
                        "id": "root",
                        "summary": root_contract.get("goal", "Initial conflict"),
                        "type": "normal",
                        "generation_status": "pending",
                    }
                },
                "edges": [],
            },
            cursors={"root": root_cursor},
            frontier=["root"],
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionSnapshot":
        if data.get("schema_version") != "evo-state/1.0":
            raise ValueError(f"Unsupported evolution state: {data.get('schema_version')}")
        return cls(
            schema_version=data["schema_version"],
            core_gdd=deepcopy(data.get("core_gdd", {})),
            story_graph=deepcopy(data.get("story_graph", {"nodes": {}, "edges": []})),
            cursors={
                node_id: NodeCursor.from_dict(cursor)
                for node_id, cursor in data.get("cursors", {}).items()
            },
            frontier=list(data.get("frontier", [])),
            completed=list(data.get("completed", [])),
            scripts=deepcopy(data.get("scripts", {})),
            node_results=deepcopy(data.get("node_results", {})),
            next_node_index=int(data.get("next_node_index", 1)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "core_gdd": deepcopy(self.core_gdd),
            "story_graph": deepcopy(self.story_graph),
            "cursors": {
                node_id: cursor.to_dict()
                for node_id, cursor in self.cursors.items()
            },
            "frontier": list(self.frontier),
            "completed": list(self.completed),
            "scripts": deepcopy(self.scripts),
            "node_results": deepcopy(self.node_results),
            "next_node_index": self.next_node_index,
        }
