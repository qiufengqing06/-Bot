"""
Image generation command: /画图
"""
import asyncio
import json

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment
from nonebot.log import logger
from openai import OpenAI

from nonebot_agent.config import config as app_config
from nonebot_agent.plugins.message_parser import extract_message_content
from nonebot_agent.tools import generate_image_tool


# /画图 command - generate images using Doubao API
draw_image_cmd = on_command("画图", aliases={"draw", "generate", "生成图片"}, priority=5, block=True)

# LLM prompt for parameter extraction
IMAGE_PARAM_EXTRACTION_PROMPT = """你是一个参数提取助手。从用户的画图请求中提取以下信息，返回 JSON 格式：

1. prompt: 图片描述（去掉尺寸相关的部分，只保留内容描述）
2. size: 图片尺寸，可选值：1080p, 2K, 4K。如果用户没有指定，返回 "4K"

用户输入示例和对应输出：
- "一只可爱的猫咪" -> {"prompt": "一只可爱的猫咪", "size": "4K"}
- "城市夜景 尺寸1080p" -> {"prompt": "城市夜景", "size": "1080p"}
- "画一个宇宙 2k分辨率" -> {"prompt": "画一个宇宙", "size": "2K"}
- "海边日落 4K" -> {"prompt": "海边日落", "size": "4K"}

只返回 JSON，不要其他内容。
"""


def extract_image_params(user_input: str) -> dict:
    """
    Use LLM to extract image generation parameters from user input.
    
    Args:
        user_input: User's drawing request
        
    Returns:
        Dict with 'prompt' and 'size' keys
    """
    try:
        from nonebot_agent.agent.llm_provider import get_provider
        from openai import OpenAI
        
        client = OpenAI(
            api_key=app_config.LLM_API_KEY,
            base_url=app_config.LLM_API_URL,
        )
        
        # Build provider-aware parameters
        provider = get_provider()
        call_params = {
            "model": app_config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": IMAGE_PARAM_EXTRACTION_PROMPT},
                {"role": "user", "content": user_input}
            ],
            "temperature": 0.1,  # Low temperature for more consistent parsing
            "max_tokens": 200
        }
        
        # Add provider-specific extra_body parameters
        extra_body = provider.build_extra_body()
        if extra_body:
            call_params["extra_body"] = extra_body
        
        response = client.chat.completions.create(**call_params)
        
        result_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON from response
        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        params = json.loads(result_text)
        
        # Validate required fields
        if "prompt" not in params:
            params["prompt"] = user_input
        if "size" not in params:
            params["size"] = "4K"
            
        logger.info(f"[ImageGen] Extracted params: {params}")
        return params
        
    except Exception as e:
        logger.warning(f"[ImageGen] Failed to extract params, using defaults: {e}")
        return {
            "prompt": user_input,
            "size": "4K"
        }


@draw_image_cmd.handle()
async def handle_draw_image(bot: Bot, event: MessageEvent):
    """
    Handle /画图 command to generate images.
    
    Usage:
        /画图 一只可爱的猫咪
        /画图 城市夜景 尺寸:1080p
        [图片] /画图 把背景换成海边
    """
    user_id = event.get_user_id()
    
    # Extract message content
    text_content, image_paths, image_urls, media_info = await extract_message_content(event.message)
    
    # Remove command prefix from text
    for prefix in ["画图", "/画图", "draw", "/draw", "generate", "/generate", "生成图片", "/生成图片"]:
        if text_content.startswith(prefix):
            text_content = text_content[len(prefix):].strip()
            break
    
    # Check if there's a description
    if not text_content:
        await draw_image_cmd.finish(
            "🎨 请输入图片描述\n\n"
            "使用方法：\n"
            "  /画图 一只可爱的猫咪\n"
            "  /画图 城市夜景 尺寸:1080p\n"
            "  [发送图片] /画图 把背景换成海边"
        )
        return
    
    # Send generating message
    await draw_image_cmd.send("🎨 正在生成图片，请稍候...")
    
    try:
        # Extract parameters using LLM
        loop = asyncio.get_event_loop()
        params = await loop.run_in_executor(
            None,
            lambda: extract_image_params(text_content)
        )
        
        prompt = params.get("prompt", text_content)
        size = params.get("size", "4K")
        
        # Determine if this is image-to-image
        reference_url = None
        if image_urls:
            reference_url = image_urls[0]  # Use first image as reference
            logger.info(f"[ImageGen] Using reference image: {reference_url[:50]}...")
        
        # Call generate_image_tool
        result = await loop.run_in_executor(
            None,
            lambda: generate_image_tool.invoke({
                "prompt": prompt,
                "size": size,
                "reference_image_url": reference_url
            })
        )
        
        logger.info(f"[ImageGen] Generate result: {result[:100] if result else 'None'}...")
        
        # Check if result is a valid URL or error message
        if result and result.startswith("http"):
            # Successfully generated - send image
            message = Message()
            message += MessageSegment.image(result)
            message += MessageSegment.text(f"\n🎨 图片已生成！\n描述：{prompt}\n尺寸：{size}")
            await draw_image_cmd.finish(message)
        else:
            # Error occurred
            await draw_image_cmd.finish(f"❌ 生成失败：{result}")
            
    except Exception as e:
        # Re-raise FinishedException - it's expected behavior from finish()
        from nonebot.exception import FinishedException
        if isinstance(e, FinishedException):
            raise
        
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[ImageGen] Error: {e}")
        logger.error(f"[ImageGen] Traceback:\n{error_detail}")
        await draw_image_cmd.finish(f"❌ 生成图片时出错：{str(e)}")
