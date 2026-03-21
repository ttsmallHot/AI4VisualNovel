import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


NODE_HEADER_RE = re.compile(r"^===\s*Node:\s*(.+?)\s*===\s*$", re.IGNORECASE)
SCENE_RE = re.compile(r"^<scene>(.+?)</scene>$")
IMAGE_RE = re.compile(r"^<image\s+id=\"([^\"]+)\">([^<]+)</image>$")
CONTENT_RE = re.compile(r"^<content\s+id=\"([^\"]+)\">([^<]+)</content>$")
CHOICE_RE = re.compile(r"^<choice\s+target=\"([^\"]+)\">(.+?)</choice>$")
JUMP_RE = re.compile(r"^<jump\s+target=\"([^\"]+)\"\s*/>$")


def slug(value: str, fallback: str = "x") -> str:
    text = re.sub(r"\s+", "_", (value or "").strip())
    text = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return fallback
    if text[0].isdigit():
        return f"_{text}"
    return text


def rpy_str(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def parse_story_nodes(story_text: str) -> List[Tuple[str, List[str]]]:
    nodes: List[Tuple[str, List[str]]] = []
    current_id = ""
    current_lines: List[str] = []

    for raw_line in story_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        node_match = NODE_HEADER_RE.match(line)
        if node_match:
            if current_id:
                nodes.append((current_id, current_lines))
            current_id = node_match.group(1).strip()
            current_lines = []
            continue
        if current_id:
            current_lines.append(line)

    if current_id:
        nodes.append((current_id, current_lines))

    return nodes


def collect_character_images(characters_dir: Path, character_id: str) -> Dict[str, str]:
    image_map: Dict[str, str] = {}
    char_dir = characters_dir / character_id
    if not char_dir.exists():
        return image_map

    for path in sorted(char_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        expression = slug(path.stem, fallback="neutral")
        image_map[expression] = f"images/characters/{character_id}/{path.name}".replace("\\", "/")
    return image_map


def collect_background_images(backgrounds_dir: Path, scenes: List[Dict]) -> Dict[str, str]:
    ext_candidates = [".png", ".jpg", ".jpeg", ".webp"]
    result: Dict[str, str] = {}

    for scene in scenes:
        scene_id = str(scene.get("id", "")).strip()
        if not scene_id:
            continue
        for ext in ext_candidates:
            candidate = backgrounds_dir / f"{scene_id}{ext}"
            if candidate.exists() and candidate.is_file():
                result[scene_id] = f"images/backgrounds/{candidate.name}".replace("\\", "/")
                break
    return result


def convert_to_renpy(
    game_design: Dict,
    story_text: str,
    images_root: Path,
) -> str:
    characters = game_design.get("characters", []) if isinstance(game_design.get("characters", []), list) else []
    scenes = game_design.get("scenes", []) if isinstance(game_design.get("scenes", []), list) else []

    characters_dir = images_root / "characters"
    backgrounds_dir = images_root / "backgrounds"

    name_to_var: Dict[str, str] = {}
    name_to_image_key: Dict[str, str] = {}
    name_to_exprs: Dict[str, set] = {}

    lines: List[str] = []

    for idx, char in enumerate(characters, 1):
        char_name = str(char.get("name", "")).strip()
        char_id = str(char.get("id", "")).strip() or f"char_{idx}"
        if not char_name:
            continue

        var_name = f"ch_{slug(char_id, fallback=f'char_{idx}') }"
        image_key = slug(char_id, fallback=f"char_{idx}")

        name_to_var[char_name] = var_name
        name_to_image_key[char_name] = image_key

        lines.append(f'define {var_name} = Character("{rpy_str(char_name)}")')

        expr_map = collect_character_images(characters_dir, char_id)
        name_to_exprs[char_name] = set(expr_map.keys())
        for expression, rel_path in expr_map.items():
            lines.append(f'image {image_key} {expression} = "{rpy_str(rel_path)}"')

    if characters:
        lines.append("")

    scene_name_to_id = {}
    for scene in scenes:
        scene_name = str(scene.get("name", "")).strip()
        scene_id = str(scene.get("id", "")).strip()
        if scene_name and scene_id:
            scene_name_to_id[scene_name] = scene_id

    bg_map = collect_background_images(backgrounds_dir, scenes)
    for scene_id, rel_path in bg_map.items():
        lines.append(f'image bg_{slug(scene_id)} = "{rpy_str(rel_path)}"')

    if bg_map:
        lines.append("")

    story_nodes = parse_story_nodes(story_text)
    if not story_nodes:
        lines.append("label start:")
        lines.append('    "未找到可转换的剧情节点。"')
        lines.append("    return")
        return "\n".join(lines) + "\n"

    root_exists = any(node_id == "root" for node_id, _ in story_nodes)
    lines.append("label start:")
    lines.append("    jump root" if root_exists else f"    jump {slug(story_nodes[0][0])}")
    lines.append("")

    for node_id, node_lines in story_nodes:
        label_name = slug(node_id, fallback="node")
        lines.append(f"label {label_name}:")

        i = 0
        while i < len(node_lines):
            line = node_lines[i]

            scene_match = SCENE_RE.match(line)
            if scene_match:
                scene_name = scene_match.group(1).strip()
                scene_id = scene_name_to_id.get(scene_name)
                if scene_id and scene_id in bg_map:
                    lines.append(f"    scene bg_{slug(scene_id)}")
                else:
                    lines.append("    scene black")
                i += 1
                continue

            image_match = IMAGE_RE.match(line)
            if image_match:
                char_name = image_match.group(1).strip()
                expression = slug(image_match.group(2).strip(), fallback="neutral")
                image_key = name_to_image_key.get(char_name)
                expr_pool = name_to_exprs.get(char_name, set())
                if image_key and expression in expr_pool:
                    lines.append(f"    show {image_key} {expression}")
                elif image_key and "neutral" in expr_pool:
                    lines.append(f"    show {image_key} neutral")
                i += 1
                continue

            content_match = CONTENT_RE.match(line)
            if content_match:
                speaker = content_match.group(1).strip()
                text = content_match.group(2).strip()
                if speaker == "旁白":
                    lines.append(f'    "{rpy_str(text)}"')
                else:
                    var_name = name_to_var.get(speaker)
                    if var_name:
                        lines.append(f'    {var_name} "{rpy_str(text)}"')
                    else:
                        lines.append(f'    "{rpy_str(speaker)}：{rpy_str(text)}"')
                i += 1
                continue

            choice_match = CHOICE_RE.match(line)
            if choice_match:
                menu_items = []
                while i < len(node_lines):
                    maybe_choice = CHOICE_RE.match(node_lines[i])
                    if not maybe_choice:
                        break
                    menu_items.append((maybe_choice.group(2).strip(), maybe_choice.group(1).strip()))
                    i += 1

                if menu_items:
                    lines.append("    menu:")
                    for text, target in menu_items:
                        lines.append(f'        "{rpy_str(text)}":')
                        lines.append(f"            jump {slug(target, fallback='node')}")
                continue

            jump_match = JUMP_RE.match(line)
            if jump_match:
                target = jump_match.group(1).strip()
                lines.append(f"    jump {slug(target, fallback='node')}")
                i += 1
                continue

            i += 1

        if not any(JUMP_RE.match(s) for s in node_lines) and not any(CHOICE_RE.match(s) for s in node_lines):
            lines.append("    return")
        lines.append("")

    return "\n".join(lines) + "\n"


def copy_assets(images_root: Path, out_game_dir: Path) -> None:
    src = images_root
    dst = out_game_dir / "images"
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="将 AI4VisualNovel 输出转换为 Ren'Py script.rpy")
    parser.add_argument("--game-design", default="data/game_design.json", help="game_design.json 路径")
    parser.add_argument("--story", default="data/story.txt", help="story.txt 路径")
    parser.add_argument("--images-root", default="data/images", help="图片根目录（含 backgrounds/characters）")
    parser.add_argument("--out-dir", default="renpy_export/game", help="Ren'Py game 目录输出路径")
    parser.add_argument("--no-copy-assets", action="store_true", help="仅导出 script.rpy，不复制 images")
    args = parser.parse_args()

    game_design_path = Path(args.game_design)
    story_path = Path(args.story)
    images_root = Path(args.images_root)
    out_game_dir = Path(args.out_dir)

    if not game_design_path.exists():
        raise FileNotFoundError(f"未找到 game_design 文件: {game_design_path}")
    if not story_path.exists():
        raise FileNotFoundError(f"未找到 story 文件: {story_path}")

    with game_design_path.open("r", encoding="utf-8") as f:
        game_design = json.load(f)
    with story_path.open("r", encoding="utf-8") as f:
        story_text = f.read()

    out_game_dir.mkdir(parents=True, exist_ok=True)
    script_content = convert_to_renpy(game_design, story_text, images_root=images_root)

    script_path = out_game_dir / "script.rpy"
    script_path.write_text(script_content, encoding="utf-8")

    if not args.no_copy_assets:
        copy_assets(images_root=images_root, out_game_dir=out_game_dir)

    print(f"✅ 已导出 Ren'Py 脚本: {script_path}")
    if not args.no_copy_assets:
        print(f"🖼️ 已复制图片资源到: {out_game_dir / 'images'}")


if __name__ == "__main__":
    main()
