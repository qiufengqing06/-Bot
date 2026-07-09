"""
Image Generation Tool
Generate images using Doubao (豆包) API - supports text-to-image and image-to-image.
"""
import os
import logging
from typing import Optional

import dotenv
from langchain.tools import tool

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# API 配置
DOUBAO_API_URL = os.getenv("DOUBAO_API_URL")
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY")

# 默认模型和尺寸
DEFAULT_MODEL = "doubao-seedream-4-5-251128"
DEFAULT_SIZE = "4K"

# 支持的尺寸映射
SIZE_MAPPING = {
    "1080p": "1920*1080",
    "2k": "2560*1440",
    "4k": "4K",
    "default": "4K",
}


def get_image_generator():
    """获取或创建 ImageGenerator 实例"""
    from nonebot_agent.utils.doubao_image_generate import ImageGenerator
    return ImageGenerator(DOUBAO_API_URL, DOUBAO_API_KEY)


def normalize_size(size_input: str) -> str:
    """
    标准化尺寸参数
    
    Args:
        size_input: 用户输入的尺寸 (如 "1080p", "2K", "4K" 等)
        
    Returns:
        API 接受的尺寸格式
    """
    if not size_input:
        return DEFAULT_SIZE
    
    size_lower = size_input.lower().strip()
    return SIZE_MAPPING.get(size_lower, DEFAULT_SIZE)


@tool(description="""生成图片工具。根据文字描述生成图片，或基于参考图片进行二次创作（图生图）。

使用场景：
- 用户使用 /画图 命令时调用此工具
- 需要根据描述创作图片时

参数：
- prompt: 图片描述文字，描述你想要生成的图片内容
- size: 图片尺寸，可选值：1080p, 2K, 4K（默认4K）
- reference_image_url: 参考图片URL（可选），用于图生图模式

返回：生成的图片URL

注意：
- 如果提供了 reference_image_url，将基于该图片进行二次创作
- 生成图片需要一定时间，请耐心等待
""")
def generate_image_tool(
    prompt: str,
    size: str = "4K",
    reference_image_url: Optional[str] = None
) -> str:
    """
    生成图片并返回URL
    
    Args:
        prompt: 图片描述
        size: 尺寸 (1080p/2K/4K)
        reference_image_url: 参考图片URL (可选，用于图生图)
        
    Returns:
        生成的图片URL，或错误信息
    """
    try:
        if not DOUBAO_API_URL or not DOUBAO_API_KEY:
            logger.error("缺少 DOUBAO_API_URL 或 DOUBAO_API_KEY 环境变量")
            return "错误：画图服务未配置，请联系管理员设置 API 密钥。"
        
        generator = get_image_generator()
        normalized_size = normalize_size(size)
        
        logger.info(f"[ImageGen] 开始生成图片: prompt='{prompt[:50]}...', size={normalized_size}, has_ref={reference_image_url is not None}")
        
        if reference_image_url:
            # 图生图模式
            image_url = generator.generate_image_from_image(
                prompt=prompt,
                image_url=reference_image_url,
                model=DEFAULT_MODEL,
                size=normalized_size
            )
            logger.info(f"[ImageGen] 图生图完成: {image_url}")
        else:
            # 文生图模式
            image_url = generator.generate_image_from_text(
                prompt=prompt,
                model=DEFAULT_MODEL,
                size=normalized_size
            )
            logger.info(f"[ImageGen] 文生图完成: {image_url}")
        
        return image_url
        
    except Exception as e:
        logger.error(f"[ImageGen] 生成图片失败: {e}")
        return f"生成图片时出错：{str(e)}"


# 导出标记前缀（类似表情包的处理方式）
IMAGE_MARKER_PREFIX = "[GENERATED_IMAGE:"
IMAGE_MARKER_SUFFIX = "]"


def create_image_marker(image_url: str) -> str:
    """创建图片标记，用于在响应中标识生成的图片"""
    return f"{IMAGE_MARKER_PREFIX}{image_url}{IMAGE_MARKER_SUFFIX}"


def is_image_marker(text: str) -> bool:
    """检查文本是否包含图片标记"""
    return IMAGE_MARKER_PREFIX in text and IMAGE_MARKER_SUFFIX in text


def extract_image_url(marker: str) -> Optional[str]:
    """从图片标记中提取URL"""
    if IMAGE_MARKER_PREFIX in marker:
        start = marker.find(IMAGE_MARKER_PREFIX) + len(IMAGE_MARKER_PREFIX)
        end = marker.find(IMAGE_MARKER_SUFFIX, start)
        if end > start:
            return marker[start:end]
    return None
