"""Incremental narrative generation for AI4VisualNovel."""

from .engine import EvolutionBackend, EvolutionEngine
from .state import EvolutionSnapshot, NodeCursor

__all__ = [
    "EvolutionBackend",
    "EvolutionEngine",
    "EvolutionSnapshot",
    "NodeCursor",
]
