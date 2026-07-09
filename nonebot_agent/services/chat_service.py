"""
Chat orchestration service.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from nonebot.log import logger

from nonebot_agent.agent.chat_output import ChatResponsePlan
from nonebot_agent.agent.graph import get_agent, parse_chat_plan
from nonebot_agent.agent.prompts import AgentMode
from nonebot_agent.config import config
from nonebot_agent.emotion import emotion_analyzer, emotion_manager
from nonebot_agent.memory.memory_manager import MemoryManager
from nonebot_agent.memory.response_guard import ResponseGuard
from nonebot_agent.tools import STICKER_MARKER_PREFIX, STICKER_MARKER_SUFFIX


ERROR_MESSAGES = [
    "调用模型时出错，请稍后再试。",
    "抱歉，我没有生成有效的回复。",
    "抱歉，我没有收到任何回复。",
]

memory_manager = MemoryManager()
response_guard = ResponseGuard()


async def generate_response(
    user_id: str,
    content: str,
    session_type: str,
    group_id: Optional[str] = None,
    mode: AgentMode = AgentMode.PROFESSIONAL,
    image_paths: Optional[List[str]] = None,
    image_urls: Optional[List[str]] = None,
    media_info: Optional[List[dict]] = None,
    current_user_nickname: Optional[str] = None,
    skill_override: Optional[str] = None,
    skill_exclusive: bool = False,
    trace_id: Optional[str] = None,
) -> ChatResponsePlan:
    """Generate agent responses and post-process them for novelty."""
    # Format trace prefix for logging
    trace_prefix = f"[trace:{trace_id}] " if trace_id else ""
    
    conversation, short_term_messages, long_term_context = memory_manager.process_message(
        user_id=user_id,
        user_message=content,
        session_type=session_type,
        group_id=group_id,
        mode=mode.value,
        has_media=bool(media_info),
        media_info=media_info,
    )

    if skill_exclusive:
        current_messages = [msg for msg in short_term_messages if isinstance(msg, HumanMessage)]
        initial_messages = current_messages[-1:] if current_messages else short_term_messages[-1:]
        long_term_context = ""
    else:
        initial_messages = short_term_messages.copy()

    recent_assistant_messages = [
        msg.content for msg in initial_messages if isinstance(msg, AIMessage) and msg.content
    ]

    emotion_label = None
    if mode == AgentMode.CHAT and not skill_exclusive:
        context_type = "group" if session_type == "group" else "c2c"
        context_id = group_id if session_type == "group" else user_id
        emotion_state = emotion_manager.get_emotion(context_type, context_id)
        emotion_label = emotion_state.get_label().value
        logger.info(f"{trace_prefix}[Emotion] Current state for {context_type}:{context_id}: {emotion_label}")

    initial_state = {
        "messages": initial_messages,
        "user_id": user_id,
        "session_type": session_type,
        "group_id": group_id,
        "long_term_context": long_term_context,
        "llm_calls": 0,
        "mode": mode.value,
        "image_paths": image_paths,
        "image_urls": image_urls,
        "image_description": None,
        "emotion_label": emotion_label,
        "current_user_nickname": current_user_nickname,
        "skill_override": skill_override,
        "skill_exclusive": skill_exclusive,
    }

    agent = get_agent(mode)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: agent.invoke(initial_state))

    messages = result.get("messages", [])
    raw_response = ""
    sticker_markers: List[str] = []

    if messages:
        for msg in messages:
            if hasattr(msg, "tool_call_id") and hasattr(msg, "content"):
                tool_content = msg.content
                if STICKER_MARKER_PREFIX in tool_content and STICKER_MARKER_SUFFIX in tool_content:
                    sticker_markers.append(tool_content)
                    logger.info(f"{trace_prefix}[Agent] Found sticker marker in tool result: {tool_content}")

        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_call_id"):
                raw_response = msg.content
                break
        else:
            raw_response = "抱歉，我没有生成有效的回复。"
    else:
        raw_response = "抱歉，我没有收到任何回复。"

    if mode == AgentMode.CHAT:
        response_plan = parse_chat_plan(
            raw_response,
            max_followups=(
                config.SKILL_EXCLUSIVE_CHAT_MAX_FOLLOWUPS if skill_exclusive else None
            ),
        )
        if sticker_markers:
            existing_stickers = {
                bubble.content for bubble in response_plan.bubbles if bubble.kind == "sticker"
            }
            missing_markers = [marker for marker in sticker_markers if marker not in existing_stickers]
            if missing_markers:
                response_plan = response_plan.append_stickers(missing_markers)
                logger.info(f"{trace_prefix}[Agent] Added {len(missing_markers)} sticker marker(s) to response plan")
    else:
        response_plan = ChatResponsePlan.from_text(raw_response)

    response_plan = response_guard.rewrite_plan_if_needed(
        plan=response_plan,
        recent_responses=recent_assistant_messages,
        mode=mode,
        user_message=content,
    )

    image_description = result.get("image_description", "")
    if image_description:
        logger.info(f"{trace_prefix}[Agent] Image description extracted: {image_description[:80]}...")

    full_response = response_plan.canonical_text().strip()
    if not full_response:
        full_response = "\n".join(
            bubble.content.strip() for bubble in response_plan.bubbles if bubble.content.strip()
        )
    is_error_response = any(err in full_response for err in ERROR_MESSAGES)

    if not is_error_response:
        stored_user_message = content
        if image_description:
            stored_user_message = f"[用户发送了图片: {image_description}] {content}".strip()

        memory_manager.save_response(
            conversation_id=conversation.id,
            user_id=user_id,
            user_message=stored_user_message,
            response=full_response,
            mode=mode.value,
            group_id=group_id,
            has_media=bool(media_info),
            image_description=image_description,
        )

        if mode == AgentMode.CHAT and not skill_exclusive:
            try:
                context_type = "group" if session_type == "group" else "c2c"
                context_id = group_id if session_type == "group" else user_id
                delta_p, delta_a, delta_d = emotion_analyzer.analyze(content)
                if delta_p != 0 or delta_a != 0 or delta_d != 0:
                    new_state = emotion_manager.update_emotion(
                        context_type, context_id, delta_p, delta_a, delta_d
                    )
                    logger.info(f"{trace_prefix}[Emotion] Updated emotion: {new_state.get_label().value}")
            except Exception as e:
                logger.error(f"{trace_prefix}[Emotion] Failed to update emotion: {e}")
    else:
        logger.warning(f"{trace_prefix}[Agent] Skipping save for error response: {full_response[:50]}...")

    return response_plan
