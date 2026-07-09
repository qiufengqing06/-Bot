"""
Sticker response parsing utilities.
Extracted from agent_chat.py for better maintainability.
"""
import os
import re

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger

from nonebot_agent.tools import (
    get_sticker_full_path,
    STICKER_MARKER_PREFIX,
    STICKER_MARKER_SUFFIX,
)


def parse_sticker_response(response: str) -> Message:
    """
    Parse response containing sticker markers and convert to Message with images.
    
    Sticker markers have the format: [STICKER:filename]
    These are converted to actual image messages using MessageSegment.image()
    
    Args:
        response: Agent response text that may contain sticker markers
        
    Returns:
        NoneBot Message object with text and image segments
    """
    message = Message()
    
    # Pattern to match [STICKER:filename]
    # Build pattern components outside f-string to avoid backslash issues
    prefix_escaped = re.escape(STICKER_MARKER_PREFIX)
    suffix_escaped = re.escape(STICKER_MARKER_SUFFIX)
    pattern = f'{prefix_escaped}([^\\]]+){suffix_escaped}'
    
    # Split by sticker markers
    parts = re.split(pattern, response)
    
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # This is regular text
            text = part.strip()
            if text:
                message += MessageSegment.text(text)
        else:
            # This is a sticker filename
            filename = part.strip()
            sticker_path = get_sticker_full_path(filename)
            
            if os.path.exists(sticker_path):
                # Use file:// protocol for local files
                message += MessageSegment.image(f"file:///{sticker_path}")
                logger.info(f"[Agent] Added sticker: {filename}")
            else:
                # Sticker file not found, log warning
                logger.warning(f"[Agent] Sticker not found: {sticker_path}")
                message += MessageSegment.text(f"[表情包: {filename}]")
    
    return message


def contains_sticker_marker(text: str) -> bool:
    """Check if text contains any sticker markers."""
    return STICKER_MARKER_PREFIX in text and STICKER_MARKER_SUFFIX in text
