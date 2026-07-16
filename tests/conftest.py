"""Shared test fixtures and configuration."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from typing import List

from nonebot_agent.agent.chat_output import ChatResponsePlan, ChatBubble


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns predefined responses."""
    client = MagicMock()
    
    # Mock chat.completions.create
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = '{"reply_mode": "single", "bubbles": [{"kind": "text", "content": "测试回复"}]}'
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    
    client.chat.completions.create.return_value = mock_response
    return client


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


@pytest.fixture
def mock_chroma_memory():
    """Mock Chroma memory client."""
    memory = MagicMock()
    memory.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    memory.add.return_value = None
    return memory


@pytest.fixture
def sample_chat_response_plan():
    """Factory for creating sample ChatResponsePlan instances."""
    def _create_plan(
        reply_mode: str = "single",
        bubbles: List[ChatBubble] = None
    ) -> ChatResponsePlan:
        if bubbles is None:
            bubbles = [
                ChatBubble(kind="text", content="测试消息", role="primary", optional=False)
            ]
        return ChatResponsePlan(reply_mode=reply_mode, bubbles=bubbles)
    
    return _create_plan


@pytest.fixture
def mock_config():
    """Mock configuration object."""
    config = MagicMock()
    config.LLM_MODEL = "test-model"
    config.LLM_API_KEY = "test-key"
    config.LLM_API_URL = "https://api.test.com"
    config.QIANWEN_API_KEY = "test-qianwen-key"
    config.DB_URL = "mysql://test"
    config.CHAT_MODE_MAX_MESSAGES = 5
    config.CHAT_MAX_FOLLOWUPS = 1
    config.MEMORY_EXTRACTION_ENABLED = False
    return config
