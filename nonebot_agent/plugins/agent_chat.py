"""
Agent Chat Plugin
NoneBot2 plugin for agent-based chat with dual-mode support and multimodal capabilities.

This is the main orchestration module. Command handlers are split into:
- nonebot_agent.plugins.commands.basic (ping/help/status/cleanup)
- nonebot_agent.plugins.commands.emotion (emotion commands)
- nonebot_agent.plugins.commands.free_chat (free chat toggle)
- nonebot_agent.plugins.commands.draw (image generation)
- nonebot_agent.plugins.commands.skills (skills management)
- nonebot_agent.plugins.commands.restart (bot restart)

Utilities are in:
- nonebot_agent.plugins.message_parser (OneBot message parsing)
- nonebot_agent.plugins.group_settings (group DB operations)
- nonebot_agent.plugins.sticker_sender (sticker marker conversion)
"""
import asyncio
import random
from datetime import datetime
from typing import Optional, List, Tuple

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent,
    Message, MessageSegment
)
from nonebot.rule import to_me
from nonebot.log import logger

from nonebot_agent.agent.graph import analyze_image_with_vision_model
from nonebot_agent.agent.prompts import AgentMode, get_mode_from_message
from nonebot_agent.config import config
from nonebot_agent.plugins.group_settings import is_free_chat_enabled
from nonebot_agent.plugins.message_parser import extract_message_content
from nonebot_agent.plugins.sticker_sender import parse_sticker_response, contains_sticker_marker
from nonebot_agent.services.chat_service import generate_response, memory_manager
from nonebot_agent.services.response_sender import response_sender
from nonebot_agent.skills import parse_skill_prefix
from nonebot_agent.utils.media_handler import cleanup_expired_images

# Import command modules to register their handlers
from nonebot_agent.plugins.commands import basic, emotion, free_chat, draw, skills, restart  # noqa: F401


def get_current_timestamp() -> str:
    """Get current timestamp string for message prefix."""
    return datetime.now().strftime("[%Y-%m-%d %H:%M]")


async def get_user_nickname(bot: Bot, user_id: str, group_id: str = None) -> str:
    """
    Get user's nickname (group card name preferred, otherwise QQ nickname).
    
    Args:
        bot: Bot instance
        user_id: User's QQ number
        group_id: Optional group ID (for getting group card name)
        
    Returns:
        User's nickname string
    """
    try:
        if group_id:
            # Get group member info (includes group card name)
            member_info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
            # Prefer group card name, fallback to nickname
            nickname = member_info.get("card") or member_info.get("nickname") or f"用户{user_id[-4:]}"
        else:
            # Get stranger info for private chat
            try:
                user_info = await bot.get_stranger_info(user_id=int(user_id))
                nickname = user_info.get("nickname") or f"用户{user_id[-4:]}"
            except Exception:
                nickname = f"用户{user_id[-4:]}"
        return nickname
    except Exception as e:
        logger.warning(f"[Agent] Failed to get nickname for {user_id}: {e}")
        return f"用户{user_id[-4:]}"


async def send_response_bubble(
    bubble,
    index: int,
    total: int,
    send_text,
    send_message,
    log_prefix: str,
):
    """Send a single bubble from a structured response plan."""
    if bubble.kind == "sticker" or contains_sticker_marker(bubble.content):
        message = parse_sticker_response(bubble.content)
        await send_message(message)
        logger.info(f"[Agent] {log_prefix} sticker [{index}/{total}]: {bubble.content[:50]}...")
    else:
        await send_text(bubble.content)
        logger.info(f"[Agent] {log_prefix} text [{index}/{total}]: {bubble.content[:50]}...")


# ============ Group Chat Recorder ============
# Records all group messages (even without @bot) for context
# Also handles free chat mode responses

group_recorder = on_message(priority=99, block=False)

