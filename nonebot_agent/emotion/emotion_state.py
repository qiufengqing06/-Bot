"""Emotion State Module - Simplified single mood score."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict
from enum import Enum
from nonebot.log import logger
from nonebot_agent.database import SessionLocal
from nonebot_agent.models import BotEmotionState


class EmotionLabel(Enum):
    HAPPY = "开心😊"
    SAD = "低落😢"
    IRRITATED = "烦躁😠"
    SLEEPY = "困倦😴"
    CUTE = "撒娇🤗"
    CONFIDENT = "自信😎"
    CALM = "平静😌"


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
    mood: int = 0
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
    
    def get_label(self) -> EmotionLabel:
        hour = datetime.now().hour
        if hour >= 23 or hour < 6:
            return EmotionLabel.SLEEPY
        if self.mood >= 40:
            return EmotionLabel.HAPPY
        if self.mood >= 20:
            return EmotionLabel.CONFIDENT
        if self.mood >= 10:
            return EmotionLabel.CUTE
        if self.mood <= -40:
            return EmotionLabel.IRRITATED
        if self.mood <= -20:
            return EmotionLabel.SAD
        return EmotionLabel.CALM
    
    def get_style_description(self) -> str:
        return EMOTION_STYLES[self.get_label()]


class EmotionManager:
    DECAY_INTERVAL_MINUTES = 30
    DECAY_RATE = 0.1
    RESET_AFTER_HOURS = 2
    NIGHT_START_HOUR = 23
    NIGHT_END_HOUR = 6
    
    def get_emotion(self, context_type: str, context_id: str) -> EmotionState:
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            if not record:
                return self._apply_time_modifiers(EmotionState())
            
            mood = int(record.pleasure * 0.5 + record.arousal * 0.3 + record.dominance * 0.2)
            state = EmotionState(mood=mood, last_updated=record.last_updated)
            state = self._apply_time_decay(state)
            return self._apply_time_modifiers(state)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    def update_emotion(self, context_type: str, context_id: str, delta_p: int = 0, delta_a: int = 0, delta_d: int = 0) -> EmotionState:
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            now = datetime.utcnow()
            mood_delta = int(delta_p * 0.5 + delta_a * 0.3 + delta_d * 0.2)
            
            if record:
                current_mood = int(record.pleasure * 0.5 + record.arousal * 0.3 + record.dominance * 0.2)
                state = EmotionState(mood=current_mood, last_updated=record.last_updated)
                state = self._apply_time_decay(state)
                new_mood = max(-100, min(100, state.mood + mood_delta))
                record.pleasure = int(new_mood * 0.6)
                record.arousal = int(new_mood * 0.3)
                record.dominance = int(new_mood * 0.1)
                record.last_updated = now
            else:
                new_mood = max(-100, min(100, mood_delta))
                record = BotEmotionState(
                    context_type=context_type, context_id=context_id,
                    pleasure=int(new_mood * 0.6), arousal=int(new_mood * 0.3),
                    dominance=int(new_mood * 0.1), last_updated=now
                )
                db.add(record)
            
            db.commit()
            db.refresh(record)
            final_mood = int(record.pleasure * 0.5 + record.arousal * 0.3 + record.dominance * 0.2)
            state = EmotionState(mood=final_mood, last_updated=record.last_updated)
            logger.info(f"[Emotion] Updated {context_type}:{context_id} -> mood={state.mood} ({state.get_label().value})")
            return state
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    def set_emotion(self, context_type: str, context_id: str, label: EmotionLabel) -> EmotionState:
        label_to_mood = {
            EmotionLabel.HAPPY: 60, EmotionLabel.SAD: -50, EmotionLabel.IRRITATED: -40,
            EmotionLabel.SLEEPY: -30, EmotionLabel.CUTE: 30, EmotionLabel.CONFIDENT: 40, EmotionLabel.CALM: 0,
        }
        mood = label_to_mood.get(label, 0)
        
        db = SessionLocal()
        try:
            record = db.query(BotEmotionState).filter(
                BotEmotionState.context_type == context_type,
                BotEmotionState.context_id == context_id
            ).first()
            
            now = datetime.utcnow()
            p, a, d = int(mood * 0.6), int(mood * 0.3), int(mood * 0.1)
            
            if record:
                record.pleasure, record.arousal, record.dominance, record.last_updated = p, a, d, now
            else:
                db.add(BotEmotionState(
                    context_type=context_type, context_id=context_id,
                    pleasure=p, arousal=a, dominance=d, last_updated=now
                ))
            
            db.commit()
            logger.info(f"[Emotion] Set {context_type}:{context_id} to {label.value}")
            return EmotionState(mood=mood, last_updated=now)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    def _apply_time_decay(self, state: EmotionState) -> EmotionState:
        if state.last_updated is None:
            return state
        elapsed = datetime.utcnow() - state.last_updated
        if elapsed > timedelta(hours=self.RESET_AFTER_HOURS):
            return EmotionState(last_updated=datetime.utcnow())
        intervals = elapsed.total_seconds() / (self.DECAY_INTERVAL_MINUTES * 60)
        if intervals >= 1:
            state.mood = int(state.mood * ((1 - self.DECAY_RATE) ** int(intervals)))
        return state
    
    def _apply_time_modifiers(self, state: EmotionState) -> EmotionState:
        hour = datetime.now().hour
        if hour >= self.NIGHT_START_HOUR or hour < self.NIGHT_END_HOUR:
            state.mood = max(-100, state.mood - 20)
        return state


emotion_manager = EmotionManager()
