"""
AI Galgame - Main Entry Point
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AI 驱动的自动化 Galgame 生成和运行系统

主要功能:
1. 使用制作人 Agent (GPT-4) 生成游戏设计
2. 使用美术 Agent (Gemini) 生成角色立绘
3. 使用编剧 Agent (GPT-4) 生成剧情
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
from agents.config import ProducerConfig, PathConfig


def setup_logging(level=logging.INFO):
    """配置日志系统"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.FileHandler(os.path.join(PathConfig.LOG_DIR, 'ai_galgame.log'), encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def create_game_flow(args):
    """创建新游戏流程"""
    print("\n" + "="*70)
    print("🎬 AI Galgame - 游戏创建模式")
    print("="*70)
    
    workflow = WorkflowController()
    
    # 初始化 Agents（统一使用 OpenAI）
    workflow.initialize_agents(
        openai_api_key=args.openai_key,
        openai_base_url=args.openai_base_url
    )
    
    # 获取用户自定义要求
    print("\n请输入您对故事的特别要求（例如：'主角是转校生，喜欢音乐'）：")
    print("（直接回车则由 AI 自由发挥）")
    user_requirements = input("> ").strip()
    
    # 创建游戏
    game_design = workflow.create_new_game(
        game_type=args.game_type,
        game_style=args.game_style,
        character_count=args.character_count,
        requirements=user_requirements
    )
    
    print("\n" + "="*70)
    print("🎉 游戏创建完成！")
    print("="*70)
    print(f"\n📖 游戏标题: {game_design['title']}")
    print(f"📝 背景故事:\n{game_design['background'][:200]}...")
    print(f"\n👥 可攻略角色:")
    for char in game_design['characters']:
        print(f"   - {char['name']}: {char['personality']}")
    
    print(f"\n💾 游戏数据已保存到: {PathConfig.DATA_DIR}")
    print(f"🎨 立绘图像保存在: {PathConfig.CHARACTERS_DIR}")
    
    print("\n提示: 运行 'python ai_galgame.py --mode play' 开始游玩")


def play_game_flow():
    """游玩游戏流程"""
    print("\n" + "="*70)
    print("🎮 AI Galgame - 游戏运行模式")
    print("="*70)
    
    # 检查游戏是否存在
    if not os.path.exists(PathConfig.GAME_DESIGN_FILE):
        print("\n❌ 未找到游戏数据!")
        print("   请先运行: python ai_galgame.py --mode create")
        return
    
    # 启动游戏 UI
    print("\n🚀 启动游戏...")
    
    # 导入并启动游戏
    from game_engine.manager import GameManager
    game = GameManager()
    game.run()


def generate_next_week_flow(args):
    """生成下一周剧情流程"""
    print("\n" + "="*70)
    print("✍️  AI Galgame - 剧情生成模式")
    print("="*70)
    
    workflow = WorkflowController()
    workflow.initialize_agents(
        openai_api_key=args.openai_key,
        openai_base_url=args.openai_base_url
    )
    
    # 加载游戏
    if not workflow.load_existing_game():
        print("\n❌ 未找到游戏数据!")
        return
    
    # 生成下一周剧情
    print(f"\n📝 正在生成第 {workflow.current_week + 1} 周剧情...")
    story = workflow.generate_next_week_story()
    
    print(f"\n✅ 剧情生成完成!")
    print(f"   长度: {len(story)} 字符")
    print(f"\n预览:")
    print(story[:300] + "...")
    
    print(f"\n💾 剧情已追加到: {ProducerConfig.STORY_FILE}")


def status_flow():
    """显示游戏状态"""
    print("\n" + "="*70)
    print("📊 AI Galgame - 游戏状态")
    print("="*70)
    
    workflow = WorkflowController()
    
    if not workflow.load_existing_game():
        print("\n❌ 未找到游戏数据!")
        return
    
    status = workflow.get_game_status()
    
    print(f"\n📖 游戏标题: {status['title']}")
    print(f"📅 当前进度: 第 {status['current_week']}/{status['total_weeks']} 周")
    
    print(f"\n👥 角色状态:")
    for char in status['characters']:
        print(f"   - {char['name']}: 好感度 {char['affection']}/100 ({char['relationship']})")
    
    if status['ending']:
        print(f"\n🎊 已达成结局: {status['ending']}")
    else:
        print(f"\n💪 继续努力，还未达成结局!")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AI Galgame - AI 驱动的自动化 Galgame 生成和运行系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 创建新游戏
  python ai_galgame.py --mode create --game-type 校园恋爱 --character-count 3
  
  # 游玩游戏
  python ai_galgame.py --mode play
  
  # 生成下一周剧情
  python ai_galgame.py --mode generate
  
  # 查看游戏状态
  python ai_galgame.py --mode status

环境变量:
  OPENAI_API_KEY     OpenAI API 密钥（用于 GPT-4 和 DALL-E）
  OPENAI_BASE_URL    OpenAI API 基础 URL（可选）
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['create', 'play', 'generate', 'status'],
        default='play',
        help='运行模式: create=创建游戏, play=游玩, generate=生成剧情, status=查看状态'
    )
    
    parser.add_argument('--game-type', default='校园恋爱', help='游戏类型')
    parser.add_argument('--game-style', default='轻松温馨', help='游戏风格')
    parser.add_argument('--character-count', type=int, default=ProducerConfig.DEFAULT_CHARACTER_COUNT, help='角色数量')
    
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
        elif args.mode == 'play':
            play_game_flow()
        elif args.mode == 'generate':
            generate_next_week_flow(args)
        elif args.mode == 'status':
            status_flow()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ 程序异常: {e}", exc_info=True)
        print(f"\n❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
