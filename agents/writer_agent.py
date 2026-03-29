"""
Writer Agent
~~~~~~~~~~~~
编剧 Agent - 负责生成每周详细剧情
使用 GPT-4 根据游戏设计和角色状态创作对话和事件
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent

from .config import WriterConfig, PathConfig
from .utils import FileHelper
from .schemas import PLOT_SEGMENTS_SCHEMA

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """编剧 Agent - 剧情生成器"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化编剧 Agent
        
        Args:
            api_key: API Key
            base_url: API Base URL
        """
        super().__init__(
            name="Writer",
            role="编剧",
            api_key=api_key,
            base_url=base_url
        )
        self.config = WriterConfig
        
        logger.info("✅ 编剧 Agent 初始化成功")
    
    def split_node_into_plots(
        self,
        node_summary: str,
        long_term_memory: str,
        available_scenes: List[str] = [],
        available_characters: List[Dict[str, Any]] = [],
        segment_count: int = 3
    ) -> List[Dict[str, Any]]:
        """将节点概要切分为剧情片段"""
        logger.info(f"✂️  正在切分剧情片段 (目标片段数: {segment_count})...")
        
        # 根据 segment_count 生成不同的指令
        if segment_count == 1:
            split_instruction = "保持为一个完整的场景，不要切分。"
        else:
            split_instruction = f"每个片段应该是一个小的场景或事件，具有明确的冲突或行动。"
        
        scenes_str = ", ".join(available_scenes) if available_scenes else "未指定，请根据剧情自由选择"
        # 构建角色的详细信息
        characters_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in available_characters
        ]) if available_characters else "未指定角色"

        prompt = self.config.PLOT_SPLIT_PROMPT.format(
            segment_count=segment_count,
            split_instruction=split_instruction,
            node_summary=node_summary,
            previous_story_summary=long_term_memory,
            available_scenes=scenes_str,
            available_characters=characters_info
        )
        try:
            # 使用专门的 System Prompt 以确保 JSON 格式
            system_prompt = "你是一个剧情结构分析助手。你的任务是将剧情概要切分为结构化的片段，并严格输出 JSON 格式。"

            result = self.call_json_with_schema(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                schema=PLOT_SEGMENTS_SCHEMA,
                object_name="plot_segments",
                temperature=0.7
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"❌ 切分剧情失败: {e}")
            return []

    def synthesize_script(
        self,
        plot_performances: List[Dict[str, Any]],
        choices: List[Dict[str, Any]] = [],
        story_context: str = "",
        available_scenes: List[str] = [],
        available_characters: List[Dict[str, Any]] = []
    ) -> str:
        """将演员表演整合成剧本"""
        logger.info("🧩 正在整合剧本 (基于结构化数据)...")
        
        # 将结构化数据转换为 JSON 字符串供 LLM 阅读
        performances_json = json.dumps(plot_performances, ensure_ascii=False, indent=2)
        choices_json = json.dumps(choices, ensure_ascii=False, indent=2)
        scenes_str = ", ".join(available_scenes) if available_scenes else "未指定"
        # 构建角色的详细信息
        characters_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in available_characters
        ]) if available_characters else "未指定"
        
        prompt = self.config.PLOT_SYNTHESIS_PROMPT.format(
            plot_performances=performances_json,
            choices=choices_json,
            story_context=story_context,
            available_scenes=scenes_str,
            available_characters=characters_info
        )

        try:
            script = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self.config.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return script
        except Exception as e:
            logger.error(f"❌ 整合剧本失败: {e}")
            return str(plot_performances)

    def decide_next_speaker(
        self,
        plot_summary: str,
        characters: List[Dict[str, Any]],
        story_context: str
    ) -> tuple[str, str]:
        """
        决定下一位发言的角色及剧情指导
        
        Returns:
            (角色名, 剧情指导) 或 ("STOP", "")
        """
        # 构建角色的详细信息
        characters_info = "\n".join([
            f"- {char.get('name', 'Unknown')}（{char.get('gender', '')},{char.get('personality', '')}）：{char.get('appearance', '')}。背景：{char.get('background', '')[:80]}..."
            for char in characters
        ])
        
        prompt = self.config.NEXT_SPEAKER_PROMPT.format(
            plot_summary=plot_summary,
            characters=characters_info,
            story_context=story_context
        )
        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个辅助剧情生成的导演助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3 # 低温度以获得更确定的结果
            )
            response = response.strip()
            
            # 解析响应
            import re
            
            # 提取 <character> 标签
            char_match = re.search(r'<character>(.+?)</character>', response, re.DOTALL)
            if not char_match:
                logger.warning("⚠️ 导演返回格式错误，未找到 <character> 标签")
                return "STOP", ""
            
            speaker = char_match.group(1).strip()
            
            # 检查是否是 STOP
            if speaker.upper() == "STOP":
                return "STOP", ""
            
            # 提取 <advice> 标签
            advice_match = re.search(r'<advice>(.+?)</advice>', response, re.DOTALL)
            guidance = advice_match.group(1).strip() if advice_match else ""
            
            logger.debug(f"🎬 解析结果: 角色={speaker}, 指导={guidance}")
            return speaker, guidance
            
        except Exception as e:
            logger.error(f"❌ 决定下一位发言者失败: {e}")
            return "STOP", ""
    
    def append_story(self, story_text: str) -> None:
        """
        将新剧情追加到story.txt
        
        Args:
            story_text: 要追加的剧情文本
        """
        if not FileHelper.safe_append_text(PathConfig.STORY_FILE, story_text):
            raise Exception("追加剧情失败")
    
    @staticmethod
    def load_story() -> str:
        """
        加载完整的story.txt
        
        Returns:
            剧情文本，文件不存在返回空字符串
        """
        try:
            with open(PathConfig.STORY_FILE, 'r', encoding='utf-8') as f:
                story = f.read()
            
            logger.info(f"📖 剧情文件已加载: {len(story)} 字符")
            return story
            
        except FileNotFoundError:
            logger.warning(f"⚠️  剧情文件不存在，将创建新文件")
            return ""
        except Exception as e:
            logger.error(f"❌ 加载剧情文件失败: {e}")
            return ""
    

    
    def parse_story_for_ui(self, story_text: str) -> List[Dict[str, Any]]:
        """
        解析剧情文本为UI可用的数据结构
        
        Args:
            story_text: 原始剧情文本
            
        Returns:
            剧情片段列表，每个片段包含对话、图像、选项等信息
        """
        logger.info("📝 解析剧情文本...")
        
        segments = []
        current_location = None
        current_time = None
        
        lines = story_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 解析场景标题 (## 地点 或 ## 地点 - 时间)
            scene_match = re.match(r'##\s*(.+)', line)
            
            if scene_match:
                content = scene_match.group(1).strip()
                if '-' in content:
                    parts = content.split('-', 1)
                    new_location = parts[0].strip()
                    new_time = parts[1].strip()
                else:
                    new_location = content
                    new_time = "Day" # 默认时间
                
                # 如果场景变化，添加场景切换标记
                if new_location != current_location:
                    segments.append({
                        "type": "scene",
                        "location": new_location,
                        "time": new_time
                    })
                
                current_time = new_time
                current_location = new_location
                continue
            
            # 解析图像标注 <image id="角色">表情</image>
            image_match = re.match(r'<image\s+id="([^"]+)">([^<]+)</image>', line)
            if image_match:
                character = image_match.group(1).strip()
                expression = image_match.group(2).strip()
                
                segments.append({
                    "type": "image",
                    "character": character,
                    "expression": expression,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析对话 (角色名: "对话内容")
            dialogue_match = re.match(r'([^:]+):\s*"?(.+?)"?$', line)
            if dialogue_match:
                speaker = dialogue_match.group(1).strip()
                text = dialogue_match.group(2).strip()
                segments.append({
                    "type": "dialogue",
                    "speaker": speaker if speaker != "NARRATOR" else None,
                    "text": text,
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项 ([CHOICE])
            if line == '[CHOICE]':
                segments.append({
                    "type": "choice_start",
                    "location": current_location,
                    "time": current_time
                })
                continue
            
            # 解析选项内容 (选项1: "文字" → [效果])
            choice_match = re.match(r'选项(\d+):\s*"(.+?)"\s*→\s*\[(.+?)\]', line)
            if choice_match:
                choice_num = int(choice_match.group(1))
                choice_text = choice_match.group(2).strip()
                effects_str = choice_match.group(3).strip()
                
                # 解析效果
                effects = self._parse_choice_effects(effects_str)
                
                segments.append({
                    "type": "choice_option",
                    "number": choice_num,
                    "text": choice_text,
                    "effects": effects
                })
                continue
        
        logger.info(f"✅ 解析完成: {len(segments)} 个片段")
        return segments
    
    def summarize_story(self, story_content: str) -> str:
        """
        生成剧情摘要
        
        Args:
            story_content: 剧情内容
            
        Returns:
            剧情摘要
        """
        logger.info("📝 生成剧情摘要...")
        
        try:
            prompt = self.config.SUMMARY_PROMPT.format(story_content=story_content)
            
            summary = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一位擅长总结故事的助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            )
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"❌ 摘要生成失败: {str(e)}")
            return story_content[-500:]  # 失败时回退到截取最后一段
