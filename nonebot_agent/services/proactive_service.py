"""Consolidated proactive messaging service."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
import random
import re
from typing import Any, List, Optional, Tuple

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
from nonebot_agent.tools.search import search_from_internet

try:
    from nonebot.log import logger
except Exception:
    logger = logging.getLogger(__name__)


# ============================================================================
# Policy helpers (from proactive_policy.py)
# ============================================================================

_INTERNAL_TOPIC_SENTINELS = {
    "SEARCH_ALWAYS", "SEARCH_ONCE", "SEARCH_NEVER", "SEARCH_AUTO", "NO_SEARCH",
    "<STRING>", "NOLIMIT",
}

_TOPIC_LABEL_PATTERN = re.compile(
    r"^(?:热搜|科技|校园|新闻|热点|娱乐|生活|体育|财经|游戏|二次元)?(?:话题|候选|标题)?[：:]\s*"
)
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_LONG_HEX_PATTERN = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_LOW_VALUE_TOPIC_PATTERN = re.compile(
    r"(\d+\s*个.{0,12}(?:题目|标题|模板|文案|句子|方法|技巧)|"
    r"(?:\d+\s*)?分钟跑通|教程|指南|速成|合集|^.+日记[：:])"
)
_PROMO_STYLE_PATTERN = re.compile(
    r"(以我.{0,12}许你|缤纷色彩|花样年华|青春(?:风采|年华|逐梦)|"
    r"踏入大学校园|刚踏入校园|你们来说|你们只好|同学们|"
    r"走又看|理还乱|校园.*大事件|活动预告|风采展示)"
)
_DETAIL_SEPARATOR = "｜"


def split_target_ids(raw_value: str) -> List[str]:
    normalized = raw_value.replace("；", ",").replace("，", ",").replace(";", ",")
    parts = re.split(r"[\s,]+", normalized)
    seen = set()
    targets = []
    for item in parts:
        cleaned = item.strip()
        if not cleaned or not cleaned.isdigit() or cleaned in seen:
            continue
        seen.add(cleaned)
        targets.append(cleaned)
    return targets


def in_active_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    hour = now.hour
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def seconds_until_active_window(now: datetime, start_hour: int, end_hour: int) -> int:
    if in_active_window(now, start_hour, end_hour):
        return 0
    next_start = datetime.combine(now.date(), time(start_hour, 0))
    if next_start <= now:
        next_start += timedelta(days=1)
    return max(int((next_start - now).total_seconds()), 60)


def choose_topic_strategy(
    session_type: str, has_summary: bool, has_online_topics: bool,
    online_probability: float, first_roll: float, second_roll: float,
) -> str:
    if not has_online_topics:
        return "history"
    if not has_summary:
        return "online"
    adjusted_probability = online_probability - 0.15 if session_type == "c2c" else online_probability
    adjusted_probability = max(0.15, min(0.9, adjusted_probability))
    if first_roll < adjusted_probability:
        return "online"
    if second_roll < 0.45:
        return "blended"
    return "history"


def strip_topic_label(text_value: str) -> str:
    cleaned = " ".join(str(text_value).split()).strip().strip("\"'""''")
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _TOPIC_LABEL_PATTERN.sub("", cleaned).strip()
    return cleaned


def clean_online_topic_text(text_value: str, query_text: str = "") -> str:
    cleaned = " ".join(str(text_value).split()).strip().strip("\"'""''")
    if not cleaned:
        return ""
    if _looks_like_internal_topic(cleaned):
        return ""
    cleaned = re.sub(r"^(?:[#\-•、\s]+|\d+[.、]\s*)+", "", cleaned).strip()
    cleaned = strip_topic_label(cleaned)
    if not cleaned:
        return ""
    if _looks_like_internal_topic(cleaned):
        return ""
    normalized = _normalize_topic_text(cleaned)
    query_normalized = _normalize_topic_text(query_text)
    if query_normalized and normalized == query_normalized:
        return ""
    if len(cleaned) > 96:
        cleaned = cleaned[:96].rstrip("，。,.、；;:：- ")
    return cleaned


def format_online_topic_candidate(label: str, topic_text: str, detail_text: str = "") -> str:
    cleaned_topic = clean_online_topic_text(topic_text)
    cleaned_detail = clean_online_topic_text(detail_text)
    if not cleaned_topic:
        cleaned_topic = cleaned_detail
        cleaned_detail = ""
    if not cleaned_topic:
        return ""
    if _normalize_topic_text(cleaned_topic) == _normalize_topic_text(cleaned_detail):
        cleaned_detail = ""
    body = _brief_topic_text(cleaned_topic, max_length=56)
    if cleaned_detail:
        body = f"{body}{_DETAIL_SEPARATOR}{_brief_detail_text(cleaned_detail)}"
    cleaned_label = re.sub(r"\s+", "", label).strip("：:话题")
    if cleaned_label:
        return f"{cleaned_label}：{body}"
    return body


def topic_to_plain_text(candidate: str) -> str:
    return clean_online_topic_text(strip_topic_label(candidate))


def split_topic_candidate(candidate: str) -> Tuple[str, str]:
    plain_text = topic_to_plain_text(candidate)
    if not plain_text:
        return "", ""
    for separator in (_DETAIL_SEPARATOR, " - "):
        if separator in plain_text:
            title, detail = plain_text.split(separator, 1)
            return (
                _brief_topic_text(clean_online_topic_text(title), max_length=56),
                _brief_detail_text(clean_online_topic_text(detail)),
            )
    return _brief_topic_text(plain_text, max_length=56), ""


def topic_candidate_has_detail(candidate: str) -> bool:
    _, detail = split_topic_candidate(candidate)
    return bool(detail)


def topic_candidate_is_chatworthy(candidate: str, require_detail: bool = False) -> bool:
    topic, detail = split_topic_candidate(candidate)
    if not topic:
        return False
    if require_detail and not detail:
        return False
    combined = f"{topic} {detail}".strip()
    if _PROMO_STYLE_PATTERN.search(combined):
        return False
    if _LOW_VALUE_TOPIC_PATTERN.search(combined):
        return False
    if len(topic) < 5:
        return False
    return True


def format_proactive_topic_message(session_type: str, topic_candidate: str) -> str:
    topic, detail = split_topic_candidate(topic_candidate)
    if not topic or not topic_candidate_is_chatworthy(topic_candidate):
        return ""
    angle = _infer_discussion_angle(topic, detail)
    if detail:
        templates = [
            f'刚刷到\u201c{topic}\u201d，说是{detail}。{angle}',
            f'刷到个\u201c{topic}\u201d，里面居然提到{detail}。{angle}',
        ]
        return random.choice(templates)
    templates = [
        f'刚刷到\u201c{topic}\u201d。{angle}',
        f'刷到\u201c{topic}\u201d这个标题的时候我愣了一下。{angle}',
    ]
    return random.choice(templates)


def message_has_proactive_leak(text_value: str) -> bool:
    cleaned = " ".join(str(text_value).split()).strip()
    if not cleaned:
        return False
    if "刚看到个话题" in cleaned or "刚刷到个话题" in cleaned:
        return True
    if re.search(r"\bSEARCH_[A-Z_]+\b", cleaned):
        return True
    if _LONG_HEX_PATTERN.search(cleaned):
        return True
    if re.search(r"(?:热搜|科技|校园)话题[：:]", cleaned):
        return True
    if any(phrase in cleaned for phrase in ("感觉还挺有聊头", "这题感觉能聊两句", "不同看法")):
        return True
    if any(phrase in cleaned for phrase in ("重点好像是", "真正值得聊", "取舍问题", "这类话题真能聊出观点")):
        return True
    return False


def _normalize_topic_text(text_value: str) -> str:
    return re.sub(r"[\s:：,，。.!！?？\-_/\\|]+", "", str(text_value)).lower()


def _looks_like_internal_topic(text_value: str) -> bool:
    cleaned = str(text_value).strip()
    upper_cleaned = cleaned.upper()
    if upper_cleaned in _INTERNAL_TOPIC_SENTINELS:
        return True
    if any(sentinel in upper_cleaned for sentinel in _INTERNAL_TOPIC_SENTINELS):
        return True
    if cleaned.startswith("http") or cleaned.startswith("<"):
        return True
    if cleaned.lower() in {"true", "false", "null", "none", "error"}:
        return True
    if re.fullmatch(r"[0-9a-fA-F]{16,}", cleaned):
        return True
    if _LOW_VALUE_TOPIC_PATTERN.search(cleaned):
        return True
    if _PROMO_STYLE_PATTERN.search(cleaned):
        return True
    if not _CJK_PATTERN.search(cleaned):
        if re.fullmatch(r"[A-Z0-9_:-]{6,}", cleaned):
            return True
        if "_" in cleaned and re.fullmatch(r"[A-Za-z0-9_:-]{8,}", cleaned):
            return True
    return False


def _brief_topic_text(text_value: str, max_length: int = 48) -> str:
    cleaned = " ".join(str(text_value).split()).strip()
    for separator in (" - ", " | ", "｜", "—", "——"):
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
    cleaned = re.split(r"[。！？!?；;]\s*", cleaned, maxsplit=1)[0].strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("，。,.、；;:：- ")
    return cleaned


def _brief_detail_text(text_value: str) -> str:
    cleaned = " ".join(str(text_value).split()).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(?:据悉|报道称|报道指出|文章称|内容提到)[，,:：\s]*", "", cleaned)
    cleaned = re.sub(r"^(?:但|不过|同时|而且|并且|其中)[，,:：\s]*", "", cleaned)
    cleaned = re.split(r"[。！？!?；;]\s*", cleaned, maxsplit=1)[0].strip()
    if len(cleaned) > 72:
        cleaned = cleaned[:72].rstrip("，。,.、；;:：- ")
    return cleaned


def _infer_discussion_angle(topic: str, detail: str) -> str:
    text = f"{topic} {detail}"
    if any(word in text for word in ("降价", "价格", "收费", "付费", "稳定币", "支付")):
        return "降价还绑条件，怎么有种食堂套餐打折的味道..."
    if any(word in text for word in ("大模型", "AI", "模型", "自动化", "工作流", "算法")):
        return "方便是方便，但我已经开始替自己的脑子担心了"
    if any(word in text for word in ("校园", "大学生", "考试", "辩论", "课程")):
        return "校园活动标题一写长，我的阅读欲就先阵亡一半"
    if any(word in text for word in ("监管", "政策", "规则", "限制", "合规")):
        return "听着挺方便，但后面的规矩估计才是重点"
    if any(word in text for word in ("游戏", "电影", "动漫", "音乐", "综艺")):
        return "我可能会先看热闹，再装作自己很懂"
    return "我第一反应是：这事表面挺普通，但总觉得哪里怪怪的"


# ============================================================================
# Proactive service (merged from runtime + service)
# ============================================================================

@dataclass(frozen=True)
class ProactiveTarget:
    session_type: str
    target_id: str
    group_id: Optional[str] = None

    @property
    def key(self) -> str:
        if self.session_type == "group" and self.group_id:
            return f"group:{self.group_id}"
        return f"c2c:{self.target_id}"


class ProactiveMessageService:
    def __init__(self) -> None:
        self.memory_manager = MemoryManager()
        self.response_guard = ResponseGuard()
        self._client: OpenAI | None = None
        self.interval_choices = (1800, 3600, 10800, 21600)
        self.private_quiet_window = timedelta(minutes=20)
        self.group_quiet_window = timedelta(minutes=40)
        self._next_allowed_send_at: dict[str, datetime] = {}
        self._last_target_key: str | None = None
        self.private_fallback_topics = [
            "轻轻问问对方最近在忙什么",
            "顺着上次聊过的话题接一句",
            "像突然想起对方一样打个招呼",
            "随口聊一句今天的状态",
        ]
        self.group_fallback_topics = [
            "在群里轻松冒个泡",
            "顺着最近群里的聊天氛围接一句",
            "抛一个很轻的闲聊话题，不要太正式",
            "像群友一样自然插一句话",
        ]
        self.private_online_queries = [
            ("热搜", "今天热点新闻 具体事件 摘要"),
            ("科技", "今天科技新闻 AI 产业 具体事件"),
            ("校园", "今天校园新闻 大学生 具体事件"),
        ]
        self.group_online_queries = [
            ("热搜", "今天热点新闻 适合讨论 具体事件"),
            ("科技", "今天科技新闻 AI 行业 具体事件"),
            ("校园", "今天校园新闻 大学生 具体事件"),
        ]

    def enabled(self) -> bool:
        return bool(self.get_targets())

    def choose_delay_seconds(self) -> int:
        return random.choice(self.interval_choices)

    def in_active_window(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        return in_active_window(now, config.PROACTIVE_DAY_START_HOUR, config.PROACTIVE_DAY_END_HOUR)

    def seconds_until_active_window(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        return seconds_until_active_window(now, config.PROACTIVE_DAY_START_HOUR, config.PROACTIVE_DAY_END_HOUR)

    def get_targets(self) -> List[ProactiveTarget]:
        targets: List[ProactiveTarget] = []
        for user_id in split_target_ids(config.INDIVIDUAL_QQ):
            targets.append(ProactiveTarget(session_type="c2c", target_id=user_id))
        for group_id in split_target_ids(config.GROUP_QQ):
            targets.append(ProactiveTarget(session_type="group", target_id=group_id, group_id=group_id))
        return targets

    async def maybe_send(self, bot: Bot) -> bool:
        target = self._pick_target()
        if target is None:
            logger.debug("[Proactive] No eligible target this round")
            return False

        context = await self._collect_context(target)
        if context is None:
            return False

        plan = await self._build_plan(target, context)
        if not plan.bubbles:
            return False

        session_key = response_sender.build_session_key(target.session_type, target.target_id, target.group_id)
        response_sender.cancel_pending(session_key)

        async def send_bubble(bubble: ChatBubble, index: int, total: int) -> None:
            text_value = bubble.content.strip()
            if not text_value:
                return
            if target.session_type == "group" and target.group_id:
                await bot.send_group_msg(group_id=int(target.group_id), message=text_value)
            else:
                await bot.send_private_msg(user_id=int(target.target_id), message=text_value)
            logger.info(f"[Proactive] Sent {target.session_type} bubble [{index}/{total}] to {target.target_id}: {text_value[:60]}...")

        sent_bubbles = await response_sender.send_plan(plan, session_key, send_bubble)
        if not sent_bubbles:
            return False

        sent_plan = ChatResponsePlan(reply_mode=plan.reply_mode, bubbles=sent_bubbles)
        canonical_text = sent_plan.canonical_text().strip()
        if not canonical_text:
            canonical_text = "\n".join(bubble.content.strip() for bubble in sent_bubbles if bubble.content.strip())

        if canonical_text:
            self.memory_manager.record_assistant_message(
                user_id=target.target_id, content=canonical_text,
                session_type=target.session_type, group_id=target.group_id, mode=AgentMode.CHAT.value,
            )
            self._mark_sent(target)

        return True

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_API_URL)
        return self._client

    def _pick_target(self) -> Optional[ProactiveTarget]:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            eligible: List[ProactiveTarget] = []
            for target in self.get_targets():
                if not self._is_target_ready(target, now):
                    continue
                conversation = self._get_existing_conversation(db, target)
                if conversation is None:
                    continue
                latest_message = self._get_latest_message(db, conversation.id)
                if latest_message is None or latest_message.created_at is None:
                    continue
                quiet_window = self.group_quiet_window if target.session_type == "group" else self.private_quiet_window
                if now - latest_message.created_at < quiet_window:
                    continue
                eligible.append(target)

            if not eligible:
                return None
            if self._last_target_key and len(eligible) > 1:
                not_last = [target for target in eligible if target.key != self._last_target_key]
                if not_last:
                    eligible = not_last
            return random.choice(eligible)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _is_target_ready(self, target: ProactiveTarget, now: datetime) -> bool:
        next_allowed = self._next_allowed_send_at.get(target.key)
        return next_allowed is None or now >= next_allowed

    def _mark_sent(self, target: ProactiveTarget) -> None:
        minutes = self._pick_target_interval_minutes(target)
        self._next_allowed_send_at[target.key] = datetime.utcnow() + timedelta(minutes=minutes)
        self._last_target_key = target.key
        logger.info(f"[Proactive] Next allowed send for {target.key} after {minutes} minutes")

    def _pick_target_interval_minutes(self, target: ProactiveTarget) -> int:
        if target.session_type == "group":
            minimum = config.PROACTIVE_GROUP_MIN_INTERVAL_MINUTES
            maximum = config.PROACTIVE_GROUP_MAX_INTERVAL_MINUTES
        else:
            minimum = config.PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES
            maximum = config.PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES
        if maximum < minimum:
            maximum = minimum
        return random.randint(minimum, maximum)

    async def _collect_context(self, target: ProactiveTarget) -> Optional[dict[str, Any]]:
        db = SessionLocal()
        try:
            conversation = self._get_existing_conversation(db, target)
            if conversation is None:
                return None

            recent_messages = self.memory_manager.get_short_term_memory(db, conversation, mode=AgentMode.CHAT.value, limit=8)
            recent_excerpt = self._format_recent_excerpt(recent_messages)
            recent_assistant_messages = [msg.content for msg in recent_messages if isinstance(msg, AIMessage) and msg.content]

            summary = self.memory_manager.summary_manager.get_summary(db, conversation.id, AgentMode.CHAT.value)
            summary_text = summary.summary if summary and summary.summary else ""

            long_term_context = summary_text
            if target.session_type == "c2c":
                long_term_context = self.memory_manager.get_long_term_context(
                    db, conversation, target.target_id, "最近适合自然延续的话题", mode=AgentMode.CHAT.value,
                )
            elif summary_text:
                long_term_context = f"[本群近期对话摘要:]\n- {summary_text}"
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        online_topics = await self._fetch_online_topics(target)
        strategy = choose_topic_strategy(
            target.session_type, bool(summary_text), bool(online_topics),
            config.PROACTIVE_ONLINE_TOPIC_PROBABILITY, random.random(), random.random(),
        )

        return {
            "recent_excerpt": recent_excerpt,
            "recent_assistant_messages": recent_assistant_messages,
            "summary_text": summary_text,
            "long_term_context": long_term_context,
            "history_topic_seed": self._pick_history_seed(target, summary_text),
            "online_topics": online_topics,
            "topic_strategy": strategy,
        }

    def _get_existing_conversation(self, db, target: ProactiveTarget) -> Optional[Conversation]:
        if target.session_type == "group" and target.group_id:
            return db.query(Conversation).filter(
                Conversation.session_type == "group", Conversation.group_id == target.group_id,
            ).first()
        return db.query(Conversation).filter(
            Conversation.session_type == "c2c", Conversation.user_id == target.target_id,
        ).first()

    def _get_latest_message(self, db, conversation_id: int) -> Optional[Message]:
        latest_message = db.query(Message).filter(
            Message.conversation_id == conversation_id, Message.mode == AgentMode.CHAT.value,
        ).order_by(Message.created_at.desc()).first()
        if latest_message is None:
            latest_message = db.query(Message).filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.created_at.desc()).first()
        return latest_message

    def _format_recent_excerpt(self, recent_messages) -> str:
        lines = []
        for message in recent_messages[-6:]:
            if isinstance(message, HumanMessage):
                lines.append(f"User: {message.content}")
            elif isinstance(message, AIMessage):
                lines.append(f"Bot: {message.content}")
        return "\n".join(lines)

    def _pick_history_seed(self, target: ProactiveTarget, summary_text: str) -> str:
        if summary_text:
            return f"优先延续这个上下文：{summary_text[:120]}"
        if target.session_type == "group":
            return random.choice(self.group_fallback_topics)
        return random.choice(self.private_fallback_topics)

    async def _fetch_online_topics(self, target: ProactiveTarget) -> List[str]:
        queries = self.group_online_queries if target.session_type == "group" else self.private_online_queries
        label, query = random.choice(queries)
        loop = asyncio.get_running_loop()
        try:
            payload = await loop.run_in_executor(None, lambda: search_from_internet.invoke({"query": query}))
        except Exception as exc:
            logger.debug(f"[Proactive] Online topic search failed: {exc}")
            return []
        return self._extract_topic_candidates(payload, label, query)

    def _extract_topic_candidates(self, payload: Any, label: str, source_query: str = "") -> List[str]:
        candidates: List[str] = []
        seen = set()
        text_keys = {"title", "name", "headline", "topic", "keyword", "summary", "snippet", "content", "desc", "description", "text"}
        skip_keys = {"search_query", "query", "search_engine", "search_intent", "search_domain_filter", "search_recency_filter", "content_size", "request_id", "user_id", "count", "id", "uuid", "trace_id"}

        def add_candidate(title: str, snippet: str = "") -> None:
            title_text = self._clean_topic_text(title, source_query)
            snippet_text = self._clean_topic_text(snippet, source_query)
            if not title_text and not snippet_text:
                return
            candidate = format_online_topic_candidate(label, title_text, snippet_text)
            plain_key = clean_online_topic_text(title_text or snippet_text)
            if not candidate or plain_key in seen or len(plain_key) < 4:
                return
            seen.add(plain_key)
            candidates.append(candidate[:180])

        def walk(node: Any, key_hint: str = "") -> None:
            if len(candidates) >= 6:
                return
            if isinstance(node, dict):
                title = self._pick_first_text(node, ("title", "name", "headline", "topic", "keyword"))
                snippet = self._pick_first_text(node, ("summary", "snippet", "content", "desc", "description", "text"))
                add_candidate(title, snippet)
                for key, value in node.items():
                    normalized_key = str(key).lower()
                    if normalized_key in skip_keys or normalized_key.endswith("_id"):
                        continue
                    if normalized_key in text_keys and isinstance(value, str):
                        continue
                    walk(value, normalized_key)
            elif isinstance(node, list):
                for item in node[:12]:
                    walk(item)
            elif isinstance(node, str) and (not key_hint or key_hint in text_keys):
                add_candidate(node)

        walk(payload)
        return candidates[:4]

    def _pick_first_text(self, data: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _clean_topic_text(self, text_value: str, source_query: str = "") -> str:
        return clean_online_topic_text(text_value, source_query)

    async def _build_plan(self, target: ProactiveTarget, context: dict[str, Any]) -> ChatResponsePlan:
        system_prompt = get_system_prompt_with_context(
            context.get("long_term_context", ""), mode=AgentMode.CHAT,
            session_type=target.session_type, group_id=target.group_id,
            current_user_nickname="群友们" if target.session_type == "group" else None,
            current_user_id=None if target.session_type == "group" else target.target_id,
        )
        proactive_instructions = (
            '你现在不是在回答用户问题，而是要主动发起一轮自然聊天。\n'
            '要求：\n'
            '- 必须保持天雨雪人设：成电大一女生，像刚刷手机随口吐槽，不要变成新闻评论员\n'
            '- 默认只发 1 条主回复，最多补 1 条 followup\n'
            '- 不要假装对方刚刚给你发了消息\n'
            '- 不要一下子问很多问题，不要写成长段正文\n'
            '- 要像突然想起对方、或者顺着之前聊天自然接一句\n'
            '- 联网候选格式通常是"分类：标题｜内容线索"，要基于内容线索聊一个具体事实或冲突点\n'
            '- 不要只复述标题，也不要写"感觉有聊头/大家怎么看/重点好像是/取舍问题"这种空泛分析腔\n'
            '- 不要使用宣传稿、社团活动推文、校园口号、教程合集当主动话题\n'
            '- 口吻可以短一点、懒一点、吐槽一点，比如"这标题也太团委推文了吧""我看两眼就想划走"\n'
            '- 如果候选只有标题没有内容线索，除非能提炼出明确冲突点，否则忽略它\n'
            '- 语气像随手分享一条内容，不要像新闻播报或营销推荐\n'
            '- 允许先用半句概括内容，再接一句自己的反应，不一定要问问题\n'
            '- 绝对不要输出搜索开关、ID、哈希、URL、接口字段或搜索词本身\n'
            '- 如果候选不像真人会聊的话题，就忽略候选，改为延续历史\n'
            '- 输出严格遵循 JSON 对象，包含 reply_mode 和 bubbles\n'
            '- 这次只发文字，不要输出表情包标记\n'
        )

        online_topics = context.get("online_topics") or []
        online_text = "\n".join(f"- {item}" for item in online_topics) if online_topics else "(暂无)"
        strategy_text = {
            "history": "优先沿着历史聊天和最近上下文自然开口",
            "online": "优先从联网话题里挑一个轻松开口，不要像播新闻",
            "blended": "可以把历史上下文和联网话题轻轻接在一起",
        }.get(context.get("topic_strategy"), "优先沿着历史聊天自然开口")

        user_prompt = (
            f'目标类型：{target.session_type}\n'
            f'最近聊天摘录：\n{context.get("recent_excerpt") or "(暂无)"}\n\n'
            f'会话摘要：\n{context.get("summary_text") or "(暂无)"}\n\n'
            f'历史延续建议：{context.get("history_topic_seed")}\n\n'
            f'联网内容候选（优先使用带"｜内容线索"的候选）：\n{online_text}\n\n'
            f'本轮建议策略：{strategy_text}\n\n'
            '请主动发起一句自然的话，必须包含一个具体内容点或明确的取舍问题。'
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
                top_p=0.9, frequency_penalty=0.4, presence_penalty=0.6, max_tokens=240,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                return self._fallback_plan(target, online_topics)

            plan = parse_chat_response_plan(content)
            plan = self.response_guard.rewrite_plan_if_needed(
                plan=plan, recent_responses=context.get("recent_assistant_messages", []),
                mode=AgentMode.CHAT, user_message="[主动发起聊天]",
            )
            if self._plan_has_proactive_leak(plan):
                return self._fallback_plan(target, online_topics)
            return plan
        except Exception as exc:
            logger.warning(f"[Proactive] Failed to generate proactive plan: {exc}")
            return self._fallback_plan(target, online_topics)

    def _plan_has_proactive_leak(self, plan: ChatResponsePlan) -> bool:
        return any(message_has_proactive_leak(bubble.content) for bubble in plan.bubbles)

    def _fallback_plan(self, target: ProactiveTarget, online_topics: Optional[List[str]] = None) -> ChatResponsePlan:
        if online_topics:
            detailed_topics = [
                item for item in online_topics
                if topic_candidate_has_detail(item) and topic_candidate_is_chatworthy(item, require_detail=True)
            ]
            fallback_topics = [item for item in online_topics if topic_candidate_is_chatworthy(item)]
            topic_pool = detailed_topics or fallback_topics
            if not topic_pool:
                return self._fallback_plan(target, None)
            topic = random.choice(topic_pool)
            text_value = format_proactive_topic_message(target.session_type, topic)
            if not text_value:
                return self._fallback_plan(target, None)
        elif target.session_type == "group":
            text_value = random.choice(["突然冒个泡", "今天群里好安静，我来轻轻敲一下门", "你们最近都在忙啥"])
        else:
            text_value = random.choice(["最近在忙啥呢", "突然想起你了，就来冒个泡", "今天过得怎么样"])
        return ChatResponsePlan(
            reply_mode="single",
            bubbles=[ChatBubble(kind="text", content=text_value, role="primary", optional=False)],
        )


proactive_service = ProactiveMessageService()
