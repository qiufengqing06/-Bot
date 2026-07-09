"""
Emotion Analyzer Module
Uses LLM to analyze how messages affect bot's emotion.
"""
import json
import re
from typing import Tuple, Optional
from openai import OpenAI

from nonebot.log import logger

from nonebot_agent.config import config


# Prompt for emotion analysis
EMOTION_ANALYSIS_PROMPT = """你是一个情绪分析器。分析用户发送的消息会如何影响一个18岁女大学生的情绪。

## 情绪维度说明
- **P (Pleasure/愉悦度)**: 消息让她开心还是难过？范围 -30 到 +30
- **A (Arousal/激动度)**: 消息让她兴奋还是平静？范围 -30 到 +30
- **D (Dominance/支配度)**: 消息让她自信还是顺从？范围 -30 to +30

## 分析规则
- 夸奖/感谢/有趣的话 → P增加
- 骂人/批评/无聊的话 → P减少
- 刺激/惊喜/争论 → A增加
- 无聊/敷衍/冷淡 → A减少
- 求助/听从建议 → D增加
- 被命令/被怀疑 → D减少

## 输出格式
只输出JSON，不要其他内容：
{"delta_p": 0, "delta_a": 0, "delta_d": 0}

## 用户消息
"""


class EmotionAnalyzer:
    """Analyzes messages to determine emotion impact using LLM."""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_API_URL
        )
        self.model = config.LLM_MODEL
    
    def analyze(
        self, 
        message: str, 
        sender_name: Optional[str] = None
    ) -> Tuple[int, int, int]:
        """
        Analyze a message's impact on bot emotion.
        
        Args:
            message: The user message to analyze
            sender_name: Optional sender name for context
            
        Returns:
            Tuple of (delta_p, delta_a, delta_d)
        """
        if not message or not message.strip():
            return 0, 0, 0
        
        try:
            # Build prompt
            prompt = EMOTION_ANALYSIS_PROMPT
            if sender_name:
                prompt += f"[来自 {sender_name}]: "
            prompt += message
            
            # Call LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```" in result_text:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
                if match:
                    result_text = match.group(1)
            
            # Try to extract JSON object
            json_match = re.search(r'\{[^}]+\}', result_text)
            if json_match:
                result_text = json_match.group()
            
            result = json.loads(result_text)
            
            delta_p = int(result.get("delta_p", 0))
            delta_a = int(result.get("delta_a", 0))
            delta_d = int(result.get("delta_d", 0))
            
            # Clamp to reasonable range
            delta_p = max(-30, min(30, delta_p))
            delta_a = max(-30, min(30, delta_a))
            delta_d = max(-30, min(30, delta_d))
            
            logger.debug(f"[Emotion] Analysis result: P={delta_p}, A={delta_a}, D={delta_d}")
            
            return delta_p, delta_a, delta_d
            
        except json.JSONDecodeError as e:
            logger.warning(f"[Emotion] Failed to parse LLM response: {e}")
            return 0, 0, 0
        except Exception as e:
            logger.error(f"[Emotion] Analysis error: {e}")
            return 0, 0, 0


# Global analyzer instance
emotion_analyzer = EmotionAnalyzer()
