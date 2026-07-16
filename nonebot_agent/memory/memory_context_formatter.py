"""Memory context formatter - extracts context formatting logic."""
from typing import List, Optional
from langchain_core.documents import Document
from nonebot.log import logger


def format_memories_as_context(
    memories: List[Document],
    title: str,
    limit: Optional[int] = None,
    user_nickname: Optional[str] = None,
    seen_memories: set = None,
    normalize_text_func = None,
    format_time_func = None,
) -> str:
    """
    Format retrieved memories with structured sections and time context.
    
    Groups memories by category, adds time context for older memories,
    and provides usage guidance for natural reference.
    """
    if not memories:
        return ""

    if seen_memories is None:
        seen_memories = set()

    # Group memories by category
    categorized = {}
    for mem in memories:
        category = mem.metadata.get("category", "其他")
        if category not in categorized:
            categorized[category] = []
        
        cleaned = mem.page_content.strip()
        if cleaned.startswith("用户问:") and "回复:" in cleaned:
            cleaned = cleaned.split("回复:", 1)[0]
            cleaned = cleaned.replace("用户问:", "用户曾提到:", 1).strip()
        
        if not cleaned:
            continue
        
        normalized = normalize_text_func(cleaned) if normalize_text_func else cleaned
        if normalized in seen_memories:
            continue
        seen_memories.add(normalized)
        
        # Add time context
        timestamp = mem.metadata.get("timestamp", "")
        time_context = format_time_func(timestamp) if format_time_func else ""
        
        categorized[category].append((cleaned, time_context))

    if not categorized:
        return ""

    # Build structured output
    context_parts = []
    
    # Header with user nickname
    if user_nickname:
        context_parts.append(f"## 关于{user_nickname}的记忆")
    else:
        context_parts.append(title)

    # Category sections
    category_names = {
        "profile": "基本身份",
        "preference": "偏好习惯",
        "status": "近况动态",
        "event": "经历事件",
    }

    for category, items in categorized.items():
        if not items:
            continue
        
        section_name = category_names.get(category, category)
        context_parts.append(f"\n### {section_name}")
        
        for content, time_context in items[:limit or len(items)]:
            if time_context:
                context_parts.append(f"- {content}{time_context}")
            else:
                context_parts.append(f"- {content}")

    # Usage guidance
    if user_nickname:
        context_parts.append(f"\n以上是对{user_nickname}的记忆。在回复中自然地引用这些信息，但不要说'根据我的记忆'之类的机械表达。")
    else:
        context_parts.append("\n以上是关于用户的记忆。在回复中自然地引用这些信息，但不要说'根据我的记忆'之类的机械表达。")

    return "\n".join(context_parts)


def format_time_context(timestamp: str) -> str:
    """Format timestamp as relative time context like '（3天前）'."""
    if not timestamp or timestamp == "Unknown time":
        return ""
    
    try:
        from datetime import datetime
        if isinstance(timestamp, str):
            # Try common formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    mem_time = datetime.strptime(timestamp, fmt)
                    break
                except ValueError:
                    continue
            else:
                return ""
        else:
            return ""
        
        # Calculate time difference
        now = datetime.utcnow()
        delta = now - mem_time
        
        if delta.days == 0:
            if delta.seconds < 3600:
                return "（刚才）"
            else:
                return "（今天）"
        elif delta.days == 1:
            return "（昨天）"
        elif delta.days < 7:
            return f"（{delta.days}天前）"
        elif delta.days < 30:
            weeks = delta.days // 7
            return f"（{weeks}周前）"
        elif delta.days < 365:
            months = delta.days // 30
            return f"（{months}个月前）"
        else:
            years = delta.days // 365
            return f"（{years}年前）"
    except Exception:
        return ""
