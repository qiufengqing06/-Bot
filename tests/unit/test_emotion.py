"""Tests for emotion state and label mapping."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import patch

from nonebot_agent.emotion.emotion_state import EmotionLabel, EmotionState


class TestEmotionState:
    """Test emotion state management and label mapping."""

    def test_get_label_maps_mood_to_happy(self):
        """High mood scores should map to HAPPY label."""
        state = EmotionState(mood=50)
        
        # Mock datetime.now() to return daytime hour
        with patch("nonebot_agent.emotion.emotion_state.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            mock_dt.utcnow.return_value = datetime.utcnow()
            
            label = state.get_label()
            assert label == EmotionLabel.HAPPY

    def test_get_label_maps_negative_mood_to_sad(self):
        """Negative mood scores should map to SAD or IRRITATED."""
        state = EmotionState(mood=-30)
        
        with patch("nonebot_agent.emotion.emotion_state.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            mock_dt.utcnow.return_value = datetime.utcnow()
            
            label = state.get_label()
            assert label == EmotionLabel.SAD

    def test_get_label_night_time_returns_sleepy(self):
        """Night time (23:00-06:00) should return SLEEPY regardless of mood."""
        state = EmotionState(mood=50)
        
        with patch("nonebot_agent.emotion.emotion_state.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 23
            mock_dt.utcnow.return_value = datetime.utcnow()
            
            label = state.get_label()
            assert label == EmotionLabel.SLEEPY

    def test_get_style_description_returns_string(self):
        """get_style_description should return a non-empty string."""
        state = EmotionState(mood=50)
        
        with patch("nonebot_agent.emotion.emotion_state.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            mock_dt.utcnow.return_value = datetime.utcnow()
            
            style = state.get_style_description()
            assert isinstance(style, str)
            assert len(style) > 0

    def test_emotion_label_enum_values(self):
        """EmotionLabel enum should have expected values."""
        assert EmotionLabel.HAPPY.value == "开心😊"
        assert EmotionLabel.SAD.value == "低落😢"
        assert EmotionLabel.CALM.value == "平静😌"
