import os
import logging
import base64
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import requests
from PIL import Image, ImageOps

from .config import APIConfig, ArtistConfig, PathConfig

logger = logging.getLogger(__name__)


class ArtistAgent:
    """美术 Agent - 角色立绘生成器（支持 OpenAI DALL-E 和 Google Imagen）"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化美术 Agent
        
        Args:
            api_key: API Key
            base_url: API Base URL
        """
        self.provider = APIConfig.IMAGE_PROVIDER.lower()
        self.api_key = api_key
        self.base_url = base_url
        self.config = ArtistConfig
        self.client = None
        self.available = False
        
        self._initialize_client()
        
    def _initialize_client(self):
        """初始化图像生成客户端"""
        if self.provider == "openai":
            from openai import OpenAI
            self.api_key = self.api_key or APIConfig.OPENAI_API_KEY
            self.base_url = self.base_url or APIConfig.OPENAI_BASE_URL
            
            if not self.api_key:
                logger.warning("⚠️ OpenAI API Key 未配置！图像生成功能将不可用")
            else:
                try:
                    self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                    self.available = True
                    logger.info("✅ 美术 Agent 初始化成功 (OpenAI DALL-E)")
                except Exception as e:
                    logger.error(f"❌ 美术 Agent 初始化失败: {e}")
                    
        elif self.provider == "google":
            try:
                from google import genai
                self.api_key = self.api_key or APIConfig.GOOGLE_API_KEY
                self.base_url = self.base_url or APIConfig.GOOGLE_BASE_URL
                
                if not self.api_key:
                    logger.warning("⚠️ Google API Key 未配置！图像生成功能将不可用")
                else:
                    client_kwargs = {"api_key": self.api_key}
                    if self.base_url:
                        # 适配自定义 endpoint
                        client_kwargs["http_options"] = {"base_url": self.base_url}
                    
                    self.client = genai.Client(**client_kwargs)
                    self.available = True
                    logger.info("✅ 美术 Agent 初始化成功 (Google Imagen)")
            except ImportError:
                logger.error("❌ google-genai 未安装")
            except Exception as e:
                logger.error(f"❌ 美术 Agent 初始化失败: {e}")
        else:
            logger.error(f"❌ 不支持的图像生成提供商: {self.provider}")
    
    def generate_character_images(
        self,
        character: Dict[str, Any],
        expressions: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        为单个角色生成多表情立绘
        
        Args:
            character: 角色设定字典
            expressions: 需要生成的表情列表，如果为None则使用默认列表
            
        Returns:
            字典，键为表情名，值为图像文件路径
        """
        character_name = character.get('name', 'unknown')
        character_id = character.get('id', character_name)
        
        # 使用传入的表情列表或默认列表
        expressions = expressions or self.config.STANDARD_EXPRESSIONS
        
        logger.info(f"🎨 为角色 [{character_name}] 生成立绘，表情: {expressions}")
        
        # 创建角色专属目录
        character_dir = os.path.join(PathConfig.CHARACTERS_DIR, character_id)
        os.makedirs(character_dir, exist_ok=True)
        
        image_paths = {}
        
        # 尝试找到 neutral 表情作为参考图
        reference_image_path = None
        
        # 确保 neutral 最先生成 (如果它在列表中)
        sorted_expressions = sorted(expressions, key=lambda x: 0 if x == 'neutral' else 1)
        
        for expression in sorted_expressions:
            try:
                # 检查图片是否已存在
                filename = f"{expression}.png"
                expected_image_path = os.path.join(character_dir, filename)
                
                if os.path.exists(expected_image_path):
                    logger.info(f"   ✅ [{expression}] 立绘已存在，跳过生成")
                    image_paths[expression] = expected_image_path
                    if expression == 'neutral':
                        reference_image_path = expected_image_path
                    continue
                
                # 生成图像
                image_path = self._generate_single_image(
                    character=character,
                    expression=expression,
                    output_dir=character_dir,
                    reference_image_path=reference_image_path
                )
                
                if image_path:
                    image_paths[expression] = image_path
                    logger.info(f"   ✅ [{expression}] 立绘生成成功")
                    if expression == 'neutral':
                        reference_image_path = image_path
                else:
                    logger.warning(f"   ⚠️  [{expression}] 立绘生成失败")
                    
            except Exception as e:
                logger.error(f"   ❌ [{expression}] 立绘生成出错: {e}")
        
        # 保存图像清单
        self._save_image_manifest(character_id, image_paths)
        
        logger.info(f"✅ 角色 [{character_name}] 立绘生成完成，共 {len(image_paths)} 张")
        
        return image_paths

    def _build_prompt(self, character: Dict[str, Any], expression_type: str, description: Optional[str] = None) -> str:
        """构建图像生成提示词"""
        appearance = character.get('appearance', 'anime style character')
        
        if expression_type == "custom" and description:
            # 自定义描述模式
            return f"Anime character, {appearance}. Action/Expression: {description}. High quality, detailed, white background."
        else:
            # 标准表情模式
            return self.config.IMAGE_PROMPT_TEMPLATE.format(
                appearance=appearance,
                expression=expression_type
            )

    def _call_image_api(self, prompt: str, reference_image_path: Optional[str] = None) -> Optional[bytes]:
        """调用图像生成 API"""
        if self.provider == "openai":
            response = self.client.images.generate(
                model=APIConfig.IMAGE_MODEL,
                prompt=prompt,
                size=self.config.IMAGE_SIZE,
                quality=self.config.IMAGE_QUALITY,
                style=self.config.IMAGE_STYLE,
                n=1
            )
            image_url = response.data[0].url
            resp = requests.get(image_url)
            return resp.content if resp.status_code == 200 else None
            
        elif self.provider == "google":
            contents = [prompt]
            if reference_image_path:
                try:
                    ref_img = Image.open(reference_image_path)
                    contents.append(ref_img)
                    contents[0] = f"Generate a variation of the character in the attached image: {prompt}"
                except Exception as e:
                    logger.warning(f"   ⚠️ 无法加载参考图: {e}")
            
            response = self.client.models.generate_content(
                model=APIConfig.IMAGE_MODEL,
                contents=contents
            )
            
            if hasattr(response, 'parts'):
                for part in response.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        return part.inline_data.data # 假设是 bytes
                    # google-genai SDK 可能返回 PIL Image 或其他格式，这里简化处理
                    # 如果 part.as_image() 返回 PIL Image
                    try:
                        img = part.as_image()
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format='PNG')
                        return buf.getvalue()
                    except:
                        pass
            return None
        return None

    def _save_image(self, image_data: bytes, filepath: Path) -> None:
        """保存图像数据到文件"""
        with open(filepath, 'wb') as f:
            f.write(image_data)
        logger.info(f"   ✅ 图像保存成功: {filepath}")

    def _remove_background(self, filepath: Path) -> None:
        """移除背景 (占位符)"""
        # TODO: 集成 rembg
        pass

    def _generate_single_image(
        self,
        character: Dict[str, Any],
        expression: str,
        output_dir: str,
        reference_image_path: Optional[str] = None
    ) -> Optional[str]:
        """生成单张立绘"""
        if not self.available: return None
        
        try:
            name = character.get('name', 'Character')
            prompt = self._build_prompt(character, expression)
            
            logger.info(f"   🎨 为 [{name}] 生成立绘 ({expression})...")
            
            image_data = self._call_image_api(prompt, reference_image_path if expression != 'neutral' else None)
            
            if image_data:
                filename = f"{expression}.png"
                filepath = Path(output_dir) / filename
                self._save_image(image_data, filepath)
                return str(filepath)
            return None
                
        except Exception as e:
            logger.error(f"❌ 图像生成失败: {e}")
            return None
    
    def _save_image_manifest(self, character_id: str, image_paths: Dict[str, str]) -> None:
        """
        保存图像清单文件
        
        Args:
            character_id: 角色ID
            image_paths: 图像路径字典
        """
        try:
            manifest_file = os.path.join(
                PathConfig.CHARACTERS_DIR,
                character_id,
                "manifest.json"
            )
            
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(image_paths, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"💾 图像清单已保存: {manifest_file}")
            
        except Exception as e:
            logger.error(f"❌ 保存图像清单失败: {e}")
    
    @staticmethod
    def load_character_images(character_id: str) -> Optional[Dict[str, str]]:
        """
        加载角色的图像清单
        
        Args:
            character_id: 角色ID
            
        Returns:
            图像路径字典，失败返回 None
        """
        try:
            manifest_file = os.path.join(
                PathConfig.CHARACTERS_DIR,
                character_id,
                "manifest.json"
            )
            
            with open(manifest_file, 'r', encoding='utf-8') as f:
                image_paths = json.load(f)
            
            logger.info(f"📖 加载角色图像清单: {character_id} ({len(image_paths)} 张)")
            return image_paths
            
        except FileNotFoundError:
            logger.warning(f"⚠️  图像清单不存在: {character_id}")
            return None
        except Exception as e:
            logger.error(f"❌ 加载图像清单失败: {e}")
            return None
    
    def generate_all_characters(self, game_design: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """
        为游戏中的所有角色生成立绘
        
        Args:
            game_design: 游戏设计文档
            
        Returns:
            字典，键为角色ID，值为该角色的图像路径字典
        """
        characters = game_design.get('characters', [])
        logger.info(f"🎨 开始为 {len(characters)} 个角色生成立绘")
        
        all_images = {}
        
        for i, character in enumerate(characters, 1):
            character_id = character.get('id', character.get('name'))
            logger.info(f"\n[{i}/{len(characters)}] 处理角色: {character.get('name')}")
            
            try:
                image_paths = self.generate_character_images(character)
                all_images[character_id] = image_paths
            except Exception as e:
                logger.error(f"❌ 角色 {character_id} 立绘生成失败: {e}")
        
        logger.info(f"\n✅ 所有角色立绘生成完成！")
        logger.info(f"   成功: {len(all_images)}/{len(characters)} 个角色")
        
        return all_images
    
    def generate_background(
        self,
        location: str,
        time_of_day: str = "day",
        atmosphere: str = "peaceful"
    ) -> Optional[str]:
        """
        生成场景背景图
        
        Args:
            location: 场景地点（如"教室"、"公园"等）
            time_of_day: 时间段（如"morning", "afternoon", "evening", "night"）
            atmosphere: 氛围（如"peaceful", "romantic", "tense"等）
            
        Returns:
            背景图片文件路径，失败返回 None
        """
        logger.info(f"🖼️  开始生成场景背景: {location} ({time_of_day})")
        
        # 生成文件名（提前检查）
        import re
        safe_location = re.sub(r'[^\w\s-]', '', location).strip().replace(' ', '_')
        filename = f"{safe_location}_{time_of_day}.png"
        file_path = os.path.join(PathConfig.BACKGROUNDS_DIR, filename)
        
        # 检查背景图是否已存在
        if os.path.exists(file_path):
            logger.info(f"   ✅ 背景图已存在，跳过生成: {file_path}")
            return file_path
        
        if not self.available or not self.client:
            logger.warning("⚠️  图像生成不可用")
            return None
        
        try:
            # 构建背景生成提示词
            prompt = self.config.BACKGROUND_PROMPT_TEMPLATE.format(
                location=location,
                time_of_day=time_of_day,
                atmosphere=atmosphere
            )
            
            logger.info(f"   🎨 生成背景: {location}...")
            logger.debug(f"   提示词: {prompt[:150]}...")
            
            if self.provider == "openai":
                # 调用 DALL-E API
                response = self.client.images.generate(
                    model=APIConfig.IMAGE_MODEL,
                    prompt=prompt,
                    size=self.config.BACKGROUND_SIZE,
                    quality=self.config.BACKGROUND_QUALITY,
                    style=self.config.IMAGE_STYLE,  # 使用与角色相同的风格
                    n=1
                )
                
                # 获取图像 URL
                image_url = response.data[0].url
                
                # 下载图像
                logger.info(f"   ⬇️  下载背景图...")
                import requests
                image_response = requests.get(image_url)
                
                if image_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(image_response.content)
                    logger.info(f"   ✅ 背景图保存成功: {file_path}")
                    return file_path
                else:
                    logger.error(f"   ❌ 背景图下载失败: HTTP {image_response.status_code}")
                    return None

            elif self.provider == "google":
                # 使用 google-genai SDK
                contents = [prompt]
                
                # 生成图像
                response = self.client.models.generate_content(
                    model=APIConfig.IMAGE_MODEL,
                    contents=contents
                )
                
                image_saved = False
                
                if hasattr(response, 'parts'):
                    for part in response.parts:
                        if part.text is not None:
                            logger.warning(f"   ⚠️ API返回文本: {part.text}")
                        
                        # 检查是否有 inline_data (图像数据)
                        if hasattr(part, 'inline_data') and part.inline_data:
                            try:
                                # 使用官方示例中的 as_image()
                                image = part.as_image()
                                image.save(file_path)
                                image_saved = True
                                break
                            except Exception as e:
                                logger.error(f"   ❌ 保存图像失败: {e}")

                if image_saved:
                    logger.info(f"   ✅ 背景图保存成功: {file_path}")
                    return file_path
                else:
                    raise ValueError("Google API 响应中未包含图像数据")
            
            else:
                raise ValueError(f"不支持的图像生成提供商: {self.provider}")
                
        except Exception as e:
            logger.error(f"❌ 背景图生成失败: {e}")
            return None
    
    def generate_all_backgrounds(self, locations: List[str]) -> Dict[str, str]:
        """
        为游戏中的所有场景生成背景图
        
        Args:
            locations: 场景地点列表
            
        Returns:
            字典，键为地点名，值为背景图路径
        """
        logger.info(f"🖼️  开始为 {len(locations)} 个场景生成背景图")
        
        background_images = {}
        
        for i, location in enumerate(locations, 1):
            logger.info(f"\n[{i}/{len(locations)}] 生成背景: {location}")
            
            try:
                # 默认生成白天场景
                bg_path = self.generate_background(
                    location=location,
                    time_of_day="afternoon",
                    atmosphere="peaceful"
                )
                if bg_path:
                    background_images[location] = bg_path
            except Exception as e:
                logger.error(f"❌ 场景 {location} 背景生成失败: {e}")
        
        logger.info(f"\n✅ 所有场景背景生成完成！")
        logger.info(f"   成功: {len(background_images)}/{len(locations)} 个场景")
        
        return background_images
    
    def generate_image_from_description(
        self,
        character: Dict[str, Any],
        description: str,
        filename_suffix: str
    ) -> Optional[str]:
        """
        根据详细描述生成单张立绘
        
        Args:
            character: 角色设定
            description: 详细的视觉描述
            filename_suffix: 文件名后缀 (例如 'scene_1_shy')
            
        Returns:
            生成的图片路径
        """
        if not self.available:
            logger.warning("⚠️ 美术 Agent 不可用，跳过生成")
            return None
            
        character_name = character.get('name', 'unknown')
        character_id = character.get('id', character_name)
        
        # 确保目录存在
        output_dir = PathConfig.CHARACTERS_DIR / character_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 构建 Prompt
        prompt = self._build_prompt(character, "custom", description)
        
        # 文件路径
        filename = f"{character_id}_{filename_suffix}.png"
        filepath = output_dir / filename
        
        # 检查是否已存在
        if filepath.exists():
            logger.info(f"   ⏭️ 图片已存在: {filename}")
            return str(filepath)
            
        logger.info(f"   🎨 正在生成: {filename} (Prompt: {description[:30]}...)")
        
        try:
            image_data = self._call_image_api(prompt)
            if image_data:
                self._save_image(image_data, filepath)
                # 自动移除背景 (如果需要)
                self._remove_background(filepath)
                return str(filepath)
        except Exception as e:
            logger.error(f"❌ 生成图片失败 {filename}: {e}")
            
        return None


# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试美术 Agent
    try:
        artist = ArtistAgent()
        
        # 测试角色
        test_character = {
            "id": "test_char",
            "name": "测试角色",
            "personality": "开朗活泼",
            "appearance": "长发，大眼睛，穿校服",
            "color": [255, 105, 180],
            "required_images": ["neutral", "happy", "shy"]
        }
        
        print("\n" + "="*50)
        print("🎨 开始生成测试角色立绘")
        print("="*50)
        
        images = artist.generate_character_images(test_character)
        
        print(f"\n✅ 生成完成！")
        print(f"   图像数量: {len(images)}")
        for expr, path in images.items():
            print(f"   - {expr}: {path}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
