"""
Agent Utils
~~~~~~~~~~~
所有 Agent 共用的工具函数
"""

import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class JSONParser:
    """JSON 解析工具类"""
    
    @staticmethod
    def parse_ai_response(content: str, save_on_fail: bool = True) -> Dict[str, Any]:
        """
        解析 AI 返回的 JSON 响应，自动处理常见格式问题
        
        Args:
            content: AI 返回的原始文本
            save_on_fail: 失败时是否保存原始响应供调试
            
        Returns:
            解析后的字典
            
        Raises:
            json.JSONDecodeError: 如果解析失败
        """
        try:
            # 第一次尝试：直接解析
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️  直接 JSON 解析失败: {e}")
            logger.info("🔧 尝试修复 JSON 格式...")
            
            try:
                # 尝试修复后再解析
                fixed_content = JSONParser.fix_json_format(content)
                result = json.loads(fixed_content)
                logger.info("✅ JSON 修复成功")
                return result
            except json.JSONDecodeError as e2:
                logger.error(f"❌ JSON 修复失败: {e2}")
                
                # 保存失败的响应供调试
                if save_on_fail:
                    JSONParser._save_failed_response(content, e2)
                
                # 给出更友好的错误提示
                logger.error("💡 建议: 检查 logs/failed_json.txt 查看原始响应")
                logger.error("💡 可能原因: AI 返回的文本中包含未转义的引号或换行符")
                raise
    
    @staticmethod
    def _save_failed_response(content: str, error: Exception) -> None:
        """
        保存解析失败的 JSON 响应
        
        Args:
            content: 失败的内容
            error: 错误信息
        """
        import os
        from datetime import datetime
        
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(log_dir, f'failed_json_{timestamp}.txt')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"=== JSON 解析失败 ===\n")
                f.write(f"时间: {datetime.now()}\n")
                f.write(f"错误: {error}\n")
                f.write(f"\n=== 原始内容 ===\n")
                f.write(content)
            
            logger.info(f"💾 失败的响应已保存: {file_path}")
        except Exception as e:
            logger.error(f"保存失败响应时出错: {e}")
    
    @staticmethod
    def fix_json_format(content: str) -> str:
        """
        修复常见的 JSON 格式问题
        
        Args:
            content: 原始 JSON 字符串
            
        Returns:
            修复后的 JSON 字符串
        """
        original_content = content
        
        # 1. 移除 markdown 代码块标记
        content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'^```\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'```', '', content)
        
        # 2. 移除 BOM 标记和首尾空白
        content = content.strip('\ufeff').strip()
        
        # 3. 提取 JSON 对象或数组
        start_obj = content.find('{')
        start_arr = content.find('[')
        
        # 确定是对象还是数组（取最靠前的一个）
        is_object = False
        if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
            start = start_obj
            open_char = '{'
            close_char = '}'
            is_object = True
        elif start_arr != -1:
            start = start_arr
            open_char = '['
            close_char = ']'
            is_object = False
        else:
            # 既没找到 { 也没找到 [，直接返回
            return content

        if start != -1:
            # 简单的括号计数法来找到匹配的结束括号
            count = 0
            end = -1
            in_string = False
            escape = False
            
            for i in range(start, len(content)):
                char = content[i]
                
                if escape:
                    escape = False
                    continue
                    
                if char == '\\':
                    escape = True
                    continue
                    
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == open_char:
                        count += 1
                    elif char == close_char:
                        count -= 1
                        if count == 0:
                            end = i
                            break
            
            if end != -1:
                content = content[start:end+1]
            else:
                # 如果计数法失败，回退到简单的 rfind
                end = content.rfind(close_char)
                if end != -1 and start < end:
                    content = content[start:end+1]
        
        # 4. 移除注释（JSON 不支持注释）
        # 移除单行注释 //
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # 移除多行注释 /* */
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # 5. 修复常见的尾部逗号问题
        # 修复数组尾部逗号 [1, 2, 3,] -> [1, 2, 3]
        content = re.sub(r',\s*]', ']', content)
        # 修复对象尾部逗号 {"a": 1,} -> {"a": 1}
        content = re.sub(r',\s*}', '}', content)
        
        # 6. 修复字符串中的换行符问题
        # 将字符串中的真实换行符替换为 \n
        def fix_string_newlines(match):
            string_content = match.group(1)
            # 替换未转义的换行符
            string_content = string_content.replace('\n', '\\n')
            string_content = string_content.replace('\r', '\\r')
            return f'"{string_content}"'
        
        # 这个正则比较复杂，谨慎使用
        # content = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', fix_string_newlines, content)
        
        # 7. 替换中文引号为英文引号（如果有）
        content = content.replace('"', '"').replace('"', '"')
        content = content.replace(''', "'").replace(''', "'")
        
        logger.debug(f"修复前: {len(original_content)} 字符")
        logger.debug(f"修复后: {len(content)} 字符")
        
        return content
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: list) -> bool:
        """
        验证字典是否包含所有必需字段
        
        Args:
            data: 要验证的字典
            required_fields: 必需字段列表
            
        Returns:
            是否通过验证
        """
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            logger.error(f"❌ 缺少必需字段: {', '.join(missing_fields)}")
            return False
        
        return True


class PromptBuilder:
    """Prompt 构建工具类"""
    
    @staticmethod
    def format_with_fallback(template: str, **kwargs) -> str:
        """
        格式化模板，对缺失的参数使用默认值
        
        Args:
            template: 模板字符串
            **kwargs: 格式化参数
            
        Returns:
            格式化后的字符串
        """
        # 提取模板中所有的占位符
        placeholders = re.findall(r'\{(\w+)\}', template)
        
        # 为缺失的参数填充默认值
        defaults = {
            'game_type': '校园恋爱',
            'game_style': '轻松温馨',
            'character_count': 3,
            'name': 'Character',
            'appearance': 'anime style character',
            'personality': 'friendly',
            'expression': 'neutral',
            'color': [100, 149, 237]
        }
        
        for placeholder in placeholders:
            if placeholder not in kwargs and placeholder in defaults:
                kwargs[placeholder] = defaults[placeholder]
        
        return template.format(**kwargs)


class FileHelper:
    """文件操作助手"""
    
    @staticmethod
    def safe_write_json(file_path: str, data: Dict[str, Any]) -> bool:
        """
        安全地写入 JSON 文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
            
        Returns:
            是否成功
        """
        try:
            import os
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 JSON 已保存: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存 JSON 失败: {e}")
            return False
    
    @staticmethod
    def safe_read_json(file_path: str) -> Optional[Dict[str, Any]]:
        """
        安全地读取 JSON 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            读取的数据，失败返回 None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"⚠️  文件不存在: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 读取文件失败: {e}")
            return None
    
    @staticmethod
    def safe_append_text(file_path: str, text: str) -> bool:
        """
        安全地追加文本到文件
        
        Args:
            file_path: 文件路径
            text: 要追加的文本
            
        Returns:
            是否成功
        """
        try:
            import os
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write("\n" + text + "\n")
            
            logger.info(f"💾 文本已追加: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 追加文本失败: {e}")
            return False


class TextProcessor:
    """文本处理工具"""
    
    @staticmethod
    def clean_ai_text(text: str) -> str:
        """
        清理 AI 生成的文本中的多余内容
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        # 移除多余的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 移除首尾空白
        text = text.strip()
        
        return text
    
    @staticmethod
    def extract_json_from_text(text: str) -> Optional[str]:
        """
        从包含其他内容的文本中提取 JSON
        
        Args:
            text: 原始文本
            
        Returns:
            提取的 JSON 字符串，找不到返回 None
        """
        # 尝试找到 JSON 对象
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        
        return None


# 导出所有工具类
__all__ = [
    'JSONParser',
    'PromptBuilder',
    'FileHelper',
    'TextProcessor'
]
