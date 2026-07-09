"""
Emotion State Module
Manages bot emotional state using simplified PAD model.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
from enum import Enum

from nonebot.log import logger

from nonebot_agent.database import SessionLocal
from nonebot_agent.models import BotEmotionState


class EmotionLabel(Enum):
    """Discrete emotion labels mapped from PAD values."""
    HAPPY = "开心😊"        # High P, non-negative A
    SAD = "低落😢"          # Low P, non-positive A  
    IRRITATED = "烦躁😠"    # Low P, High A
    SLEEPY = "困倦😴"       # Very low A
    CUTE = "撒娇🤗"         # High P, High A, Low D
    CONFIDENT = "自信😎"    # Non-negative P, Non-negative A, High D
    CALM = "平静😌"         # Neutral state


# Emotion style descriptions for each label
EMOTION_STYLES: Dict[EmotionLabel, str] = {
    EmotionLabel.HAPPY: "话多、热情、主动延伸话题、多用积极的语气词（呢、呀、啦）",
    EmotionLabel.SAD: "话少、回复简短、偶尔叹气、语气低沉（唉、嗯...）",
    EmotionLabel.IRRITATED: "吐槽增多、语气冲、不耐烦、爱用省略号",
    EmotionLabel.SLEEPY: "回复简短、多用困意emoji（😪😴）、语气慢吞吞",
    EmotionLabel.CUTE: "语气软萌、多用颜文字、撒娇卖萌、用叠词（好哒、嘻嘻）",
    EmotionLabel.CONFIDENT: "语气坚定、爱给建议、自信满满、用肯定句",
    EmotionLabel.CALM: "正常状态，保持默认的说话风格",
}


@dataclass
class EmotionState:
    """Data class for emotion state."""
    pleasure: int = 0       # -100 ~ 100
    arousal: int = 0        # -100 ~ 100
    dominance: int = 0      # -100 ~ 100
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
    
    def clamp_values(self):
        """Ensure all values are within valid range."""
        self.pleasure = max(-100, min(100, self.pleasure))
        self.arousal = max(-100, min(100, self.arousal))
        self.dominance = max(-100, min(100, self.dominance))
    
    def get_label(self) -> EmotionLabel:
        """Map PAD values to discrete emotion label."""
        p, a, d = self.pleasure, self.arousal, self.dominance
        
        # Priority order for emotion detection
        if a <= -50:
            return EmotionLabel.SLEEPY
        if p <= -30 and a >= 30:
            return EmotionLabel.IRRITATED
        if p <= -30 and a <= 0:
            return EmotionLabel.SAD
        if p >= 20 and a >= 20 and d <= -20:
            return EmotionLabel.CUTE
        if p >= 0 and a >= 0 and d >= 40:
            return EmotionLabel.CONFIDENT
        if p >= 30 and a >= 0:
            return EmotionLabel.HAPPY
        return EmotionLabel.CALM
    
    def get_style_description(self) -> str:
        """Get the speaking style for current emotion."""
        return EMOTION_STYLES[self.get_label()]


class EmotionManager:
    """
    Manager for bot emotion states.
    Handles per-user (C2C) and per-group emotions.
    """
    
    # Time decay settings
    DECAY_INTERVAL_MINUTES = 30     # Apply decay every 30 min
    DECAY_RATE = 0.1                # Decay 10% per interval
    RESET_AFTER_HOURS = 2           # Reset after 2 hours of inactivity
    
    # Night time sleepiness
    NIGHT_START_HOUR = 23
    NIGHT_END_HOUR = 6
    
    def __init__(self):
        pass
    
    def get_emotion(self, context_type: str, context_id: str) -> EmotionState:
        """
        Get current emotion state for a context (user or group).
        Applies time decay before returning.
        
        Args:
            context_type: "c2c" or "group"
            context_id: user_id or group_id
            
        Returns:
            EmotionState with current values
        """
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            if not record:
                # Create new neutral state
                state = EmotionState()
                return self._apply_time_modifiers(state)
            
            state = EmotionState(
                pleasure=record.pleasure,
                arousal=record.arousal,
                dominance=record.dominance,
                last_updated=record.last_updated
            )
            
            # Apply time decay
            state = self._apply_time_decay(state)
            state = self._apply_time_modifiers(state)
            
            return state
            
        finally:
            db.close()
    
    def update_emotion(
        self, 
        context_type: str, 
        context_id: str,
        delta_p: int = 0,
        delta_a: int = 0,
        delta_d: int = 0
    ) -> EmotionState:
        """
        Update emotion state with deltas.
        
        Args:
            context_type: "c2c" or "group"
            context_id: user_id or group_id  
            delta_p: Change in pleasure
            delta_a: Change in arousal
            delta_d: Change in dominance
            
        Returns:
            Updated EmotionState
        """
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            now = datetime.utcnow()
            
            if record:
                # Apply decay first, then add deltas
                state = EmotionState(
                    pleasure=record.pleasure,
                    arousal=record.arousal,
                    dominance=record.dominance,
                    last_updated=record.last_updated
                )
                state = self._apply_time_decay(state)
                
                record.pleasure = state.pleasure + delta_p
                record.arousal = state.arousal + delta_a
                record.dominance = state.dominance + delta_d
                record.last_updated = now
                
                # Clamp values
                record.pleasure = max(-100, min(100, record.pleasure))
                record.arousal = max(-100, min(100, record.arousal))
                record.dominance = max(-100, min(100, record.dominance))
            else:
                record = BotEmotionState(
                    context_type=context_type,
                    context_id=context_id,
                    pleasure=max(-100, min(100, delta_p)),
                    arousal=max(-100, min(100, delta_a)),
                    dominance=max(-100, min(100, delta_d)),
                    last_updated=now
                )
                db.add(record)
            
            db.commit()
            db.refresh(record)
            
            state = EmotionState(
                pleasure=record.pleasure,
                arousal=record.arousal,
                dominance=record.dominance,
                last_updated=record.last_updated
            )
            
            logger.info(
                f"[Emotion] Updated {context_type}:{context_id} -> "
                f"P={state.pleasure}, A={state.arousal}, D={state.dominance} "
                f"({state.get_label().value})"
            )
            
            return state
            
        finally:
            db.close()
    
    def set_emotion(
        self,
        context_type: str,
        context_id: str,
        label: EmotionLabel
    ) -> EmotionState:
        """
        Set emotion to a specific label (for master control).
        
        Args:
            context_type: "c2c" or "group"
            context_id: user_id or group_id
            label: Target emotion label
            
        Returns:
            New EmotionState
        """
        # Map labels to PAD values
        label_to_pad = {
            EmotionLabel.HAPPY: (50, 30, 0),
            EmotionLabel.SAD: (-50, -30, 0),
            EmotionLabel.IRRITATED: (-30, 50, 0),
            EmotionLabel.SLEEPY: (0, -70, 0),
            EmotionLabel.CUTE: (40, 40, -40),
            EmotionLabel.CONFIDENT: (20, 20, 60),
            EmotionLabel.CALM: (0, 0, 0),
        }
        
        p, a, d = label_to_pad.get(label, (0, 0, 0))
        
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            now = datetime.utcnow()
            
            if record:
                record.pleasure = p
                record.arousal = a
                record.dominance = d
                record.last_updated = now
            else:
                record = BotEmotionState(
                    context_type=context_type,
                    context_id=context_id,
                    pleasure=p,
                    arousal=a,
                    dominance=d,
                    last_updated=now
                )
                db.add(record)
            
            db.commit()
            
            state = EmotionState(pleasure=p, arousal=a, dominance=d, last_updated=now)
            
            logger.info(f"[Emotion] Set {context_type}:{context_id} to {label.value}")
            
            return state
            
        finally:
            db.close()
    
    def _apply_time_decay(self, state: EmotionState) -> EmotionState:
        """Apply time-based decay to emotion values."""
        if state.last_updated is None:
            return state
        
        now = datetime.utcnow()
        elapsed = now - state.last_updated
        
        # Reset after long inactivity
        if elapsed > timedelta(hours=self.RESET_AFTER_HOURS):
            return EmotionState(last_updated=now)
        
        # Calculate decay intervals
        intervals = elapsed.total_seconds() / (self.DECAY_INTERVAL_MINUTES * 60)
        
        if intervals >= 1:
            decay_factor = (1 - self.DECAY_RATE) ** int(intervals)
            state.pleasure = int(state.pleasure * decay_factor)
            state.arousal = int(state.arousal * decay_factor)
            state.dominance = int(state.dominance * decay_factor)
        
        return state
    
    def _apply_time_modifiers(self, state: EmotionState) -> EmotionState:
        """Apply time-based modifiers (e.g., night sleepiness)."""
        current_hour = datetime.now().hour
        
        # Night time: decrease arousal (more sleepy)
        if current_hour >= self.NIGHT_START_HOUR or current_hour < self.NIGHT_END_HOUR:
            state.arousal = max(-100, state.arousal - 30)
        
        return state


# Global emotion manager instance
emotion_manager = EmotionManager()
