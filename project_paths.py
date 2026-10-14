"""Project location helpers shared by the CLI and Dashboard."""

from __future__ import annotations

import os
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parent
LEGACY_PROJECTS_ROOT = TOOL_ROOT / "data"
DEFAULT_PROJECTS_ROOT = TOOL_ROOT / "games"


def projects_root(value: str | os.PathLike[str] | None = None) -> Path:
    """Return the configured directory that contains standalone projects."""
    configured = value or os.getenv("AI4VN_PROJECTS_ROOT")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_PROJECTS_ROOT


def is_path_reference(value: str) -> bool:
    path = Path(value).expanduser()
    return path.is_absolute() or len(path.parts) > 1 or value.startswith(".")


def resolve_project_path(
    value: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve a project path while retaining compatibility with data/<name>."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("project must be provided")

    if is_path_reference(raw):
        return Path(raw).expanduser().resolve()

    external = projects_root(root) / raw
    legacy = LEGACY_PROJECTS_ROOT / raw
    if external.exists():
        return external.resolve()
    if legacy.exists():
        return legacy.resolve()
    return external.resolve()


def discover_projects(
    root: str | os.PathLike[str] | None = None,
    *,
    include_legacy: bool = False,
) -> dict[str, Path]:
    """Discover immediate project directories, preferring standalone projects."""
    found: dict[str, Path] = {}
    roots = [projects_root(root)]
    if include_legacy and LEGACY_PROJECTS_ROOT.resolve() != roots[0].resolve():
        roots.append(LEGACY_PROJECTS_ROOT)

    for container in roots:
        if not container.exists():
            continue
        for candidate in sorted(container.iterdir()):
            if candidate.is_dir() and not candidate.name.startswith("."):
                found.setdefault(candidate.name, candidate.resolve())
    return found
