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
            base_url: API Base URL (例如:
        """
        # 优先使用传入的参数，否则尝试从环境变量读取
        self.api_key = api_key or APIConfig.MUSIC_API_KEY
        self.base_url = base_url or APIConfig.MUSIC_BASE_URL
        
        # 确保输出目录存在
        self.output_dir = Path(PathConfig.BGM_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("🎵 音乐 Agent 初始化完成")

    def generate_bgm(self, game_design: Dict[str, Any]) -> Optional[str]:
        """
        根据游戏设计生成背景音乐
        """
        title = game_design.get('title', 'Game Theme')
        music_style = game_design.get('music_style', 'Anime, Piano, Emotional')
        music_prompt = game_design.get('music_prompt', f"A beautiful theme song for {title}")
        
        # 检查是否已存在
        file_name = "theme.mp3"
        file_path = self.output_dir / file_name
        if file_path.exists():
            logger.info(f"✅ 背景音乐已存在，跳过生成: {file_path}")
            return str(file_path)

        logger.info(f"🎵 正在生成背景音乐: {title}")
        logger.info(f"   风格: {music_style}")
        
        # 构造请求参数
        # 参考 music_generator.py 的逻辑
        # tags: 对应 music_style
        # prompt: 对应 music_prompt (虽然 music_generator.py 里 prompt 是 "a"，但这里我们用 music_prompt 填充 tags 可能会更好，或者直接用 music_style)
        # 实际上 music_generator.py 里 tags 是 "Pure music, light music..."，prompt 是 "a"
        # 我们这里将 music_style 和 music_prompt 组合进 tags，或者只用 music_style
        
        # 组合 tags
        tags = f"Pure music, light music, game, galgame, {music_style}"
        
        payload = {
            "prompt": "", 
            "tags": tags,
            "mv": APIConfig.MUSIC_MODEL,
            "title": title,
            "make_instrumental": True
        }
        
        # 构造 API URL
        # 提交接口: /suno/submit/music
        base_url_clean = self.base_url.rstrip('/')
        # 如果 base_url 已经包含了 /suno/submit/music，则需要处理，但通常 base_url 是域名
        # 假设 base_url 是 https://api.vectorengine.ai
        submit_url = f"{base_url_clean}/suno/submit/music"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            # 1. 发起生成请求
            logger.info(f"   🚀 发送生成请求到: {submit_url}")
            response = requests.post(submit_url, json=payload, headers=headers, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"❌ 音乐生成请求失败: {response.status_code} - {response.text}")
                return None
            
            try:
                resp_json = response.json()
                # music_generator.py: music_id = json.loads(response.text)["data"]
                # 假设返回结构是 {"code": 200, "data": "music_id_string", ...}
                music_id = resp_json.get("data")
                if not music_id:
                     logger.error(f"❌ 无法获取 music_id: {resp_json}")
                     return None
            except json.JSONDecodeError:
                logger.error(f"❌ 响应不是有效的 JSON 格式: {response.text[:200]}...")
                return None
                
            logger.info(f"   ⏳ 任务已提交 (ID: {music_id})，等待生成...")
            
            # 2. 轮询等待生成
            fetch_url = f"{base_url_clean}/suno/fetch/{music_id}"
            audio_url = self._wait_for_generation(fetch_url, headers)

            if not audio_url:
                logger.error(f"❌ 音乐生成超时或失败")
                return None
                
            # 3. 下载音频
            logger.info(f"   📥 正在下载音乐: {audio_url}")
            file_name = "theme.mp3"
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

    def _wait_for_generation(self, fetch_url: str, headers: Dict) -> Optional[str]:
        """轮询等待异步生成任务完成"""
        max_retries = 60 # 10分钟超时
        for _ in range(max_retries):
            try:
                response = requests.get(fetch_url, headers=headers, timeout=30)
                if response.status_code != 200:
                    logger.warning(f"   ⚠️ 轮询请求失败: {response.status_code}")
                    time.sleep(10)
                    continue
                
                data = response.json()
                # music_generator.py: if response_data['data']["status"] == 'SUCCESS':
                # 注意：这里假设 data['data'] 是一个字典，包含 status
                # 结构可能是 {"code": 200, "data": {"status": "SUCCESS", "data": [...]}}
                
                inner_data = data.get("data", {})
                status = inner_data.get("status")
                
                if status == 'SUCCESS':
                    # 获取音频 URL
                    # music_generator.py: audio_urls = [item["audio_url"] for item in response_data["data"]["data"]]
                    clips = inner_data.get("data", [])
                    if clips and len(clips) > 0:
                        return clips[0].get("audio_url")
                elif status == 'FAILED':
                    logger.error(f"❌ 生成任务失败: {inner_data.get('error_message')}")
                    return None
                
                # 继续等待
                logger.info("   ⏳ 生成中...")
                time.sleep(10)
                
            except Exception as e:
                logger.warning(f"   ⚠️ 轮询异常: {e}")
                time.sleep(10)
        
        return None
