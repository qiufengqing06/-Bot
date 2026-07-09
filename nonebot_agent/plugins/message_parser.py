"""
Message parsing utilities for OneBot message segments.
Extracted from agent_chat.py for better maintainability.
"""
from typing import List, Tuple

from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger

from nonebot_agent.utils.media_handler import download_and_save_image


async def extract_message_content(message: Message) -> Tuple[str, List[str], List[str], List[dict]]:
    """
    Extract text, images, and other media from a message.
    
    Args:
        message: OneBot message object
        
    Returns:
        Tuple of (text_content, image_local_paths, image_urls, media_info_list)
    """
    text_parts = []
    image_paths = []
    image_urls = []
    media_info = []
    logger.debug(f"[Agent] Extracting message content: {message}")
    for seg in message:
        if seg.type == "text":
            text_parts.append(seg.data.get("text", ""))
        
        elif seg.type == "image":
            # Get image URL and download
            url = seg.data.get("url")
            file_name = seg.data.get("file", "unknown.jpg")
            
            if url:
                image_urls.append(url)  # Keep original URL for API
                local_path = await download_and_save_image(url)
                if local_path:
                    image_paths.append(local_path)
                    media_info.append({
                        "type": "image",
                        "url": url,
                        "file_name": file_name,
                        "local_path": local_path
                    })
                    logger.info(f"[Agent] Saved image: {local_path}")
        
        elif seg.type == "video":
            url = seg.data.get("url")
            file_name = seg.data.get("file", "unknown.mp4")
            media_info.append({
                "type": "video",
                "url": url,
                "file_name": file_name,
                "local_path": None  # Video not saved locally for now
            })
            logger.info(f"[Agent] Received video: {file_name}")
        
        elif seg.type == "file":
            file_name = seg.data.get("name", "unknown")
            file_id = seg.data.get("id")
            media_info.append({
                "type": "file",
                "file_id": file_id,
                "file_name": file_name,
                "local_path": None
            })
            logger.info(f"[Agent] Received file: {file_name}")

    text_content = "".join(text_parts).strip()
    return text_content, image_paths, image_urls, media_info
