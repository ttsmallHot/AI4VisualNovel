"""Single-asset candidates. Generation never writes to the live images directory."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid

RASTER = {".png", ".jpg", ".jpeg", ".webp"}


def write_record(folder: Path, record: dict) -> None:
    temporary = folder / f".{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, folder / "request.json")


def asset_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.startswith("images/"):
        raise ValueError("Choose an image from this game.")
    path = (root / relative).resolve()
    path.relative_to((root / "images").resolve())
    path.relative_to(root.resolve())
    if path.suffix.lower() not in RASTER or not path.is_file():
        raise ValueError("Only existing PNG, JPEG, and WebP assets are supported.")
    return path


def request_folder(root: Path, request_id: str) -> Path:
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("Invalid generation record.")
    folder = root / ".ai4vn" / "regenerations" / request_id
    folder.resolve().relative_to(root.resolve())
    return folder


def read_record(root: Path, request_id: str) -> dict:
    return json.loads((request_folder(root, request_id) / "request.json").read_text(encoding="utf-8"))


def latest(root: Path, relative: str) -> dict | None:
    asset_path(root, relative)
    records = []
    for path in (root / ".ai4vn" / "regenerations").glob("*/request.json"):
        try:
            record = read_record(root, path.parent.name)
            if record.get("asset") == relative:
                records.append(record)
        except (OSError, ValueError):
            continue
    return max(records, key=lambda item: item["created_at"]) if records else None


def prepare(root: Path, relative: str, feedback: str) -> dict:
    from PIL import Image

    source = asset_path(root, relative)
    if not isinstance(feedback, str) or len(feedback) > 2000:
        raise ValueError("Revision instructions must not exceed 2,000 characters.")
    previous = latest(root, relative)
    if previous and previous["status"] in {"queued", "running", "ready"}:
        raise RuntimeError("This asset already has a running task or an image awaiting review. Resolve it first.")
    with Image.open(source) as image:
        image.verify()
    design = json.loads((root / "game_design.json").read_text(encoding="utf-8"))
    request_id = uuid.uuid4().hex
    folder = request_folder(root, request_id)
    folder.mkdir(parents=True)
    try:
        original = folder / ("original" + source.suffix.lower())
        shutil.copy2(source, original)
        parts = Path(relative).parts
        kind = "character" if len(parts) == 4 and parts[1] == "characters" else "background" if parts[1] == "backgrounds" else "cg" if parts[1] == "cg" else "other"
        subject = next((c for c in design.get("characters", []) if c.get("id") == parts[2]), {}) if kind == "character" else {}
        if kind == "background":
            subject = next((scene for scene in design.get("scenes", []) if source.stem in {scene.get("id"), scene.get("name"), re.sub(r"[^\w\s-]", "", scene.get("name", "")).strip().replace(" ", "_")}), {})
        if kind == "cg":
            manifest = root / "cg_manifest.json"
            cgs = json.loads(manifest.read_text()) if manifest.exists() else []
            subject = next((cg for cg in cgs if cg.get("id") == source.stem), {})
        references = [{"file": original.name, "role": "Current image to revise; preserve its subject, framing and composition unless requested otherwise."}]
        if kind == "character" and source.stem != "neutral":
            neutral = source.parent / "neutral.png"
            if neutral.is_file():
                neutral.resolve().relative_to(root.resolve())
                shutil.copy2(neutral, folder / "identity.png")
                references[0]["role"] = "Current expression image to revise, not the identity or framing standard. Keep its expression unless requested otherwise."
                references.append({"file": "identity.png", "role": "This is neutral.png for the SAME character: the canonical reference for face, hair, clothes, rendering style, viewing angle, body proportions, character scale and framing. Match these while applying the requested expression and corrections."})
        if kind == "cg":
            for character_id in subject.get("characters", []):
                if not isinstance(character_id, str) or not re.fullmatch(r"[\w-]+", character_id):
                    continue
                neutral = root / "images" / "characters" / character_id / "neutral.png"
                if neutral.is_file():
                    neutral.resolve().relative_to(root.resolve())
                    filename = f"identity_{len(references)}.png"
                    shutil.copy2(neutral, folder / filename)
                    references.append({"file": filename, "role": f"Canonical character identity: {character_id}."})
        record = {"id": request_id, "asset": relative, "kind": kind, "feedback": feedback.strip(), "status": "queued", "created_at": time.time(), "original": original.name, "source_hash": hashlib.sha256(original.read_bytes()).hexdigest(), "references": references, "subject": subject, "design": design, "error": ""}
        write_record(folder, record)
        return record
    except Exception:
        shutil.rmtree(folder)
        raise


def accept(root: Path, request_id: str) -> dict:
    from PIL import Image

    folder = request_folder(root, request_id)
    record = read_record(root, request_id)
    if record["status"] == "accepted":
        return record
    if record["status"] != "ready":
        raise RuntimeError("The new image is not ready yet.")
    destination = asset_path(root, record["asset"])
    if hashlib.sha256(destination.read_bytes()).hexdigest() != record["source_hash"]:
        raise RuntimeError("The original image was modified by another task. Keep the current image and regenerate.")
    with Image.open(folder / "candidate.png") as image:
        image.load()
        output = io.BytesIO()
        file_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[destination.suffix.lower()]
        image.convert("RGB" if file_format == "JPEG" else "RGBA").save(output, format=file_format)
    backup = root / ".ai4vn" / "backups" / "assets" / request_id / destination.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, backup)
    temporary = destination.with_name(f".{request_id}.tmp")
    try:
        temporary.write_bytes(output.getvalue())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    record.update(status="accepted", backup=str(backup.relative_to(root)), accepted_at=time.time())
    write_record(folder, record)
    return record


def discard(root: Path, request_id: str) -> dict:
    record = read_record(root, request_id)
    if record["status"] not in {"ready", "failed", "discarded"}:
        raise RuntimeError("Wait for generation to finish before discarding this task.")
    record["status"] = "discarded"
    write_record(request_folder(root, request_id), record)
    return record


def generate(root: Path, request_id: str, artist=None) -> None:
    from PIL import Image

    folder = request_folder(root, request_id)
    record = read_record(root, request_id)
    record.update(status="running", pid=os.getpid())
    write_record(folder, record)
    try:
        if artist is None:
            from agents.artist_agent import ArtistAgent
            artist = ArtistAgent()
        if not artist.available:
            raise RuntimeError("No image model is configured. Check the project image model settings.")
        references = [str(folder / item["file"]) for item in record["references"]]
        context = "\n".join(f"Input {index}: {item['role']}" for index, item in enumerate(record["references"], 1))
        with Image.open(folder / record["original"]) as original:
            size = "1024x1536" if original.height > original.width * 1.15 else "1536x1024" if original.width > original.height * 1.15 else "1024x1024"
        # Older saved requests predate the design snapshot; resume using project data.
        design = record.get("design")
        if design is None:
            design = json.loads((root / "game_design.json").read_text(encoding="utf-8"))
        source = Path(record["asset"])
        subject = record.get("subject", {})
        output = folder / "generated"
        common = {"feedback": record["feedback"], "output_dir": str(output), "image_size": size, "reference_context": context}
        setting = {"story_background": design.get("background", ""), "art_style": design.get("art_style", "")}
        if record["kind"] == "character":
            character = subject or next((item for item in design.get("characters", []) if item.get("id") == source.parts[2]), {"id": source.parts[2], "name": source.parts[2]})
            result = artist.generate_character_images(
                character=character, expressions=[source.stem],
                reference_image_paths=references, **setting, **common,
            ).get(source.stem)
        elif record["kind"] == "background":
            result = artist.generate_background(
                location=subject.get("name") or source.stem,
                atmosphere=subject.get("atmosphere", "peaceful"),
                reference_image_paths=references, **setting, **common,
            )
        elif record["kind"] == "cg":
            cg = subject or {"id": source.stem, "description": ""}
            characters = [item for item in design.get("characters", []) if item.get("id") in cg.get("characters", [])]
            result = artist.generate_cg(cg=cg, characters=characters, reference_image_paths=references, **setting, **common)
        elif source.stem == "title_screen":
            result = artist.generate_title_image(
                title=design.get("title", ""), background_desc=design.get("background", ""),
                character_images=references, art_style=design.get("art_style", ""), **common,
            )
        else:
            result = artist.generate_image_variation(
                reference_image_paths=references, **setting, **common,
            )
        if not result:
            raise RuntimeError("The image service returned no usable image. Check the connection and try again.")
        Path(result).resolve().relative_to(output.resolve())
        candidate = folder / "candidate.png"
        with Image.open(result) as image:
            image.convert("RGBA").save(candidate)
        with Image.open(candidate) as image:
            image.load()
            if record["kind"] == "character" and (image.mode != "RGBA" or image.getchannel("A").getextrema()[0] == 255):
                raise RuntimeError("Unable to process the transparent character background. Please try again.")
        record.update(status="ready", finished_at=time.time())
        write_record(folder, record)
    except Exception as exc:
        record.update(status="failed", error=str(exc)[:500], finished_at=time.time())
        write_record(folder, record)
        raise


if __name__ == "__main__":
    import logging
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    logging.basicConfig(level=logging.INFO)
    generate(Path(sys.argv[1]).resolve(), sys.argv[2])
