"""
Emotion Module
Bot emotion management using PAD model.
"""
from nonebot_agent.emotion.emotion_state import (
    EmotionState,
    EmotionLabel,
    EmotionManager,
    emotion_manager,
    EMOTION_STYLES,
)
from nonebot_agent.emotion.emotion_analyzer import (
    EmotionAnalyzer,
    emotion_analyzer,
)

__all__ = [
    "EmotionState",
    "EmotionLabel", 
    "EmotionManager",
    "emotion_manager",
    "EMOTION_STYLES",
    "EmotionAnalyzer",
    "emotion_analyzer",
]
