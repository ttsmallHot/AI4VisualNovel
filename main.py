"""
AI Visual Novel - Main Entry Point
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AI 驱动的自动化 Visual Novel 生成和运行系统

主要功能:
1. 使用制作人 Agent生成游戏设计
2. 使用美术 Agent生成角色立绘
3. 使用编剧 Agent生成剧情
4. 启动游戏 UI 进行游玩
"""

import sys
import os
import logging
import argparse
import importlib
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from workflow import WorkflowController
from agents.config import ProducerConfig, DesignerConfig, PathConfig


def load_input_config(input_file: str) -> dict:
    """加载 input.yaml 配置文件。"""
    if not input_file or not os.path.exists(input_file):
        return {}

    try:
        yaml = importlib.import_module("yaml")
    except ImportError:
        print("⚠️ 未安装 PyYAML，无法读取 input.yaml（将继续使用命令行参数）")
        print("   可执行: pip install pyyaml")
        return {}

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return config if isinstance(config, dict) else {}
    except Exception as e:
        print(f"⚠️ 读取 input.yaml 失败: {e}，将继续使用命令行参数")
        return {}


def _read_text_file(file_path: str) -> str:
    if not file_path:
        return ""
    if not os.path.exists(file_path):
        print(f"⚠️ 找不到文件: {file_path}")
        return ""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"⚠️ 读取文件失败 {file_path}: {e}")
        return ""


def resolve_design_inputs(args) -> tuple[str, list]:
    """统一解析 design 阶段输入：requirements + OC 角色。"""
    input_file = args.input_file
    input_config = load_input_config(input_file)

    requirements_path = args.requirements_file
    if not requirements_path:
        requirements_cfg = input_config.get("requirements", {}) if isinstance(input_config.get("requirements", {}), dict) else {}
        requirements_path = requirements_cfg.get("file_path")

    oc_cfg = input_config.get("oc", {}) if isinstance(input_config.get("oc", {}), dict) else {}

    if requirements_path:
        print(f"\n📖 正在读取世界观/需求文件: {requirements_path}")
    user_requirements = _read_text_file(requirements_path) if requirements_path else ""
    if user_requirements:
        print(f"✅ 已加载构想: {user_requirements[:50]}...")
    else:
        print("\n💡 未提供有效需求文件，将由 AI 自由发挥内容。")

    oc_characters = oc_cfg.get("characters", [])
    if not isinstance(oc_characters, list):
        print("⚠️ input.yaml 中 oc.characters 不是数组，已忽略")
        oc_characters = []
    else:
        oc_characters = [item for item in oc_characters if isinstance(item, dict)]

    if oc_characters:
        print(f"🧩 已加载 OC 角色: {len(oc_characters)} 个（来自 input.yaml）")

    return user_requirements, oc_characters


