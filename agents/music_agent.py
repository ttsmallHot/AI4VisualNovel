import logging
import json
import os
import requests
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .config import PathConfig, APIConfig

logger = logging.getLogger(__name__)

class MusicAgent:
    """音乐生成 Agent - 负责生成游戏背景音乐"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化 Music Agent
        
        Args:
            api_key: API Key (如果需要)
            base_url: API Base URL (例如: https://api.suno-proxy.com/v1)
        """
        # 优先使用传入的参数，否则尝试从环境变量读取
        self.api_key = api_key or APIConfig.MUSIC_API_KEY
        self.base_url = base_url or APIConfig.MUSIC_BASE_URL
        
        # 确保输出目录存在
        self.output_dir = PathConfig.AUDIO_DIR / "bgm"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("🎵 音乐 Agent 初始化完成")

    def generate_bgm(self, game_design: Dict[str, Any]) -> Optional[str]:
        """
        根据游戏设计生成背景音乐
        
        Args:
            game_design: 游戏设计文档
            
        Returns:
            生成的音乐文件路径 (str) 或 None
        """
        title = game_design.get('title', 'Game Theme')
        music_style = game_design.get('music_style', 'Anime, Piano, Emotional')
        music_prompt = game_design.get('music_prompt', f"A beautiful theme song for {title}")
        
        logger.info(f"🎵 正在生成背景音乐: {title}")
        logger.info(f"   风格: {music_style}")
        
        # 构造请求参数 (参考用户提供的截图)
        payload = {
            "title": title,
            "tags": music_style,
            "generation_type": "TEXT",
            "prompt": music_prompt,
            "negative_tags": "low quality, noise, distortion",
            "mv": "chirp-v3-5" # 使用较新的模型
        }
        
        # 尝试调用 API
        # 注意：这里假设是一个兼容 OpenAI 格式或者特定的 POST 接口
        # 如果用户说是 "OpenAI 接口"，通常是指 /v1/chat/completions (Suno 插件) 
        # 或者是一个自定义的生成端点。
        # 根据截图参数，这更像是一个直接的生成接口。
        # 我们这里假设它是一个 POST 请求到 base_url/suno/generate (假设路径)
        # 或者直接是 base_url (如果用户给的是完整路径)
        
        # 为了兼容性，我们先尝试直接 POST 到 base_url
        # 如果 base_url 是类似 https://api.example.com/v1，我们可能需要追加路径
        # 这里我们假设 base_url 就是完整的生成端点，或者用户会在 .env 里配置完整的
        
        target_url = self.base_url
        if not target_url.endswith('/generate') and 'suno' not in target_url:
             # 简单的启发式：如果 URL 看起来像根路径，尝试追加常见的生成路径
             # 但最稳妥的是让用户提供完整的 Endpoint
             pass

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            # 1. 发起生成请求
            logger.info("   🚀 发送生成请求...")
            response = requests.post(target_url, json=payload, headers=headers, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"❌ 音乐生成请求失败: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            # 解析返回结果
            # 假设返回格式包含 audio_url 或类似字段
            # 不同的代理服务返回格式可能不同，这里需要根据实际情况调整
            # 常见的 Suno API 返回是一个列表，包含生成的 clip 信息
            
            audio_url = None
            
            # 尝试适配常见的返回格式
            if isinstance(data, list) and len(data) > 0:
                audio_url = data[0].get('audio_url') or data[0].get('url')
            elif isinstance(data, dict):
                audio_url = data.get('audio_url') or data.get('url')
                # 如果是异步任务，可能返回 task_id
                if not audio_url and 'id' in data:
                    task_id = data['id']
                    logger.info(f"   ⏳ 任务已提交 (ID: {task_id})，等待生成...")
                    audio_url = self._wait_for_generation(target_url, task_id, headers)

            if not audio_url:
                logger.error(f"❌ 无法从响应中获取音频 URL: {data}")
                return None
                
            # 2. 下载音频
            logger.info(f"   📥 正在下载音乐: {audio_url}")
            file_name = "theme.mp3" # 统一命名为 theme.mp3
            file_path = self.output_dir / file_name
            
            with requests.get(audio_url, stream=True) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
            logger.info(f"✅ 背景音乐已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 音乐生成异常: {e}")
            return None

    def _wait_for_generation(self, base_url: str, task_id: str, headers: Dict) -> Optional[str]:
        """轮询等待异步生成任务完成"""
        # 这是一个通用的轮询逻辑，具体 URL 结构可能需要调整
        # 假设查询 URL 是 base_url/feed 或 base_url/{id}
        
        # 这里的逻辑比较依赖具体的 API 实现
        # 暂时先留空，假设是同步返回或者 URL 直接可用
        # 如果是异步，通常需要另一个 fetch 接口
        return None
