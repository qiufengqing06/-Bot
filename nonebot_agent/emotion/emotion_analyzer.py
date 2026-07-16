"""
Emotion Analyzer Module
Keyword-based heuristic emotion analysis (replaces LLM).
"""
from typing import Tuple, Optional
from nonebot.log import logger


# Keyword lists for mood scoring
POSITIVE_KEYWORDS = [
    "谢谢", "感谢", "厉害", "棒", "赞", "好", "喜欢", "爱", "开心", "高兴",
    "有趣", "好玩", "不错", "优秀", "漂亮", "可爱", "聪明", "太好了", "真好",
    "哈哈", "嘻嘻", "么么", "抱抱", "辛苦了", "加油", "支持",
]

NEGATIVE_KEYWORDS = [
    "讨厌", "烦", "无聊", "差", "烂", "笨", "傻", "滚", "闭嘴", "讨厌你",
    "难过", "伤心", "失望", "生气", "愤怒", "郁闷", "不开心", "糟糕", "太差",
    "唉", "哎", "无语", "服了", "醉了",
]

EXCITING_KEYWORDS = [
    "哇", "天哪", "震惊", "惊喜", "激动", "兴奋", "太棒了", "不敢相信",
    "真的吗", "不会吧", "啊", "哦", "OMG",
]

BORING_KEYWORDS = [
    "嗯", "哦", "随便", "都行", "无所谓", "一般", "还好", "就那样",
]

CONFIDENT_KEYWORDS = [
    "请教", "怎么办", "帮我", "建议", "你觉得", "我想听你的", "听你的",
]

SUBMISSIVE_KEYWORDS = [
    "命令", "必须", "滚", "闭嘴", "不准", "禁止", "你敢",
]

CUTE_KEYWORDS = [
    "抱抱", "亲亲", "么么", "撒娇", "卖萌", "好哒", "嘻嘻", "萌萌",
]


class EmotionAnalyzer:
    """Analyzes messages using keyword heuristic scanning."""
    
    def analyze(self, message: str, sender_name: Optional[str] = None) -> Tuple[int, int, int]:
        """
        Analyze message impact on emotion using keyword scanning.
        
        Returns:
            Tuple of (delta_p, delta_a, delta_d)
        """
        if not message or not message.strip():
            return 0, 0, 0
        
        # Count keyword matches
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in message)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in message)
        exc_count = sum(1 for kw in EXCITING_KEYWORDS if kw in message)
        bor_count = sum(1 for kw in BORING_KEYWORDS if kw in message)
        conf_count = sum(1 for kw in CONFIDENT_KEYWORDS if kw in message)
        sub_count = sum(1 for kw in SUBMISSIVE_KEYWORDS if kw in message)
        cute_count = sum(1 for kw in CUTE_KEYWORDS if kw in message)
        
        # Calculate mood delta (-100 to 100)
        mood_delta = 0
        mood_delta += pos_count * 8   # Positive keywords boost mood
        mood_delta -= neg_count * 10  # Negative keywords reduce mood
        mood_delta += exc_count * 5   # Exciting keywords boost arousal
        mood_delta -= bor_count * 6   # Boring keywords reduce arousal
        mood_delta += conf_count * 7  # Confidence-boosting keywords
        mood_delta -= sub_count * 8   # Submissive keywords
        
        # Clamp to range
        mood_delta = max(-30, min(30, mood_delta))
        
        # Map mood to PAD deltas
        # Positive mood → high P, moderate A
        # Negative mood → low P
        # Exciting → high A
        # Boring → low A
        # Confident → high D
        # Submissive → low D
        # Cute → low D
        
        delta_p = mood_delta
        delta_a = (exc_count - bor_count) * 10
        delta_d = (conf_count - sub_count - cute_count) * 8
        
        # Clamp all values
        delta_p = max(-30, min(30, delta_p))
        delta_a = max(-30, min(30, delta_a))
        delta_d = max(-30, min(30, delta_d))
        
        if mood_delta != 0 or delta_a != 0 or delta_d != 0:
            logger.debug(f"[Emotion] Keyword analysis: mood={mood_delta}, P={delta_p}, A={delta_a}, D={delta_d}")
        
        return delta_p, delta_a, delta_d


# Global analyzer instance
emotion_analyzer = EmotionAnalyzer()
