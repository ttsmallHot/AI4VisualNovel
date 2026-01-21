import os
import logging
import base64
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
from PIL import Image, ImageOps
from rembg import remove, new_session

from .config import APIConfig, ArtistConfig, PathConfig

logger = logging.getLogger(__name__)


class ArtistAgent:
    """美术 Agent - 角色立绘生成器（支持 OpenAI GPT Image 和 Google Imagen）"""
    
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
                    logger.info("✅ 美术 Agent 初始化成功")
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
        expressions: Optional[List[str]] = None,
        feedback: Optional[str] = None,
        reference_image_paths: Optional[List[str]] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None
    ) -> Dict[str, str]:
        """
        为单个角色生成多表情立绘
        
        Args:
            character: 角色设定字典
            expressions: 需要生成的表情列表，如果为None则使用默认列表
            feedback: 针对本次生成的修改建议 (会附加到 Prompt 中)
            reference_image_paths: 强制指定的参考图路径列表 (可选)
            story_background: 故事背景描述
            art_style: 美术风格描述
            
        Returns:
            字典，键为表情名，值为图像文件路径
        """
        character_name = character.get('name', 'unknown')
        character_id = character.get('id', character_name)
        
        # 使用传入的表情列表或默认列表
        expressions = expressions or self.config.STANDARD_EXPRESSIONS
        
        logger.info(f"🎨 为角色 [{character_name}] 生成立绘，表情: {expressions}")
        if feedback:
            logger.info(f"   💡 包含修改建议: {feedback}")
        if art_style:
            logger.info(f"   🎨 美术风格: {art_style}")
        
        # 创建角色专属目录
        character_dir = os.path.join(PathConfig.CHARACTERS_DIR, character_id)
        os.makedirs(character_dir, exist_ok=True)
        
        image_paths = {}
        
        # 如果未指定参考图，尝试自动查找 neutral 表情
        if not reference_image_paths:
            neutral_path = os.path.join(character_dir, "neutral.png")
            if os.path.exists(neutral_path):
                reference_image_paths = [neutral_path]
                logger.info(f"   🔍 自动加载参考图: {neutral_path}")
        
        # 确保 neutral 最先生成 (如果它在列表中)
        sorted_expressions = sorted(expressions, key=lambda x: 0 if x == 'neutral' else 1)
        
        for expression in sorted_expressions:
            try:
                # 检查图片是否已存在
                filename = f"{expression}.png"
                expected_image_path = os.path.join(character_dir, filename)
                
                # 如果图片已存在，且没有反馈意见（不是在修正），则跳过
                if os.path.exists(expected_image_path) and not feedback:
                    logger.info(f"   ✅ [{expression}] 立绘已存在，跳过生成")
                    image_paths[expression] = expected_image_path
                    if expression == 'neutral':
                        reference_image_paths = [expected_image_path]
                    continue
                
                if feedback and os.path.exists(expected_image_path):
                    logger.info(f"   🔄 [{expression}] 立绘已存在，但收到反馈意见，正在重新生成...")
                
                # 生成图像
                image_path = self._generate_single_image(
                    character=character,
                    expression=expression,
                    output_dir=character_dir,
                    reference_image_paths=reference_image_paths,
                    feedback=feedback,
                    story_background=story_background,
                    art_style=art_style
                )
                
                if image_path:
                    image_paths[expression] = image_path
                    logger.info(f"   ✅ [{expression}] 立绘生成成功")
                    if expression == 'neutral':
                        reference_image_paths = [image_path]
                else:
                    logger.warning(f"   ⚠️  [{expression}] 立绘生成失败")
                    
            except Exception as e:
                logger.error(f"   ❌ [{expression}] 立绘生成出错: {e}")
        
        logger.info(f"✅ 角色 [{character_name}] 立绘生成完成，共 {len(image_paths)} 张")
        
        return image_paths

    def _build_prompt(
        self, 
        character: Dict[str, Any], 
        expression_type: str, 
        description: Optional[str] = None, 
        feedback: Optional[str] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None
    ) -> str:
        """构建图像生成提示词"""
        appearance = character.get('appearance', 'anime style character')
        personality = character.get('personality', 'Unknown')
        
        # 构建基础 prompt
        if expression_type == "custom" and description:
            # 自定义描述模式
            base_prompt = self.config.IMAGE_PROMPT_TEMPLATE.format(
                story_background=story_background or "A visual novel game",
                art_style=art_style or "Japanese anime style",
                appearance=appearance,
                personality=personality,
                expression=description
            )
        else:
            # 标准表情模式
            base_prompt = self.config.IMAGE_PROMPT_TEMPLATE.format(
                story_background=story_background or "A visual novel game",
                art_style=art_style or "Japanese anime style",
                appearance=appearance,
                personality=personality,
                expression=expression_type
            )
        
        # 如果有 feedback，作为重要的修正指令追加到 prompt 最后
        if feedback:
            base_prompt += f"\n\n⚠️ IMPORTANT CORRECTIONS FROM CHARACTER REVIEW:\n{feedback}\n\nSTRICT REQUIREMENT: Maintain absolute visual consistency with the character's original facial features, hair, clothing, and art style while applying the above corrections."
        
        return base_prompt

    def _call_image_api(self, prompt: str, reference_image_paths: Optional[List[str]] = None) -> Optional[bytes]:
        """调用图像生成 API (使用 Responses API 给 OpenAI，使用 Models API 给 Google)"""
        if self.provider == "openai":
            try:
                # 构建输入。如果有参考图，我们需要将其编码为 Base64 塞入 input 中
                messages = [{"type": "input_text", "text": prompt}]
                action = "generate"
                
                if reference_image_paths:
                    for path in reference_image_paths:
                        if os.path.exists(path):
                            with open(path, "rb") as image_file:
                                b64_data = base64.b64encode(image_file.read()).decode("utf-8")
                                # 根据文档，使用 data URL 格式
                                messages.append({
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{b64_data}"
                                })
                    if len(messages) > 1:
                        action = "auto" # 有图片时让模型决定是编辑还是参考
                
                # 调用 Responses API
                response = self.client.responses.create(
                    model=APIConfig.IMAGE_MODEL,
                    input=[{"role": "user", "content": messages}],
                    tools=[{
                        "type": "image_generation",
                        "action": action,
                        "size": self.config.IMAGE_SIZE,
                        "input_fidelity": "high" if action == "auto" else "low"
                    }]
                )
                
                # 从响应中提取生成的图像 (Responses API 返回的是 base64)
                for output in response.output:
                    if output.type == "image_generation_call" and output.result:
                        return base64.b64decode(output.result)
                
                return None
            except Exception as e:
                logger.error(f"❌ OpenAI Responses API 调用失败: {e}")
                return None
            
        elif self.provider == "google":
            contents = [prompt]
            if reference_image_paths:
                for path in reference_image_paths:
                    if not path or not os.path.exists(path):
                        continue
                    try:
                        ref_img = Image.open(path)
                        contents.append(ref_img)
                    except Exception as e:
                        logger.warning(f"   ⚠️ 无法加载参考图 [{path}]: {e}")
                
                if len(contents) > 1:
                    contents[0] = f"Generate a variation of the character in the attached images, maintaining visual consistency: {prompt}"
            
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
        """移除背景"""
        try:
            logger.info(f"   ✂️ 正在移除背景: {filepath.name} (使用 isnet-anime 模型)...")
            input_image = Image.open(filepath)
            
            # 使用专门针对动漫优化的模型 isnet-anime
            session = new_session("isnet-anime")
            
            # 重新启用 alpha_matting 以获得更好的边缘质量
            # 调整参数以更激进地去除发丝间的背景杂色
            output_image = remove(
                input_image, 
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=200, # 降低前景阈值，让更多边缘区域参与计算
                alpha_matting_background_threshold=20,  # 提高背景阈值，强制低透明度区域变透明
                alpha_matting_erode_size=10, # 恢复到默认腐蚀大小，避免过度腐蚀丢失细节
                alpha_matting_base_size=0  # 保持原始分辨率
            )
            
            output_image.save(filepath)
            logger.info(f"   ✅ 背景移除成功")
        except Exception as e:
            logger.error(f"   ❌ 背景移除失败: {e}")

    def _generate_single_image(
        self,
        character: Dict[str, Any],
        expression: str,
        output_dir: str,
        reference_image_paths: Optional[List[str]] = None,
        feedback: Optional[str] = None,
        story_background: Optional[str] = None,
        art_style: Optional[str] = None
    ) -> Optional[str]:
        """生成单张立绘"""
        if not self.available: return None
        
        try:
            name = character.get('name', 'Character')
            prompt = self._build_prompt(
                character, 
                expression, 
                feedback=feedback,
                story_background=story_background,
                art_style=art_style
            )
            
            logger.info(f"   🎨 为 [{name}] 生成立绘 ({expression})...")
            
            # 使用参考图（如果提供）
            # 注意：不再排除 neutral，因为其他角色的 neutral 可能需要参考主角
            image_data = self._call_image_api(prompt, reference_image_paths)
            
            if image_data:
                filename = f"{expression}.png"
                filepath = Path(output_dir) / filename
                self._save_image(image_data, filepath)
                
                # 移除背景
                self._remove_background(filepath)
                
                return str(filepath)
            return None
                
        except Exception as e:
            logger.error(f"❌ 图像生成失败: {e}")
            return None
    
    def generate_background(
        self,
        location: str,
        time_of_day: str = "",
        atmosphere: str = "peaceful",
        story_background: str = "",
        art_style: str = ""
    ) -> Optional[str]:
        """
        生成场景背景图
        
        Args:
            location: 场景地点（如"教室"、"公园"等）
            time_of_day: 时间段（可选，如"morning", "afternoon"）
            atmosphere: 氛围（如"peaceful", "romantic", "tense"等）
            story_background: 故事背景说明
            art_style: 美术风格指南
            
        Returns:
            背景图片文件路径，失败返回 None
        """
        logger.info(f"🖼️  开始生成场景背景: {location}")
        
        # 生成文件名（提前检查）
        import re
        safe_location = re.sub(r'[^\w\s-]', '', location).strip().replace(' ', '_')
        
        # 如果指定了时间段，则加后缀；否则直接用地点名
        if time_of_day:
            filename = f"{safe_location}_{time_of_day}.png"
        else:
            filename = f"{safe_location}.png"
            
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
                atmosphere=atmosphere,
                story_background=story_background,
                art_style=art_style
            )
            
            logger.info(f"   🎨 生成背景: {location}...")
            logger.debug(f"   提示词: {prompt[:150]}...")
            
            # 统一使用 _call_image_api 获取字节数据
            image_data = self._call_image_api(prompt)
            
            if image_data:
                self._save_image(image_data, Path(file_path))
                return file_path
            return None

        except Exception as e:
            logger.error(f"❌ 背景图生成失败: {e}")
            return None
    
    def generate_all_backgrounds(self, locations: List[str], story_background: str = "", art_style: str = "") -> Dict[str, str]:
        """
        为游戏中的所有场景生成背景图
        
        Args:
            locations: 场景地点列表
            story_background: 故事背景说明
            art_style: 美术风格指南
            
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
                    time_of_day="",  # 不指定时间段，避免文件名带后缀
                    atmosphere="peaceful",
                    story_background=story_background,
                    art_style=art_style
                )
                if bg_path:
                    background_images[location] = bg_path
            except Exception as e:
                logger.error(f"❌ 场景 {location} 背景生成失败: {e}")
        
        logger.info(f"\n✅ 所有场景背景生成完成！")
        logger.info(f"   成功: {len(background_images)}/{len(locations)} 个场景")
        
        return background_images
    
    def generate_title_image(self, title: str, background_desc: str, character_images: List[str] = None) -> Optional[str]:
        """
        生成游戏标题画面
        
        Args:
            title: 游戏标题
            background_desc: 背景/主题描述
            character_images: 角色立绘参考图路径列表 (用于保持一致性)
            
        Returns:
            图片文件路径，失败返回 None
        """
        logger.info(f"🖼️  开始生成标题画面: {title}")
        
        filename = "title_screen.png"
        file_path = os.path.join(PathConfig.IMAGES_DIR, filename)
        
        # 强制重新生成，因为可能需要更新角色一致性
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"   🗑️ 删除旧标题画面，重新生成以匹配角色...")
            except:
                pass
            
        if not self.available or not self.client:
            logger.warning("⚠️  图像生成不可用")
            return None
            
        try:
            prompt = self.config.TITLE_IMAGE_PROMPT_TEMPLATE.format(
                title=title,
                background=background_desc
            )
            
            logger.info(f"   🎨 生成标题画面...")
            
            # 统一使用 _call_image_api 获取字节数据
            image_data = self._call_image_api(prompt, reference_image_paths=character_images)
            
            if image_data:
                self._save_image(image_data, Path(file_path))
                return file_path
            return None

        except Exception as e:
            logger.error(f"❌ 标题画面生成失败: {e}")
            return None
