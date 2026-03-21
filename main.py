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
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from workflow import WorkflowController
from agents.config import ProducerConfig, DesignerConfig, PathConfig


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


def create_game_flow(args):
    """创建新游戏流程"""
    print("\n" + "="*70)
    print("🎬 AI Visual Novel - 游戏创建模式")
    print("="*70)
    
    workflow = WorkflowController()
    
    # 初始化 Agents（统一使用 OpenAI）
    workflow.initialize_agents(
        openai_api_key=args.openai_key,
        openai_base_url=args.openai_base_url
    )
    
    # 获取用户自定义要求
    user_requirements = ""
    if args.requirements_file:
        if os.path.exists(args.requirements_file):
            print(f"\n📖 正在从文件读取游戏构想: {args.requirements_file}")
            try:
                with open(args.requirements_file, 'r', encoding='utf-8') as f:
                    user_requirements = f.read().strip()
                    print(f"✅ 已加载构想: {user_requirements[:50]}...")
            except Exception as e:
                print(f"⚠️ 读取文件失败: {e}，将使用空需求继续。")
        else:
            print(f"⚠️ 找不到需求文件: {args.requirements_file}，将使用空需求继续。")
    else:
        print("\n💡 未提供需求文件，将由 AI 自由发挥内容。")
    
    # 创建游戏 (这里为了兼容老命令，连放三个阶段跑完)
    game_design = workflow.run_design_phase(
        character_count=args.character_count,
        requirements=user_requirements
    )
    workflow.run_script_phase()
    workflow.run_render_phase()
    
    print("\n" + "="*70)
    print("🎉 游戏创建完成！")
    print("="*70)
    print(f"\n📖 游戏标题: {game_design['title']}")
    print(f"📝 背景故事:\n{game_design['background'][:200]}...")
    print(f"\n👥 游戏角色:")
    for char in game_design['characters']:
        print(f"   - {char['name']}: {char['personality']}")
    
    print(f"\n💾 游戏数据已保存到: {PathConfig.DATA_DIR}")
    print(f"🎨 立绘图像保存在: {PathConfig.CHARACTERS_DIR}")
    
    print(f"\n提示: 运行 'python main.py --mode play' 开始游玩")


def play_game_flow():
    """游玩游戏流程"""
    print("\n" + "="*70)
    print("🎮 AI Visual Novel - 游戏运行模式")
    print("="*70)
    
    # 检查游戏是否存在
    if not os.path.exists(PathConfig.GAME_DESIGN_FILE):
        print("\n❌ 未找到游戏数据!")
        print("   请先运行: python main.py --mode create")
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
    
    user_requirements = ""
    if args.requirements_file and os.path.exists(args.requirements_file):
        with open(args.requirements_file, 'r', encoding='utf-8') as f:
            user_requirements = f.read().strip()
            
    workflow.run_design_phase(
        character_count=args.character_count,
        requirements=user_requirements
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

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AI Visual Novel - AI 驱动的自动化 Visual Novel 生成和运行系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 创建新游戏
  python main.py --mode create --requirements-file data/story.txt
  
  # 游玩游戏
  python main.py --mode play

环境变量:
  OPENAI_API_KEY     OpenAI API 密钥（用于 GPT 和图像生成）
  OPENAI_BASE_URL    OpenAI API 基础 URL（可选）
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['create', 'design', 'script', 'render', 'play'],
        default='play',
        help='运行模式: \n  create=一键跑完所有流程(不推荐)\n  design=仅生成大纲设定\n  script=仅根据大纲生成文本剧本\n  render=根据剧本渲染图片素材\n  play=游玩'
    )
    
    parser.add_argument('--character-count', type=int, default=DesignerConfig.DEFAULT_CHARACTER_COUNT, help='角色数量')
    parser.add_argument('--requirements-file', help='包含游戏构想的文本文件路径')
    
    parser.add_argument('--openai-key', help='OpenAI API Key (覆盖环境变量)')
    parser.add_argument('--openai-base-url', help='OpenAI API Base URL (覆盖环境变量)')
    
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    # 根据模式执行
    try:
        if args.mode == 'create':
            create_game_flow(args)
        elif args.mode == 'design':
            design_game_flow(args)
        elif args.mode == 'script':
            script_game_flow(args)
        elif args.mode == 'render':
            render_game_flow(args)
        elif args.mode == 'play':
            play_game_flow()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ 程序异常: {e}", exc_info=True)
        print(f"\n❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
