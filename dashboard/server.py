#!/usr/bin/env python3
"""Small, dependency-free dashboard server for AI4VisualNovel."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import mimetypes
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_paths import discover_projects, projects_root
from dashboard import asset_regeneration


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = ROOT / "dashboard"
STATIC_ROOT = DASHBOARD_ROOT / "static"
PROJECTS_ROOT = projects_root()
INCLUDE_LEGACY = False
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
TEXT_EXTENSIONS = {".json", ".txt", ".yaml", ".yml", ".md", ".rpy", ".log"}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
AGENT_PROCESSES: dict[str, subprocess.Popen] = {}
AGENT_ACTIVE: set[str] = set()
AGENT_LOCK = threading.RLock()
STORY_WRITE_LOCK = threading.Lock()
GRAPH_WRITE_LOCK = threading.Lock()
ASSET_WRITE_LOCK = threading.Lock()
STORY_NODE_HEADER_RE = re.compile(
    r"^===\s*Node:\s*(.+?)\s*===[ \t]*(?:\r?\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_response(data: object, status: int = 200) -> tuple[int, bytes]:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return status, payload


def project_name(value: str | None) -> str:
    value = (value or "").strip()
    if not value or "/" in value or "\\" in value or value.startswith("."):
        raise ValueError("Invalid project name")
    return value


def project_dir(value: str | None) -> Path:
    name = project_name(value)
    path = discover_projects(PROJECTS_ROOT, include_legacy=INCLUDE_LEGACY).get(name)
    if path is None:
        raise FileNotFoundError(f"Project not found: {name}")
    return path


def safe_relative_path(value: str | None, root: Path) -> Path:
    raw = unquote(value or "").lstrip("/")
    path = (root / raw).resolve()
    path.relative_to(root.resolve())
    return path


def read_json(path: Path, fallback: object | None = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def graph_revision(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("story_graph.json", "game_design.json"):
        path = root / name
        digest.update(b"present:" + path.read_bytes() if path.exists() else b"absent:")
        digest.update(b"\x00")
    return digest.hexdigest()


def validate_story_graph(graph: object) -> None:
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), dict) or not isinstance(graph.get("edges"), list):
        raise ValueError("The story graph must contain nodes and edges.")
    nodes, edges = graph["nodes"], graph["edges"]
    if "root" not in nodes:
        raise ValueError("The root starting node is required.")
    if len(nodes) > 1000 or len(edges) > 5000:
        raise ValueError("The story graph is too large.")
    for key, node in nodes.items():
        if not re.fullmatch(r"[\w-]{1,80}", key) or key in {"__proto__", "constructor", "prototype"}:
            raise ValueError(f"Invalid node ID: {key}")
        if not isinstance(node, dict) or node.get("id") != key:
            raise ValueError(f"Node ID mismatch: {key}")
        if not isinstance(node.get("summary"), str) or not node["summary"].strip():
            raise ValueError(f"Enter a summary for {key}.")
        if node.get("type") not in ("normal", "merge"):
            raise ValueError(f"Invalid node type: {key}")
    outgoing = {key: [] for key in nodes}
    indegree = dict.fromkeys(nodes, 0)
    pairs = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("Invalid connection format.")
        source, target, text = edge.get("from"), edge.get("to"), edge.get("choice_text")
        if not isinstance(source, str) or not isinstance(target, str) or source not in nodes or target not in nodes:
            raise ValueError("A connection points to a missing node.")
        if source == target or (source, target) in pairs:
            raise ValueError("Self-connections and duplicate connections are not allowed.")
        if text is not None and not isinstance(text, str):
            raise ValueError("Choice text must be a string or null.")
        pairs.add((source, target))
        outgoing[source].append(edge)
        indegree[target] += 1
    for key, branches in outgoing.items():
        if len(branches) > 1 and any(not (edge.get("choice_text") or "").strip() for edge in branches):
            raise ValueError(f"{key} has multiple branches. Enter choice text for each connection.")
    queue = [key for key, count in indegree.items() if not count]
    visited = 0
    while queue:
        key = queue.pop()
        visited += 1
        for edge in outgoing[key]:
            indegree[edge["to"]] -= 1
            if not indegree[edge["to"]]:
                queue.append(edge["to"])
    if visited != len(nodes):
        raise ValueError("The story graph cannot contain cycles.")
    reachable, queue = set(), ["root"]
    while queue:
        key = queue.pop()
        if key not in reachable:
            reachable.add(key)
            queue.extend(edge["to"] for edge in outgoing[key])
    if len(reachable) != len(nodes):
        raise ValueError("Some nodes cannot be reached from root. Add the missing connections.")


def save_story_graph(root: Path, graph: object, revision: str | None) -> dict:
    validate_story_graph(graph)
    with GRAPH_WRITE_LOCK:
        with JOBS_LOCK:
            busy = any(job.get("name") == root.name and job.get("status") in {"queued", "running"} for job in JOBS.values())
        with AGENT_LOCK:
            busy = busy or str(root.resolve()) in AGENT_ACTIVE
        if busy:
            raise RuntimeError("A project task is running. Wait for it to finish before editing the graph.")
        if revision != graph_revision(root):
            raise RuntimeError("Project files have changed. Refresh before editing again. Your draft is still in the editor.")
        graph_path, design_path = root / "story_graph.json", root / "game_design.json"
        original = {path: path.read_text(encoding="utf-8") if path.exists() else None for path in (graph_path, design_path)}
        design = json.loads(original[design_path]) if original[design_path] is not None else None
        if design is not None and not isinstance(design, dict):
            raise ValueError("Invalid game_design.json. The story graph cannot be synchronized safely.")
        backup = root / ".ai4vn" / "backups" / "story_graph" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        for path, content in original.items():
            if content is not None:
                (backup / path.name).write_text(content, encoding="utf-8")
        written = []
        try:
            write_json_atomic(graph_path, graph)
            written.append(graph_path)
            if design is not None:
                design["story_graph"] = graph
                write_json_atomic(design_path, design)
                written.append(design_path)
        except Exception:
            for path in reversed(written):
                if original[path] is None:
                    path.unlink(missing_ok=True)
                else:
                    write_text_atomic(path, original[path])
            raise
        return {"ok": True, "graph": graph, "graph_revision": graph_revision(root), "backup": str(backup.relative_to(root))}


def design_inputs(root: Path) -> dict:
    saved = read_json(root / ".ai4vn" / "design_input.json", {})
    if isinstance(saved, dict):
        return {
            "story_requirements": saved.get("story_requirements", ""),
            "scenes": saved.get("scenes", []),
            "character_count": saved.get("character_count", 3),
            "characters": saved.get("characters", []),
        } if saved else {"story_requirements": read_text(root / "requirements.txt").strip(), "scenes": [], "character_count": 3, "characters": []}
    return {"story_requirements": read_text(root / "requirements.txt").strip(), "scenes": [], "character_count": 3, "characters": []}


def save_design_inputs(root: Path, value: object) -> list[str]:
    if not isinstance(value, dict):
        raise ValueError("Design settings must be a JSON object.")
    story = value.get("story_requirements", "")
    scenes = value.get("scenes", [])
    count = value.get("character_count", 3)
    characters = value.get("characters", [])
    if not isinstance(story, str) or len(story) > 10000:
        raise ValueError("Story requirements must not exceed 10,000 characters.")
    if not isinstance(scenes, list) or len(scenes) > 30 or any(not isinstance(scene, str) or not scene.strip() or len(scene) > 200 for scene in scenes):
        raise ValueError("Enter up to 30 nonempty locations, each no longer than 200 characters.")
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError("The character count must be between 1 and 20.")
    if not isinstance(characters, list) or len(characters) > count:
        raise ValueError("Added characters cannot exceed the total character count.")
    normalized = []
    seen_names = set()
    seen_ids = set()
    uploads = []
    for index, character in enumerate(characters, 1):
        if not isinstance(character, dict):
            raise ValueError("Invalid character data.")
        name = character.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or name.strip() in seen_names:
            raise ValueError("Character names must be unique, nonempty, and at most 80 characters.")
        seen_names.add(name.strip())
        fields = {}
        for key in ("gender", "personality", "appearance", "background"):
            field = character.get(key, "")
            if not isinstance(field, str) or len(field) > 1000:
                raise ValueError("Each character field must be at most 1,000 characters.")
            fields[key] = field.strip()
        char_id = character.get("id") or f"character_{index}"
        if not isinstance(char_id, str) or not re.fullmatch(r"[\w-]{1,80}", char_id) or char_id in seen_ids:
            raise ValueError("Invalid or duplicate character ID.")
        seen_ids.add(char_id)
        entry = {"id": char_id, "name": name.strip(), "is_protagonist": character.get("is_protagonist") is True, **fields}
        image_data = character.get("neutral_image_data")
        existing = character.get("neutral_image_path")
        if image_data:
            from PIL import Image, ImageOps, UnidentifiedImageError
            try:
                if not isinstance(image_data, str) or not re.match(r"^data:image/(png|jpeg|webp);base64,", image_data):
                    raise ValueError("Character images must be PNG, JPEG, or WebP.")
                raw = base64.b64decode(image_data.split(",", 1)[1], validate=True)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("Each character image must be no larger than 8 MB.")
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 20_000_000:
                        raise ValueError("Unsupported image format or image larger than 20 megapixels.")
                    output = io.BytesIO()
                    ImageOps.exif_transpose(image).convert("RGBA").save(output, format="PNG")
                relative = Path(".ai4vn") / "oc" / char_id / f"{uuid.uuid4().hex}.png"
                uploads.append((root / relative, output.getvalue()))
                entry["neutral_image_path"] = str(relative)
            except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise ValueError("Unable to read the image. Upload a PNG, JPEG, or WebP file.") from exc
        elif existing:
            if not isinstance(existing, str):
                raise ValueError("Invalid character image path.")
            source = (root / existing).resolve()
            source.relative_to((root / ".ai4vn" / "oc").resolve())
            if not source.is_file():
                raise ValueError("Character image not found. Please upload it again.")
            entry["neutral_image_path"] = str(source.relative_to(root.resolve()))
        normalized.append(entry)

    story = story.strip()
    scenes = [scene.strip() for scene in scenes]
    requirements = story
    if scenes:
        requirements += ("\n\n" if requirements else "") + "Location requirements (include these locations and descriptions in the design):\n" + "\n".join(f"- {scene}" for scene in scenes)
    config = {"story_requirements": story, "scenes": scenes, "character_count": count, "characters": normalized, "oc": {"characters": normalized}}
    for image_path, content in uploads:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(content)
    write_json_atomic(root / ".ai4vn" / "design_input.json", config)
    write_text_atomic(root / "requirements.txt", requirements + "\n" if requirements else "")
    return ["--input-file", str(root / ".ai4vn" / "design_input.json"), "--character-count", str(count)]


def create_game(value: object) -> dict:
    """Create an empty game under the library root without starting model calls."""
    if not isinstance(value, dict):
        raise ValueError("Invalid game data.")
    title = value.get("title", "")
    story = value.get("story_requirements", "")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 80:
        raise ValueError("The game title must be between 1 and 80 characters.")
    if not isinstance(story, str) or len(story) > 10000:
        raise ValueError("The story idea must not exceed 10,000 characters.")
    name = value.get("name")
    if name is None:
        name = re.sub(r"[^\w-]+", "_", title.strip()).strip("_")
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,80}", name):
        raise ValueError("Game folder names may contain only letters, numbers, underscores, and hyphens.")
    root = PROJECTS_ROOT / name
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError as exc:
        raise FileExistsError("A game with that name already exists. Choose another name.") from exc
    try:
        write_json_atomic(root / "project.json", {"title": title.strip(), "description": story.strip()})
        save_design_inputs(root, {"story_requirements": story.strip(), "character_count": value.get("character_count", 3), "scenes": value.get("scenes", []), "characters": value.get("characters", [])})
    except Exception:
        shutil.rmtree(root)
        raise
    return {"ok": True, "project": name, "title": title.strip()}


def codex_command() -> str | None:
    configured = os.getenv("AI4VN_CODEX", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(["codex", "/Applications/ChatGPT.app/Contents/Resources/codex"])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        resolved = shutil_which(candidate)
        if resolved:
            return resolved
    return None


def agent_state_path(root: Path) -> Path:
    return root / ".ai4vn" / "agent" / "session.json"


def default_agent_state() -> dict:
    return {
        "thread_id": None,
        "status": "idle",
        "job_id": None,
        "activity": "",
        "log": "",
        "messages": [],
        "updated_at": utc_now(),
    }


def load_agent_state(root: Path) -> dict:
    state = read_json(agent_state_path(root), {})
    if not isinstance(state, dict):
        state = {}
    result = default_agent_state()
    result.update(state)
    if not isinstance(result.get("messages"), list):
        result["messages"] = []
    key = str(root.resolve())
    if key not in AGENT_ACTIVE and result.get("status") == "running":
        result["status"] = "interrupted"
        result["activity"] = "The previous task stopped when the Dashboard restarted."
    result["available"] = bool(codex_command())
    return result


def save_agent_state(root: Path, state: dict) -> None:
    persisted = {key: value for key, value in state.items() if key != "available"}
    persisted["updated_at"] = utc_now()
    write_json_atomic(agent_state_path(root), persisted)


def agent_system_prompt(root: Path) -> str:
    return f"""你是 AI4VisualNovel 项目的执行 Agent。当前游戏项目目录是：{root}
