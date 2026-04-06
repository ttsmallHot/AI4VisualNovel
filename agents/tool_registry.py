"""
Story Graph Tool Registry
~~~~~~~~~~~~~~~~~~~~~~~~~
提供统一的工具调用入口，便于在 Agent 内外复用。
"""

from typing import Any, Dict, List

from .story_graph import StoryGraph


class StoryGraphTools:
    """故事图工具集合。"""

    @staticmethod
    def graph_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
        story_graph = payload.get("story_graph", {}) if isinstance(payload, dict) else {}
        wrapped = {"story_graph": story_graph}
        graph = StoryGraph(wrapped)

        is_valid, error_message = graph.validate()
        topo = graph.topological_sort()
        leaf_nodes = [node_id for node_id in graph.nodes.keys() if len(graph.get_children(node_id)) == 0]

        return {
            "is_valid": is_valid,
            "error": "" if is_valid else error_message,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "leaf_count": len(leaf_nodes),
            "topo_count": len(topo),
        }

    @staticmethod
    def enumerate_paths(payload: Dict[str, Any]) -> Dict[str, Any]:
        story_graph = payload.get("story_graph", {}) if isinstance(payload, dict) else {}
        max_paths = payload.get("max_paths", 128) if isinstance(payload, dict) else 128

        try:
            max_paths = int(max_paths)
        except Exception:
            max_paths = 128
        max_paths = max(1, min(max_paths, 300))

        wrapped = {"story_graph": story_graph}
        graph = StoryGraph(wrapped)
        paths = graph.enumerate_all_paths(start_node="root", max_paths=max_paths)

        path_records: List[Dict[str, Any]] = []
        lengths: List[int] = []
        for idx, path in enumerate(paths, 1):
            lengths.append(len(path))
            path_records.append(
                {
                    "path_id": f"P{idx:03d}",
                    "nodes": path,
                    "length": len(path),
                    "ending": path[-1] if path else "",
                }
            )

        return {
            "path_count": len(paths),
            "min_length": min(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
            "sample_paths": path_records[:30],
        }


_TOOL_REGISTRY = {
    "graph_validate": StoryGraphTools.graph_validate,
    "enumerate_paths": StoryGraphTools.enumerate_paths,
}


def list_available_tools() -> List[str]:
    """返回当前可用工具名。"""
    return sorted(_TOOL_REGISTRY.keys())


def call_tool(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """统一工具调用入口。"""
    if tool_name not in _TOOL_REGISTRY:
        raise ValueError(f"未知工具: {tool_name}")
    handler = _TOOL_REGISTRY[tool_name]
    return handler(payload or {})
