"""Pure policy helpers for proactive messaging."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import re
from typing import List


_INTERNAL_TOPIC_SENTINELS = {
    "SEARCH_ALWAYS",
    "SEARCH_ONCE",
    "SEARCH_NEVER",
    "SEARCH_AUTO",
    "NO_SEARCH",
    "<STRING>",
    "NOLIMIT",
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
    session_type: str,
    has_summary: bool,
    has_online_topics: bool,
    online_probability: float,
    first_roll: float,
    second_roll: float,
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
    """Remove category labels that sound robotic when sent to chat."""

    cleaned = " ".join(str(text_value).split()).strip().strip("\"'“”‘’")
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _TOPIC_LABEL_PATTERN.sub("", cleaned).strip()
    return cleaned


def clean_online_topic_text(text_value: str, query_text: str = "") -> str:
    cleaned = " ".join(str(text_value).split()).strip().strip("\"'“”‘’")
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
    plain_text = strip_topic_label(candidate)
    return clean_online_topic_text(plain_text)


def split_topic_candidate(candidate: str) -> tuple[str, str]:
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
        if session_type == "group":
            templates = [
                "刚刷到“{topic}”，说是{detail}。{angle}",
                "刷到个“{topic}”，里面居然提到{detail}。{angle}",
            ]
        else:
            templates = [
                "刚刷到“{topic}”，说是{detail}。{angle}",
                "刷到个“{topic}”，里面居然提到{detail}。{angle}",
            ]
        return random_choice(templates).format(topic=topic, detail=detail, angle=angle)

    if session_type == "group":
        templates = [
            "刚刷到“{topic}”。{angle}",
            "刷到“{topic}”这个标题的时候我愣了一下。{angle}",
        ]
    else:
        templates = [
            "刚刷到“{topic}”。{angle}",
            "刷到“{topic}”这个标题的时候我愣了一下。{angle}",
        ]
    return random_choice(templates).format(topic=topic, angle=angle)


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
    if any(
        phrase in cleaned
        for phrase in ("感觉还挺有聊头", "这题感觉能聊两句", "不同看法")
    ):
        return True
    if any(
        phrase in cleaned
        for phrase in ("重点好像是", "真正值得聊", "取舍问题", "这类话题真能聊出观点")
    ):
        return True
    return False


def random_choice(items: List[str]) -> str:
    import random

    return random.choice(items)


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