AI4VisualNovel 工具源码目录是：{ROOT}

用户会用自然语言要求你创作、检查或修改视觉小说。你需要自行检查项目现状、判断并执行必要步骤，不要让用户选择 design/script/render 阶段。

可用的稳定命令：
- python {ROOT / 'main.py'} --mode design --project {root}
- python {ROOT / 'main.py'} --mode script --project {root}
- python {ROOT / 'main.py'} --mode render --project {root}
- python {ROOT / 'main.py'} --mode export-renpy --project {root}

工作约束：
1. 先检查现有 game_design.json、story_graph.json、story.txt 和 images/，只执行完成请求所需的步骤。
2. 用户提出新的故事创意时，把自然语言整理进项目的 requirements.txt，再按当前缺失内容自行运行设计、剧本和渲染；已有内容不要无条件覆盖，先判断是新建还是修改。
3. 用户指出某张图有问题时，先定位对应角色、表情、场景或 CG，再使用项目现有 ArtistAgent/Workflow 的反馈重绘能力做定向修改；不要无关把整套资产全部重做。
4. 保持项目现有目录结构，生成物只写入当前游戏项目；工具源码修改只在确实需要修复能力时进行。
5. 允许直接编辑剧情和 JSON，但必须保持格式可被 AI4VisualNovel 读取，并在结束前做相应校验。
6. 不要只给操作建议。除非缺少无法推断的创作要求或外部凭据，否则直接执行。
7. 最终用中文简洁说明做了什么、改了哪些文件、验证结果，以及确实需要用户处理的问题。
"""


def agent_event(event: dict) -> tuple[str | None, str | None, str | None]:
    event_type = str(event.get("type", ""))
    thread_id = str(event.get("thread_id")) if event_type == "thread.started" and event.get("thread_id") else None
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    item_type = str(item.get("type", ""))
    message = None
    activity = None
    if event_type == "item.completed" and item_type == "agent_message":
        message = str(item.get("text", "")).strip() or None
    elif event_type == "item.started" and item_type == "command_execution":
        activity = "Running command"
    elif event_type == "item.completed" and item_type == "command_execution":
        activity = "Command completed"
    elif event_type == "turn.started":
        activity = "Analyzing the project and working"
    return thread_id, message, activity


def codex_agent_command(executable: str, root: Path, thread_id: str | None, prompt: str) -> list[str]:
    common = [
        "--json",
        "--skip-git-repo-check",
        "--disable",
        "plugins",
        "-c",
        "sandbox_workspace_write.network_access=true",
    ]
    if thread_id:
        return [executable, "exec", "resume", *common, thread_id, prompt]
    return [
        executable,
        "exec",
        *common,
        "--sandbox",
        "workspace-write",
        "-C",
        str(root),
        "--add-dir",
        str(ROOT),
        f"{agent_system_prompt(root)}\n\n用户当前请求：\n{prompt}",
    ]


def start_agent(name: str, prompt: str) -> str:
    root = project_dir(name)
    executable = codex_command()
    if not executable:
        raise RuntimeError("Codex CLI not found. Set AI4VN_CODEX to its executable path.")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Enter a request for the agent.")
    if len(prompt) > 20_000:
        raise ValueError("Keep your message under 20,000 characters.")

    with GRAPH_WRITE_LOCK, AGENT_LOCK:
        key = str(root.resolve())
        if key in AGENT_ACTIVE:
            raise RuntimeError("The project agent is running. Wait for it to finish or stop it first.")
        state = load_agent_state(root)
        job_id = uuid.uuid4().hex[:12]
        state["status"] = "running"
        state["job_id"] = job_id
        state["activity"] = "Starting agent"
        state["log"] = ""
        state["messages"].append({"role": "user", "text": prompt, "ts": utc_now()})
        save_agent_state(root, state)
        AGENT_ACTIVE.add(key)
        thread = threading.Thread(target=run_agent, args=(name, root, prompt, job_id), daemon=True)
        thread.start()
        return job_id


def run_agent(name: str, root: Path, prompt: str, job_id: str) -> None:
    key = str(root.resolve())
    state = load_agent_state(root)
    executable = codex_command()
    if not executable:
        return
    thread_id = state.get("thread_id")
    command = codex_agent_command(executable, root, str(thread_id) if thread_id else None, prompt)

    raw_output: list[str] = []
    assistant_messages: list[str] = []
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            start_new_session=True,
        )
        with AGENT_LOCK:
            AGENT_PROCESSES[key] = process
        assert process.stdout is not None
        for line in process.stdout:
            raw_output.append(line)
            raw_log = "".join(raw_output)[-30000:]
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = None
            with AGENT_LOCK:
                state = load_agent_state(root)
                state["log"] = raw_log
                if isinstance(event, dict):
                    new_thread_id, message, activity = agent_event(event)
                    if new_thread_id:
                        state["thread_id"] = new_thread_id
                    if message:
                        assistant_messages.append(message)
                    if activity:
                        state["activity"] = activity
                save_agent_state(root, state)
        returncode = process.wait()
        with AGENT_LOCK:
            state = load_agent_state(root)
            if returncode == 0:
                state["status"] = "completed"
                state["activity"] = "Task completed"
                reply = assistant_messages[-1] if assistant_messages else "Task completed."
                state["messages"].append({"role": "assistant", "text": reply, "ts": utc_now()})
            elif state.get("status") != "interrupted":
                state["status"] = "failed"
                state["activity"] = "Agent failed"
                detail = "".join(raw_output)[-4000:].strip()
                state["messages"].append({"role": "assistant", "text": f"Execution failed.\n\n{detail}", "ts": utc_now(), "is_error": True})
            state["job_id"] = None
            save_agent_state(root, state)
    except Exception:
        with AGENT_LOCK:
            state = load_agent_state(root)
            state["status"] = "failed"
            state["job_id"] = None
            state["activity"] = "Unable to start agent"
            state["log"] = traceback.format_exc()
            state["messages"].append({"role": "assistant", "text": f"Unable to start agent。\n\n{state['log'][-4000:]}", "ts": utc_now(), "is_error": True})
            save_agent_state(root, state)
    finally:
        with AGENT_LOCK:
            AGENT_PROCESSES.pop(key, None)
            AGENT_ACTIVE.discard(key)


def interrupt_agent(name: str) -> None:
    root = project_dir(name)
    with AGENT_LOCK:
        process = AGENT_PROCESSES.get(str(root.resolve()))
        if not process or process.poll() is not None:
            raise RuntimeError("The agent has no running task.")
        state = load_agent_state(root)
        state["status"] = "interrupted"
        state["job_id"] = None
        state["activity"] = "Stopped"
        state["messages"].append({"role": "assistant", "text": "This task has been stopped.", "ts": utc_now(), "is_error": True})
        save_agent_state(root, state)
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass


def list_projects() -> list[dict]:
    result = []
    for name, path in discover_projects(PROJECTS_ROOT, include_legacy=INCLUDE_LEGACY).items():
        # A shared games directory also contains unrelated engines and empty folders.
        if not any((path / marker).is_file() for marker in (
            "game_design.json", "story_graph.json", "story.txt", ".ai4vn/design_input.json",
        )):
            continue
        design = read_json(path / "game_design.json", {})
        metadata = read_json(path / "project.json", {})
        if not isinstance(metadata, dict):
            metadata = {}
        graph = read_json(path / "story_graph.json", {})
        cgs = read_json(path / "cg_manifest.json", [])
        cover = None
        for directory in (path / "images" / "backgrounds", path / "images" / "cg"):
            if directory.is_dir():
                image = next((item for item in sorted(directory.iterdir()) if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS), None)
                if image:
                    cover = f"/media/{quote(name, safe='')}/{quote(image.relative_to(path).as_posix(), safe='/')}"
                    break
        result.append(
            {
                "name": name,
                "title": (design.get("title") if isinstance(design, dict) else None) or metadata.get("title") or name,
                "description": (design.get("background") if isinstance(design, dict) else None) or metadata.get("description") or "",
                "cover": cover,
                "path": str(path),
                "characters": len(design.get("characters", [])) if isinstance(design, dict) and isinstance(design.get("characters"), list) else 0,
                "scenes": len(design.get("scenes", [])) if isinstance(design, dict) and isinstance(design.get("scenes"), list) else 0,
                "nodes": len(graph.get("nodes", {})) if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) else 0,
                "cgs": len(cgs) if isinstance(cgs, list) else 0,
                "has_story": (path / "story.txt").exists(),
                "has_images": any(candidate.is_file() for candidate in (path / "images").rglob("*")),
            }
        )
    return result


def generation_progress(root: Path) -> dict:
    """Report missing outputs so partial runs can be resumed from the UI."""
    design = read_json(root / "game_design.json", {})
    graph = read_json(root / "story_graph.json", {})
    nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
    story_nodes = {node["id"] for node in story_sections(read_text(root / "story.txt")) if node["raw"].strip()}
    missing_nodes = sorted(set(nodes) - story_nodes)
    expected = {"images/title_screen.png"}
    if isinstance(design, dict):
        for scene in design.get("scenes", []):
            name = re.sub(r'[^\w\s-]', '', scene["name"]).strip().replace(' ', '_')
            expected.add(f"images/backgrounds/{name}.png")
        expressions = read_json(root / "character_expressions.json", {})
        for character in design.get("characters", []):
            character_id = character.get("id", character["name"])
            for expression in {"neutral", *expressions.get(character["name"], [])}:
                expected.add(f"images/characters/{character_id}/{expression}.png")
    for cg in read_json(root / "cg_manifest.json", []):
        expected.add(f"images/cg/{cg['id']}.png")
    missing_assets = sorted(path for path in expected if not (root / path).is_file())
    return {
        "script_complete": bool(nodes) and not missing_nodes,
        "missing_nodes": missing_nodes,
        "assets_complete": not missing_assets,
        "missing_assets": missing_assets,
    }


def story_sections(story_text: str) -> list[dict]:
    headers = list(STORY_NODE_HEADER_RE.finditer(story_text))
    sections = []
    for index, header in enumerate(headers):
        body_end = headers[index + 1].start() if index + 1 < len(headers) else len(story_text)
        sections.append(
            {
                "id": header.group(1).strip(),
                "body_start": header.end(),
                "body_end": body_end,
                "raw": story_text[header.end():body_end].strip("\r\n"),
            }
        )
    return sections


def parse_story(story_text: str) -> list[dict]:
    nodes: list[dict] = []
    for section in story_sections(story_text):
        node = {"id": section["id"], "raw": section["raw"], "lines": []}
        for raw in section["raw"].splitlines():
            line = raw.strip()
            if not line:
                continue
            parsed = {"type": "raw", "text": line}
            scene = re.fullmatch(r"<scene>(.+?)</scene>", line)
            image = re.fullmatch(r'<image\s+id="([^"]+)">([^<]+)</image>', line)
            cg = re.fullmatch(r'<cg\s+id="([^"]+)"\s*/>', line)
            content = re.fullmatch(r'<content\s+id="([^"]+)">([^<]+)</content>', line)
            jump = re.fullmatch(r'<jump\s+target="([^"]+)"\s*/>', line)
            choice = re.fullmatch(r'<choice\s+target="([^"]+)">(.+?)</choice>', line)
            if scene:
                parsed = {"type": "scene", "value": scene.group(1).strip()}
            elif image:
                parsed = {"type": "image", "speaker": image.group(1).strip(), "expression": image.group(2).strip()}
            elif cg:
                parsed = {"type": "cg", "id": cg.group(1).strip()}
            elif content:
                parsed = {"type": "narration" if content.group(1).strip().casefold() in {"旁白", "narrator"} else "dialogue", "speaker": content.group(1).strip(), "text": content.group(2).strip()}
            elif jump:
                parsed = {"type": "jump", "target": jump.group(1).strip()}
            elif choice:
                parsed = {"type": "choice", "target": choice.group(1).strip(), "text": choice.group(2).strip()}
            node["lines"].append(parsed)
        nodes.append(node)
    return nodes


def replace_story_node(story_text: str, node_id: str, content: str) -> str:
    node_id = node_id.strip()
    if not node_id or "\n" in node_id or "\r" in node_id:
        raise ValueError("Invalid node ID")
    if STORY_NODE_HEADER_RE.search(content):
        raise ValueError("Node content cannot contain Node headers.")

    sections = story_sections(story_text)
    section = next((item for item in sections if item["id"] == node_id), None)
    if section is None:
        raise ValueError(f"Story node not found: {node_id}")

    body = content.strip("\r\n")
    separator = "\n\n" if section["body_end"] < len(story_text) else "\n"
    return story_text[:section["body_start"]] + body + separator + story_text[section["body_end"]:]


def save_story_node(path: Path, node_id: str, content: str, original: str | None) -> list[dict]:
    with STORY_WRITE_LOCK:
        story_text = path.read_text(encoding="utf-8")
        current = next((item for item in story_sections(story_text) if item["id"] == node_id), None)
        if current is None:
            raise ValueError(f"Story node not found: {node_id}")
        if original is not None and current["raw"] != original:
            raise RuntimeError("The script was changed by another task. Refresh before editing again.")

        updated = replace_story_node(story_text, node_id, content)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return parse_story(updated)


def asset_list(root: Path, project: str | None = None) -> list[dict]:
    images_root = root / "images"
    if not images_root.exists():
        return []
    result = []
    for path in sorted(images_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(root).as_posix()
        parts = path.relative_to(images_root).parts
        if relative.startswith("images/backgrounds/"):
            kind, category, group = "background", "scene", parts[0] if parts else "backgrounds"
        elif relative.startswith("images/characters/"):
            kind, category, group = "character", "character", parts[1] if len(parts) > 1 else "unassigned"
        elif relative.startswith("images/cg/"):
            kind, category, group = "cg", "cg", "Story CG"
        else:
            kind, category, group = "asset", "other", parts[0] if parts else "other"
        project_key = quote(project or root.name, safe="")
        asset_path = quote(relative, safe="/")
        result.append({"path": relative, "name": path.name, "kind": kind, "category": category, "group": group, "url": f"/media/{project_key}/{asset_path}?v={path.stat().st_mtime_ns}", "can_regenerate": path.suffix.lower() in asset_regeneration.RASTER})
    return result


def regeneration_result(name: str, record: dict | None) -> dict:
    if record is None:
        return {"request": None}
    result = {key: record.get(key) for key in ("id", "asset", "status", "feedback", "error", "backup")}
    base = f"/api/assets/regeneration/image?project={quote(name, safe='')}&id={record['id']}"
    result["original_url"] = base + "&version=original"
    result["candidate_url"] = base + "&version=candidate" if record["status"] in {"ready", "accepted"} else None
    return {"request": result}


def current_regeneration(name: str, relative: str) -> dict:
    root = project_dir(name)
    with ASSET_WRITE_LOCK:
        record = asset_regeneration.latest(root, relative)
        if record and record["status"] in {"queued", "running"}:
            with JOBS_LOCK:
                job = next((job for job in JOBS.values() if job["kind"] == "asset-regenerate" and job["command"][-1] == record["id"]), None)
            interrupted = False
            if not job:
                import time
                if record.get("pid"):
                    try:
                        os.kill(record["pid"], 0)
                    except ProcessLookupError:
                        interrupted = True
                elif time.time() - record["created_at"] > 60:
                    interrupted = True
            if interrupted or (job and job["status"] in {"failed", "completed"}):
                record = asset_regeneration.read_record(root, record["id"])
                if record["status"] in {"queued", "running"}:
                    record.update(status="failed", error="Generation was interrupted. Please try again.")
                    asset_regeneration.write_record(asset_regeneration.request_folder(root, record["id"]), record)
        return regeneration_result(name, record)


def renpy_sdk() -> str | None:
    configured = os.getenv("RENPY_SDK", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(["renpy", "renpy.sh", "/Applications/renpy/renpy.sh"])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        resolved = shutil_which(candidate)
        if resolved:
            return resolved
    return None


def shutil_which(command: str) -> str | None:
    for folder in os.getenv("PATH", "").split(os.pathsep):
        candidate = Path(folder) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def create_renpy_project(name: str) -> Path:
    source = project_dir(name)
    design = read_json(source / "game_design.json", {})
    story = read_text(source / "story.txt")
    if not isinstance(design, dict) or not story.strip():
        raise ValueError("The project is missing game_design.json or story.txt.")

    output = source / ".ai4vn" / "builds" / "renpy_project"
    game_dir = output / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from export_renpy import convert_to_renpy, copy_assets

    (game_dir / "script.rpy").write_text(convert_to_renpy(design, story, source / "images"), encoding="utf-8")
    copy_assets(source / "images", game_dir)
    options = game_dir / "options.rpy"
    if not options.exists():
        title = str(design.get("title", name)).replace('"', "'")
        options.write_text(f'define config.name = "{title}"\ndefine config.version = "1.0"\n', encoding="utf-8")
    (output / "README.txt").write_text("Exported by AI4VisualNovel Dashboard. Open this directory in the Ren'Py Launcher.\n", encoding="utf-8")
    return output


def renpy_project_archive(name: str) -> tuple[str, bytes]:
    output = project_dir(name) / ".ai4vn" / "builds" / "renpy_project"
    if not output.exists() or not output.is_dir():
        output = create_renpy_project(name)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                bundle.write(path, path.relative_to(output.parent).as_posix())
    return f"{name}-renpy-project.zip", archive.getvalue()


def new_job(kind: str, name: str, command: list[str]) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "kind": kind, "name": name, "command": command, "status": "queued", "started_at": None, "finished_at": None, "returncode": None, "log": ""}
    with GRAPH_WRITE_LOCK, JOBS_LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()
    return job_id


def run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = utc_now()
    try:
        process = subprocess.Popen(job["command"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env={**os.environ, "PYTHONPATH": str(ROOT)})
        output = []
        assert process.stdout is not None
        for line in process.stdout:
            output.append(line)
            with JOBS_LOCK:
                job["log"] = "".join(output)[-20000:]
        returncode = process.wait()
        with JOBS_LOCK:
            job["returncode"] = returncode
            job["status"] = "completed" if returncode == 0 else "failed"
            job["finished_at"] = utc_now()
    except Exception:
        with JOBS_LOCK:
            job["status"] = "failed"
            job["finished_at"] = utc_now()
            job["log"] = traceback.format_exc()


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "AI4VisualNovelDashboard/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {format % args}")

    def send_json(self, data: object, status: int = 200) -> None:
        status, payload = json_response(data, status)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        limit = 36_000_000 if urlparse(self.path).path == "/api/projects" else 1_000_000
        if length < 0 or length > limit:
            raise ValueError("Request body is too large.")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/assets/regeneration":
                name = project_name(query.get("project", [None])[0])
                return self.send_json(current_regeneration(name, query.get("path", [""])[0]))
            if path == "/api/assets/regeneration/image":
                root = project_dir(query.get("project", [None])[0])
                request_id = query.get("id", [""])[0]
                record = asset_regeneration.read_record(root, request_id)
                version = query.get("version", [""])[0]
                if version not in {"original", "candidate"}:
                    raise ValueError("Invalid image version.")
                filename = record["original"] if version == "original" else "candidate.png"
                return self.send_file(asset_regeneration.request_folder(root, request_id) / filename)
            if path == "/api/projects":
                return self.send_json({"projects": list_projects()})
            if path == "/api/status":
                selected = query.get("project", [None])[0]
                project = project_dir(selected) if selected else None
                return self.send_json({"project": selected, "project_path": str(project) if project else None, "project_exists": bool(project and project.exists()), "renpy_sdk": renpy_sdk(), "root": str(ROOT), "projects_root": str(PROJECTS_ROOT), "jobs": len(JOBS)})
            if path == "/api/project":
                name = project_name(query.get("project", [None])[0])
                root = project_dir(name)
                revision = graph_revision(root)
                design = read_json(root / "game_design.json", {})
                metadata = read_json(root / "project.json", {})
                graph = read_json(root / "story_graph.json", {})
                # A concurrent writer must not make an old graph appear current.
                if revision != graph_revision(root):
                    raise RuntimeError("The project is being updated. Please try again.")
                cgs = read_json(root / "cg_manifest.json", [])
                return self.send_json({"name": name, "path": str(root), "metadata": metadata if isinstance(metadata, dict) else {}, "design_inputs": design_inputs(root), "design": design, "graph": graph, "graph_revision": revision, "cgs": cgs if isinstance(cgs, list) else [], "story": parse_story(read_text(root / "story.txt")), "assets": asset_list(root, name), "progress": generation_progress(root)})
            if path == "/api/story":
                name = project_name(query.get("project", [None])[0])
                return self.send_json({"project": name, "nodes": parse_story(read_text(project_dir(name) / "story.txt"))})
            if path == "/api/assets":
                name = project_name(query.get("project", [None])[0])
                return self.send_json({"project": name, "assets": asset_list(project_dir(name), name)})
            if path == "/api/agent":
                name = project_name(query.get("project", [None])[0])
                with AGENT_LOCK:
                    return self.send_json({"project": name, **load_agent_state(project_dir(name))})
            if path == "/api/download-renpy":
                name = project_name(query.get("project", [None])[0])
                filename, content = renpy_project_archive(name)
                return self.send_bytes(content, "application/zip", filename)
            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = dict(JOBS.get(job_id, {}))
                return self.send_json(job, 200 if job else 404)
            if path.startswith("/media/"):
                parts = path.split("/", 3)
                if len(parts) < 4:
                    return self.send_json({"error": "Missing asset path."}, 400)
                root = project_dir(unquote(parts[2]))
                file_path = safe_relative_path(parts[3], root)
                allowed = [root / "images", root / ".ai4vn" / "oc"]
                if not any(file_path.is_relative_to(directory.resolve()) for directory in allowed):
                    raise ValueError("Only image assets can be accessed.")
                if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    raise ValueError("Only image assets can be accessed.")
                return self.send_file(file_path)
            return self.send_static(path)
        except (ValueError, FileNotFoundError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            data = self.body_json()
            if parsed.path in {"/api/assets/regenerate", "/api/assets/regeneration/accept", "/api/assets/regeneration/discard"}:
                name = project_name(data.get("project"))
                root = project_dir(name)
                with ASSET_WRITE_LOCK:
                    if parsed.path == "/api/assets/regenerate":
                        record = asset_regeneration.prepare(root, data.get("path"), data.get("feedback", ""))
                        command = [sys.executable, str(DASHBOARD_ROOT / "asset_regeneration.py"), str(root), record["id"]]
                        new_job("asset-regenerate", name, command)
                        return self.send_json(regeneration_result(name, record), 202)
                    if parsed.path.endswith("/accept"):
                        record = asset_regeneration.accept(root, data.get("id"))
                    else:
                        record = asset_regeneration.discard(root, data.get("id"))
                    return self.send_json(regeneration_result(name, record))
            if parsed.path == "/api/projects":
                return self.send_json(create_game(data), 201)
            if parsed.path == "/api/graph":
                return self.send_json(save_story_graph(project_dir(data.get("project")), data.get("graph"), data.get("revision")))
            if parsed.path == "/api/agent/message":
                name = project_name(data.get("project"))
                prompt = str(data.get("message", ""))
                job_id = start_agent(name, prompt)
                return self.send_json({"ok": True, "project": name, "job_id": job_id}, 202)
            if parsed.path == "/api/agent/interrupt":
                name = project_name(data.get("project"))
                interrupt_agent(name)
                return self.send_json({"ok": True, "project": name})
            if parsed.path == "/api/story/node":
                name = project_name(data.get("project"))
                node_id = str(data.get("node_id", ""))
                content = data.get("content")
                original = data.get("original")
                if not isinstance(content, str):
                    raise ValueError("Node content must be a string.")
                if original is not None and not isinstance(original, str):
                    raise ValueError("Original node content must be a string.")
                nodes = save_story_node(project_dir(name) / "story.txt", node_id, content, original)
                return self.send_json({"ok": True, "project": name, "node_id": node_id, "nodes": nodes})
            if parsed.path == "/api/export-renpy":
                name = project_name(data.get("project"))
                output = create_renpy_project(name)
                return self.send_json({"ok": True, "project": name, "output": str(output), "relative_output": str(output)})
            if parsed.path == "/api/build-renpy":
                name = project_name(data.get("project"))
                output = create_renpy_project(name)
                sdk = renpy_sdk()
                if not sdk:
                    return self.send_json({"ok": False, "error": "Ren'Py SDK not found. Set RENPY_SDK and try again.", "exported": str(output)}, 409)
                custom = os.getenv("RENPY_BUILD_COMMAND", "").strip()
                if custom:
                    command = [part.format(renpy=sdk, project=str(output), target=str(data.get("target", ""))) for part in shlex.split(custom)]
                else:
                    command = [sdk, str(output), "distribute"]
                job_id = new_job("renpy-build", name, command)
                return self.send_json({"ok": True, "job_id": job_id, "command": command, "output": str(output)}, 202)
            if parsed.path == "/api/run":
                name = project_name(data.get("project"))
                mode = str(data.get("mode", "")).strip()
                if mode not in {"design", "script", "render"}:
                    raise ValueError("Unsupported generation mode.")
                command = [sys.executable, str(ROOT / "main.py"), "--mode", mode, "--project", str(project_dir(name))]
                if mode == "design" and "design_input" in data:
                    if (project_dir(name) / "game_design.json").exists():
                        raise RuntimeError("A game design already exists. Review it before making changes.")
                    command.extend(save_design_inputs(project_dir(name), data["design_input"]))
                for key, flag in (("input_file", "--input-file"), ("requirements_file", "--requirements-file")):
                    value = data.get(key)
                    if value not in (None, ""):
                        command.extend([flag, str(value)])
                job_id = new_job("pipeline", name, command)
                return self.send_json({"ok": True, "job_id": job_id, "command": command}, 202)
            self.send_json({"error": "Not found"}, 404)
        except (RuntimeError, FileExistsError) as exc:
            self.send_json({"error": str(exc)}, 409)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def send_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/", "/index.html"} else path.lstrip("/")
        file_path = safe_relative_path(relative, STATIC_ROOT)
        self.send_file(file_path)

    def send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_json({"error": "File not found."}, 404)
            return
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        self.send_bytes(content, content_type)

    def send_bytes(self, content: bytes, content_type: str, download_name: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI4VisualNovel Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--projects-root", help="Games directory (default: AI4VisualNovel/games)")
    args = parser.parse_args()
    global PROJECTS_ROOT
    PROJECTS_ROOT = projects_root(args.projects_root)
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"AI4VisualNovel Dashboard: http://{args.host}:{args.port}")
    print(f"Projects root: {PROJECTS_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
