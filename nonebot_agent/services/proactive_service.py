"""Background proactive chat service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import random
from typing import List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from nonebot.adapters.onebot.v11 import Bot
from openai import OpenAI

from nonebot_agent.agent.chat_output import ChatBubble, ChatResponsePlan, parse_chat_response_plan
from nonebot_agent.agent.prompts import AgentMode, get_system_prompt_with_context
from nonebot_agent.config import config
from nonebot_agent.database import SessionLocal
from nonebot_agent.memory.memory_manager import MemoryManager
from nonebot_agent.memory.response_guard import ResponseGuard
from nonebot_agent.models import Conversation, Message
from nonebot_agent.services.response_sender import response_sender

try:
    from nonebot.log import logger
except Exception:
    logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProactiveTarget:
    session_type: str
    target_id: str
    group_id: Optional[str] = None


class ProactiveMessageService:
    def __init__(self) -> None:
        self.memory_manager = MemoryManager()
        self.response_guard = ResponseGuard()
        self._client: OpenAI | None = None
        self.interval_choices = (1800, 3600, 10800, 21600)
        self.private_quiet_window = timedelta(minutes=20)
        self.group_quiet_window = timedelta(minutes=40)
        self.private_fallback_topics = [
            "轻轻问问对方最近在忙什么",
            "延续上次聊过的话题",
            "用自然一点的方式打个招呼",
            "像突然想起对方一样随口聊一句",
        ]
        self.group_fallback_topics = [
            "在群里轻松冒个泡",
            "顺着最近群里的聊天氛围接一句",
            "抛一个很轻的闲聊话题，不要太正式",
            "像群友一样自然插一句话",
        ]

    def enabled(self) -> bool:
        return bool(self.get_targets())

    def choose_delay_seconds(self) -> int:
        return random.choice(self.interval_choices)

    def get_targets(self) -> List[ProactiveTarget]:
        targets: List[ProactiveTarget] = []
        for user_id in self._split_targets(config.INDIVIDUAL_QQ):
            targets.append(ProactiveTarget(session_type="c2c", target_id=user_id))
        for group_id in self._split_targets(config.GROUP_QQ):
            targets.append(ProactiveTarget(session_type="group", target_id=group_id, group_id=group_id))
        return targets

    async def maybe_send(self, bot: Bot) -> bool:
        target = self._pick_target()
        if target is None:
            logger.debug("[Proactive] No eligible target this round")
            return False

        context = self._collect_context(target)
        if context is None:
            return False

        plan = await self._build_plan(target, context)
        if not plan.bubbles:
            return False

        session_key = response_sender.build_session_key(
            target.session_type,
            target.target_id,
            target.group_id,
        )
        response_sender.cancel_pending(session_key)

        async def send_bubble(bubble: ChatBubble, index: int, total: int) -> None:
            text = bubble.content.strip()
            if not text:
                return
            if target.session_type == "group" and target.group_id:
                await bot.send_group_msg(group_id=int(target.group_id), message=text)
            else:
                await bot.send_private_msg(user_id=int(target.target_id), message=text)
            logger.info(
                f"[Proactive] Sent {target.session_type} bubble [{index}/{total}] to {target.target_id}: {text[:60]}..."
            )

        sent_bubbles = await response_sender.send_plan(plan, session_key, send_bubble)
        if not sent_bubbles:
            return False

        sent_plan = ChatResponsePlan(reply_mode=plan.reply_mode, bubbles=sent_bubbles)
        canonical_text = sent_plan.canonical_text().strip()
        if not canonical_text:
            canonical_text = "\n".join(
                bubble.content.strip() for bubble in sent_bubbles if bubble.content.strip()
            )

        if canonical_text:
            self.memory_manager.record_assistant_message(
                user_id=target.target_id,
                content=canonical_text,
                session_type=target.session_type,
                group_id=target.group_id,
                mode=AgentMode.CHAT.value,
            )

        return True

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=config.LLM_API_KEY,
                base_url=config.LLM_API_URL,
            )
        return self._client

    @staticmethod
    def _split_targets(raw_value: str) -> List[str]:
        return [item.strip() for item in raw_value.replace(";", ",").split(",") if item.strip()]

    def _pick_target(self) -> Optional[ProactiveTarget]:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            eligible: List[ProactiveTarget] = []
            for target in self.get_targets():
                conversation = self._get_existing_conversation(db, target)
                if conversation is None:
                    continue

                latest_message = db.query(Message).filter(
                    Message.conversation_id == conversation.id,
                    Message.mode == AgentMode.CHAT.value,
                ).order_by(Message.created_at.desc()).first()

                if latest_message is None:
                    latest_message = db.query(Message).filter(
                        Message.conversation_id == conversation.id
                    ).order_by(Message.created_at.desc()).first()

                if latest_message is None or latest_message.created_at is None:
                    continue

                quiet_window = (
                    self.group_quiet_window if target.session_type == "group" else self.private_quiet_window
                )
                if now - latest_message.created_at < quiet_window:
                    continue

                eligible.append(target)

            return random.choice(eligible) if eligible else None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _collect_context(self, target: ProactiveTarget) -> Optional[dict]:
        db = SessionLocal()
        try:
            conversation = self._get_existing_conversation(db, target)
            if conversation is None:
                return None

            recent_messages = self.memory_manager.get_short_term_memory(
                db,
                conversation,
                mode=AgentMode.CHAT.value,
                limit=8,
            )
            recent_excerpt = self._format_recent_excerpt(recent_messages)
            recent_assistant_messages = [
                msg.content for msg in recent_messages if isinstance(msg, AIMessage) and msg.content
            ]

            summary = self.memory_manager.summary_manager.get_summary(
                db,
                conversation.id,
                AgentMode.CHAT.value,
            )
            summary_text = summary.summary if summary and summary.summary else ""

            long_term_context = summary_text
            if target.session_type == "c2c":
                long_term_context = self.memory_manager.get_long_term_context(
                    db,
                    conversation,
                    target.target_id,
                    "最近适合自然延续的话题",
                    mode=AgentMode.CHAT.value,
                )
            elif summary_text:
                long_term_context = f"[本群近期对话摘要:]\n- {summary_text}"

            return {
                "conversation": conversation,
                "recent_excerpt": recent_excerpt,
                "recent_assistant_messages": recent_assistant_messages,
                "summary_text": summary_text,
                "long_term_context": long_term_context,
                "topic_seed": self._pick_topic_seed(target, summary_text),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _get_existing_conversation(self, db, target: ProactiveTarget) -> Optional[Conversation]:
        if target.session_type == "group" and target.group_id:
            return db.query(Conversation).filter(
                Conversation.session_type == "group",
                Conversation.group_id == target.group_id,
            ).first()
        return db.query(Conversation).filter(
            Conversation.session_type == "c2c",
            Conversation.user_id == target.target_id,
        ).first()

    def _format_recent_excerpt(self, recent_messages) -> str:
        lines = []
        for message in recent_messages[-6:]:
            if isinstance(message, HumanMessage):
                lines.append(f"User: {message.content}")
            elif isinstance(message, AIMessage):
                lines.append(f"Bot: {message.content}")
        return "\n".join(lines)

    def _pick_topic_seed(self, target: ProactiveTarget, summary_text: str) -> str:
        if summary_text:
            return f"优先延续这个上下文：{summary_text[:120]}"
        if target.session_type == "group":
            return random.choice(self.group_fallback_topics)
        return random.choice(self.private_fallback_topics)

    async def _build_plan(self, target: ProactiveTarget, context: dict) -> ChatResponsePlan:
        system_prompt = get_system_prompt_with_context(
            context.get("long_term_context", ""),
            mode=AgentMode.CHAT,
            session_type=target.session_type,
            group_id=target.group_id,
            current_user_nickname="群友们" if target.session_type == "group" else None,
            current_user_id=None if target.session_type == "group" else target.target_id,
        )
        proactive_instructions = (
            "你现在不是在回答用户问题，而是要主动发起一轮自然聊天。\n"
            "要求：\n"
            "- 默认只发 1 条主回复，最多补 1 条 followup\n"
            "- 不要假装对方刚刚给你发了消息\n"
            "- 不要一下子问很多问题，不要写成长段正文\n"
            "- 要像突然想起对方、或者顺着之前聊天自然接一句\n"
            "- 输出严格遵循 JSON 对象，包含 reply_mode 和 bubbles\n"
            "- 这次只发文字，不要输出表情包标记\n"
        )
        user_prompt = (
            f"目标类型：{target.session_type}\n"
            f"最近聊天摘录：\n{context.get('recent_excerpt') or '(暂无)'}\n\n"
            f"会话摘要：\n{context.get('summary_text') or '(暂无)'}\n\n"
            f"本轮建议话题：{context.get('topic_seed')}\n\n"
            "请主动发起一句自然的话。"
        )

        try:
            response = self._get_client().chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "system", "content": proactive_instructions},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=config.LLM_CHAT_TEMPERATURE,
                top_p=0.9,
                frequency_penalty=0.4,
                presence_penalty=0.6,
                max_tokens=240,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                return self._fallback_plan(target)

            plan = parse_chat_response_plan(content)
            plan = self.response_guard.rewrite_plan_if_needed(
                plan=plan,
                recent_responses=context.get("recent_assistant_messages", []),
                mode=AgentMode.CHAT,
                user_message="[主动发起聊天]",
            )
            return plan
        except Exception as exc:
            logger.warning(f"[Proactive] Failed to generate proactive plan: {exc}")
            return self._fallback_plan(target)

    def _fallback_plan(self, target: ProactiveTarget) -> ChatResponsePlan:
        if target.session_type == "group":
            text = random.choice(
                [
                    "突然冒个泡",
                    "今天群里怎么这么安静",
                    "你们最近都在忙啥",
                ]
            )
        else:
            text = random.choice(
                [
                    "最近在忙啥呢",
                    "突然想起你了",
                    "今天过得怎么样",
                ]
            )
        return ChatResponsePlan(
            reply_mode="single",
            bubbles=[ChatBubble(kind="text", content=text, role="primary", optional=False)],
        )


proactive_service = ProactiveMessageService()