def setup_logging(level=logging.INFO):
    """配置日志系统"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.FileHandler(os.path.join(PathConfig.LOG_DIR, 'ai_visual_novel.log'), encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def play_game_flow():
    """游玩游戏流程"""
    print("\n" + "="*70)
    print("🎮 AI Visual Novel - 游戏运行模式")
    print("="*70)
    
    # 检查游戏是否存在
    if not os.path.exists(PathConfig.GAME_DESIGN_FILE):
        print("\n❌ 未找到游戏数据!")
        print("   请先按阶段运行: python main.py --mode design -> script -> render")
        return
    
    # 启动游戏 UI
    print("\n🚀 启动游戏...")
    
    # 导入并启动游戏
    from game_engine.manager import GameManager
    game = GameManager()
    game.run()


def design_game_flow(args):
    """仅运行设计阶段"""
    print("\n" + "="*70)
    print("🎬 AI Visual Novel - [阶段 1] 游戏设计模式")
    print("="*70)
    
    workflow = WorkflowController()
    workflow.initialize_agents(openai_api_key=args.openai_key, openai_base_url=args.openai_base_url)
    
    user_requirements, oc_characters = resolve_design_inputs(args)
            
    workflow.run_design_phase(
        character_count=args.character_count,
        requirements=user_requirements,
        oc_characters=oc_characters
    )

def script_game_flow(args):
    """仅运行剧本生成阶段"""
    print("\n" + "="*70)
    print("🎬 AI Visual Novel - [阶段 2] 剧本生成模式")
    print("="*70)
    
    workflow = WorkflowController()
    workflow.initialize_agents(openai_api_key=args.openai_key, openai_base_url=args.openai_base_url)
    workflow.run_script_phase()

def render_game_flow(args):
    """仅运行渲染阶段"""
    print("\n" + "="*70)
    print("🎬 AI Visual Novel - [阶段 3] 资产渲染模式")
    print("="*70)
    
    workflow = WorkflowController()
    workflow.initialize_agents(openai_api_key=args.openai_key, openai_base_url=args.openai_base_url)
    workflow.run_render_phase()


def export_renpy_flow(args):
    """导出 Ren'Py 项目脚本与资源"""
    print("\n" + "="*70)
    print("🎬 AI Visual Novel - Ren'Py 导出模式")
    print("="*70)

    if not os.path.exists(PathConfig.GAME_DESIGN_FILE):
        print(f"\n❌ 未找到文件: {PathConfig.GAME_DESIGN_FILE}")
        print("   请先运行: python main.py --mode design")
        return

    if not os.path.exists(PathConfig.STORY_FILE):
        print(f"\n❌ 未找到文件: {PathConfig.STORY_FILE}")
        print("   请先运行: python main.py --mode script")
        return

    exporter = importlib.import_module("export_renpy")

    with open(PathConfig.GAME_DESIGN_FILE, "r", encoding="utf-8") as f:
        game_design = json.load(f)
    with open(PathConfig.STORY_FILE, "r", encoding="utf-8") as f:
        story_text = f.read()

    out_game_dir = Path(args.renpy_out_dir)
    out_game_dir.mkdir(parents=True, exist_ok=True)

    script_content = exporter.convert_to_renpy(
        game_design=game_design,
        story_text=story_text,
        images_root=Path(PathConfig.IMAGES_DIR)
    )

    script_path = out_game_dir / "script.rpy"
    script_path.write_text(script_content, encoding="utf-8")

    if not args.renpy_no_copy_assets:
        exporter.copy_assets(images_root=Path(PathConfig.IMAGES_DIR), out_game_dir=out_game_dir)

    print(f"\n✅ Ren'Py 脚本已导出: {script_path}")
    if not args.renpy_no_copy_assets:
        print(f"🖼️ Ren'Py 资源已复制到: {out_game_dir / 'images'}")
    print("\n下一步: 在 Ren'Py Launcher 中打开导出项目根目录并运行。")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AI Visual Novel - AI 驱动的自动化 Visual Novel 生成和运行系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    # 按阶段生成新游戏
        python main.py --mode design --input-file input.yaml
        python main.py --mode script
        python main.py --mode render

    # 仅导出现有数据到 Ren'Py
        python main.py --mode export-renpy
  
  # 游玩游戏
  python main.py --mode play

环境变量:
  OPENAI_API_KEY     OpenAI API 密钥（用于 GPT 和图像生成）
  OPENAI_BASE_URL    OpenAI API 基础 URL（可选）
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['design', 'script', 'render', 'play', 'export-renpy'],
        default='play',
        help='运行模式: \n  design=仅生成大纲设定\n  script=仅根据大纲生成文本剧本\n  render=根据剧本渲染图片素材\n  play=游玩\n  export-renpy=导出 Ren\'Py 项目'
    )
    
    parser.add_argument('--character-count', type=int, default=DesignerConfig.DEFAULT_CHARACTER_COUNT, help='角色数量')
    parser.add_argument('--requirements-file', help='包含游戏构想的文本文件路径（会覆盖 input.yaml 中的 requirements.file_path）')
    parser.add_argument('--input-file', help='统一输入配置文件路径（YAML）')
    
    parser.add_argument('--openai-key', help='OpenAI API Key (覆盖环境变量)')
    parser.add_argument('--openai-base-url', help='OpenAI API Base URL (覆盖环境变量)')
    parser.add_argument('--renpy-out-dir', default='renpy_export/game', help='Ren\'Py game 目录输出路径')
    parser.add_argument('--renpy-no-copy-assets', action='store_true', help='导出 Ren\'Py 时不复制 images 资源')
    
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    # 根据模式执行
    try:
        if args.mode == 'design':
            design_game_flow(args)
        elif args.mode == 'script':
            script_game_flow(args)
        elif args.mode == 'render':
            render_game_flow(args)
        elif args.mode == 'play':
            play_game_flow()
        elif args.mode == 'export-renpy':
            export_renpy_flow(args)
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ 程序异常: {e}", exc_info=True)
        print(f"\n❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