@group_recorder.handle()
async def record_group_message(bot: Bot, event: MessageEvent):
    """
    Record group messages to memory.
    If free chat mode is enabled, may also generate responses.
    """
    # Only process group messages
    if not isinstance(event, GroupMessageEvent):
        return
    
    # Skip if bot is mentioned (will be handled by agent_reply)
    if event.is_tome():
        return
    
    user_id = event.get_user_id()
    group_id = str(event.group_id)
    session_key = response_sender.build_session_key("group", user_id, group_id)
    response_sender.cancel_pending(session_key)
    
    # Get user nickname
    nickname = await get_user_nickname(bot, user_id, group_id)
    
    # Extract message content
    text_content, image_paths, image_urls, media_info = await extract_message_content(event.message)
    
    # Skip empty messages
    if not text_content and not image_paths:
        return
    
    # Build content string for storage with timestamp and nickname
    timestamp = get_current_timestamp()
    # Format: [时间] [昵称(QQ后4位)]: 消息内容
    content = f"{timestamp} [{nickname}({user_id[-4:]})]: {text_content}"
    
    # Analyze images with vision model if present
    if image_urls or image_paths:
        try:
            # Run vision analysis in thread pool (synchronous function)
            loop = asyncio.get_event_loop()
            image_description = await loop.run_in_executor(
                None,
                lambda: analyze_image_with_vision_model(image_paths, image_urls)
            )
            if image_description:
                content += f" [发送了图片: {image_description}]"
                logger.info(f"[Agent] Analyzed group image: {image_description[:50]}...")
            else:
                content += f" [图片x{len(image_urls or image_paths)}]"
        except Exception as e:
            logger.warning(f"[Agent] Failed to analyze group image: {e}")
            content += f" [图片x{len(image_urls or image_paths)}]"
    
    # Record to memory
    try:
        memory_manager.record_group_message(
            user_id=user_id,
            group_id=group_id,
            content=content,
            has_media=bool(media_info),
            media_info=media_info,
            is_bot_mentioned=False,
            nickname=nickname
        )
        logger.debug(f"[Agent] Recorded group message from {nickname}({user_id}) in {group_id}")
    except Exception as e:
        logger.error(f"[Agent] Failed to record group message: {e}")
    
    # Check if free chat mode is enabled
    free_chat_enable, reply_probability = is_free_chat_enabled(group_id)
    
    if not free_chat_enable:
        return
    
    # Roll for reply probability
    if random.randint(1, 100) > reply_probability:
        logger.debug(f"[Agent] Free chat: skipped reply (prob={reply_probability}%)")
        return
    
    logger.info(f"[Agent] Free chat mode: replying to {user_id} in {group_id}")
    
    # Generate response using agent (chat mode for free chat)
    try:
        mode = AgentMode.CHAT
        response_plan = await generate_response(
            user_id=user_id,
            content=text_content,
            session_type="group",
            group_id=group_id,
            mode=mode,
            image_paths=image_paths,
            image_urls=image_urls,
            media_info=media_info,
            current_user_nickname=nickname
        )

        await response_sender.send_plan(
            plan=response_plan,
            session_key=session_key,
            send_bubble=lambda bubble, index, total: send_response_bubble(
                bubble=bubble,
                index=index,
                total=total,
                send_text=lambda text: bot.send_group_msg(group_id=int(group_id), message=text),
                send_message=lambda message: bot.send_group_msg(group_id=int(group_id), message=message),
                log_prefix="Free chat sent",
            ),
        )
                
    except Exception as e:
        import traceback
        logger.error(f"[Agent] Free chat error: {e}")
        logger.error(f"[Agent] Traceback:\n{traceback.format_exc()}")


# ============ Agent Chat Handler ============
# Triggered when the bot is @mentioned or in private chat

agent_reply = on_message(rule=to_me(), priority=10, block=True)

@agent_reply.handle()
async def handle_agent_message(bot: Bot, event: MessageEvent):
    """
    Handle incoming messages and generate agent responses.
    
    Supports:
    - Private chat (C2C)
    - Group chat (@mention)
    - Dual mode (chat/professional based on "/" prefix)
    - Multimodal messages (images)
    """
    user_id = event.get_user_id()
    
    # Extract message content (text + images)
    text_content, image_paths, image_urls, media_info = await extract_message_content(event.message)
    
    # Skip if no content at all
    if not text_content and not image_paths:
        await agent_reply.finish("你好！请问有什么可以帮助你的？")
    
    # Determine mode and optional skill override based on message content
    skill_route = parse_skill_prefix(text_content)
    if skill_route:
        mode = AgentMode.CHAT
        processed_content = skill_route.content or "和我聊聊吧"
        skill_override = skill_route.skill_name
        skill_exclusive = skill_route.exclusive
    else:
        mode, processed_content = get_mode_from_message(text_content)
        skill_override = None
        skill_exclusive = False
    
    # Add timestamp prefix to the message
    timestamp = get_current_timestamp()
    processed_content = f"{timestamp} {processed_content}"
    
    # Determine session type and group_id
    if isinstance(event, GroupMessageEvent):
        session_type = "group"
        group_id = str(event.group_id)
        session_key = response_sender.build_session_key(session_type, user_id, group_id)
        logger.info(f"[Agent] Group message from {user_id} in {group_id}: {text_content[:50]}...")
    else:
        session_type = "c2c"
        group_id = None
        session_key = response_sender.build_session_key(session_type, user_id, group_id)
        logger.info(f"[Agent] Private message from {user_id}: {text_content[:50]}...")

    response_sender.cancel_pending(session_key)
    
    # Get user nickname for context
    nickname = await get_user_nickname(bot, user_id, group_id)
    
    # Log media info
    if image_paths:
        logger.info(f"[Agent] Message includes {len(image_paths)} image(s)")
    
    logger.info(
        f"[Agent] Mode: {mode.value}, skill_override={skill_override}, "
        f"skill_exclusive={skill_exclusive}"
    )
    
    try:
        # Generate response using agent
        response_plan = await generate_response(
            user_id=user_id,
            content=processed_content,
            session_type=session_type,
            group_id=group_id,
            mode=mode,
            image_paths=image_paths,
            image_urls=image_urls,
            media_info=media_info,
            current_user_nickname=nickname,
            skill_override=skill_override,
            skill_exclusive=skill_exclusive,
        )

        await response_sender.send_plan(
            plan=response_plan,
            session_key=session_key,
            send_bubble=lambda bubble, index, total: send_response_bubble(
                bubble=bubble,
                index=index,
                total=total,
                send_text=agent_reply.send,
                send_message=agent_reply.send,
                log_prefix="Sent reply",
            ),
        )
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"[Agent] Error handling message: {e}")
        logger.error(f"[Agent] Full traceback:\n{error_details}")
        await agent_reply.send("抱歉，我遇到了一些问题，请稍后再试 😅")


# ============ Periodic Cleanup Task ============
# Clean up expired images

async def cleanup_task():
    """Periodic task to clean up expired images."""
    while True:
        try:
            deleted = cleanup_expired_images()
            if deleted > 0:
                logger.info(f"[Agent] Cleaned up {deleted} expired images")
        except Exception as e:
            logger.error(f"[Agent] Image cleanup error: {e}")
        
        # Run daily
        await asyncio.sleep(86400)


# Start cleanup task on plugin load (optional, can be triggered manually)
# asyncio.create_task(cleanup_task())
